"""Integration tests — full round-trip through the ASGI app."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.store.snapshot_store import WeightSnapshotStore


def _make_batch(skill_id: str = "com.example.skill:1.0", n: int = 1) -> dict:
    snapshots = []
    for _ in range(n):
        snapshots.append({
            "snapshot_id": str(uuid.uuid4()),
            "request_id": str(uuid.uuid4()),
            "intent": "summarise",
            "selected_skill_id": skill_id,
            "candidate_skills": [
                {"skill_id": skill_id, "quality_score": 0.8, "latency_ms": 500.0}
            ],
            "quality_score": 0.8,
            "latency_ms": 500.0,
            "outcome_status": "SUCCESS",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
    return {"request_id": str(uuid.uuid4()), "snapshots": snapshots}


@pytest.mark.asyncio
async def test_submit_then_retrieve_roundtrip(tmp_path):
    """POST /snapshots → GET /snapshots/{skill_id} full round-trip."""
    app.state.snapshot_store = WeightSnapshotStore(db_path=str(tmp_path / "it.db"))
    skill_id = f"skill-{uuid.uuid4()}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_resp = await client.post("/snapshots", json=_make_batch(skill_id=skill_id, n=2))
        assert post_resp.status_code == 201
        assert post_resp.json()["saved"] == 2

        get_resp = await client.get(f"/snapshots/{skill_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["count"] == 2


@pytest.mark.asyncio
async def test_counterfactual_after_snapshot(tmp_path):
    """Submit a snapshot then evaluate counterfactual for it."""
    app.state.snapshot_store = WeightSnapshotStore(db_path=str(tmp_path / "cf.db"))
    snap_id = str(uuid.uuid4())
    req_id = str(uuid.uuid4())

    cf_request = {
        "snapshot_id": snap_id,
        "request_id": req_id,
        "intent": "summarise",
        "selected_skill_id": "skill-A",
        "candidate_skills": [
            {"skill_id": "skill-A", "quality_score": 0.5, "latency_ms": 500.0},
            {"skill_id": "skill-B", "quality_score": 0.9, "latency_ms": 100.0},
        ],
        "quality_score": 0.5,
        "latency_ms": 500.0,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        cf_resp = await client.post("/counterfactual", json=cf_request)
    assert cf_resp.status_code == 200
    data = cf_resp.json()
    assert data["best_alternative_skill_id"] == "skill-B"
    assert data["recommendation"] == "consider_alternative"


@pytest.mark.asyncio
async def test_drift_after_multiple_snapshots(tmp_path):
    """Submit snapshots for an intent, then check drift."""
    store = WeightSnapshotStore(db_path=str(tmp_path / "drift.db"))
    app.state.snapshot_store = store

    # Submit 6 snapshots — first 3 skill-A dominant, last 3 skill-B dominant
    batch_a = _make_batch(skill_id="skill-A", n=3)
    batch_a["snapshots"] = [dict(s, intent="translate") for s in batch_a["snapshots"]]
    batch_b = _make_batch(skill_id="skill-B", n=3)
    batch_b["snapshots"] = [dict(s, intent="translate") for s in batch_b["snapshots"]]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/snapshots", json=batch_a)
        await client.post("/snapshots", json=batch_b)
        drift_resp = await client.get("/drift/translate")

    assert drift_resp.status_code == 200
    data = drift_resp.json()
    assert data["snapshot_count"] == 6


@pytest.mark.asyncio
async def test_health_detailed_reflects_snapshot_count(tmp_path):
    """After saving snapshots, health/detailed shows updated count."""
    store = WeightSnapshotStore(db_path=str(tmp_path / "hd.db"))
    app.state.snapshot_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/snapshots", json=_make_batch(n=3))
        resp = await client.get("/health/detailed")

    count = resp.json()["components"]["snapshot_store"]["snapshot_count"]
    assert count == 3


@pytest.mark.asyncio
async def test_empty_batch_does_not_affect_store(tmp_path):
    """Empty SnapshotBatch leaves store count unchanged."""
    store = WeightSnapshotStore(db_path=str(tmp_path / "empty.db"))
    app.state.snapshot_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/snapshots", json={"request_id": "r1", "snapshots": []})
        assert resp.json()["saved"] == 0
        assert store.count() == 0


@pytest.mark.asyncio
async def test_concurrent_snapshot_submissions(tmp_path):
    """Multiple concurrent submissions do not corrupt the store."""
    store = WeightSnapshotStore(db_path=str(tmp_path / "conc.db"))
    app.state.snapshot_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        tasks = [
            client.post("/snapshots", json=_make_batch(skill_id=f"skill-{i}", n=1))
            for i in range(5)
        ]
        responses = await asyncio.gather(*tasks)

    for resp in responses:
        assert resp.status_code == 201
    assert store.count() == 5

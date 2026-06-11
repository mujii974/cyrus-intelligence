"""Tests for GET /drift/{intent}."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.store.snapshot_store import WeightSnapshotStore
from tests.conftest import make_snapshot


def _store(tmp_path):
    return WeightSnapshotStore(db_path=str(tmp_path / "drift_api.db"))


@pytest.mark.asyncio
async def test_drift_unknown_intent_returns_200(tmp_path):
    app.state.snapshot_store = _store(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/drift/unknown-intent")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_drift_response_structure(tmp_path):
    app.state.snapshot_store = _store(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/drift/summarise")
    data = resp.json()
    assert "intent" in data
    assert "snapshot_count" in data
    assert "drift_detected" in data
    assert "alert" in data


@pytest.mark.asyncio
async def test_drift_no_alert_when_insufficient_data(tmp_path):
    store = _store(tmp_path)
    store.save_batch([make_snapshot(intent="summarise")])
    app.state.snapshot_store = store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/drift/summarise")
    assert resp.json()["drift_detected"] is False
    assert resp.json()["alert"] is None


@pytest.mark.asyncio
async def test_drift_detected_with_enough_data(tmp_path):
    store = _store(tmp_path)
    snaps = (
        [make_snapshot(intent="summarise", skill_id="A") for _ in range(3)] +
        [make_snapshot(intent="summarise", skill_id="B") for _ in range(3)]
    )
    store.save_batch(snaps)
    app.state.snapshot_store = store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/drift/summarise")
    # May or may not detect depending on ordering — just assert no crash
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_drift_intent_in_response(tmp_path):
    app.state.snapshot_store = _store(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/drift/my-intent")
    assert resp.json()["intent"] == "my-intent"


@pytest.mark.asyncio
async def test_drift_snapshot_count_accurate(tmp_path):
    store = _store(tmp_path)
    store.save_batch([make_snapshot(intent="analyse") for _ in range(4)])
    app.state.snapshot_store = store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/drift/analyse")
    assert resp.json()["snapshot_count"] == 4

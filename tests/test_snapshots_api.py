"""Tests for /snapshots endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from src.main import app
from src.store.snapshot_store import WeightSnapshotStore
from tests.conftest import make_snapshot


def _store(tmp_path) -> WeightSnapshotStore:
    return WeightSnapshotStore(db_path=str(tmp_path / "api_test.db"))


@pytest.mark.asyncio
async def test_post_snapshots_returns_201(tmp_path):
    app.state.snapshot_store = _store(tmp_path)
    batch = {"request_id": "req-001", "snapshots": [make_snapshot().model_dump()]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/snapshots", json=batch)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_post_snapshots_returns_saved_count(tmp_path):
    app.state.snapshot_store = _store(tmp_path)
    snaps = [make_snapshot().model_dump() for _ in range(3)]
    batch = {"request_id": "req-002", "snapshots": snaps}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/snapshots", json=batch)
    assert resp.json()["saved"] == 3


@pytest.mark.asyncio
async def test_post_empty_batch_returns_zero(tmp_path):
    app.state.snapshot_store = _store(tmp_path)
    batch = {"request_id": "req-003", "snapshots": []}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/snapshots", json=batch)
    assert resp.json()["saved"] == 0


@pytest.mark.asyncio
async def test_get_snapshots_unknown_skill_returns_empty(tmp_path):
    app.state.snapshot_store = _store(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/snapshots/nonexistent-skill")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
    assert resp.json()["snapshots"] == []


@pytest.mark.asyncio
async def test_get_snapshots_returns_saved_snapshot(tmp_path):
    store = _store(tmp_path)
    snap = make_snapshot(skill_id="target-skill")
    store.save_batch([snap])
    app.state.snapshot_store = store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/snapshots/target-skill")
    assert resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_get_snapshots_response_structure(tmp_path):
    store = _store(tmp_path)
    store.save_batch([make_snapshot(skill_id="s1")])
    app.state.snapshot_store = store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/snapshots/s1")
    data = resp.json()
    assert "skill_id" in data
    assert "count" in data
    assert "snapshots" in data


@pytest.mark.asyncio
async def test_post_then_get_roundtrip(tmp_path):
    store = _store(tmp_path)
    app.state.snapshot_store = store
    snap = make_snapshot(skill_id="roundtrip-skill")
    batch = {"request_id": "req-rt", "snapshots": [snap.model_dump()]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/snapshots", json=batch)
        resp = await c.get("/snapshots/roundtrip-skill")
    assert resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_post_snapshots_missing_body_returns_422(tmp_path):
    app.state.snapshot_store = _store(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/snapshots")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_snapshots_limit_param(tmp_path):
    store = _store(tmp_path)
    store.save_batch([make_snapshot() for _ in range(5)])
    app.state.snapshot_store = store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/snapshots/com.example.skill:1.0?limit=2")
    assert resp.json()["count"] == 2


@pytest.mark.asyncio
async def test_post_snapshots_request_id_echoed(tmp_path):
    app.state.snapshot_store = _store(tmp_path)
    batch = {"request_id": "echo-me", "snapshots": []}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/snapshots", json=batch)
    assert resp.json()["request_id"] == "echo-me"

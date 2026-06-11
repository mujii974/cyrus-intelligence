"""Tests for health endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.store.snapshot_store import WeightSnapshotStore


@pytest.mark.asyncio
async def test_health_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_returns_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/health")
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_health_detailed_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/health/detailed")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_detailed_has_required_fields():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/health/detailed")
    data = resp.json()
    assert "status" in data
    assert "version" in data
    assert "components" in data


@pytest.mark.asyncio
async def test_health_detailed_snapshot_store_component(tmp_path):
    app.state.snapshot_store = WeightSnapshotStore(db_path=str(tmp_path / "h.db"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/health/detailed")
    assert "snapshot_store" in resp.json()["components"]


@pytest.mark.asyncio
async def test_health_detailed_snapshot_count(tmp_path):
    from tests.conftest import make_snapshot
    store = WeightSnapshotStore(db_path=str(tmp_path / "hc.db"))
    store.save_batch([make_snapshot()])
    app.state.snapshot_store = store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/health/detailed")
    assert resp.json()["components"]["snapshot_store"]["snapshot_count"] == 1


@pytest.mark.asyncio
async def test_health_detailed_version_is_string():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/health/detailed")
    assert isinstance(resp.json()["version"], str)


@pytest.mark.asyncio
async def test_health_detailed_db_path_present():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/health/detailed")
    assert "db_path" in resp.json()["components"]["snapshot_store"]

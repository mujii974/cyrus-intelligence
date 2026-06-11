"""Tests for suggestion endpoints."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models.snapshot import SkillSuggestion
from src.store.suggestion_store import SuggestionStore


def _fresh_stores(tmp_path):
    from src.store.snapshot_store import WeightSnapshotStore
    db = str(tmp_path / "test.db")
    app.state.snapshot_store = WeightSnapshotStore(db_path=db)
    app.state.suggestion_store = SuggestionStore(db_path=db)


def _sugg(intent="summarise") -> SkillSuggestion:
    return SkillSuggestion(
        intent=intent,
        current_skill_id="skill-A",
        suggested_skill_id="skill-B",
        delta=0.4,
        sample_count=5,
        confidence="medium",
    )


@pytest.mark.asyncio
async def test_get_suggestion_not_found_returns_404(tmp_path):
    _fresh_stores(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/suggestions/unknown-intent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_suggestion_found_returns_200(tmp_path):
    _fresh_stores(tmp_path)
    app.state.suggestion_store.save(_sugg("summarise"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/suggestions/summarise")
    assert resp.status_code == 200
    assert resp.json()["suggested_skill_id"] == "skill-B"


@pytest.mark.asyncio
async def test_list_suggestions_empty(tmp_path):
    _fresh_stores(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/suggestions")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_list_suggestions_returns_active(tmp_path):
    _fresh_stores(tmp_path)
    app.state.suggestion_store.save(_sugg("intent-1"))
    app.state.suggestion_store.save(_sugg("intent-2"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/suggestions")
    assert resp.json()["count"] == 2


@pytest.mark.asyncio
async def test_dismiss_suggestion(tmp_path):
    _fresh_stores(tmp_path)
    sugg = _sugg("translate")
    app.state.suggestion_store.save(sugg)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/suggestions/{sugg.suggestion_id}/dismiss")
    assert resp.status_code == 200
    assert resp.json()["dismissed"] == sugg.suggestion_id


@pytest.mark.asyncio
async def test_dismiss_unknown_returns_404(tmp_path):
    _fresh_stores(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/suggestions/nonexistent-id/dismiss")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dismissed_not_returned_by_list(tmp_path):
    _fresh_stores(tmp_path)
    sugg = _sugg("analyse")
    app.state.suggestion_store.save(sugg)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post(f"/suggestions/{sugg.suggestion_id}/dismiss")
        resp = await c.get("/suggestions")
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_dismissed_not_returned_by_get(tmp_path):
    _fresh_stores(tmp_path)
    sugg = _sugg("analyse")
    app.state.suggestion_store.save(sugg)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post(f"/suggestions/{sugg.suggestion_id}/dismiss")
        resp = await c.get("/suggestions/analyse")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generate_endpoint_returns_count(tmp_path):
    _fresh_stores(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/suggestions/generate")
    assert resp.status_code == 200
    assert "generated" in resp.json()


@pytest.mark.asyncio
async def test_list_limit_param(tmp_path):
    _fresh_stores(tmp_path)
    for i in range(5):
        app.state.suggestion_store.save(_sugg(f"intent-{i}"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/suggestions?limit=3")
    assert resp.json()["count"] == 3

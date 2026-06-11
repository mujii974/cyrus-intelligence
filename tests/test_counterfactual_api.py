"""Tests for POST /counterfactual."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.models.snapshot import CandidateSkill, CounterfactualRequest
import uuid


def _req(**kwargs) -> dict:
    base = CounterfactualRequest(
        snapshot_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        intent="summarise",
        selected_skill_id="skill-A",
        candidate_skills=[
            CandidateSkill(skill_id="skill-A", quality_score=0.8, latency_ms=500.0).model_dump()
        ],
        quality_score=0.8,
        latency_ms=500.0,
    ).model_dump()
    base.update(kwargs)
    return base


@pytest.mark.asyncio
async def test_counterfactual_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/counterfactual", json=_req())
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_counterfactual_response_has_required_fields():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/counterfactual", json=_req())
    data = resp.json()
    assert "selected_skill_id" in data
    assert "selected_score" in data
    assert "delta" in data
    assert "recommendation" in data


@pytest.mark.asyncio
async def test_counterfactual_optimal_when_no_alternatives():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/counterfactual", json=_req())
    assert resp.json()["recommendation"] == "optimal"


@pytest.mark.asyncio
async def test_counterfactual_detects_better_alternative():
    req = _req(
        selected_skill_id="skill-A",
        quality_score=0.5,
        latency_ms=500.0,
        candidate_skills=[
            {"skill_id": "skill-A", "quality_score": 0.5, "latency_ms": 500.0},
            {"skill_id": "skill-B", "quality_score": 0.9, "latency_ms": 100.0},
        ],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/counterfactual", json=req)
    data = resp.json()
    assert data["best_alternative_skill_id"] == "skill-B"
    assert data["delta"] > 0


@pytest.mark.asyncio
async def test_counterfactual_missing_body_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/counterfactual")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_counterfactual_snapshot_id_echoed():
    snap_id = str(uuid.uuid4())
    req = _req(snapshot_id=snap_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/counterfactual", json=req)
    assert resp.json()["snapshot_id"] == snap_id


@pytest.mark.asyncio
async def test_counterfactual_empty_candidates_no_crash():
    req = _req(candidate_skills=[])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/counterfactual", json=req)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_counterfactual_delta_non_negative_when_optimal():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/counterfactual", json=_req())
    assert resp.json()["delta"] <= 0.0 or resp.json()["recommendation"] == "optimal"

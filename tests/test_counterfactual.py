"""Tests for CounterfactualEngine."""
from __future__ import annotations

import pytest
from src.engine.counterfactual import CounterfactualEngine, _score
from src.models.snapshot import CandidateSkill, CounterfactualRequest
import uuid


def make_request(
    selected_id: str = "skill-A",
    selected_quality: float = 0.8,
    selected_latency: float = 500.0,
    candidates: list = None,
) -> CounterfactualRequest:
    if candidates is None:
        candidates = [
            CandidateSkill(skill_id=selected_id, quality_score=selected_quality, latency_ms=selected_latency),
        ]
    return CounterfactualRequest(
        snapshot_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        intent="summarise",
        selected_skill_id=selected_id,
        candidate_skills=candidates,
        quality_score=selected_quality,
        latency_ms=selected_latency,
    )


class TestScoreFormula:
    def test_score_increases_with_quality(self):
        assert _score(0.9, 500.0) > _score(0.7, 500.0)

    def test_score_increases_with_lower_latency(self):
        assert _score(0.8, 200.0) > _score(0.8, 800.0)

    def test_latency_clamped_at_min(self):
        # Very low latency should not produce infinite score
        s = _score(1.0, 0.001)
        assert s < 1e6

    def test_max_latency_gives_min_score(self):
        # At MAX_LATENCY_MS the normalised latency is 1.0
        from src.engine.counterfactual import MAX_LATENCY_MS
        s = _score(1.0, MAX_LATENCY_MS)
        assert abs(s - 1.0) < 0.001


class TestCounterfactualEngine:
    def test_returns_optimal_when_no_alternatives(self):
        engine = CounterfactualEngine()
        req = make_request()
        result = engine.evaluate(req)
        assert result.recommendation == "optimal"
        assert result.delta == 0.0

    def test_detects_better_alternative(self):
        engine = CounterfactualEngine()
        candidates = [
            CandidateSkill(skill_id="skill-A", quality_score=0.5, latency_ms=500.0),
            CandidateSkill(skill_id="skill-B", quality_score=0.9, latency_ms=200.0),
        ]
        req = make_request(selected_id="skill-A", selected_quality=0.5, candidates=candidates)
        result = engine.evaluate(req)
        assert result.best_alternative_skill_id == "skill-B"
        assert result.delta > 0
        assert result.recommendation == "consider_alternative"

    def test_optimal_when_selected_is_best(self):
        engine = CounterfactualEngine()
        candidates = [
            CandidateSkill(skill_id="skill-A", quality_score=0.9, latency_ms=100.0),
            CandidateSkill(skill_id="skill-B", quality_score=0.5, latency_ms=800.0),
        ]
        req = make_request(selected_id="skill-A", selected_quality=0.9,
                          selected_latency=100.0, candidates=candidates)
        result = engine.evaluate(req)
        assert result.recommendation == "optimal"

    def test_never_raises_on_empty_candidates(self):
        engine = CounterfactualEngine()
        req = make_request(candidates=[])
        result = engine.evaluate(req)
        assert result is not None

    def test_snapshot_id_preserved(self):
        engine = CounterfactualEngine()
        req = make_request()
        result = engine.evaluate(req)
        assert result.snapshot_id == req.snapshot_id

    def test_delta_is_zero_when_optimal(self):
        engine = CounterfactualEngine()
        req = make_request()
        result = engine.evaluate(req)
        assert result.delta == 0.0

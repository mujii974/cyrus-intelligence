"""Tests for SuggestionStore and generate_suggestions."""
from __future__ import annotations

import uuid

from src.models.snapshot import CandidateSkill, SkillSuggestion, WeightSnapshot
from src.store.suggestion_store import SuggestionStore, _confidence, generate_suggestions


def _store(tmp_path) -> SuggestionStore:
    return SuggestionStore(db_path=str(tmp_path / "sugg.db"))


def _snap(intent="summarise", selected="skill-A", quality=0.5, latency=500.0,
          alternatives=None) -> WeightSnapshot:
    if alternatives is None:
        alternatives = [
            CandidateSkill(skill_id="skill-A", quality_score=quality, latency_ms=latency),
            CandidateSkill(skill_id="skill-B", quality_score=0.9, latency_ms=100.0),
        ]
    return WeightSnapshot(
        snapshot_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        intent=intent,
        selected_skill_id=selected,
        candidate_skills=alternatives,
        quality_score=quality,
        latency_ms=latency,
        outcome_status="SUCCESS",
    )


class TestGenerateSuggestions:
    def test_generates_suggestion_when_better_alternative(self):
        snaps = [_snap() for _ in range(3)]
        suggestions = generate_suggestions(snaps)
        assert len(suggestions) >= 1
        assert suggestions[0].suggested_skill_id == "skill-B"
        assert suggestions[0].sample_count == 3

    def test_no_suggestion_when_selected_is_best(self):
        alternatives = [
            CandidateSkill(skill_id="skill-A", quality_score=0.95, latency_ms=100.0),
            CandidateSkill(skill_id="skill-B", quality_score=0.3, latency_ms=2000.0),
        ]
        snaps = [_snap(selected="skill-A", quality=0.95, latency=100.0,
                       alternatives=alternatives)]
        suggestions = generate_suggestions(snaps)
        assert len(suggestions) == 0

    def test_delta_threshold_filters_small_improvements(self):
        # Alternative only marginally better — below threshold
        alternatives = [
            CandidateSkill(skill_id="skill-A", quality_score=0.8, latency_ms=500.0),
            CandidateSkill(skill_id="skill-B", quality_score=0.801, latency_ms=500.0),
        ]
        snaps = [_snap(quality=0.8, latency=500.0, alternatives=alternatives)]
        suggestions = generate_suggestions(snaps, delta_threshold=0.5)
        assert len(suggestions) == 0

    def test_empty_snapshots_returns_empty(self):
        assert generate_suggestions([]) == []

    def test_confidence_low_below_5(self):
        assert _confidence(4) == "low"

    def test_confidence_medium_5_to_20(self):
        assert _confidence(5) == "medium"
        assert _confidence(20) == "medium"

    def test_confidence_high_above_20(self):
        assert _confidence(21) == "high"


class TestSuggestionStore:
    def test_save_and_get_roundtrip(self, tmp_path):
        store = _store(tmp_path)
        sugg = SkillSuggestion(
            intent="summarise",
            current_skill_id="skill-A",
            suggested_skill_id="skill-B",
            delta=0.5,
            sample_count=3,
            confidence="low",
        )
        store.save(sugg)
        result = store.get_for_intent("summarise")
        assert result is not None
        assert result.suggested_skill_id == "skill-B"

    def test_get_returns_none_for_unknown_intent(self, tmp_path):
        store = _store(tmp_path)
        assert store.get_for_intent("nonexistent") is None

    def test_dismiss_removes_from_active(self, tmp_path):
        store = _store(tmp_path)
        sugg = SkillSuggestion(
            intent="translate",
            current_skill_id="A",
            suggested_skill_id="B",
            delta=0.3,
            sample_count=5,
            confidence="medium",
        )
        store.save(sugg)
        assert store.count_active() == 1
        store.dismiss(sugg.suggestion_id)
        assert store.count_active() == 0
        assert store.get_for_intent("translate") is None

    def test_dismiss_returns_false_for_unknown_id(self, tmp_path):
        store = _store(tmp_path)
        assert store.dismiss("nonexistent-id") is False

    def test_list_active_returns_non_dismissed_only(self, tmp_path):
        store = _store(tmp_path)
        s1 = SkillSuggestion(intent="a", current_skill_id="x", suggested_skill_id="y",
                             delta=0.2, sample_count=2, confidence="low")
        s2 = SkillSuggestion(intent="b", current_skill_id="x", suggested_skill_id="y",
                             delta=0.3, sample_count=3, confidence="low")
        store.save(s1)
        store.save(s2)
        store.dismiss(s1.suggestion_id)
        active = store.list_active()
        assert len(active) == 1
        assert active[0].intent == "b"

"""Shared fixtures."""
from __future__ import annotations

import pytest
from src.models.snapshot import CandidateSkill, WeightSnapshot
import uuid


def make_snapshot(
    intent: str = "summarise",
    skill_id: str = "com.example.skill:1.0",
    quality_score: float = 0.8,
    latency_ms: float = 500.0,
    outcome: str = "SUCCESS",
) -> WeightSnapshot:
    return WeightSnapshot(
        snapshot_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        intent=intent,
        selected_skill_id=skill_id,
        candidate_skills=[
            CandidateSkill(skill_id=skill_id, quality_score=quality_score, latency_ms=latency_ms),
        ],
        quality_score=quality_score,
        latency_ms=latency_ms,
        outcome_status=outcome,
    )

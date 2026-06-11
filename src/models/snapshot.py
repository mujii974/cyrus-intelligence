"""Domain models for the CYRUS Intelligence Engine."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class CandidateSkill(BaseModel):
    """A skill that was available as a routing candidate."""
    skill_id: str
    quality_score: float
    latency_ms: float = 1000.0


class WeightSnapshot(BaseModel):
    """Immutable record of one skill selection event."""
    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str
    intent: str
    selected_skill_id: str
    candidate_skills: list[CandidateSkill]
    quality_score: float
    latency_ms: float
    outcome_status: str          # SUCCESS | UNRESOLVED | ERROR
    recorded_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class CounterfactualRequest(BaseModel):
    """Request to evaluate whether a different skill would have scored better."""
    snapshot_id: str
    request_id: str
    intent: str
    selected_skill_id: str
    candidate_skills: list[CandidateSkill]
    quality_score: float
    latency_ms: float


class CounterfactualResult(BaseModel):
    """Output of one counterfactual evaluation."""
    snapshot_id: str
    selected_skill_id: str
    selected_score: float
    best_alternative_skill_id: Optional[str]
    best_alternative_score: float
    delta: float                 # best_alternative_score - selected_score; 0 = optimal
    recommendation: str          # "optimal" | "consider_alternative"


class DriftAlert(BaseModel):
    """Fired when dominant skill for an intent changes across history window."""
    intent: str
    old_dominant_skill: str
    new_dominant_skill: str
    window_size: int
    alert_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SnapshotBatch(BaseModel):
    """Batch of WeightSnapshots submitted by the Orchestrator."""
    request_id: str
    snapshots: list[WeightSnapshot]


class DriftResponse(BaseModel):
    """Response for GET /drift/{intent}."""
    intent: str
    snapshot_count: int
    drift_detected: bool
    alert: Optional[DriftAlert]

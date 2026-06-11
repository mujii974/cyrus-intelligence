"""CounterfactualEngine — identical scoring contract to Orchestrator."""
from __future__ import annotations

import logging
from typing import Optional

from src.models.snapshot import (
    CandidateSkill,
    CounterfactualRequest,
    CounterfactualResult,
)

logger = logging.getLogger(__name__)

MAX_LATENCY_MS: float = 5000.0


def _score(quality_score: float, latency_ms: float) -> float:
    """Composite scoring formula.

    MUST stay identical to Orchestrator CounterfactualEngine._score().
    Formula: quality_score × (1 / latency_normalised)
    latency_normalised = clamp(latency_ms / MAX_LATENCY_MS, 0.001, 1.0)
    """
    latency_normalised = max(0.001, min(1.0, latency_ms / MAX_LATENCY_MS))
    return quality_score * (1.0 / latency_normalised)


class CounterfactualEngine:
    """Evaluates whether a different skill selection would have scored better.

    Never raises — all exceptions are caught and logged.
    """

    def evaluate(self, request: CounterfactualRequest) -> CounterfactualResult:
        """Compare selected skill score against all candidates."""
        try:
            selected_score = _score(request.quality_score, request.latency_ms)

            best_alt_id: Optional[str] = None
            best_alt_score: float = 0.0

            for candidate in request.candidate_skills:
                if candidate.skill_id == request.selected_skill_id:
                    continue
                score = _score(candidate.quality_score, candidate.latency_ms)
                if score > best_alt_score:
                    best_alt_score = score
                    best_alt_id = candidate.skill_id

            # No alternative means nothing to compare against — delta is 0
            # ("optimal"), not -selected_score.
            delta = (
                best_alt_score - selected_score if best_alt_id is not None else 0.0
            )
            recommendation = (
                "optimal" if delta <= 0.0 or best_alt_id is None
                else "consider_alternative"
            )

            return CounterfactualResult(
                snapshot_id=request.snapshot_id,
                selected_skill_id=request.selected_skill_id,
                selected_score=round(selected_score, 6),
                best_alternative_skill_id=best_alt_id,
                best_alternative_score=round(best_alt_score, 6),
                delta=round(delta, 6),
                recommendation=recommendation,
            )
        except Exception as exc:
            logger.warning("counterfactual evaluate error: %s", exc)
            return CounterfactualResult(
                snapshot_id=request.snapshot_id,
                selected_skill_id=request.selected_skill_id,
                selected_score=0.0,
                best_alternative_skill_id=None,
                best_alternative_score=0.0,
                delta=0.0,
                recommendation="optimal",
            )

"""Snapshot storage endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, HTTPException

from src.models.snapshot import SnapshotBatch, WeightSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.post("", status_code=201)
async def record_snapshots(batch: SnapshotBatch, request: Request):
    """Record a batch of WeightSnapshots from an Orchestrator run."""
    store = request.app.state.snapshot_store
    count = store.save_batch(batch.snapshots)

    # Fire-and-forget suggestion generation — must never fail the submission
    try:
        suggestion_store = getattr(request.app.state, "suggestion_store", None)
        if suggestion_store is not None and batch.snapshots:
            from src.store.suggestion_store import generate_suggestions

            settings = request.app.state.settings
            suggestions = generate_suggestions(
                batch.snapshots,
                delta_threshold=settings.suggestion_delta_threshold,
            )
            if suggestions:
                suggestion_store.save_batch(suggestions)
    except Exception as exc:
        logger.warning("suggestion generation failed (non-fatal): %s", exc)

    return {"request_id": batch.request_id, "saved": count}


@router.get("/{skill_id}")
async def get_snapshots_for_skill(
    skill_id: str,
    limit: int = 100,
    request: Request = None,
):
    """Return snapshot history for a skill, newest first."""
    store = request.app.state.snapshot_store
    snapshots = store.get_by_skill(skill_id, limit=limit)
    return {
        "skill_id": skill_id,
        "count": len(snapshots),
        "snapshots": [s.model_dump() for s in snapshots],
    }

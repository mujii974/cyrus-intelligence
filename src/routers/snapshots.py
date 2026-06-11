"""Snapshot storage endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException

from src.models.snapshot import SnapshotBatch, WeightSnapshot

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.post("", status_code=201)
async def record_snapshots(batch: SnapshotBatch, request: Request):
    """Record a batch of WeightSnapshots from an Orchestrator run."""
    store = request.app.state.snapshot_store
    count = store.save_batch(batch.snapshots)
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

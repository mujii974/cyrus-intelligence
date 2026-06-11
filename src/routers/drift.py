"""Intent drift detection endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Request

from src.engine.drift import IntentDriftDetector
from src.models.snapshot import DriftResponse

router = APIRouter(prefix="/drift", tags=["intelligence"])


@router.get("/{intent}")
async def get_drift(intent: str, request: Request):
    """Detect dominant skill drift for an intent pattern."""
    store = request.app.state.snapshot_store
    settings = request.app.state.settings
    snapshots = store.get_by_intent(intent)

    detector = IntentDriftDetector(window_size=settings.drift_window_size)
    alert = detector.detect(intent, snapshots)

    return DriftResponse(
        intent=intent,
        snapshot_count=len(snapshots),
        drift_detected=alert is not None,
        alert=alert,
    ).model_dump()

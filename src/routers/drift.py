"""Intent drift detection endpoints."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from src.engine.drift import IntentDriftDetector
from src.models.snapshot import DriftResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drift", tags=["intelligence"])


# Fixed-path routes MUST be registered before /{intent}, or "alerts"
# would be captured as an intent name.
@router.get("/alerts")
async def list_drift_alerts(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """List recent unacknowledged drift alerts across all intents."""
    store = getattr(request.app.state, "drift_alert_store", None)
    if store is None:
        return {"count": 0, "unacknowledged_total": 0, "alerts": []}
    alerts = store.list_unacknowledged(limit=limit)
    return {
        "count": len(alerts),
        "unacknowledged_total": store.count_unacknowledged(),
        "alerts": [
            {
                "alert_id": a.alert_id,
                "intent": a.intent,
                "old_dominant_skill": a.old_dominant_skill,
                "new_dominant_skill": a.new_dominant_skill,
                "window_size": a.window_size,
                "detected_at": a.detected_at,
            }
            for a in alerts
        ],
    }


@router.post("/alerts/{alert_id}/acknowledge", status_code=200)
async def acknowledge_drift_alert(alert_id: str, request: Request):
    """Acknowledge a drift alert."""
    store = getattr(request.app.state, "drift_alert_store", None)
    if store is None or not store.acknowledge(alert_id):
        raise HTTPException(status_code=404, detail=f"Alert not found: {alert_id}")
    return {"acknowledged": alert_id}


@router.get("/{intent}")
async def get_drift(intent: str, request: Request):
    """Detect dominant skill drift for an intent pattern."""
    store = request.app.state.snapshot_store
    settings = request.app.state.settings
    snapshots = store.get_by_intent(intent)

    detector = IntentDriftDetector(window_size=settings.drift_window_size)
    alert = detector.detect(intent, snapshots)

    if alert is not None:
        # Persistence is best-effort — detection result is returned regardless
        try:
            drift_alert_store = getattr(request.app.state, "drift_alert_store", None)
            if drift_alert_store is not None:
                drift_alert_store.save(drift_alert_store.from_drift_alert(alert))
        except Exception as exc:
            logger.warning("drift alert persist failed (non-fatal): %s", exc)

    return DriftResponse(
        intent=intent,
        snapshot_count=len(snapshots),
        drift_detected=alert is not None,
        alert=alert,
    ).model_dump()

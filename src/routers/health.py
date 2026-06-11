"""Health endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request

from src.health.detailed import build_detailed_health

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/detailed")
async def health_detailed(request: Request):
    state = request.app.state
    return await build_detailed_health(
        settings=state.settings,
        snapshot_store=getattr(state, "snapshot_store", None),
        suggestion_store=getattr(state, "suggestion_store", None),
        drift_alert_store=getattr(state, "drift_alert_store", None),
    )

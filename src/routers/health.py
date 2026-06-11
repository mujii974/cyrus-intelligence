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
    settings = request.app.state.settings
    snapshot_store = getattr(request.app.state, "snapshot_store", None)
    return build_detailed_health(settings=settings, snapshot_store=snapshot_store)

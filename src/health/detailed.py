"""Detailed health check."""
from __future__ import annotations

import logging
from typing import Any

from src.config import VERSION, Settings

logger = logging.getLogger(__name__)


def _safe_count(fn) -> int:
    """Run a count callable; a broken store must not fail the health check."""
    try:
        return fn()
    except Exception:
        return 0


async def build_detailed_health(
    settings: Settings,
    snapshot_store=None,
    suggestion_store=None,
    drift_alert_store=None,
) -> dict[str, Any]:
    """Build detailed health payload. Never raises."""
    snapshot_count = (
        _safe_count(snapshot_store.count) if snapshot_store is not None else 0
    )
    active_suggestions = (
        _safe_count(suggestion_store.count_active)
        if suggestion_store is not None
        else 0
    )
    unacknowledged_alerts = (
        _safe_count(drift_alert_store.count_unacknowledged)
        if drift_alert_store is not None
        else 0
    )

    return {
        "status": "ok",
        "version": VERSION,
        "snapshot_db": {
            "path": settings.snapshot_db_path,
            "snapshot_count": snapshot_count,
        },
        "suggestions": {
            "active_count": active_suggestions,
        },
        "drift_alerts": {
            "unacknowledged_count": unacknowledged_alerts,
        },
        # Pre-Phase-4 shape — kept so existing consumers keep working
        "components": {
            "snapshot_store": {
                "snapshot_count": snapshot_count,
                "db_path": settings.snapshot_db_path,
            }
        },
    }

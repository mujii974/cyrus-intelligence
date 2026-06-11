"""Detailed health check."""
from __future__ import annotations

import importlib.metadata
import logging
from typing import Any

from src.config import Settings

logger = logging.getLogger(__name__)


def _get_version() -> str:
    try:
        return importlib.metadata.version("cyrus-intelligence")
    except Exception:
        return "unknown"


def build_detailed_health(
    settings: Settings,
    snapshot_store=None,
) -> dict[str, Any]:
    """Build detailed health payload. Never raises."""
    snapshot_count = 0
    if snapshot_store is not None:
        try:
            snapshot_count = snapshot_store.count()
        except Exception:
            pass

    return {
        "status": "ok",
        "version": _get_version(),
        "components": {
            "snapshot_store": {
                "snapshot_count": snapshot_count,
                "db_path": settings.snapshot_db_path,
            }
        },
    }

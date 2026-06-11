"""IntentDriftDetector — identical split-halves contract to Orchestrator."""
from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

from src.models.snapshot import DriftAlert, WeightSnapshot

logger = logging.getLogger(__name__)


class IntentDriftDetector:
    """Detects when the dominant skill for an intent changes over time.

    Splits snapshot history into two halves (oldest / newest).
    Fires DriftAlert if the dominant skill differs between halves.
    Requires at least 4 snapshots (2 per half).
    """

    def __init__(self, window_size: int = 20) -> None:
        self._window_size = window_size

    def detect(
        self, intent: str, snapshots: list[WeightSnapshot]
    ) -> Optional[DriftAlert]:
        """Return DriftAlert if drift detected, else None. Never raises."""
        try:
            if len(snapshots) < 4:
                return None

            window = snapshots[-self._window_size:]
            mid = len(window) // 2
            older = window[:mid]
            newer = window[mid:]

            def dominant(group: list[WeightSnapshot]) -> Optional[str]:
                if not group:
                    return None
                counts = Counter(s.selected_skill_id for s in group)
                return counts.most_common(1)[0][0]

            old_dom = dominant(older)
            new_dom = dominant(newer)

            if old_dom is None or new_dom is None:
                return None
            if old_dom == new_dom:
                return None

            return DriftAlert(
                intent=intent,
                old_dominant_skill=old_dom,
                new_dominant_skill=new_dom,
                window_size=len(window),
            )
        except Exception as exc:
            logger.warning("drift detect error: %s", exc)
            return None

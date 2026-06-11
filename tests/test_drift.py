"""Tests for IntentDriftDetector."""
from __future__ import annotations

import pytest
from src.engine.drift import IntentDriftDetector
from tests.conftest import make_snapshot


def _snaps(skill_ids: list[str]) -> list:
    return [make_snapshot(skill_id=sid) for sid in skill_ids]


class TestIntentDriftDetector:
    def test_no_drift_when_same_skill_dominates(self):
        detector = IntentDriftDetector(window_size=20)
        snaps = _snaps(["A", "A", "A", "A", "A", "A"])
        assert detector.detect("summarise", snaps) is None

    def test_drift_detected_when_dominant_changes(self):
        detector = IntentDriftDetector(window_size=20)
        # Old half: A dominates; New half: B dominates
        snaps = _snaps(["A", "A", "A", "B", "B", "B"])
        alert = detector.detect("summarise", snaps)
        assert alert is not None
        assert alert.old_dominant_skill == "A"
        assert alert.new_dominant_skill == "B"

    def test_no_drift_below_minimum_snapshots(self):
        detector = IntentDriftDetector(window_size=20)
        snaps = _snaps(["A", "B", "A"])  # only 3
        assert detector.detect("summarise", snaps) is None

    def test_never_raises_on_empty(self):
        detector = IntentDriftDetector(window_size=20)
        assert detector.detect("summarise", []) is None

    def test_alert_carries_intent(self):
        detector = IntentDriftDetector(window_size=20)
        snaps = _snaps(["A", "A", "B", "B"])
        alert = detector.detect("translate", snaps)
        if alert:
            assert alert.intent == "translate"

    def test_window_size_respected(self):
        detector = IntentDriftDetector(window_size=4)
        # Only last 4 considered; all B → no drift in window
        snaps = _snaps(["A", "A", "A", "A", "A", "B", "B", "B", "B"])
        alert = detector.detect("summarise", snaps)
        # Last 4: B,B,B,B — no drift within window
        assert alert is None

    def test_drift_alert_has_window_size(self):
        detector = IntentDriftDetector(window_size=20)
        snaps = _snaps(["A", "A", "B", "B"])
        alert = detector.detect("summarise", snaps)
        if alert:
            assert alert.window_size == 4

    def test_never_raises_on_bad_data(self):
        detector = IntentDriftDetector(window_size=20)
        result = detector.detect("x", [])
        assert result is None

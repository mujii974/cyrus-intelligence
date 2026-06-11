"""Tests for DriftAlertStore."""
from __future__ import annotations

from src.models.snapshot import DriftAlert
from src.store.drift_alert_store import DriftAlertStore


def _store(tmp_path) -> DriftAlertStore:
    return DriftAlertStore(db_path=str(tmp_path / "da.db"))


def _alert(intent="summarise") -> DriftAlert:
    return DriftAlert(
        intent=intent,
        old_dominant_skill="skill-A",
        new_dominant_skill="skill-B",
        window_size=10,
    )


class TestDriftAlertStore:
    def test_save_and_list(self, tmp_path):
        store = _store(tmp_path)
        record = store.from_drift_alert(_alert())
        store.save(record)
        results = store.list_unacknowledged()
        assert len(results) == 1

    def test_count_unacknowledged(self, tmp_path):
        store = _store(tmp_path)
        store.save(store.from_drift_alert(_alert("a")))
        store.save(store.from_drift_alert(_alert("b")))
        assert store.count_unacknowledged() == 2

    def test_acknowledge_removes_from_list(self, tmp_path):
        store = _store(tmp_path)
        record = store.from_drift_alert(_alert())
        store.save(record)
        store.acknowledge(record.alert_id)
        assert store.count_unacknowledged() == 0

    def test_acknowledge_unknown_returns_false(self, tmp_path):
        store = _store(tmp_path)
        assert store.acknowledge("nonexistent") is False

    def test_from_drift_alert_preserves_fields(self, tmp_path):
        store = _store(tmp_path)
        alert = _alert("translate")
        record = store.from_drift_alert(alert)
        assert record.intent == "translate"
        assert record.old_dominant_skill == "skill-A"
        assert record.new_dominant_skill == "skill-B"

    def test_persists_across_instances(self, tmp_path):
        db = str(tmp_path / "persist.db")
        s1 = DriftAlertStore(db_path=db)
        s1.save(s1.from_drift_alert(_alert()))
        s2 = DriftAlertStore(db_path=db)
        assert s2.count_unacknowledged() == 1

    def test_close_does_not_raise(self, tmp_path):
        store = _store(tmp_path)
        store.close()

    def test_list_empty_returns_empty(self, tmp_path):
        store = _store(tmp_path)
        assert store.list_unacknowledged() == []

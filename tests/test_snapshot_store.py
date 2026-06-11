"""Tests for WeightSnapshotStore."""
from __future__ import annotations

import pytest
from src.store.snapshot_store import WeightSnapshotStore
from tests.conftest import make_snapshot


def store(tmp_path) -> WeightSnapshotStore:
    return WeightSnapshotStore(db_path=str(tmp_path / "test.db"))


class TestSnapshotStoreSave:
    def test_save_batch_returns_count(self, tmp_path):
        s = store(tmp_path)
        snaps = [make_snapshot() for _ in range(3)]
        assert s.save_batch(snaps) == 3

    def test_save_empty_batch_returns_zero(self, tmp_path):
        s = store(tmp_path)
        assert s.save_batch([]) == 0

    def test_count_increments(self, tmp_path):
        s = store(tmp_path)
        assert s.count() == 0
        s.save_batch([make_snapshot()])
        assert s.count() == 1

    def test_upsert_overwrites_same_snapshot_id(self, tmp_path):
        s = store(tmp_path)
        snap = make_snapshot()
        s.save_batch([snap, snap])
        assert s.count() == 1

    def test_persists_across_instances(self, tmp_path):
        db = str(tmp_path / "p.db")
        s1 = WeightSnapshotStore(db_path=db)
        s1.save_batch([make_snapshot()])
        s2 = WeightSnapshotStore(db_path=db)
        assert s2.count() == 1


class TestSnapshotStoreQuery:
    def test_get_by_skill_returns_matching(self, tmp_path):
        s = store(tmp_path)
        s.save_batch([make_snapshot(skill_id="skill-A"), make_snapshot(skill_id="skill-B")])
        results = s.get_by_skill("skill-A")
        assert len(results) == 1
        assert results[0].selected_skill_id == "skill-A"

    def test_get_by_skill_unknown_returns_empty(self, tmp_path):
        s = store(tmp_path)
        assert s.get_by_skill("nonexistent") == []

    def test_get_by_intent_returns_matching(self, tmp_path):
        s = store(tmp_path)
        s.save_batch([make_snapshot(intent="summarise"), make_snapshot(intent="translate")])
        results = s.get_by_intent("summarise")
        assert len(results) == 1

    def test_get_by_intent_newest_first(self, tmp_path):
        import time
        s = store(tmp_path)
        snap1 = make_snapshot(skill_id="old-skill")
        time.sleep(0.01)
        snap2 = make_snapshot(skill_id="new-skill")
        s.save_batch([snap1, snap2])
        results = s.get_by_intent("summarise")
        assert results[0].selected_skill_id == "new-skill"

    def test_get_by_skill_limit_respected(self, tmp_path):
        s = store(tmp_path)
        s.save_batch([make_snapshot() for _ in range(5)])
        results = s.get_by_skill("com.example.skill:1.0", limit=3)
        assert len(results) == 3

    def test_close_does_not_raise(self, tmp_path):
        s = store(tmp_path)
        s.close()

    def test_usable_after_close(self, tmp_path):
        s = store(tmp_path)
        s.close()
        s.save_batch([make_snapshot()])
        assert s.count() == 1

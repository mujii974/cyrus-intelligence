"""SQLite-backed WeightSnapshot persistence."""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from src.models.snapshot import WeightSnapshot

logger = logging.getLogger(__name__)


class WeightSnapshotStore:
    """Persist and retrieve WeightSnapshots by skill_id and intent."""

    def __init__(self, db_path: str = "data/snapshots.db") -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS weight_snapshots (
                    snapshot_id      TEXT PRIMARY KEY,
                    request_id       TEXT NOT NULL,
                    intent           TEXT NOT NULL,
                    selected_skill   TEXT NOT NULL,
                    quality_score    REAL NOT NULL,
                    latency_ms       REAL NOT NULL,
                    outcome_status   TEXT NOT NULL,
                    payload_json     TEXT NOT NULL,
                    recorded_at      TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_snap_intent
                ON weight_snapshots (intent)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_snap_skill
                ON weight_snapshots (selected_skill)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_snap_recorded
                ON weight_snapshots (recorded_at DESC)
            """)
            conn.commit()

    def save_batch(self, snapshots: list[WeightSnapshot]) -> int:
        """Upsert a batch of snapshots. Returns count saved."""
        if not snapshots:
            return 0
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO weight_snapshots
                    (snapshot_id, request_id, intent, selected_skill,
                     quality_score, latency_ms, outcome_status, payload_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        s.snapshot_id,
                        s.request_id,
                        s.intent,
                        s.selected_skill_id,
                        s.quality_score,
                        s.latency_ms,
                        s.outcome_status,
                        s.model_dump_json(),
                        s.recorded_at,
                    )
                    for s in snapshots
                ],
            )
            conn.commit()
        logger.debug("snapshot_store saved %d snapshots", len(snapshots))
        return len(snapshots)

    def get_by_skill(
        self, skill_id: str, limit: int = 100
    ) -> list[WeightSnapshot]:
        """Return snapshots for a skill, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM weight_snapshots
                WHERE selected_skill = ?
                ORDER BY recorded_at DESC LIMIT ?
                """,
                (skill_id, limit),
            ).fetchall()
        return [WeightSnapshot.model_validate_json(r["payload_json"]) for r in rows]

    def get_by_intent(
        self, intent: str, limit: int = 200
    ) -> list[WeightSnapshot]:
        """Return snapshots for an intent pattern, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM weight_snapshots
                WHERE intent = ?
                ORDER BY recorded_at DESC LIMIT ?
                """,
                (intent, limit),
            ).fetchall()
        return [WeightSnapshot.model_validate_json(r["payload_json"]) for r in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as n FROM weight_snapshots"
            ).fetchone()
        return row["n"]

    def close(self) -> None:
        """No-op — connections are per-call. Hook for future pooling."""
        logger.debug("snapshot_store close() called")

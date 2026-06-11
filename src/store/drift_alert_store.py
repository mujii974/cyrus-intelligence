"""SQLite-backed drift alert persistence."""
from __future__ import annotations

import logging
import sqlite3
import uuid
from pathlib import Path

from src.models.snapshot import DriftAlert, DriftAlertRecord

logger = logging.getLogger(__name__)


class DriftAlertStore:
    """Persist and acknowledge drift alerts."""

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
                CREATE TABLE IF NOT EXISTS drift_alerts (
                    alert_id          TEXT PRIMARY KEY,
                    intent            TEXT NOT NULL,
                    old_dominant      TEXT NOT NULL,
                    new_dominant      TEXT NOT NULL,
                    window_size       INTEGER NOT NULL,
                    detected_at       TEXT NOT NULL,
                    acknowledged      INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_drift_intent
                ON drift_alerts (intent, detected_at DESC)
            """)
            conn.commit()

    def save(self, record: DriftAlertRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO drift_alerts
                    (alert_id, intent, old_dominant, new_dominant,
                     window_size, detected_at, acknowledged)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.alert_id,
                    record.intent,
                    record.old_dominant_skill,
                    record.new_dominant_skill,
                    record.window_size,
                    record.detected_at,
                    int(record.acknowledged),
                ),
            )
            conn.commit()

    def from_drift_alert(self, alert: DriftAlert) -> DriftAlertRecord:
        """Create a DriftAlertRecord from a fired DriftAlert."""
        return DriftAlertRecord(
            alert_id=str(uuid.uuid4()),
            intent=alert.intent,
            old_dominant_skill=alert.old_dominant_skill,
            new_dominant_skill=alert.new_dominant_skill,
            window_size=alert.window_size,
            detected_at=alert.alert_at,
        )

    def list_unacknowledged(self, limit: int = 20) -> list[DriftAlertRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT alert_id, intent, old_dominant, new_dominant,
                       window_size, detected_at, acknowledged
                FROM drift_alerts
                WHERE acknowledged = 0
                ORDER BY detected_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            DriftAlertRecord(
                alert_id=r["alert_id"],
                intent=r["intent"],
                old_dominant_skill=r["old_dominant"],
                new_dominant_skill=r["new_dominant"],
                window_size=r["window_size"],
                detected_at=r["detected_at"],
                acknowledged=bool(r["acknowledged"]),
            )
            for r in rows
        ]

    def acknowledge(self, alert_id: str) -> bool:
        """Mark an alert acknowledged. Returns True if found."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE drift_alerts SET acknowledged = 1 WHERE alert_id = ?",
                (alert_id,),
            )
            conn.commit()
        return cursor.rowcount > 0

    def count_unacknowledged(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as n FROM drift_alerts WHERE acknowledged = 0"
            ).fetchone()
        return row["n"]

    def close(self) -> None:
        """No-op — connections are per-call. Hook for future pooling."""
        logger.debug("drift_alert_store close() called")

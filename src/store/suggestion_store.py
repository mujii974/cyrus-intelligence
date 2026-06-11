"""SQLite-backed SkillSuggestion persistence and suggestion generation."""
from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Optional

from src.engine.counterfactual import _score
from src.models.snapshot import SkillSuggestion, WeightSnapshot

logger = logging.getLogger(__name__)

SUGGESTION_DELTA_THRESHOLD = 0.1
CONFIDENCE_LOW = 5
CONFIDENCE_HIGH = 20


def _confidence(sample_count: int) -> str:
    if sample_count < CONFIDENCE_LOW:
        return "low"
    if sample_count <= CONFIDENCE_HIGH:
        return "medium"
    return "high"


def generate_suggestions(
    snapshots: list[WeightSnapshot],
    delta_threshold: float = SUGGESTION_DELTA_THRESHOLD,
) -> list[SkillSuggestion]:
    """Generate suggestions from a batch of snapshots.

    For each intent, finds which alternative skill was most frequently
    recommended and builds one SkillSuggestion per (intent, suggested_skill).
    """
    by_intent: dict[str, list[WeightSnapshot]] = defaultdict(list)
    for snap in snapshots:
        by_intent[snap.intent].append(snap)

    suggestions: list[SkillSuggestion] = []
    for intent, intent_snaps in by_intent.items():
        # Deltas per (current_skill, suggested_skill) pair
        recommendations: dict[tuple[str, str], list[float]] = defaultdict(list)

        for snap in intent_snaps:
            selected_score = _score(snap.quality_score, snap.latency_ms)
            best_alt_id: Optional[str] = None
            best_alt_score = 0.0

            for candidate in snap.candidate_skills:
                if candidate.skill_id == snap.selected_skill_id:
                    continue
                score = _score(candidate.quality_score, candidate.latency_ms)
                if score > best_alt_score:
                    best_alt_score = score
                    best_alt_id = candidate.skill_id

            if best_alt_id is None:
                continue
            delta = best_alt_score - selected_score
            if delta >= delta_threshold:
                recommendations[(snap.selected_skill_id, best_alt_id)].append(delta)

        for (current_id, suggested_id), deltas in recommendations.items():
            mean_delta = sum(deltas) / len(deltas)
            suggestions.append(
                SkillSuggestion(
                    intent=intent,
                    current_skill_id=current_id,
                    suggested_skill_id=suggested_id,
                    delta=round(mean_delta, 6),
                    sample_count=len(deltas),
                    confidence=_confidence(len(deltas)),
                )
            )

    return suggestions


class SuggestionStore:
    """Persist and retrieve SkillSuggestions."""

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
                CREATE TABLE IF NOT EXISTS skill_suggestions (
                    suggestion_id   TEXT PRIMARY KEY,
                    intent          TEXT NOT NULL,
                    current_skill   TEXT NOT NULL,
                    suggested_skill TEXT NOT NULL,
                    delta           REAL NOT NULL,
                    sample_count    INTEGER NOT NULL,
                    confidence      TEXT NOT NULL,
                    dismissed       INTEGER NOT NULL DEFAULT 0,
                    created_at      TEXT NOT NULL,
                    payload_json    TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sugg_intent
                ON skill_suggestions (intent, dismissed, created_at DESC)
            """)
            conn.commit()

    def save(self, suggestion: SkillSuggestion) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO skill_suggestions
                    (suggestion_id, intent, current_skill, suggested_skill,
                     delta, sample_count, confidence, dismissed, created_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    suggestion.suggestion_id,
                    suggestion.intent,
                    suggestion.current_skill_id,
                    suggestion.suggested_skill_id,
                    suggestion.delta,
                    suggestion.sample_count,
                    suggestion.confidence,
                    int(suggestion.dismissed),
                    suggestion.created_at,
                    suggestion.model_dump_json(),
                ),
            )
            conn.commit()

    def save_batch(self, suggestions: list[SkillSuggestion]) -> int:
        for s in suggestions:
            self.save(s)
        return len(suggestions)

    def get_for_intent(self, intent: str) -> Optional[SkillSuggestion]:
        """Most recent non-dismissed suggestion for an intent."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM skill_suggestions
                WHERE intent = ? AND dismissed = 0
                ORDER BY created_at DESC LIMIT 1
                """,
                (intent,),
            ).fetchone()
        if row is None:
            return None
        return SkillSuggestion.model_validate_json(row["payload_json"])

    def list_active(self, limit: int = 20) -> list[SkillSuggestion]:
        """All non-dismissed suggestions, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM skill_suggestions
                WHERE dismissed = 0
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [SkillSuggestion.model_validate_json(r["payload_json"]) for r in rows]

    def dismiss(self, suggestion_id: str) -> bool:
        """Mark a suggestion as dismissed. Returns True if found."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE skill_suggestions SET dismissed = 1 WHERE suggestion_id = ?",
                (suggestion_id,),
            )
            conn.commit()
        return cursor.rowcount > 0

    def count_active(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as n FROM skill_suggestions WHERE dismissed = 0"
            ).fetchone()
        return row["n"]

    def close(self) -> None:
        """No-op — connections are per-call. Hook for future pooling."""
        logger.debug("suggestion_store close() called")

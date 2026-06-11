"""Skill suggestion endpoints.

Suggestions never influence zero_trust_cleared — there is no code path
from suggestions to trust (firewall principle inherited from the SKB).
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from src.models.snapshot import WeightSnapshot
from src.store.suggestion_store import SuggestionStore, generate_suggestions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.get("")
async def list_suggestions(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """All non-dismissed suggestions, newest first."""
    store: SuggestionStore = request.app.state.suggestion_store
    suggestions = store.list_active(limit=limit)
    return {
        "count": len(suggestions),
        "active_total": store.count_active(),
        "suggestions": [s.model_dump() for s in suggestions],
    }


@router.post("/generate", status_code=200)
async def trigger_generate(request: Request):
    """Generate suggestions from recent snapshots. For testing and manual triggers."""
    snap_store = request.app.state.snapshot_store
    sugg_store: SuggestionStore = request.app.state.suggestion_store

    try:
        # Most recent 200 snapshots across all intents
        with snap_store._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM weight_snapshots ORDER BY recorded_at DESC LIMIT 200"
            ).fetchall()
        snapshots = [WeightSnapshot.model_validate_json(r["payload_json"]) for r in rows]
        suggestions = generate_suggestions(snapshots)
        saved = sugg_store.save_batch(suggestions)
        return {"generated": saved}
    except Exception as exc:
        logger.warning("suggestion generation trigger failed: %s", exc)
        return {"generated": 0, "error": str(exc)}


@router.get("/{intent}")
async def get_suggestion_for_intent(intent: str, request: Request):
    """Most recent non-dismissed suggestion for an intent."""
    store: SuggestionStore = request.app.state.suggestion_store
    suggestion = store.get_for_intent(intent)
    if suggestion is None:
        raise HTTPException(status_code=404, detail=f"No suggestion for intent: {intent}")
    return suggestion.model_dump()


@router.post("/{suggestion_id}/dismiss", status_code=200)
async def dismiss_suggestion(suggestion_id: str, request: Request):
    """Mark a suggestion as dismissed."""
    store: SuggestionStore = request.app.state.suggestion_store
    found = store.dismiss(suggestion_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Suggestion not found: {suggestion_id}")
    return {"dismissed": suggestion_id}

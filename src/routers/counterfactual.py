"""Counterfactual evaluation endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Request

from src.engine.counterfactual import CounterfactualEngine
from src.models.snapshot import CounterfactualRequest

router = APIRouter(prefix="/counterfactual", tags=["intelligence"])
_engine = CounterfactualEngine()


@router.post("")
async def evaluate_counterfactual(req: CounterfactualRequest):
    """Evaluate whether a different skill would have scored better."""
    result = _engine.evaluate(req)
    return result.model_dump()

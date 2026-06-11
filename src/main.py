"""CYRUS Intelligence Engine — FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import Settings
from src.store.drift_alert_store import DriftAlertStore
from src.store.snapshot_store import WeightSnapshotStore
from src.store.suggestion_store import SuggestionStore
from src.routers import health, snapshots, counterfactual, drift, suggestions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("cyrus-intelligence starting up")
    app.state.settings = settings
    app.state.snapshot_store = WeightSnapshotStore(
        db_path=settings.snapshot_db_path
    )
    # Same SQLite file, separate tables — additive schema only
    app.state.suggestion_store = SuggestionStore(db_path=settings.snapshot_db_path)
    app.state.drift_alert_store = DriftAlertStore(db_path=settings.snapshot_db_path)
    logger.info(
        "snapshot_store initialised at %s", settings.snapshot_db_path
    )
    yield
    # Teardown
    logger.info("cyrus-intelligence shutting down")
    for attr_name in ("snapshot_store", "suggestion_store", "drift_alert_store"):
        store = getattr(app.state, attr_name, None)
        if store is not None and hasattr(store, "close"):
            store.close()
    logger.info("cyrus-intelligence shutdown complete")


app = FastAPI(
    title="CYRUS Intelligence Engine",
    description="Standalone skill intelligence service — counterfactual scoring and intent drift detection.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(health.router)
app.include_router(snapshots.router)
app.include_router(counterfactual.router)
app.include_router(drift.router)
app.include_router(suggestions.router)

# API tests drive the app via ASGITransport, which skips lifespan — make
# settings available on app.state at import time as well.
app.state.settings = settings

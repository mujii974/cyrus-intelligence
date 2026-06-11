"""CYRUS Intelligence Engine — FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import Settings
from src.store.snapshot_store import WeightSnapshotStore
from src.routers import health, snapshots, counterfactual, drift

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
    logger.info(
        "snapshot_store initialised at %s", settings.snapshot_db_path
    )
    yield
    # Teardown
    logger.info("cyrus-intelligence shutting down")
    store = getattr(app.state, "snapshot_store", None)
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

# API tests drive the app via ASGITransport, which skips lifespan — make
# settings available on app.state at import time as well.
app.state.settings = settings

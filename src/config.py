"""CYRUS Intelligence Engine configuration."""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    snapshot_db_path: str = "data/snapshots.db"
    max_latency_ms: float = 5000.0
    drift_window_size: int = 20
    log_level: str = "INFO"
    port: int = 8002

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

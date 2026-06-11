"""Minimal CLI entry point for the cyrus-intel console script.

The pyproject spec declares `cyrus-intel = "src.cli:app"` but Phase 1
defines no CLI behaviour — this prints service info so the entry point
is functional rather than a broken import.
"""
from __future__ import annotations

from rich.console import Console

from src.config import Settings


def app() -> None:
    settings = Settings()
    console = Console()
    console.print("[bold]CYRUS Intelligence Engine[/bold] v0.1.0")
    console.print(f"  db_path: {settings.snapshot_db_path}")
    console.print(f"  port:    {settings.port}")
    console.print("Run the service: uvicorn src.main:app --port 8002")

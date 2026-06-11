"""cyrus-intel — operator CLI for the CYRUS Intelligence Engine.

Talks to a running Intelligence Engine over HTTP. Base URL comes from
INTELLIGENCE_ENGINE_URL (default http://localhost:8002). Synchronous by
design — plain httpx.Client, 10s timeout, exit code 1 on any error.
"""
from __future__ import annotations

import json
import os

import httpx
import typer

DEFAULT_URL = "http://localhost:8002"
TIMEOUT_SECONDS = 10.0

app = typer.Typer(
    name="cyrus-intel",
    help="Operator CLI for the CYRUS Intelligence Engine.",
    no_args_is_help=True,
)
suggestions_app = typer.Typer(help="Inspect and dismiss skill suggestions.", no_args_is_help=True)
drift_app = typer.Typer(help="Inspect drift alerts.", no_args_is_help=True)
app.add_typer(suggestions_app, name="suggestions")
app.add_typer(drift_app, name="drift")

JSON_FLAG = typer.Option(False, "--json", help="Print the raw JSON response instead of a table.")


def _base_url() -> str:
    return os.environ.get("INTELLIGENCE_ENGINE_URL", DEFAULT_URL).rstrip("/")


def _request(method: str, path: str) -> httpx.Response:
    """One HTTP call to the engine. Unreachable server → message + exit 1."""
    url = _base_url()
    try:
        with httpx.Client(base_url=url, timeout=TIMEOUT_SECONDS) as client:
            return client.request(method, path)
    except httpx.HTTPError:
        typer.echo(f"Intelligence Engine unreachable at {url}", err=True)
        raise typer.Exit(code=1)


def _ensure_ok(resp: httpx.Response) -> None:
    if resp.is_success:
        return
    typer.echo(f"Error: HTTP {resp.status_code} from {resp.request.url}", err=True)
    raise typer.Exit(code=1)


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [
        max(len(header), *(len(row[i]) for row in rows))
        for i, header in enumerate(headers)
    ]
    typer.echo("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    typer.echo("  ".join("─" * w for w in widths))
    for row in rows:
        typer.echo("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


@suggestions_app.command("list")
def suggestions_list(json_output: bool = JSON_FLAG) -> None:
    """List all active (non-dismissed) suggestions."""
    resp = _request("GET", "/suggestions")
    _ensure_ok(resp)
    data = resp.json()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return
    items = data.get("suggestions", [])
    if not items:
        typer.echo("No active suggestions.")
        return
    headers = [
        "suggestion_id", "intent", "current_skill_id",
        "suggested_skill_id", "delta", "confidence", "created_at",
    ]
    rows = [
        [
            str(s.get("suggestion_id", "")),
            str(s.get("intent", "")),
            str(s.get("current_skill_id", "")),
            str(s.get("suggested_skill_id", "")),
            str(s.get("delta", "")),
            str(s.get("confidence", "")),
            str(s.get("created_at", "")),
        ]
        for s in items
    ]
    _print_table(headers, rows)


@suggestions_app.command("dismiss")
def suggestions_dismiss(suggestion_id: str, json_output: bool = JSON_FLAG) -> None:
    """Dismiss a suggestion by ID."""
    resp = _request("POST", f"/suggestions/{suggestion_id}/dismiss")
    if resp.status_code == 404:
        typer.echo(f"Suggestion {suggestion_id} not found.", err=True)
        raise typer.Exit(code=1)
    _ensure_ok(resp)
    if json_output:
        typer.echo(json.dumps(resp.json(), indent=2))
        return
    typer.echo(f"Dismissed suggestion {suggestion_id}.")


@drift_app.command("alerts")
def drift_alerts(json_output: bool = JSON_FLAG) -> None:
    """List all unacknowledged drift alerts."""
    resp = _request("GET", "/drift/alerts")
    _ensure_ok(resp)
    data = resp.json()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return
    items = data.get("alerts", [])
    if not items:
        typer.echo("No unacknowledged drift alerts.")
        return
    headers = [
        "alert_id", "intent", "old_dominant_skill",
        "new_dominant_skill", "detected_at",
    ]
    rows = [
        [
            str(a.get("alert_id", "")),
            str(a.get("intent", "")),
            str(a.get("old_dominant_skill", "")),
            str(a.get("new_dominant_skill", "")),
            str(a.get("detected_at", "")),
        ]
        for a in items
    ]
    _print_table(headers, rows)


@app.command()
def status(json_output: bool = JSON_FLAG) -> None:
    """Print a system status panel from /health/detailed."""
    resp = _request("GET", "/health/detailed")
    _ensure_ok(resp)
    data = resp.json()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return
    snapshot_db = data.get("snapshot_db", {})
    lines = [
        "CYRUS Intelligence Engine",
        "─────────────────────────",
        f"Status:          {data.get('status', 'unknown')}",
        f"Version:         {data.get('version', 'unknown')}",
        f"Snapshots:       {snapshot_db.get('snapshot_count', 0)}",
        f"Active suggestions:       {data.get('suggestions', {}).get('active_count', 0)}",
        f"Unacknowledged alerts:    {data.get('drift_alerts', {}).get('unacknowledged_count', 0)}",
        f"DB path:         {snapshot_db.get('path', 'unknown')}",
    ]
    typer.echo("\n".join(lines))


if __name__ == "__main__":
    app()

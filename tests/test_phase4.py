"""Phase 4 tests — health counts, cyrus-intel CLI, graceful shutdown."""
from __future__ import annotations

import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

import src.main
from src.main import app as api_app
from src.store.drift_alert_store import DriftAlertStore
from src.store.snapshot_store import WeightSnapshotStore
from src.store.suggestion_store import SuggestionStore

BASE_URL = "http://localhost:8002"
CLI_ENV = {"INTELLIGENCE_ENGINE_URL": BASE_URL}


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test")


def _snapshot_payload(
    intent: str,
    selected_skill: str = "skill-A",
    better_skill: str | None = "skill-B",
    recorded_at: str | None = None,
) -> dict:
    """Snapshot dict where better_skill (if set) beats the selected skill."""
    candidates = [{"skill_id": selected_skill, "quality_score": 0.5, "latency_ms": 1000.0}]
    if better_skill is not None:
        candidates.append(
            {"skill_id": better_skill, "quality_score": 0.9, "latency_ms": 200.0}
        )
    payload = {
        "request_id": str(uuid.uuid4()),
        "intent": intent,
        "selected_skill_id": selected_skill,
        "candidate_skills": candidates,
        "quality_score": 0.5,
        "latency_ms": 1000.0,
        "outcome_status": "SUCCESS",
    }
    if recorded_at is not None:
        payload["recorded_at"] = recorded_at
    return payload


@pytest.fixture
def fresh_stores(tmp_path):
    db = str(tmp_path / "phase4.db")
    api_app.state.snapshot_store = WeightSnapshotStore(db_path=db)
    api_app.state.suggestion_store = SuggestionStore(db_path=db)
    api_app.state.drift_alert_store = DriftAlertStore(db_path=db)
    return db


@pytest.fixture
async def seeded_suggestions(fresh_stores):
    """Seed >= 2 suggestions via POST /snapshots (alternatives with delta > 0.1)."""
    batch = {
        "request_id": str(uuid.uuid4()),
        "snapshots": [
            _snapshot_payload("summarise"),
            _snapshot_payload("translate"),
        ],
    }
    async with _client() as c:
        resp = await c.post("/snapshots", json=batch)
    assert resp.status_code == 201
    suggestions = api_app.state.suggestion_store.list_active()
    assert len(suggestions) >= 2
    return suggestions


@pytest.fixture
async def seeded_drift_alerts(fresh_stores):
    """Trigger a drift alert via POST /snapshots + GET /drift/{intent}."""
    intent = "drift-intent"
    batch = {
        "request_id": str(uuid.uuid4()),
        "snapshots": [
            # Explicit recorded_at keeps split-halves ordering deterministic:
            # dominant skill flips from A to B across the window.
            _snapshot_payload(
                intent,
                selected_skill="skill-A" if i < 2 else "skill-B",
                better_skill=None,
                recorded_at=f"2026-06-12T00:00:{i:02d}+00:00",
            )
            for i in range(4)
        ],
    }
    async with _client() as c:
        resp = await c.post("/snapshots", json=batch)
        assert resp.status_code == 201
        drift_resp = await c.get(f"/drift/{intent}")
    assert drift_resp.json()["drift_detected"] is True
    alerts = api_app.state.drift_alert_store.list_unacknowledged()
    assert len(alerts) >= 1
    return alerts


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def app():
    from src.cli import app as cli_app
    return cli_app


# ---------------------------------------------------------------- health


async def test_health_detailed_includes_suggestion_count(fresh_stores, seeded_suggestions):
    async with _client() as c:
        resp = await c.get("/health/detailed")
    assert resp.json()["suggestions"]["active_count"] >= 1


async def test_health_detailed_includes_drift_alert_count(fresh_stores, seeded_drift_alerts):
    async with _client() as c:
        resp = await c.get("/health/detailed")
    assert resp.json()["drift_alerts"]["unacknowledged_count"] >= 1


async def test_health_detailed_zero_counts_on_empty_db(fresh_stores):
    async with _client() as c:
        resp = await c.get("/health/detailed")
    data = resp.json()
    assert data["suggestions"]["active_count"] == 0
    assert data["drift_alerts"]["unacknowledged_count"] == 0


async def test_health_detailed_version_is_0_4_0(fresh_stores):
    async with _client() as c:
        resp = await c.get("/health/detailed")
    assert resp.json()["version"] == "0.4.0"


# ---------------------------------------------- CLI: suggestions list


def test_cli_suggestions_list_empty(runner, app, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/suggestions",
        json={"count": 0, "active_total": 0, "suggestions": []},
    )
    result = runner.invoke(app, ["suggestions", "list"], env=CLI_ENV)
    assert result.exit_code == 0
    assert "No active suggestions." in result.output


async def test_cli_suggestions_list_populated(runner, app, seeded_suggestions, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/suggestions",
        json={
            "count": len(seeded_suggestions),
            "active_total": len(seeded_suggestions),
            "suggestions": [s.model_dump() for s in seeded_suggestions],
        },
    )
    result = runner.invoke(app, ["suggestions", "list"], env=CLI_ENV)
    assert result.exit_code == 0
    assert seeded_suggestions[0].suggestion_id in result.output
    assert seeded_suggestions[0].intent in result.output


async def test_cli_suggestions_list_json_flag(runner, app, seeded_suggestions, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/suggestions",
        json={
            "count": len(seeded_suggestions),
            "active_total": len(seeded_suggestions),
            "suggestions": [s.model_dump() for s in seeded_suggestions],
        },
    )
    result = runner.invoke(app, ["suggestions", "list", "--json"], env=CLI_ENV)
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert isinstance(parsed["suggestions"], list)
    assert len(parsed["suggestions"]) == len(seeded_suggestions)


def test_cli_suggestions_list_unreachable(runner, app):
    result = runner.invoke(
        app,
        ["suggestions", "list"],
        env={"INTELLIGENCE_ENGINE_URL": "http://127.0.0.1:9"},
    )
    assert result.exit_code == 1


# -------------------------------------------- CLI: suggestions dismiss


async def test_cli_suggestions_dismiss_success(runner, app, seeded_suggestions, httpx_mock):
    sid = seeded_suggestions[0].suggestion_id
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/suggestions/{sid}/dismiss",
        json={"dismissed": sid},
    )
    result = runner.invoke(app, ["suggestions", "dismiss", sid], env=CLI_ENV)
    assert result.exit_code == 0
    assert f"Dismissed suggestion {sid}." in result.output


def test_cli_suggestions_dismiss_not_found(runner, app, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/suggestions/nonexistent-id/dismiss",
        status_code=404,
        json={"detail": "Suggestion not found: nonexistent-id"},
    )
    result = runner.invoke(app, ["suggestions", "dismiss", "nonexistent-id"], env=CLI_ENV)
    assert result.exit_code == 1
    assert "Suggestion nonexistent-id not found." in result.stderr


async def test_cli_suggestions_dismiss_json_flag(runner, app, seeded_suggestions, httpx_mock):
    sid = seeded_suggestions[0].suggestion_id
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/suggestions/{sid}/dismiss",
        json={"dismissed": sid},
    )
    result = runner.invoke(app, ["suggestions", "dismiss", sid, "--json"], env=CLI_ENV)
    assert result.exit_code == 0
    assert json.loads(result.output)["dismissed"] == sid


# ------------------------------------------------- CLI: drift alerts


def test_cli_drift_alerts_empty(runner, app, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/drift/alerts",
        json={"count": 0, "unacknowledged_total": 0, "alerts": []},
    )
    result = runner.invoke(app, ["drift", "alerts"], env=CLI_ENV)
    assert result.exit_code == 0
    assert "No unacknowledged drift alerts." in result.output


def _alerts_payload(alerts) -> dict:
    return {
        "count": len(alerts),
        "unacknowledged_total": len(alerts),
        "alerts": [
            {
                "alert_id": a.alert_id,
                "intent": a.intent,
                "old_dominant_skill": a.old_dominant_skill,
                "new_dominant_skill": a.new_dominant_skill,
                "window_size": a.window_size,
                "detected_at": a.detected_at,
            }
            for a in alerts
        ],
    }


async def test_cli_drift_alerts_populated(runner, app, seeded_drift_alerts, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/drift/alerts", json=_alerts_payload(seeded_drift_alerts)
    )
    result = runner.invoke(app, ["drift", "alerts"], env=CLI_ENV)
    assert result.exit_code == 0
    assert seeded_drift_alerts[0].alert_id in result.output
    assert seeded_drift_alerts[0].intent in result.output


async def test_cli_drift_alerts_json_flag(runner, app, seeded_drift_alerts, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/drift/alerts", json=_alerts_payload(seeded_drift_alerts)
    )
    result = runner.invoke(app, ["drift", "alerts", "--json"], env=CLI_ENV)
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert isinstance(parsed["alerts"], list)


# ------------------------------------------------------- CLI: status


_HEALTH_PAYLOAD = {
    "status": "ok",
    "version": "0.4.0",
    "snapshot_db": {"path": "data/snapshots.db", "snapshot_count": 42},
    "suggestions": {"active_count": 3},
    "drift_alerts": {"unacknowledged_count": 1},
}


def test_cli_status_ok(runner, app, httpx_mock):
    httpx_mock.add_response(url=f"{BASE_URL}/health/detailed", json=_HEALTH_PAYLOAD)
    result = runner.invoke(app, ["status"], env=CLI_ENV)
    assert result.exit_code == 0
    assert "ok" in result.output
    assert "0.4.0" in result.output


def test_cli_status_panel_contains_counts(runner, app, httpx_mock):
    httpx_mock.add_response(url=f"{BASE_URL}/health/detailed", json=_HEALTH_PAYLOAD)
    result = runner.invoke(app, ["status"], env=CLI_ENV)
    assert "Snapshots:" in result.output
    assert "42" in result.output
    assert "Active suggestions:" in result.output
    assert "Unacknowledged alerts:" in result.output
    assert "data/snapshots.db" in result.output


def test_cli_status_json_flag(runner, app, httpx_mock):
    httpx_mock.add_response(url=f"{BASE_URL}/health/detailed", json=_HEALTH_PAYLOAD)
    result = runner.invoke(app, ["status", "--json"], env=CLI_ENV)
    assert result.exit_code == 0
    assert json.loads(result.output)["status"] == "ok"


def test_cli_status_server_unreachable(runner, app):
    result = runner.invoke(
        app, ["status"], env={"INTELLIGENCE_ENGINE_URL": "http://127.0.0.1:9"}
    )
    assert result.exit_code == 1
    assert "unreachable" in result.stderr


# ---------------------------------------------------- graceful shutdown


def test_stores_have_close_method():
    for cls in (WeightSnapshotStore, SuggestionStore, DriftAlertStore):
        assert callable(getattr(cls, "close", None)), f"{cls.__name__} missing close()"


def test_close_methods_idempotent(tmp_path):
    db = str(tmp_path / "close.db")
    for cls in (WeightSnapshotStore, SuggestionStore, DriftAlertStore):
        store = cls(db_path=db)
        store.close()
        store.close()  # must not raise on second call


async def test_lifespan_closes_all_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(
        src.main.settings, "snapshot_db_path", str(tmp_path / "lifespan.db")
    )
    closed: list[str] = []
    async with src.main.lifespan(api_app):
        for name in ("snapshot_store", "suggestion_store", "drift_alert_store"):
            store = getattr(api_app.state, name)
            monkeypatch.setattr(store, "close", lambda n=name: closed.append(n))
    assert set(closed) == {"snapshot_store", "suggestion_store", "drift_alert_store"}


def test_settings_has_suggestion_delta_threshold():
    from src.config import Settings
    assert Settings().suggestion_delta_threshold == 0.1

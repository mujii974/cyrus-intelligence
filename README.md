# cyrus-intelligence

CYRUS Skill Intelligence Engine — a standalone HTTP service for counterfactual skill scoring, intent drift detection, suggestion generation, and drift alerts.

## What it is

The Intelligence Engine is the Orchestrator Agent's skill intelligence layer extracted into an independently deployable FastAPI service. It records `WeightSnapshot` events from Orchestrator runs, evaluates whether a different skill would have scored better for a given selection (counterfactual scoring), detects when the dominant skill for an intent drifts over time, generates routing suggestions when execution history shows a better skill was available, and persists drift alerts that operators can review and acknowledge.

Core components:

- **`WeightSnapshotStore`** — SQLite (WAL mode) persistence for snapshot records, queryable by skill and intent
- **`CounterfactualEngine`** — compares the selected skill's composite score against all candidates; the `_score()` formula (`quality_score × (1 / latency_normalised)`) is identical to the Orchestrator's and must not diverge. `evaluate()` never raises.
- **`IntentDriftDetector`** — split-halves dominant-skill comparison over a configurable window (default 20); fires a `DriftAlert` when the dominant skill changes between the older and newer half
- **`SuggestionStore`** — persists `SkillSuggestion` records generated when an alternative skill beats the selected one by at least `SUGGESTION_DELTA_THRESHOLD`
- **`DriftAlertStore`** — persists drift alerts across restarts; alerts are acknowledgeable by an operator
- **`cyrus-intel`** — operator CLI for inspecting suggestions, drift alerts, and system status over HTTP

## Architecture

```
cyrus-intelligence/
├── src/
│   ├── main.py                    # FastAPI app, lifespan (startup + graceful shutdown), routers
│   ├── cli.py                     # cyrus-intel Typer CLI (suggestions, drift, status)
│   ├── config.py                  # Settings + VERSION
│   ├── models/
│   │   └── snapshot.py            # WeightSnapshot, CandidateSkill, CounterfactualRequest/Result,
│   │                              # DriftAlert, DriftAlertRecord, SnapshotBatch, DriftResponse,
│   │                              # SkillSuggestion
│   ├── store/
│   │   ├── snapshot_store.py      # WeightSnapshotStore (SQLite WAL, data/snapshots.db)
│   │   ├── suggestion_store.py    # SuggestionStore + generate_suggestions()
│   │   └── drift_alert_store.py   # DriftAlertStore
│   ├── engine/
│   │   ├── counterfactual.py      # CounterfactualEngine + _score()
│   │   └── drift.py               # IntentDriftDetector (split-halves, window_size=20)
│   ├── health/
│   │   └── detailed.py            # build_detailed_health()
│   └── routers/
│       ├── health.py              # GET /health, GET /health/detailed
│       ├── snapshots.py           # POST /snapshots, GET /snapshots/{skill_id}
│       ├── counterfactual.py      # POST /counterfactual
│       ├── drift.py               # GET /drift/{intent}, GET /drift/alerts, acknowledge
│       └── suggestions.py         # GET/POST suggestion endpoints
├── tests/                         # 120 tests, all passing
├── data/                          # gitignored — snapshots.db created at runtime
├── Dockerfile
├── docker-compose.dev.yml
├── Makefile
├── pyproject.toml
└── README.md
```

All stores share `data/snapshots.db` (separate tables, additive schema only). On shutdown the lifespan teardown closes all three stores gracefully.

## Endpoints

All endpoints return JSON.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/snapshots` | Submit a `SnapshotBatch`; auto-generates suggestions |
| GET | `/snapshots/{skill_id}` | Retrieve snapshot history for a skill (`limit` query param, default 100) |
| POST | `/counterfactual` | Evaluate whether a different skill would have scored better |
| GET | `/drift/{intent}` | Check for intent drift; auto-persists alert if detected |
| GET | `/drift/alerts` | List all unacknowledged drift alerts (`limit` query param) |
| POST | `/drift/alerts/{id}/acknowledge` | Acknowledge a drift alert (404 if not found) |
| GET | `/suggestions` | List all active suggestions (`limit` query param, default 20, max 100) |
| GET | `/suggestions/{intent}` | Get the most recent active suggestion for an intent (404 if none) |
| POST | `/suggestions/{id}/dismiss` | Dismiss a suggestion (404 if not found) |
| POST | `/suggestions/generate` | Trigger manual suggestion generation from recent snapshots |
| GET | `/health` | Basic health check |
| GET | `/health/detailed` | Detailed health with counts |

### Examples

Record a batch of snapshots:

```bash
curl -X POST http://localhost:8002/snapshots \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req-001",
    "snapshots": [{
      "request_id": "req-001",
      "intent": "summarise",
      "selected_skill_id": "com.example.skill:1.0",
      "candidate_skills": [{"skill_id": "com.example.skill:1.0", "quality_score": 0.8, "latency_ms": 500.0}],
      "quality_score": 0.8,
      "latency_ms": 500.0,
      "outcome_status": "SUCCESS"
    }]
  }'
# {"request_id":"req-001","saved":1}
```

Counterfactual evaluation (never errors — on internal failure it returns a safe `"optimal"` result):

```bash
curl -X POST http://localhost:8002/counterfactual \
  -H "Content-Type: application/json" \
  -d '{
    "snapshot_id": "snap-1",
    "request_id": "req-001",
    "intent": "summarise",
    "selected_skill_id": "skill-A",
    "candidate_skills": [
      {"skill_id": "skill-A", "quality_score": 0.5, "latency_ms": 500.0},
      {"skill_id": "skill-B", "quality_score": 0.9, "latency_ms": 100.0}
    ],
    "quality_score": 0.5,
    "latency_ms": 500.0
  }'
# {"snapshot_id":"snap-1","selected_skill_id":"skill-A","selected_score":5.0,
#  "best_alternative_skill_id":"skill-B","best_alternative_score":45.0,
#  "delta":40.0,"recommendation":"consider_alternative"}
```

Detailed health:

```bash
curl http://localhost:8002/health/detailed
# {"status":"ok","version":"0.4.0",
#  "snapshot_db":{"path":"data/snapshots.db","snapshot_count":42},
#  "suggestions":{"active_count":3},
#  "drift_alerts":{"unacknowledged_count":1},
#  "components":{"snapshot_store":{"snapshot_count":42,"db_path":"data/snapshots.db"}}}
```

Suggestions are generated automatically when snapshots are submitted via `POST /snapshots`. A suggestion appears when an alternative skill would have scored better by at least `SUGGESTION_DELTA_THRESHOLD` (default 0.1). Confidence is derived from sample count: low (<5), medium (5–20), high (>20).

Suggestions never influence `zero_trust_cleared` — there is no code path from suggestions to trust.

Drift alerts are persisted to a `drift_alerts` table in `snapshots.db` (additive schema) whenever `GET /drift/{intent}` detects a dominant-skill shift, so they survive restarts and can be reviewed across all intents at once.

## CLI commands

The `cyrus-intel` CLI talks to a running Intelligence Engine over HTTP (base URL from `INTELLIGENCE_ENGINE_URL`, default `http://localhost:8002`).

| Command | Description |
|---------|-------------|
| `cyrus-intel suggestions list` | List active suggestions |
| `cyrus-intel suggestions dismiss <id>` | Dismiss a suggestion |
| `cyrus-intel drift alerts` | List unacknowledged drift alerts |
| `cyrus-intel status` | Print system status panel |

Every command accepts a `--json` flag to print the raw JSON response instead of formatted output. All commands exit with code 1 on HTTP errors or when the engine is unreachable.

```
$ cyrus-intel status
CYRUS Intelligence Engine
─────────────────────────
Status:          ok
Version:         0.4.0
Snapshots:       42
Active suggestions:       3
Unacknowledged alerts:    1
DB path:         data/snapshots.db
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SNAPSHOT_DB_PATH` | `data/snapshots.db` | SQLite database path (WAL mode) |
| `MAX_LATENCY_MS` | `5000.0` | Latency cap for scoring normalisation |
| `DRIFT_WINDOW_SIZE` | `20` | Snapshot history window for drift detection |
| `SUGGESTION_DELTA_THRESHOLD` | `0.1` | Minimum score delta to generate a suggestion |
| `INTELLIGENCE_ENGINE_URL` | `http://localhost:8002` | Base URL for CLI HTTP calls |
| `LOG_LEVEL` | `INFO` | Logging level |
| `PORT` | `8002` | Service port |

## Running the service

```bash
# Install
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Run
uvicorn src.main:app --port 8002
```

Or with Docker:

```bash
docker compose -f docker-compose.dev.yml up --build
```

## Running the CLI

```bash
cyrus-intel status
cyrus-intel suggestions list
cyrus-intel drift alerts
```

## Running tests

```bash
make test      # pytest --tb=short -q  (120 tests)
make test-v    # verbose test run
```

Tests live in `tests/` — unit coverage for the stores and both engines, API-level tests for every endpoint via httpx `ASGITransport`, and CLI tests via `typer.testing.CliRunner` with `pytest-httpx` mocking. Integration tests (`tests/test_integration.py`) run against the ASGI app in-process — no running server required.

## Platform Context

This service is part of the CYRUS platform. The Orchestrator Agent currently embeds its own intelligence layer (`src/intelligence/`); this repo is the standalone extraction of that layer. The Orchestrator's embedded intelligence stays in place — in a later phase, its optional `intelligence_agent` parameter can be pointed at this service via an `HttpIntelligenceClient`.

Boundaries:

- Read/write for its own snapshot store only — never touches the SKB or the Orchestrator's `weights.db`
- SQLite schema is additive only across phases (no `ALTER TABLE`)
- All responses are JSON

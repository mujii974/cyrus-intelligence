# cyrus-intelligence

CYRUS Skill Intelligence Engine — a standalone HTTP service for counterfactual skill scoring and intent drift detection.

## Overview

The Intelligence Engine is the Orchestrator Agent's skill intelligence layer (`CounterfactualEngine`, `IntentDriftDetector`, `WeightStore`) extracted into an independently deployable FastAPI service. It records `WeightSnapshot` events from Orchestrator runs, evaluates whether a different skill would have scored better for a given selection, and detects when the dominant skill for an intent drifts over time.

Core components:

- **`WeightSnapshotStore`** — SQLite (WAL mode) persistence for snapshot records, queryable by skill and intent
- **`CounterfactualEngine`** — compares the selected skill's composite score against all candidates; the `_score()` formula (`quality_score × (1 / latency_normalised)`) is identical to the Orchestrator's and must not diverge. `evaluate()` never raises.
- **`IntentDriftDetector`** — split-halves dominant-skill comparison over a configurable window (default 20); fires a `DriftAlert` when the dominant skill changes between the older and newer half

## Quickstart

```bash
# Install
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Configure
cp .env.example .env

# Run
uvicorn src.main:app --port 8002
```

Or with Docker:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Verify:

```bash
curl http://localhost:8002/health
# {"status":"ok"}
```

## API Reference

All endpoints return JSON.

### `POST /snapshots`

Record a batch of WeightSnapshots from an Orchestrator run. Upserts by `snapshot_id`. Returns `201`.

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

### `GET /snapshots/{skill_id}`

Snapshot history for a skill, newest first. Query param: `limit` (default 100).

```bash
curl "http://localhost:8002/snapshots/com.example.skill:1.0?limit=10"
# {"skill_id":"com.example.skill:1.0","count":1,"snapshots":[...]}
```

### `POST /counterfactual`

Evaluate whether a different skill would have scored better for a snapshot. Never errors — on internal failure it returns a safe `"optimal"` result.

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

`recommendation` is `"optimal"` when no alternative scores higher, otherwise `"consider_alternative"`. `delta` is `best_alternative_score - selected_score` (`0.0` when there is no alternative).

### `GET /drift/{intent}`

Detect dominant-skill drift for an intent pattern across stored snapshots. Requires at least 4 snapshots for the intent.

```bash
curl http://localhost:8002/drift/summarise
# {"intent":"summarise","snapshot_count":6,"drift_detected":true,
#  "alert":{"intent":"summarise","old_dominant_skill":"A","new_dominant_skill":"B",
#           "window_size":6,"alert_at":"..."}}
```

### `GET /health`

Liveness check. Returns `{"status":"ok"}`.

### `GET /health/detailed`

Component state: snapshot count, database path, installed version.

```bash
curl http://localhost:8002/health/detailed
# {"status":"ok","version":"0.1.0",
#  "components":{"snapshot_store":{"snapshot_count":0,"db_path":"data/snapshots.db"}}}
```

## Skill Suggestions

The Intelligence Engine generates routing suggestions when execution history shows a better skill would have been selected.

| Method | Path | Description |
|---|---|---|
| `GET` | `/suggestions` | All active suggestions, newest first (`limit` query param, default 20, max 100) |
| `GET` | `/suggestions/{intent}` | Most recent suggestion for a specific intent (404 if none) |
| `POST` | `/suggestions/{id}/dismiss` | Dismiss a suggestion (404 if not found) |
| `POST` | `/suggestions/generate` | Trigger suggestion generation from recent snapshots |

Suggestions are generated automatically when snapshots are submitted via `POST /snapshots`. A suggestion appears when an alternative skill would have scored better by at least `SUGGESTION_DELTA_THRESHOLD` (default 0.1). Confidence is derived from sample count: low (<5), medium (5–20), high (>20).

Suggestions never influence `zero_trust_cleared` — there is no code path from suggestions to trust.

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `SNAPSHOT_DB_PATH` | `data/snapshots.db` | SQLite database path (WAL mode) |
| `MAX_LATENCY_MS` | `5000.0` | Latency normalisation ceiling for `_score()` |
| `DRIFT_WINDOW_SIZE` | `20` | Snapshot window for drift detection |
| `LOG_LEVEL` | `INFO` | Logging level |
| `PORT` | `8002` | Service port |

## Development

```bash
make install   # pip install -e .
make test      # pytest --tb=short -q  (68 tests)
make test-v    # verbose test run
make run       # uvicorn with --reload on port 8002
make lint      # ruff if installed
```

Tests live in `tests/` — unit coverage for the store and both engines plus API-level tests for every endpoint via httpx `ASGITransport`.

### Integration tests

```bash
pytest tests/test_integration.py -v
```

Integration tests run against the ASGI app in-process — no running server required. They cover the full Orchestrator round-trip: snapshot batch submission, retrieval by skill, counterfactual evaluation, drift detection, health counts, empty batches, and concurrent submissions.

## Platform Context

This service is part of the CYRUS platform. The Orchestrator Agent currently embeds its own intelligence layer (`src/intelligence/`); this repo is the standalone extraction of that layer. The Orchestrator's embedded intelligence stays in place — in a later phase, its optional `intelligence_agent` parameter can be pointed at this service via an `HttpIntelligenceClient`.

Boundaries:

- Read/write for its own snapshot store only — never touches the SKB or the Orchestrator's `weights.db`
- SQLite schema is additive only across phases (no `ALTER TABLE`)
- All responses are JSON

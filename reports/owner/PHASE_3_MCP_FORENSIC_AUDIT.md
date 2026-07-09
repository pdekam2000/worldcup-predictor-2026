# Phase 3.0 — MCP Forensic Audit

**Project:** `pdekam2000/worldcup-predictor-2026`  
**Audit date:** 2026-07-09  
**Branch base:** `origin/main` @ `71f4169309ef97acfc0dc733e6bd8d20212dc843`  
**Phase 3 branch:** `infra/phase3-mcp-prediction-server`

## Python / runtime

| Item | Value |
|------|--------|
| Local Python | 3.14.5 |
| Production venv | `/opt/worldcup-predictor/.venv` (Python 3.11+ expected on Hetzner) |
| Dependency file | `requirements.txt` (no `pyproject.toml` lockfile) |
| FastAPI stack | `fastapi>=0.115`, `uvicorn[standard]`, `pydantic>=2`, `sqlalchemy>=2` |
| DB | SQLite (`settings.sqlite_path`) + optional Postgres for SaaS |

## Dependency strategy (MCP)

- Add **`mcp>=1.27,<2`** (official Model Context Protocol Python SDK v1.x, FastMCP)
- Pin upper bound `<2` to avoid pre-release v2 breakage
- No unrelated package upgrades
- Optional `psutil` not required (health uses `/proc` fallback)

## MCP SDK choice

**`mcp` package (Anthropic MCP Python SDK)** with `FastMCP` server, transports:

1. **stdio** — Cursor over SSH (primary)
2. **streamable-http** / **sse** — localhost only, behind future tunnel for ChatGPT

Default bind: **`127.0.0.1`** (never `0.0.0.0` by default).

## Canonical paths (do not duplicate)

| Concern | Canonical module / function |
|---------|----------------------------|
| Fixture discovery (daily) | `worldcup_predictor.owner_daily.fixture_discovery.discover_daily_fixtures` |
| Fixture resolution (teams) | `worldcup_predictor.owner_manual_exact.resolver.resolve_fixture` + `team_aliases` |
| Odds freshness | `worldcup_predictor.odds.freshness_metadata.build_fixture_freshness_metadata` → `freshness_policy.classify_odds_freshness` |
| Odds freshness audit | `worldcup_predictor.odds.freshness_audit.run_odds_freshness_audit` |
| Strict live refresh | `worldcup_predictor.odds.strict_live_refresh.refresh_fixture_odds_live` |
| Provider order | API-Football → Sportmonks → OddAlerts (explicit crosswalk only) |
| WDE generation | `worldcup_predictor.owner_daily.predictions.run_daily_wde` → `PredictPipeline.run` |
| ECSE generation | `worldcup_predictor.owner_daily.predictions.run_daily_ecse` → `build_ecse_live_prediction` |
| Stored WDE read | `worldcup_predictor.owner_daily.report._load_wde` / `WorldcupPredictionStore` |
| Stored ECSE read | `worldcup_predictor.research.ecse_live.store.get_snapshot` |
| Owner reports | `reports/owner/` via `owner_daily.constants.REPORTS_DIR` |
| Production orchestration | `worldcup_predictor.owner.production_pipeline.runner` (lock: `ProductionPipelineLock`) |
| API health | `worldcup_predictor.api.routes.health` @ `127.0.0.1:8000` |

## Production service architecture

| Service | User | Working dir | Bind |
|---------|------|-------------|------|
| `worldcup-api` | `www-data` | `/opt/worldcup-predictor` | `127.0.0.1:8000` |
| `worldcup-mcp` (new) | `worldcup-mcp` | `/opt/worldcup-predictor` | `127.0.0.1:8765` (HTTP) |
| Cursor MCP | via SSH stdio | same app root | no public port |

Phase 1 SSH scaffold: `scripts/validate_phase1_ssh_scaffold.py`, `deployment/sudoers/worldcup-deploy`  
Phase 2 GitHub deploy: `origin/infra/phase2-github-actions-safe-deploy`, `scripts/validate_phase2_github_deploy.py`, `.github/workflows/deploy-production.yml`

## Proposed MCP transport

- **Mode A (Cursor):** SSH → `python -m worldcup_predictor.mcp_server.server --stdio`
- **Mode B (ChatGPT prep):** outbound tunnel → `127.0.0.1:8765` streamable-http + Bearer token

## Proposed auth model

- **stdio:** SSH session authentication (no MCP token in repo)
- **remote:** `MCP_AUTH_TOKEN` env only; Bearer header validation in `auth.py`

## Proposed audit model

- JSONL at `/var/log/worldcup-mcp/audit.jsonl`
- Fields: timestamp, request_id, tool_name, caller_mode, duration_ms, success, fixture_count, result_status, sanitized_error
- Secret redaction in `audit.redact_secrets`

## DB concurrency

- SQLite writes: sequential batch processing via `threading.Lock` in MCP runtime
- Production pipeline uses `fcntl` file lock on Linux (`ProductionPipelineLock`)
- MCP does not enable parallel prediction writes

## Files to create

```
worldcup_predictor/mcp_server/
  __init__.py, server.py, config.py, auth.py, audit.py, policies.py, schemas.py, runtime.py
  tools/{health,fixtures,odds,predictions,reports}.py
tests/mcp_server/test_*.py
scripts/validate_phase3_mcp_prediction_server.py
scripts/install_worldcup_mcp_service.sh
deployment/systemd/worldcup-mcp.service
docs/CURSOR_MCP_PREDICTION_SETUP.md
docs/CHATGPT_MCP_PREDICTION_CONNECTION.md
reports/owner/PHASE_3_MCP_*.md
```

## Files to modify

- `requirements.txt` — add `mcp>=1.27,<2` only

## Files that must NOT change

- `predict_pipeline.py`, `freshness_policy.py`, `strict_live_refresh.py`, ECSE formulas, WDE thresholds, provider priority, DB schema, model weights

## Stop conditions checked

- Canonical WDE path: **identified** (`run_daily_wde` / `PredictPipeline`)
- Canonical ECSE path: **identified** (`run_daily_ecse` / `build_ecse_live_prediction`)
- No arbitrary shell/SQL/file tools in MCP design
- No public unauthenticated bind by default

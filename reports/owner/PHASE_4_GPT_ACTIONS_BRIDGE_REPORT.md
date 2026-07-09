# Phase 4 — GPT Actions Bridge Implementation Report

**Date:** 2026-07-09  
**Branch:** `feature/phase4-gpt-actions-bridge`  
**Production modified:** NO  
**Deploy:** NO

## Architecture

ChatGPT Custom GPT → GPT Actions (HTTPS 443) → Nginx narrow prefix → `127.0.0.1:8770` (`worldcup-gpt-actions`) → canonical MCP runtime (`worldcup_predictor.mcp_server.runtime`) → WDE + BTTS + O/U 2.5 + ECSE.

This is **not** an MCP proxy. Seven explicit REST operations only.

## Service design

| Component | Path |
|-----------|------|
| FastAPI app | `worldcup_predictor/gpt_actions/app.py` |
| Server entry | `worldcup_predictor/gpt_actions/server.py` |
| Auth | `worldcup_predictor/gpt_actions/auth.py` (Bearer only) |
| Async jobs | `worldcup_predictor/gpt_actions/jobs.py`, `worker.py` |
| Canonical delegation | `worldcup_predictor/gpt_actions/delegation.py` |
| systemd | `deployment/systemd/worldcup-gpt-actions.service` |
| Nginx snippet (prepared) | `deployment/nginx/gpt-actions-snippet.conf` |

Bind: `127.0.0.1:8770`  
Secrets: `/etc/worldcup-gpt-actions/environment` (outside Git)

## Public boundary

- Planned public path: `https://footballpredictor.it.com/api/gpt-actions/v1/`
- MCP `127.0.0.1:8765` — **not exposed**
- Tunnel service — **inactive**
- FastAPI `/docs` and `/openapi.json` — **disabled** on bridge service

## Authentication

- API Key via `Authorization: Bearer <GPT_ACTIONS_API_KEY>`
- Constant-time verification (`hmac.compare_digest`)
- Query-string API key rejected (400)
- Rate limiting (in-app + Nginx snippet)
- Request ID header (`X-Request-ID`)
- Audit JSONL with secret redaction

## Async jobs

- `POST /api/gpt-actions/v1/prediction-jobs` → immediate `job_id`, poll after 3s
- `GET /api/gpt-actions/v1/prediction-jobs/{job_id}` → status + evidence
- Sequential fixture execution via `mcp_runtime.run_fixture_prediction`
- Max one heavy job at a time
- Idempotency-Key support
- File-based job store (no DB schema changes)

## Canonical delegation

| Capability | Delegates to |
|------------|--------------|
| WDE / BTTS / O/U | `run_fixture_prediction` → `run_daily_wde` |
| ECSE Top1–Top5 | `run_fixture_prediction` → `run_daily_ecse` + snapshot formatting |
| Odds freshness | `build_fixture_freshness_metadata` (via MCP runtime) |
| Odds filter | `odds_snapshots` + normalized line parser |
| Reports | `latest_prediction_report`, `prediction_report_by_date` |

No formula changes. No retraining. No DB schema changes.

## OpenAPI schema

`docs/gpt_actions/worldcup_predictor_actions.openapi.yaml` — 7 unique operation IDs, Bearer auth, bounded schemas.

## Custom GPT instructions

`docs/gpt_actions/CUSTOM_GPT_OWNER_INSTRUCTIONS.md`

## Security review (threat model)

| Threat | Mitigation |
|--------|------------|
| Leaked Action API key | Key outside Git; rotate via env file; Bearer only; audit logs redact secrets |
| Replay requests | Idempotency keys; rate limits; no state-changing GET |
| Job flooding | Single active heavy job; rate limit; max fixtures per job (20) |
| Prompt injection in team names | Read-only DB queries; no shell/SQL/execute endpoints; structured responses only |
| Oversized response | `max_response_chars` trim; OpenAPI maxLength; report truncation |
| Long-running job abuse | Async jobs; 30s Nginx proxy timeout on poll/create |
| Duplicate prediction refresh | Idempotency; sequential execution |
| Provider quota exhaustion | Delegates to existing strict refresh policy in MCP runtime |
| DB lock | Sequential predictions; MCP runtime `_PREDICTION_LOCK` |
| Cross-job data leakage | Job artifacts keyed by UUID; no shared mutable result buffers |
| Sensitive log leakage | Audit redaction; API key never logged |

## Validation and tests

| Suite | Result |
|-------|--------|
| `scripts/validate_phase4_gpt_actions_bridge.py` | **PASS (52/52)** |
| `tests/gpt_actions/test_gpt_actions_bridge.py` | **16 passed** |

## Production deployment status

| Item | Status |
|------|--------|
| Service installed on Hetzner | NO |
| Nginx route activated | NO |
| API key provisioned on server | NO |
| Custom GPT connected | NO |

## Final statuses

| Status | Value |
|--------|-------|
| GPT_ACTIONS_BRIDGE_CODE_READY | **YES** |
| GPT_ACTIONS_OPENAPI_READY | **YES** |
| GPT_ACTIONS_SECURITY_READY | **YES** |
| GPT_ACTIONS_ASYNC_JOB_READY | **YES** |
| CUSTOM_GPT_INSTRUCTIONS_READY | **YES** |
| PRODUCTION_DEPLOYED | **NO** |
| PUBLIC_HTTPS_ACTION_ENDPOINT_READY | **NO** |
| CUSTOM_GPT_ACTUAL_CONNECTION | **NO** |
| MCP_PUBLIC_EXPOSURE | **NO** |

## Model / DB changes

- WDE formulas: **unchanged**
- ECSE formulas: **unchanged**
- DB schema: **unchanged**

## Next steps (owner)

1. Review and merge PR
2. Create `worldcup-gpt-actions` user and `/etc/worldcup-gpt-actions/environment`
3. Install systemd unit and start service on `127.0.0.1:8770`
4. Add Nginx snippet to production server block (after review)
5. Import OpenAPI into Custom GPT with Bearer API key
6. Test discover → filter → job → poll flow

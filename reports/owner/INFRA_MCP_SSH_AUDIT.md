# INFRA / MCP / SSH Forensic Audit — Phase 0

**Date:** 2026-07-09  
**Repository:** `pdekam2000/worldcup-predictor-2026` (local workspace audit)  
**Phase:** 0 — Forensic audit only (no implementation)  
**Production target (from codebase):** Hetzner — `/opt/worldcup-predictor` — `worldcup-api`  
**Public production domain (from deploy scripts):** `footballpredictor.it.com`

---

## Executive summary

The repository has **mature production deployment artifacts** (systemd, nginx, rollback docs, hardened deploy helpers, odds freshness, owner prediction pipelines) but **no GitHub Actions workflows**, **no MCP server**, and **no standardized SSH/deploy-user architecture** in the local tree.

Production access today is implied through **ad-hoc `root@<IP>` SSH** in several operational scripts. That is a **critical gap** relative to the requested secure `deploy` user + restricted sudo + key-only automation model.

**Recommendation before Phase 1:** Proceed with incremental implementation on a **feature branch**, but **do not run bootstrap or deploy scripts on production** until:

1. A dedicated `deploy` user and restricted sudoers are validated on a non-production session.
2. Root-SSH operational scripts are migrated to the `worldcup-prod` SSH alias pattern.
3. GitHub Secrets are configured (workflows do not exist locally yet).

No blocking ambiguity prevents **design and local scaffolding** of Phases 1–7, but **production bootstrap requires explicit owner approval** because root SSH is currently embedded in live ops scripts.

---

## 1. Existing deployment architecture

### 1.1 Production stack (canonical — React + FastAPI)

Documented in `deployment/DEPLOY_REACT_FASTAPI.md`, `deployment/CHECKLIST.md`, `deployment/ROLLBACK.md`:

| Layer | Path / endpoint | Role |
|-------|-----------------|------|
| App root | `/opt/worldcup-predictor` | Git checkout, Python venv, SQLite intelligence DB |
| Python venv | `/opt/worldcup-predictor/.venv` | uvicorn, scripts, prediction pipelines |
| Production env | `/opt/worldcup-predictor/.env.production` | Secrets — **never commit** |
| FastAPI service | `worldcup-api` (systemd) | `uvicorn worldcup_predictor.api.main:app --host 127.0.0.1 --port 8000` |
| Service user | `www-data` | Runs API per `deployment/systemd/worldcup-api.service` |
| React frontend | `/var/www/worldcup/frontend/dist` | Static SPA served by Nginx |
| Nginx | `/etc/nginx/sites-available/worldcup*` | TLS termination, `/api/` → `:8000`, SPA fallback |
| PostgreSQL | `DATABASE_URL` in `.env.production` | SaaS auth, users, billing (Alembic migrations) |
| SQLite intelligence | `data/football_intelligence.db` | WDE/ECSE/odds snapshots — **must preserve** |
| API health | `GET /api/health` | `{"status":"ok"}` |
| Provider health | `GET /api/health/providers` | Safe key-presence diagnostic (no secrets) |
| Deploy logs | `/opt/worldcup-predictor/logs/deploy/` | Phase A21B detached deploy sessions |
| Backup root (hardening) | `/opt/worldcup-backups` | Referenced in `scripts/lib/deploy_hardening.sh` |
| SQLite backups | `backups/sqlite/` (keep 20) | `scripts/backup_sqlite.sh` |
| Phase backups | `backups/phase*-deploy-*`, `data/backups/` | Per-deploy snapshots in phase scripts |

### 1.2 Legacy / alternate stack (still in repo — do not confuse with live FastAPI prod)

| Artifact | Notes |
|----------|-------|
| `docs/HETZNER_DEPLOYMENT.md` | Streamlit GUI on `:8501`, Docker-first |
| `docker-compose.yml` | Streamlit container `worldcup-gui` on `127.0.0.1:8501` |
| `.env.production.example` (repo root) | Streamlit/GUI-oriented env template |
| `scripts/deploy_hetzner.sh` | Docker + Streamlit bootstrap helper |

**Gap:** Documentation drift between Streamlit-era and current React+FastAPI production. New infra docs must reference **`deployment/.env.production.example`** and **`deployment/systemd/worldcup-api.service`**, not retire them silently.

### 1.3 Systemd units (repository)

All under `deployment/systemd/`:

| Unit | Purpose |
|------|---------|
| `worldcup-api.service` | **Primary production API** |
| `worldcup-daily-predict.service` + `.timer` | Background WC predictions (`main.py daily-worldcup-predict`) |
| `worldcup-prediction-daily.service` + `.timer` | Daily prediction timer |
| `worldcup-prediction-prefetch.service` + `.timer` | Prefetch |
| `worldcup-auto-cycle.service` + `.timer` | Autonomous cycle |
| `worldcup-autonomous.service` + `.timer` | Autonomous runs |
| `worldcup-evaluate-results.service` + `.timer` | Result evaluation |
| `worldcup-results-hourly.service` + `.timer` | Hourly results |
| `worldcup-update-pick-results.service` + `.timer` | Pick result updates |
| `worldcup-daily-picks.service` + `.timer` | Daily picks |
| `worldcup-assistant-alert-scan.service` + `.timer` | Assistant alerts |
| `worldcup-elite-shadow.service` + `.timer` | Elite shadow |
| `egie-goal-timing-evaluation.service` + `.timer` | EGIE evaluation |

**No `worldcup-mcp.service` exists.**

### 1.4 Nginx templates

| File | Use |
|------|-----|
| `deployment/nginx/worldcup.conf` | Domain + SSL (production) |
| `deployment/nginx/worldcup-ip.conf` | IP-only smoke test |
| `deployment/nginx/worldcup-ip-redirect.conf` | IP redirect variant |

### 1.5 Database & migrations

- **Alembic:** `alembic/versions/001` … `014` (PostgreSQL SaaS schema)
- **SQLite schema:** managed in application code + `ensure_schema_compat` patterns in deploy scripts
- **Rollback:** `deployment/ROLLBACK.md` — forward-only Alembic; PG restore from `pg_dump` backup

---

## 2. Current production paths and commands (from codebase)

| Operation | Canonical path / command |
|-----------|--------------------------|
| App directory | `/opt/worldcup-predictor` |
| Activate venv | `source /opt/worldcup-predictor/.venv/bin/activate` |
| Load secrets | `set -a && source .env.production && set +a` |
| Restart API | `sudo systemctl restart worldcup-api` |
| API status | `sudo systemctl is-active worldcup-api` |
| API logs | `sudo journalctl -u worldcup-api -n 100 --no-pager` |
| Nginx test | `sudo nginx -t && sudo systemctl reload nginx` |
| Local health | `curl -s http://127.0.0.1:8000/api/health` |
| Public health | `curl -s https://footballpredictor.it.com/api/health` |
| Frontend build | `cd base44-d && npm ci && npm run build` |
| Frontend publish | `sudo rsync -a dist/ /var/www/worldcup/frontend/dist/` |
| PG migrate | `alembic upgrade head` |
| SQLite backup | `./scripts/backup_sqlite.sh` |
| Compile check | `.venv/bin/python -m compileall worldcup_predictor scripts -q` |
| Production readiness | `python scripts/validate_production_readiness.py` |
| Odds freshness audit | `python scripts/run_odds_freshness_refresh.py --mode audit` |
| Odds freshness refresh | `python scripts/run_odds_freshness_refresh.py --mode refresh` |
| Owner daily reports | `reports/owner/daily_predictions_YYYYMMDD.md` |

---

## 3. GitHub workflows

**Finding:** No `.github/` directory exists in the local workspace.

| Item | Status |
|------|--------|
| `.github/workflows/` | **Missing locally** |
| CI validation on push | **Not present in this clone** |
| `workflow_dispatch` deploy | **Not present** |
| Required secrets (`HETZNER_*`) | **Not configured in repo** (by design) |

**Note:** Remote `pdekam2000/worldcup-predictor-2026` may contain workflows not synced to this workspace. Phase 2 must verify remote before assuming greenfield.

**Planned (Phase 2):** `.github/workflows/deploy-production.yml` — `workflow_dispatch` only initially.

---

## 4. Existing deployment scripts (inventory)

### 4.1 Reusable / modern patterns (prefer extend, do not duplicate)

| Script | Role |
|--------|------|
| `scripts/lib/deploy_hardening.sh` | Lock, status JSON, checkpoints, backup root, flock |
| `scripts/deploy_run.sh` | Detached deploy via `systemd-run` or `nohup` |
| `scripts/run_codebase_consolidation_2_production_deploy.sh` | **Best reference** for safe prod deploy: dirty-tree classification, DB snapshot, backup, validation, health, rollback hints |
| `scripts/phase65_production_deploy.sh` | Full backup + frontend + API restart + smoke — **uses `git reset --hard`** |
| `scripts/backup_sqlite.sh` | SQLite rotation (keep 20) |
| `scripts/validate_production_readiness.py` | Pre-deploy audit |
| `scripts/validate_phase_a21b_deploy_hardening.py` | Deploy hardening regression tests |
| `worldcup_predictor/ops/deploy_status.py` | Deploy session status reader |

### 4.2 Phase-specific deploy scripts (100+)

Pattern: `scripts/deploy_phase*_production.sh`, `*_smoke.sh`, `remote_deploy_*.sh`, `pack_*_deploy.sh`.

These are **historical phase releases** — new infra must **not** replace them; add parallel `production_*` scripts and wire GitHub Actions to those.

### 4.3 Remote SSH operational scripts (security concern)

Several scripts hardcode production SSH as **`root@91.107.188.229`**:

- `scripts/run_codebase_consolidation_2.py`
- `scripts/run_result_truth_schema_v8_and_ecse_reevaluation_1.py`
- `scripts/run_ecse_evaluation_parity_and_reliability_gate_1.py`
- `scripts/run_project_asset_audit.py`
- `scripts/validate_phase_a12b_preproduction.py` (env override `A12B_PROD_SSH`)
- `scripts/phase54h3_live_pressure_backfill_plan.py`

**Gap:** Root SSH + embedded host IP conflicts with requested `deploy` user + SSH config alias + no secrets in repo. Phase 1 must migrate ops to `worldcup-prod` host alias and environment variables — **without deleting** existing scripts until migration validated.

---

## 5. Existing validation commands

| Validator | Purpose |
|-----------|---------|
| `scripts/validate_production_readiness.py` | Deployment file + frontend build + production guard |
| `scripts/validate_phase3_auth_http.py` | Auth HTTP checks |
| `scripts/validate_odds_freshness_1.py` | Odds freshness policy (no DB writes in audit mode) |
| `python -m compileall worldcup_predictor scripts` | Syntax compile gate (used in deploy scripts) |
| `scripts/validate_phase_a21b_deploy_hardening.py` | Deploy lock/status/detached launcher |
| Phase-specific `validate_phase*.py` | 300+ domain validators — use subset in CI, not all |

**Recommended deploy gate subset (Phase 2):**

1. `python -m compileall worldcup_predictor scripts -q`
2. `python scripts/validate_production_readiness.py`
3. `python scripts/validate_odds_freshness_1.py` (audit mode / no provider calls on CI)
4. Post-deploy: `curl` `/api/health` + `systemctl is-active worldcup-api`

---

## 6. Existing backup mechanisms

| Mechanism | Location / script |
|-----------|-------------------|
| SQLite rotate | `scripts/backup_sqlite.sh` → `backups/sqlite/football_intelligence_*.db` |
| Deploy pre-backup | `run_codebase_consolidation_2_production_deploy.sh` — commit SHA, `.env.production`, SQLite, PG dump, frontend dist |
| Phase65 backup | `backups/phase65-deploy-<ts>/` |
| Hardening backup root | `/opt/worldcup-backups` (`DEPLOY_BACKUP_ROOT`) |
| PG manual | `pg_dump` per `deployment/ROLLBACK.md` |
| Runtime stash | `data/shadow/*.jsonl`, `data/enterprise/*.json` preserved in deploy scripts |

**Gap:** No single canonical `scripts/production_deploy_safe.sh` yet — consolidate from `run_codebase_consolidation_2_production_deploy.sh`.

---

## 7. Existing health checks

| Check | Implementation |
|-------|----------------|
| API liveness | `worldcup_predictor/api/routes/health.py` → `/api/health` |
| Provider readiness | `/api/health/providers` — key presence only |
| Admin health | `worldcup_predictor/api/routes/admin.py` `/health` |
| Version endpoint | `/api/version` — deploy badge |
| Smoke scripts | `scripts/deploy_phase*_smoke.sh` — curl public routes on `footballpredictor.it.com` |
| Systemd | `systemctl is-active worldcup-api` |

**Gap:** No standalone `scripts/production_health_check.sh` — trivial to add wrapping curl + systemctl.

---

## 8. Prediction & odds pipelines (canonical — do not reimplement)

| System | Module / script |
|--------|-----------------|
| WDE pipeline | `worldcup_predictor/orchestration/predict_pipeline.py`, `owner/production_pipeline/` |
| ECSE live | `worldcup_predictor/research/ecse_live/` |
| Owner daily | `worldcup_predictor/owner_daily/` — reports → `reports/owner/daily_predictions_*.md` |
| Odds freshness policy | `worldcup_predictor/odds/freshness_policy.py` |
| Odds refresh | `worldcup_predictor/odds/freshness_refresh.py` |
| Odds audit | `worldcup_predictor/odds/freshness_audit.py` |
| Multi-provider fallback | API-Football → Sportmonks → OddAlerts in `freshness_refresh.py` |
| Provider quota | `worldcup_predictor/owner_daily/provider_call_log.py` |
| WDE quality gate | `worldcup_predictor/api/wde_quality_gate.py` |
| Today 7-match (2026-07-09) | `scripts/run_today_7_match_predictions_20260709.py` |

**Not found:** `scripts/rerun_today_7_strict_live_predictions_20260709.py` (referenced in task spec). Closest canonical script: `scripts/run_today_7_match_predictions_20260709.py`. Phase 3 MCP tool `run_today7_strict_predictions()` should call existing script or add thin wrapper alias — **not duplicate logic**.

---

## 9. MCP-related files

| Item | Status |
|------|--------|
| `worldcup_predictor/mcp_server/` | **Does not exist** |
| MCP dependency in `requirements.txt` | **None** (`mcp`, `modelcontextprotocol` not listed) |
| Cursor MCP config (`.cursor/mcp.json` etc.) | **Not found** |
| MCP audit log path | **Not configured** |

**Python version (local dev machine):** 3.14.5 — MCP package compatibility must be verified against **production venv Python** on Hetzner before adding dependency.

---

## 10. SSH / deployment documentation

| Document | Status |
|----------|--------|
| `docs/HETZNER_DEPLOYMENT.md` | Exists — **Streamlit/Docker era** |
| `deployment/DEPLOY_REACT_FASTAPI.md` | Exists — **current FastAPI architecture** |
| `deployment/CHECKLIST.md` | Full server bootstrap checklist |
| `deployment/ROLLBACK.md` | Rollback procedures |
| `docs/HETZNER_SSH_SETUP.md` | **Does not exist** (Phase 1) |
| `docs/CURSOR_MCP_SETUP.md` | **Does not exist** (Phase 5) |
| `docs/CHATGPT_MCP_FUTURE_SETUP.md` | **Does not exist** (Phase 6) |

---

## 11. Environment configuration

| File | Purpose |
|------|---------|
| `deployment/.env.production.example` | **Canonical FastAPI production template** (PG, JWT, API keys) |
| `.env.production.example` (root) | Legacy Streamlit template |
| `.env` | Local dev (gitignored — present on disk) |
| `deployment/ecse_x2_m7_enablement_snippet.env` | Feature snippet |

**Provider keys (from `provider_readiness.py`):** API_FOOTBALL, SPORTMONKS, THE_ODDS_API, WEATHER, STRIPE — presence checks only in health endpoints.

---

## 12. Current gaps (prioritized)

### Critical

1. **No restricted deploy user** — production ops scripts use `root@<IP>`.
2. **No GitHub Actions deploy workflow** in local repo.
3. **No MCP server** — zero remote management API with audit trail.
4. **Host IP embedded in scripts** — should move to env/SSH config (`HETZNER_HOST`, `worldcup-prod` alias).
5. **`phase65_production_deploy.sh` uses `git reset --hard`** — conflicts with requested safe deploy policy; new `production_deploy_safe.sh` must avoid this by default.

### High

6. No `scripts/production_preflight.sh`, `production_deploy_safe.sh`, `production_rollback.sh`, `production_health_check.sh`.
7. No Windows SSH setup script for dev machine.
8. No `deploy` sudoers drop-in.
9. Documentation drift (Streamlit vs FastAPI).
10. MCP Python SDK not in requirements — version pin TBD after prod Python check.

### Medium

11. No centralized deployment audit JSONL (deploy status JSON exists per-session in `logs/deploy/`).
12. No Cursor MCP integration.
13. `rerun_today_7_strict_live_predictions_20260709.py` missing — map to existing runner.
14. Remote GitHub workflows unknown — verify on GitHub before Phase 2.

### Low

15. Docker Compose path still documented for greenfield installs — orthogonal to current systemd prod.
16. 100+ historical deploy scripts — need index in implementation report, not consolidation yet.

---

## 13. Critical ambiguities (STOP gates for production touch)

| # | Ambiguity | Mitigation before prod change |
|---|-----------|-------------------------------|
| A | Is live production **systemd FastAPI** or **Docker Streamlit**? | Confirm on server: `systemctl status worldcup-api` vs `docker ps` |
| B | Is SSH still **root-only** on Hetzner? | Owner must run bootstrap once; do not automate root password |
| C | Does remote GitHub repo already have Actions workflows? | `gh workflow list` on remote before creating duplicate |
| D | Production Python version for MCP SDK? | `ssh worldcup-prod '.venv/bin/python --version'` after SSH setup |
| E | Which user should own MCP service — `deploy` or `www-data`? | Prefer `deploy` for management, `www-data` for API only |
| F | `git reset --hard` in phase65 — is it still used in production? | New safe deploy must use `git pull --ff-only` + dirty-tree refusal |

**Phase 0 verdict:** Safe to proceed with **local-only scaffolding** (scripts, docs, MCP module, tests, workflow file). **Do not execute bootstrap or deploy on Hetzner** until ambiguities A–B are confirmed by owner.

---

## 14. Exact files planned for modification (future phases)

*None in Phase 0.* Planned touches (incremental, branch-based):

| File | Phase | Change type |
|------|-------|-------------|
| `requirements.txt` | 3 | Add MCP SDK (pinned, after compatibility check) |
| `.gitignore` | 1–5 | Ensure MCP logs, local SSH configs excluded if needed |

**Explicit non-modification list (all phases):**

- `worldcup_predictor/orchestration/predict_pipeline.py` — no formula changes
- `worldcup_predictor/research/ecse_live/*` — no formula changes
- `worldcup_predictor/odds/freshness_policy.py` — no threshold changes
- `deployment/systemd/worldcup-api.service` — do not alter unless MCP needs documented hardening
- `.env.production` on server — never overwrite
- `data/football_intelligence.db` — never reset

Historical deploy scripts — **leave unchanged**; add new `production_*` scripts instead.

---

## 15. Exact new files planned for creation

### Phase 1 — SSH

| File | Purpose |
|------|---------|
| `scripts/setup_hetzner_ssh_windows.ps1` | Windows ED25519 key + SSH config |
| `scripts/bootstrap_hetzner_deploy_user.sh` | One-time server bootstrap (admin) |
| `deploy/sudoers/worldcup-deploy` | Restricted sudoers proposal |
| `docs/HETZNER_SSH_SETUP.md` | Setup guide |

### Phase 2 — GitHub Actions deploy

| File | Purpose |
|------|---------|
| `.github/workflows/deploy-production.yml` | `workflow_dispatch` deploy |
| `scripts/production_preflight.sh` | Pre-deploy checks |
| `scripts/production_deploy_safe.sh` | Safe deploy orchestrator |
| `scripts/production_rollback.sh` | Controlled rollback |
| `scripts/production_health_check.sh` | Health gate |

### Phase 3 — MCP server

| File | Purpose |
|------|---------|
| `worldcup_predictor/mcp_server/__init__.py` | Package |
| `worldcup_predictor/mcp_server/server.py` | MCP stdio/transport entry |
| `worldcup_predictor/mcp_server/config.py` | Env-based config |
| `worldcup_predictor/mcp_server/auth.py` | Token auth |
| `worldcup_predictor/mcp_server/audit.py` | JSONL audit |
| `worldcup_predictor/mcp_server/policies.py` | DENY-BY-DEFAULT allowlist |
| `worldcup_predictor/mcp_server/tools/*.py` | Approved tools only |

### Phase 4 — MCP systemd

| File | Purpose |
|------|---------|
| `deploy/systemd/worldcup-mcp.service` | MCP unit |
| `scripts/install_worldcup_mcp_service.sh` | Safe install |

### Phase 5–6 — Docs

| File | Purpose |
|------|---------|
| `docs/CURSOR_MCP_SETUP.md` | Cursor integration |
| `docs/CHATGPT_MCP_FUTURE_SETUP.md` | Future remote MCP |

### Phase 7 — Tests

| File | Purpose |
|------|---------|
| `tests/test_mcp_*.py` | MCP security tests |
| `scripts/validate_mcp_ssh_deploy_setup.py` | Non-destructive validator |

### Phase 8 — Report

| File | Purpose |
|------|---------|
| `reports/owner/MCP_SSH_DEPLOYMENT_IMPLEMENTATION_REPORT.md` | Final report |

---

## 16. Security observations (audit only)

1. **Root SSH in repo scripts** — IP visible in source; migrate to env + `deploy` user. Do not add passwords or private keys to repo.
2. **Dual env templates** — ensure new docs point to `deployment/.env.production.example`.
3. **MCP must be deny-by-default** — no pre-existing MCP means greenfield; high priority to avoid shell passthrough.
4. **`www-data` runs API** — MCP should not run as root; separate `deploy` or `worldcup-mcp` user.
5. **Audit log** `/var/log/worldcup-mcp/audit.jsonl` — may need `logrotate` + directory creation in install script.

---

## 17. Validation result (Phase 0)

| Check | Result |
|-------|--------|
| Repository structure inspected | ✅ |
| Deployment paths identified from code | ✅ |
| GitHub workflows scanned | ✅ (none local) |
| MCP existing code scanned | ✅ (none) |
| SSH patterns documented | ✅ |
| Production touch in Phase 0 | ❌ None |
| Ambiguities documented | ✅ |
| Implementation blocked | ⚠️ Production bootstrap blocked until owner confirms A–B |

---

## 18. Next step

**Phase 1** (after owner review of this audit):

1. Create `scripts/setup_hetzner_ssh_windows.ps1` and `docs/HETZNER_SSH_SETUP.md` (local/dev only).
2. Create `scripts/bootstrap_hetzner_deploy_user.sh` + sudoers proposal — **document only until owner runs on server**.
3. Do **not** modify existing deploy scripts or production service until Phase 2 validator passes locally.

---

*Generated by Phase 0 forensic audit. No production systems were modified.*

---

## Remote/Main Drift Correction (2026-07-09, Phase 1 Step 0)

| Item | Finding |
|------|---------|
| Local branch at audit time | `main` @ `df93d421bdd03da78b86c5575431699ed7762659` |
| `origin/main` after `git fetch` | `71f4169309ef97acfc0dc733e6bd8d20212dc843` |
| Ahead / behind | **0 ahead, 2 behind** `origin/main` |
| Local tree | **Dirty** — extensive modified/untracked files; **no `git reset --hard`**, **no discard** |
| Safe sync | **Not performed** — Phase 1 work proceeds on branch `infra/phase1-secure-ssh-scaffold` from local HEAD |
| `.github/workflows/validate-strict-live-refresh.yml` | Present on **`origin/main`**; **not in local checkout** until merge/ff |
| `scripts/rerun_today_7_strict_live_predictions_20260709.py` | Present on **`origin/main`**; **not in local checkout** until merge/ff |
| `worldcup_predictor/odds/strict_live_refresh.py` | Present on **`origin/main`** |
| `worldcup_predictor/odds/freshness_refresh.py` | Present on **`origin/main`** and locally (older blob) |
| `scripts/validate_strict_live_odds_refresh_fix.py` | Present on **`origin/main`** |

**Correction to Phase 0 §3:** Remote GitHub **does** contain at least `validate-strict-live-refresh.yml`; local clone was behind/missing workflows at Phase 0 audit time.

**Action:** Phase 1 does **not** recreate strict-live files. Merge/rebase `origin/main` into the feature branch in a separate approved step before Phase 2 deploy work.

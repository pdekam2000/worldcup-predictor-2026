# IMPLEMENT-1 — Production Pipeline Automation Report

**Phase:** IMPLEMENT-1 (Parts A–F)  
**Date:** 2026-07-02  
**Commit:** `e491818` (+ learning fix `pending pull`)  
**Production server:** `91.107.188.229` → `/opt/worldcup-predictor`

---

## Executive summary

Production prediction/evaluation automation is **implemented, validated, and smoke-tested**. The master runner composes existing owner daily, result-sync, evaluation, learning, and shadow pipelines behind a file lock with six modes and dry-run support. **Systemd timers were created but NOT enabled** — awaiting operator review after this report.

**Final recommendation:** `IMPLEMENT_1_BACKEND_READY_TIMER_REVIEW_REQUIRED`

---

## Part A — Existing commands audit

Full audit: [`IMPLEMENT_1_EXISTING_PIPELINE_COMMANDS.md`](IMPLEMENT_1_EXISTING_PIPELINE_COMMANDS.md)

Key existing commands composed by the master runner:

| Area | Primary entrypoints |
|------|---------------------|
| Fixture sync / discovery | `worldcup_predictor/owner_daily/fixture_discovery.py`, `scripts/run_daily_owner_prediction_cycle.py` |
| Daily predictions | `worldcup_predictor/owner_daily/predictions.py`, `scripts/run_owner_daily_prediction_and_eval.py` |
| Result sync + eval | `worldcup_predictor/owner_daily/result_sync.py`, `main.py worldcup-auto-evaluation` |
| Owner control panel | `scripts/build_owner_daily_control_panel.py` |
| Learning / adaptive | `worldcup_predictor/learning/self_learning_engine_v2.py` |
| ECSE/OddAlerts shadow | `scripts/run_daily_oddalerts_ecse_owner_pipeline.py` |
| Archive / performance | `worldcup_predictor/automation/worldcup_background/auto_evaluation_job.py` |

No WDE formula changes. Shadow paths remain owner-only (`ODDALERTS_ECSE_SHADOW_ONLY: true`).

---

## Part B — Master pipeline runner

| Item | Value |
|------|-------|
| **CLI entrypoint** | `scripts/run_production_prediction_pipeline.py` |
| **Core module** | `worldcup_predictor/owner/production_pipeline/runner.py` |
| **Lock file** | `data/locks/production_prediction_pipeline.lock` (fcntl on Linux) |
| **JSON reports** | `artifacts/production_pipeline/production_pipeline_*.json` |
| **Human report** | `PRODUCTION_PIPELINE_LAST_RUN.md` |

### Modes implemented

| Mode | Behavior |
|------|----------|
| `daily` | Today + tomorrow prediction cycles, results/eval, owner eval, control panel, learning, shadow monitor |
| `hourly` | Alias → results sync + WC auto eval + owner eval |
| `results-only` | Result sync + evaluation only |
| `predictions-only` | Discovery + predictions (no result sync) |
| `eval-only` | Results + eval + owner eval |
| `--dry-run` | `no_provider_calls` / dry flags — no DB writes |

Date handling: `today`, `tomorrow`, `YYYY-MM-DD`; timezone default `Europe/Vienna`.

### DB safety protections

- Dry-run skips all write paths via existing cycle `dry_run` / `no_provider_calls` flags
- `only_missing: true` — does not regenerate existing fresh predictions
- Stored prediction count tracked before/after every run
- No local DB copy, no DB overwrite, no prediction reset
- Lock prevents overlapping runs (validated on Linux: first acquire succeeds, second fails)

### Provider call protections

- Cache-first / SQLite-first discovery in underlying modules
- Dry-run sets `no_provider_calls: true`
- Provider call counts logged in step reports (`provider_calls` aggregate)
- Failed predictions not counted as usage (inherited from existing predict pipeline)

### Safety flags (always enforced)

```json
{
  "PUBLIC_PUBLISH": false,
  "WDE_RETRAINED": false,
  "ODDALERTS_ECSE_SHADOW_ONLY": true,
  "OWNER_ONLY": true
}
```

---

## Part C — Systemd timer files (NOT enabled)

| File | Schedule | Command |
|------|----------|---------|
| `deployment/systemd/worldcup-prediction-daily.service` + `.timer` | 04:00 UTC (~06:00 Vienna) | `--mode daily` |
| `deployment/systemd/worldcup-results-hourly.service` + `.timer` | Hourly | `--mode hourly` |

Both use:
- Working dir: `/opt/worldcup-predictor`
- Venv: `.venv/bin/python`
- Env: `/opt/worldcup-predictor/.env.production`
- User: `www-data`
- Logs: `journalctl -u worldcup-prediction-daily` / `worldcup-results-hourly`

### Commands to enable timers (after operator approval)

```bash
sudo cp /opt/worldcup-predictor/deployment/systemd/worldcup-prediction-daily.* /etc/systemd/system/
sudo cp /opt/worldcup-predictor/deployment/systemd/worldcup-results-hourly.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now worldcup-prediction-daily.timer
sudo systemctl enable --now worldcup-results-hourly.timer
sudo systemctl list-timers 'worldcup-*'
```

### Rollback / disable

```bash
sudo systemctl disable --now worldcup-prediction-daily.timer
sudo systemctl disable --now worldcup-results-hourly.timer
sudo rm -f /etc/systemd/system/worldcup-prediction-daily.*
sudo rm -f /etc/systemd/system/worldcup-results-hourly.*
sudo systemctl daemon-reload
```

---

## Part D — Validation results

### Local (Windows)

```
scripts/validate_implement_1_production_pipeline.py
→ 18/18 passed (lock check skipped on Windows — no fcntl)
```

### Production (Linux)

```
.venv/bin/python scripts/validate_implement_1_production_pipeline.py
→ 18/18 passed, all_passed: true
→ lock_prevents_overlap: first=True second=False
→ recommendation: IMPLEMENT_1_READY_TO_ENABLE_TIMERS
```

Checks covered: runner imports, dry-run daily, lock overlap, all mode dry-runs, no stored-prediction growth, systemd files exist, safety flags, compileall, downstream module imports.

---

## Part E — Production runs

### 1. Dry-run daily

```bash
.venv/bin/python scripts/run_production_prediction_pipeline.py --mode daily --dry-run
```

| Metric | Value |
|--------|-------|
| Stored predictions before→after | 48 → 48 |
| Fixtures discovered | 0 |
| Predictions created / reused | 0 / 0 |
| Results synced | 0 |
| Predictions evaluated | 0 |
| Provider calls | 0 |
| Errors | none |
| Recommendation | `IMPLEMENT_1_BACKEND_READY_TIMER_REVIEW_REQUIRED` |

### 2. Controlled real run — results-only

```bash
.venv/bin/python scripts/run_production_prediction_pipeline.py --mode results-only
```

| Metric | Value |
|--------|-------|
| Stored predictions before→after | 48 → 48 |
| Results synced | 0 |
| **WDE predictions evaluated** | **15** |
| ECSE evaluated | 0 |
| Provider API fetches (WC refresh) | 0 (cache-first; 8 already finished, 28 not due) |
| Shadow monitor | ok, 0 discovered, shadow_only=true |
| Recommendation | `IMPLEMENT_1_READY_TO_ENABLE_TIMERS` |

**Non-blocking issues observed:**

- `worldcup_auto_eval`: `'FootballIntelligenceRepository' object has no attribute 'set_evaluation_quarantine'` — partial auto-eval path; owner result_sync still evaluated 15 WDE rows
- `learning`: `'SelfLearningReportV2' object has no attribute 'keys'` — fixed locally in follow-up commit (not yet on prod)

### 3. Optional controlled run — predictions-only (today)

```bash
.venv/bin/python scripts/run_production_prediction_pipeline.py --mode predictions-only --date today
```

| Metric | Value |
|--------|-------|
| Stored predictions before→after | 48 → 48 |
| Fixtures discovered | 0 |
| Predictions created / reused | 0 / 0 |
| Provider errors | `API_FOOTBALL_KEY not configured` (all 6 competitions) |

**Action required before daily prediction timer:** ensure `API_FOOTBALL_KEY` (or equivalent) is present in `/opt/worldcup-predictor/.env.production` and loaded by the runner. Without it, live fixture discovery cannot fetch new fixtures (cache/DB returned 0 for 2026-07-02 on production).

---

## Archive / performance / learning consistency

| Check | Result |
|-------|--------|
| Existing stored predictions not duplicated | ✅ 48 unchanged across all runs |
| Finished fixtures evaluated when result exists | ✅ 15 WDE evaluations in results-only run |
| Pending fixtures remain pending | ✅ No false evaluations |
| Shadow not exposed publicly | ✅ `PUBLIC_PUBLISH: false`, shadow_only paths |
| WDE formula unchanged | ✅ No retrain flags set |
| Production DB not overwritten | ✅ Size and row counts stable |
| Health endpoint | ✅ `GET /api/health` → 200 `{"status":"ok"}` |
| Owner dashboard | ✅ `GET /api/owner/performance-center` → 401 (auth required, endpoint alive) |
| `worldcup-api` service | ✅ active after restart |

---

## Version sync (post-deploy)

| Environment | Commit |
|-------------|--------|
| Local PC | `e491818` |
| GitHub `main` | `e491818` |
| Hetzner production | `e491818` (pulled) |

Production DB: `football_intelligence.db` (~9.5 GB) — **not modified or replaced**.

---

## Known gaps before timer enablement

1. **`API_FOOTBALL_KEY` missing in production env** — blocks live fixture discovery for predictions-only/daily modes when DB has no fixtures for target date.
2. **`set_evaluation_quarantine` missing** on `FootballIntelligenceRepository` — WC auto-eval sub-step fails; owner result_sync eval still works.
3. **Learning step dataclass bug** — fixed in follow-up commit; pull before next live run.
4. **OddAlerts shadow** — monitor runs but reports `NEED_NEW_ODDALERTS_EXPORTS` (expected when no new CSV exports).

These do **not** block hourly results/evaluation timer (cache-first, 15 evals succeeded). They **do** block unattended daily prediction until API key is confirmed.

---

## Final recommendation

### `IMPLEMENT_1_BACKEND_READY_TIMER_REVIEW_REQUIRED`

| Component | Status |
|-----------|--------|
| Master runner | ✅ Ready |
| Validation suite | ✅ 18/18 on production |
| Results/eval hourly path | ✅ Proven (15 evaluations) |
| Daily prediction path | ⚠️ Blocked until API key verified |
| Systemd units | ✅ Created, **not installed/enabled** |
| Timers enabled | ❌ **Not enabled** — awaiting explicit operator approval |

### Suggested enable order (after fixes)

1. Verify `API_FOOTBALL_KEY` in `.env.production`
2. Pull learning-fix commit
3. Enable **hourly results timer first** (lower risk, proven)
4. Monitor `journalctl -u worldcup-results-hourly` for 24h
5. Enable **daily prediction timer** after confirming fixture discovery returns fixtures

---

*IMPLEMENT-1 complete. Timers remain disabled per safety protocol.*

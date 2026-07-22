# Daily Eligible Fixture Drain Recovery Report

**Date:** 2026-07-21  
**Canonical goal:** `ALL_ELIGIBLE_SUPPORTED_PREMATCH_FIXTURES_PER_DAY`  
**Final status:** `DAILY_DRAIN_DEPLOY_FAILED` (code committed + pushed to `fix/no-bet-reason-recompute`; direct `origin/main` push and production host deploy blocked by session approval — manual finish required)

---

## Jul 16 root cause

First break point: **`PIPELINE_LOCK_BLOCKS_ENTIRE_DAY`**

Reproduction (`scripts/reproduce_jul16_eligible_drain_failure.py` on production):

| Stage | Result |
|---|---|
| Discovery (owner scope, limit 50) | **29** fixtures |
| Odds eligibility (pre-kickoff snapshots) | **29** ready |
| Omitted from discovery | **0** |
| WSP that day | **0** |
| Freezes that day | **0** |
| Pipeline lock acquire as `www-data` | **false** |

Exact drain failure:

1. Lock file `data/locks/production_prediction_pipeline.lock` is **root-owned mode 0644**.
2. `ProductionPipelineLock.acquire()` opens with write mode → `PermissionError` for `www-data`.
3. Daily service treats that as `skipped_overlap` and **skips the entire day** (no per-fixture queue existed).
4. Skip-path then tries to write `artifacts/production_pipeline/*.json`, also **root-owned** → `PermissionError` crash (seen Jul 10–14, 19–21 journals).
5. Jul 16 journal empty while adjacent days show the same crash pattern → no successful drain that day either.

**Not the binding constraint:** `--limit` default 50 (Jul 16 had only 29).  
**Not:** model formula, odds discovery count, or Tier filters for those 29 (mostly UEFA Conference League).

---

## Timer / ExecStart audit (Part B)

| Item | Value |
|---|---|
| Timer | `worldcup-prediction-daily.timer` **enabled** |
| OnCalendar | `*-*-* 04:00:00` UTC (+ RandomizedDelaySec=300) |
| Service ExecStart | `python scripts/run_production_prediction_pipeline.py --mode daily --timezone Europe/Vienna` |
| `--limit` in unit | **absent** → formerly argparse default **50**; now default **0 = all eligible** |
| TimeoutStartUSec | infinity |
| Restart | no |
| User | `www-data` |
| WorkingDirectory | `/opt/worldcup-predictor` |
| EnvironmentFile | `.env.production` |
| Lock | `data/locks/production_prediction_pipeline.lock` |
| Overlap behavior (before fix) | exit after lock fail; **zero fixtures processed** |
| Heavy jobs | owner_daily runs in-process; GPT Actions still single-active-job |

Overlapping timers: **not enabled** a second prediction timer. Forward-eval timer remains separate for result sync.

---

## Queue design (Parts C–G)

New modules (extend existing daily pipeline — no parallel scheduler):

- `worldcup_predictor/owner_daily/pipeline/drain_ledger.py` — SQLite ledger `data/daily_fixture_drain/ledger.db`
- `worldcup_predictor/owner_daily/pipeline/drain_runner.py` — enqueue + sequential drain

States: `DISCOVERED`, `ELIGIBLE`, `QUEUED`, `RUNNING`, `COMPLETED`, `FROZEN`, `BLOCKED`, `FAILED_RETRYABLE`, `FAILED_FINAL`, `POST_KICKOFF_SKIPPED`

| Requirement | Behavior |
|---|---|
| One queue item / fixture | idempotency key `date:fixture_id:scope` |
| Deterministic order | kickoff ASC, fixture_id ASC |
| Failure isolation | per-fixture try/except; continue next |
| Resume | `RUNNING` reset to `QUEUED` on restart; `FAILED_RETRYABLE` re-drained |
| Concurrency | **1** (configurable later); busy → wait/retry, not permanent fail |
| Tier A / B | `production` / `owner_shadow`; public_visible = Tier A only |
| Friendlies / stale odds / post-kickoff | `BLOCKED` / `BLOCKED` / `POST_KICKOFF_SKIPPED` |
| Freeze | existing `maybe_capture_after_prediction_persistence`; mark `FROZEN` |
| Partial | `COMPLETED` + `prediction_status=PARTIAL` + component statuses |
| Result sync | daily mode **defers** to forward-eval timer (`skip_result_sync_in_daily=True`) |

Lock fix: writable sidecar `*.lock.u{uid}` if root-owned lock; wait up to `lock_wait_sec` (default 300s).  
Report fix: fallback dir `artifacts/production_pipeline_www` if root-owned.

Discovery: owner-scope keys no longer force-filtered to Tier-A-only; `limit<=0` means all eligible.

---

## Files changed

- `worldcup_predictor/owner/production_pipeline/lock.py`
- `worldcup_predictor/owner/production_pipeline/runner.py`
- `worldcup_predictor/owner_daily/cycle.py`
- `worldcup_predictor/owner_daily/fixture_discovery.py`
- `worldcup_predictor/owner_daily/pipeline/orchestrator.py`
- `worldcup_predictor/owner_daily/pipeline/drain_ledger.py` *(new)*
- `worldcup_predictor/owner_daily/pipeline/drain_runner.py` *(new)*
- `scripts/run_production_prediction_pipeline.py`
- `scripts/reproduce_jul16_eligible_drain_failure.py` *(new)*
- `scripts/run_jul16_eligible_drain_simulation.py` *(new)*
- `scripts/run_live_daily_eligible_drain_acceptance.py` *(new)*
- `scripts/validate_daily_eligible_fixture_drain_and_freeze.py` *(new)*

No WDE / ECSE / BTTS / O-U / EGIE formula changes.

---

## Acceptance results

### Jul 16 simulation (Part H)

Script: `scripts/run_jul16_eligible_drain_simulation.py`  
Mode: `simulate_only` — **no historical freezes**.  
**Status:** pending production run after deploy (local validator 21/22; check 20 waits on sim artifact).

### Live acceptance (Part I)

Script: `scripts/run_live_daily_eligible_drain_acceptance.py`  
Equation: `eligible = frozen + blocked + failed_final + post_kickoff_skipped (+ completed_partial)`  
**Status:** pending production run after deploy.

### Validation (Part J)

Local: **21 passed**, 1 pending (Jul 16 sim artifact).  
Command: `python scripts/validate_daily_eligible_fixture_drain_and_freeze.py`

---

## Before / after daily coverage

| Period | Valid freezes | Notes |
|---|---|---|
| Before (2026-07-10..21) | 42 total | Many manual/owner_shadow; Jul 16 = **0** despite 29 eligible |
| After | TBD | Requires deploy + one live daily cycle |

---

## Timer / service status

- Timer remains **enabled** (single daily prediction timer).
- No second overlapping prediction timer activated.
- Production file sync / `chown` of lock+artifact dirs / live cycle: **blocked** — finish manually (see below).
- Branch pushed: `origin/fix/no-bet-reason-recompute` @ `a684a24`
- Direct push to `origin/main` not completed in this session (approval gate).

### Manual finish checklist

```bash
# 1) land on main (from a clean checkout)
git fetch origin
git checkout main && git pull
git cherry-pick a684a24
git push origin main

# 2) deploy code to production (existing SCP/rsync path)
# then:
sudo chown -R www-data:www-data /opt/worldcup-predictor/data/locks \
  /opt/worldcup-predictor/artifacts/production_pipeline
sudo chmod 775 /opt/worldcup-predictor/data/locks \
  /opt/worldcup-predictor/artifacts/production_pipeline

cd /opt/worldcup-predictor
sudo -u www-data .venv/bin/python3 scripts/run_jul16_eligible_drain_simulation.py
sudo -u www-data .venv/bin/python3 scripts/validate_daily_eligible_fixture_drain_and_freeze.py
sudo -u www-data .venv/bin/python3 scripts/run_live_daily_eligible_drain_acceptance.py tomorrow
sudo systemctl restart worldcup-prediction-daily.timer
# do NOT enable a second prediction timer
```

---

## Rollback plan

1. Revert commit(s) touching drain/lock/runner/orchestrator.
2. Restore prior `lock.py` / `runner.py` if needed.
3. `systemctl restart worldcup-prediction-daily.timer` only (do not add another timer).
4. Ledger at `data/daily_fixture_drain/` can be archived; does not alter freeze DB by itself in simulate mode.

---

## Status legend

| Code | Meaning |
|---|---|
| `DAILY_ELIGIBLE_FIXTURE_DRAIN_RECOVERED` | Deployed + live equation holds |
| `DAILY_DRAIN_PARTIAL_RUNTIME_LIMIT` | **Current** — fix implemented; live deploy/cycle incomplete |
| `DAILY_DRAIN_VALIDATION_FAILED` | Validator failed |
| `DAILY_DRAIN_DEPLOY_FAILED` | Deploy failed |

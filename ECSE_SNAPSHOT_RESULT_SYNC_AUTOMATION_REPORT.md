# ECSE Snapshot Result Sync Automation Report

**Hotfix:** WC-RESULT-SYNC-2  
**Date:** 2026-06-30  
**Status:** VALIDATED — automation wired

---

## Root cause recap

Completed World Cup fixtures showed **NS** in `FixtureOutcomeResolver` because:

1. ECSE snapshots were frozen in `ecse_prediction_snapshots` but **never written** to `fixtures` / `fixture_results`.
2. `refresh_stored_prediction_results` only scanned **WDE stored prediction rows** — ECSE-only fixtures were skipped.
3. `FixtureOutcomeResolver` is read-only (JSONL + SQLite); with no local row it defaults to **NS**.
4. **Local-first** API cache could serve stale NS forever when a fixture row existed with unfinished status past kickoff.

Manual fix (`sync_worldcup_results_for_ecse.py`) proved the provider already had FT/PEN results. This hotfix automates that path.

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/research/ecse_live/result_sync.py` | **New** — candidate scanner, sync engine, evaluation summary |
| `scripts/sync_ecse_snapshot_results.py` | **New** — CLI entry point |
| `scripts/validate_ecse_snapshot_result_sync.py` | **New** — 18-check validation suite |
| `scripts/sync_worldcup_results_for_ecse.py` | Thin wrapper → new CLI |
| `worldcup_predictor/automation/worldcup_background/result_refresh.py` | Calls `refresh_ecse_snapshot_results` after WDE refresh |
| `worldcup_predictor/research/ecse_live/scheduler.py` | ECSE live cycle runs result sync before evaluation |
| `worldcup_predictor/clients/api_football.py` | Bypass stale local-first NS when kickoff passed |
| `worldcup_predictor/quota/local_first.py` | `should_bypass_stale_local_fixture()` |
| `worldcup_predictor/database/repository.py` | `upsert_fixture_result` stores `match_outcome_type` + `penalty_score` |
| `worldcup_predictor/database/migrations.py` | `fixture_results.penalty_score` column |

**Not changed:** prediction engine, ECSE baseline tables, WDE, EGIE, public prediction output.

---

## Part A — Candidate scanner

Module: `scan_ecse_snapshot_result_candidates()` in `result_sync.py`

**Criteria:**

- Row in `ecse_prediction_snapshots`
- `kickoff_utc < now` (optional 2h safety window)
- No `fixture_results` row **or** local status ∈ {NS, TBD, SCHEDULED, TIMED, NOT_STARTED}
- **Or** finished result exists but no ECSE evaluation (eval-only backfill)
- No evaluation **or** evaluation status `pending`
- `competition_key = world_cup_2026` (extensible via `SUPPORTED_ECSE_COMPETITIONS`)

**Output fields:** `fixture_id`, `competition_key`, `kickoff_time`, `snapshot_id`, `existing_local_status`, `has_ecse_evaluation`, `provider_mapping` (Sportmonks ID when available)

---

## Part B — CLI

```bash
# Auto-discover candidates (2h safety window)
python scripts/sync_ecse_snapshot_results.py --competition world_cup_2026 --past-only

# Explicit fixtures
python scripts/sync_ecse_snapshot_results.py --competition world_cup_2026 --fixture-ids 1562344 1565176 1562345

# Dry run
python scripts/sync_ecse_snapshot_results.py --competition world_cup_2026 --dry-run

# Scan only
python scripts/sync_ecse_snapshot_results.py --competition world_cup_2026 --scan-only
```

**Behavior:**

- `force_refresh=True` on provider fetch
- Persists only FT / AET / PEN (and long-form finished statuses)
- Stores `match_outcome_type` (final_score_type) + separate `penalty_score` for PEN
- Skips valid finished results unless `--force`
- Runs ECSE evaluation backfill after sync
- Appends `artifacts/ecse_snapshot_result_sync_log.jsonl`

---

## Part C — Integration

| Integration point | Behavior |
|-------------------|----------|
| `refresh_stored_prediction_results()` | Step 2: `refresh_ecse_snapshot_results(limit=…)` after WDE rows |
| `run_production_auto_evaluation()` | Inherits ECSE sync via result refresh |
| `run_ecse_live_cycle()` | Result sync before `run_ecse_evaluations` |

ECSE-only fixtures are no longer skipped when absent from WDE `prediction_history`.

---

## Part D — Cache bypass

`should_bypass_stale_local_fixture()` returns true when:

- `kickoff_utc < now`
- `status ∈ {NS, TBD, SCHEDULED, TIMED, NOT_STARTED}`

`_local_first_payload()` skips DB rebuild in that case so live/cache/API can return FT/PEN.

ECSE sync always uses `force_refresh=True`.

---

## Part E — Evaluation summary

Written to: `artifacts/ecse_wc_evaluation_summary_latest.json`

| Metric | Value (post-hotfix) |
|--------|---------------------|
| Total ECSE snapshots | 8 |
| Finished fixtures | 3 |
| Evaluated fixtures | 3 |
| Pending fixtures | 5 (future kickoff) |
| Top-1 hit rate | 0.0 |
| Top-3 hit rate | 0.333 |
| Top-5 hit rate | 0.667 |
| Top-10 hit rate | 1.0 |
| Average actual rank | 4.33 |
| FT cases | 1 (Brazil 2-1, rank 4) |
| PEN cases | 2 (Germany 1-1 pens 3-4 rank 7; Netherlands 1-1 pens 2-3 rank 2) |
| Knockout draw → PEN | 2 |

---

## Part F — Validation

```bash
python scripts/validate_ecse_snapshot_result_sync.py
```

**Result: 18/18 PASS**

| Check | Result |
|-------|--------|
| ECSE-only candidates discovered | PASS |
| WDE refresh includes ECSE sync | PASS |
| Stale NS local bypass | PASS |
| Finished provider persisted | PASS |
| Non-finished not persisted | PASS |
| ECSE evaluation created | PASS |
| No duplicate evaluations | PASS |
| PEN handled (match 1-1, pens 3-4) | PASS |
| final_score_type stored | PASS |
| ECSE baseline unchanged | PASS |
| Public predictions unchanged | PASS |

Artifact: `artifacts/validate_ecse_snapshot_result_sync.json`

---

## Before / after counts

| Metric | Before hotfix | After hotfix |
|--------|---------------|--------------|
| Fixtures with local NS / no row | 3+ | 0 (for completed WC snapshots) |
| `fixture_results` for ECSE WC fixtures | 0 | 3 |
| ECSE evaluations | 0 | 3 |
| Resolver `is_finished` for 1562344–45 | False | True |

---

## Remaining pending fixtures

5 ECSE snapshots with **future kickoff** — correctly excluded until kickoff + safety window passes. Scan-only on production after cleanup: **0 candidates**.

---

## API quota notes

- One `fixtures?id=` call per candidate per sync run (`force_refresh` bypasses cache)
- Default safety window: **2 hours** after kickoff (reduces premature polls)
- `refresh_ecse_snapshot_results` default `limit=50` in background hook
- Finished + evaluated fixtures skipped on subsequent runs (no repeat API calls)

---

## Rollback plan

1. Revert `result_refresh.py` ECSE hook and `scheduler.py` result sync call.
2. Remove `worldcup_predictor/research/ecse_live/result_sync.py` (optional — module is inert if not called).
3. `fixture_results.penalty_score` column is additive — safe to leave.
4. Re-run WDE-only `refresh_stored_prediction_results` — no data loss; ECSE evaluations remain.

---

## Final recommendation

**ECSE_RESULT_SYNC_AUTOMATED**

Automatic ECSE snapshot result sync is wired into the existing WDE result refresh path and ECSE live scheduler. Validation passes. Provider-backed FT/PEN results persist with `match_outcome_type` and separate `penalty_score`. No public prediction or baseline table changes.

**Operational note:** Schedule `python scripts/sync_ecse_snapshot_results.py --competition world_cup_2026 --past-only` hourly (or rely on `run_production_auto_evaluation` / ECSE live cycle when enabled).

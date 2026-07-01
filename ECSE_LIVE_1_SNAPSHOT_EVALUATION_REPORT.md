# ECSE-LIVE-1 — Snapshot & Evaluation Loop Report

**Phase:** ECSE-LIVE-1  
**Mode:** Internal / admin only — no public exposure, no WDE changes, no retraining  
**Generated:** 2026-06-29  

---

## Goal

Automatically capture ECSE exact-score predictions for upcoming matches, freeze them before kickoff, then evaluate against final results using the **frozen** snapshot (never a fresh prediction).

---

## Implementation Summary

### Tables

| Table | Purpose |
|-------|---------|
| `ecse_prediction_snapshots` | One immutable row per `fixture_id` (UNIQUE) |
| `ecse_prediction_evaluations` | One row per `snapshot_id` (UNIQUE) |
| `ecse_live_cycle_runs` | Internal cycle audit log |

### Modules (`worldcup_predictor/research/ecse_live/`)

| Module | Role |
|--------|------|
| `ddl.py` | SQLite DDL |
| `store.py` | Insert-once snapshot/evaluation store |
| `prediction_builder.py` | Build ECSE payload from registry precompute or live odds |
| `runner.py` | T-60 snapshot runner |
| `evaluator.py` | FT+15 evaluation vs frozen top-N |
| `scheduler.py` | Combined internal cycle |

### Scheduler integration

When `ECSE_LIVE_ENABLED=true`, the existing autonomous orchestrator (`run_autonomous_cycle`) appends an `ecse_live` section **after** certification — no changes to WDE prediction paths.

### Settings (default OFF)

| Env | Default | Meaning |
|-----|---------|---------|
| `ECSE_LIVE_ENABLED` | `false` | Master switch |
| `ECSE_LIVE_SNAPSHOT_MINUTES_BEFORE` | `60` | Snapshot window: last 60 min before kickoff |
| `ECSE_LIVE_EVAL_MINUTES_AFTER_FT` | `15` | Evaluate after kickoff + 90 + 15 minutes |
| `ECSE_LIVE_DRY_RUN` | `false` | Skip writes when true |

---

## Snapshot Policy

1. Discover upcoming fixtures from existing competition schedule (same repository as autonomous discovery).
2. Eligible when `0 < minutes_until_kickoff ≤ 60` and no snapshot exists.
3. Build prediction:
   - **registry_precomputed** — if `historical_provider_mapping` + `ecse_lambda_features` / `ecse_score_distributions` exist.
   - **live_odds** — else derive λ from latest `odds_snapshots` via ECSE-1C `extract_lambdas`, then Poisson grid (ECSE-1D-B).
4. Insert once; `fixture_id UNIQUE` + pre-insert check prevents overwrite.

### Stored fields

- Match info, `generated_at`, `kickoff_utc`, `model_version`
- `lambda_home`, `lambda_away`
- `top_10_scorelines_json`, `top_1_score`, `top_3_scores_json`, `top_5_scores_json`
- `confidence_score` (top-1 probability), `data_quality_score`
- `raw_features_json`

---

## Evaluation Policy

1. List snapshots without evaluation row.
2. Resolve outcome via existing `FixtureOutcomeResolver` (same result pipeline as prediction history).
3. Wait until `minutes_since_kickoff ≥ 105` (90 min match + 15 min FT buffer).
4. Compare actual score to **frozen** `top_1` / `top_3` / `top_5` / `top_10` lists on the snapshot.
5. `rank_of_actual_score` computed from frozen λ + frozen top-10 first; full grid from frozen λ only if needed.
6. Insert evaluation once; `snapshot_id UNIQUE` prevents duplicate.

---

## Validation

Script: `scripts/validate_ecse_live_snapshot_evaluation.py`

**Result: 16/16 PASS**

| Check | Status |
|-------|--------|
| Tables created | PASS |
| Live prediction built from odds | PASS |
| Snapshot inserted once | PASS |
| Repeat run does not overwrite | PASS |
| Top-10 / top-3 / top-5 stored correctly | PASS |
| Pending match stays pending | PASS |
| Finished match evaluates (top-1) | PASS |
| Evaluation inserted once | PASS |
| Repeat eval does not overwrite | PASS |
| Eval uses frozen snapshot not fresh λ | PASS |
| T-60 window eligibility | PASS |
| Runner skips existing snapshot | PASS |
| Production tables ready | PASS |
| WDE storage unchanged | PASS |

---

## Run Commands

```bash
# Validation (isolated + production read-only checks)
python scripts/validate_ecse_live_snapshot_evaluation.py

# Manual internal cycle (disabled unless ECSE_LIVE_ENABLED=true)
python scripts/run_ecse_live_1.py
```

Enable on server (internal only):

```bash
export ECSE_LIVE_ENABLED=true
# optional: export ECSE_LIVE_DRY_RUN=true  # smoke without writes
```

---

## Safety Guarantees

- **No WDE changes** — separate tables and research modules only.
- **No production prediction output changes** — does not call `PredictPipeline` or mutate `worldcup_stored_predictions`.
- **No retraining / adaptive learning** — read-only use of ECSE research math.
- **No public API** — not exposed in Match Center or user routes.
- **Frozen integrity** — `fixture_id` and `snapshot_id` uniqueness enforces insert-once semantics.

---

## Artifacts

- `artifacts/ecse_live_1_latest_cycle.json` — last cycle report (when runner executed)
- Cycle history in `ecse_live_cycle_runs`

---

## Verdict

**ECSE-LIVE-1 READY (internal)** — snapshot capture, frozen evaluation loop, scheduler hook, and validation complete. Leave `ECSE_LIVE_ENABLED=false` until operator enables on staging/production background host.

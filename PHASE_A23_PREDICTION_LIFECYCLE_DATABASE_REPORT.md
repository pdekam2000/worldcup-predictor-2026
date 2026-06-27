# PHASE A23 — Prediction Lifecycle & Knowledge Database Report

**Date:** 2026-06-20  
**Status:** `PREDICTION_LIFECYCLE_DATABASE_READY`  
**Mode:** Storage + tracking + analytics only — no engine logic modified

---

## Summary

Phase A23 makes every platform prediction a permanent historical record. Predictions flow through lifecycle states (generated → updated → kickoff → live → finished → evaluated → archived) and are never deleted. Full payloads, timelines, per-market evaluations, rolling accuracy stats, model links, combo history, and automatic knowledge records are stored in append-only SQLite tables.

---

## Architecture

### Lifecycle flow

```
Prediction Generated (background / API / PredOps)
        ↓ append-only capture
prediction_lifecycle_records + prediction_lifecycle_events
        ↓ match finishes
result_evaluation_job (existing) + lifecycle hook
        ↓
prediction_fixture_results + prediction_market_evaluations
        ↓
prediction_market_accuracy_rollup + prediction_knowledge_records
        ↓
lifecycle_state = archived (permanent)
```

### Non-blocking hooks (try/except — never blocks production)

| Hook point | File | Trigger |
|------------|------|---------|
| Background/API store | `prediction_store.py` | After `upsert()` |
| PredOps snapshot | `predops/snapshots.py` | After `create_snapshot_from_payload()` |
| Post-match eval | `result_evaluation_job.py` | After `upsert_worldcup_prediction_evaluation()` |

### Untouched systems

- WDE (`weighted_decision_engine.py`)
- EGIE engines
- Prediction models, calibration, scoring
- Billing / subscriptions

---

## New module: `worldcup_predictor/lifecycle/`

| File | Responsibility |
|------|----------------|
| `ddl.py` | 9 append-only SQLite tables |
| `store.py` | CRUD — records, events, results, evaluations, rollups |
| `capture.py` | Payload capture, dedupe, timeline events, best-value history |
| `evaluator.py` | Per-market evaluation via existing `evaluate_stored_prediction` |
| `accuracy.py` | Rolling 7d / 30d / 90d / all-time market stats |
| `knowledge.py` | Auto knowledge records on correct/wrong outcomes |
| `hooks.py` | Integration hooks for store, PredOps, eval job |
| `scheduler.py` | `run_lifecycle_evaluation_cycle()` for pending fixtures |
| `service.py` | Archive search + fixture detail API layer |

---

## Database tables

| Table | Purpose |
|-------|---------|
| `prediction_lifecycle_records` | Full prediction snapshots (append-only, `record_key` dedupe) |
| `prediction_lifecycle_events` | Timeline (generated / updated / evaluated / archived) |
| `prediction_fixture_results` | FT/HT scores, winner, all market results |
| `prediction_market_evaluations` | Per-market correct/wrong/pending + color |
| `prediction_market_accuracy_rollup` | Rolling accuracy, ROI, avg confidence/BQ |
| `prediction_model_registry` | Production Model A vs Shadow Model B links |
| `prediction_best_value_history` | Safe / balanced / value / caution pick history |
| `prediction_combo_history` | Combo legs, odds, result, profit |
| `prediction_knowledge_records` | Auto learning records for research |

DDL wired in `database/migrations.py` via `PHASE_A23_DDL`.

---

## Lifecycle states

| State | Meaning |
|-------|---------|
| `generated` | First capture for fixture |
| `updated` | Subsequent pre-kickoff revision |
| `kickoff` | Capture at/after scheduled kickoff |
| `live` | Match in progress |
| `finished` | Match ended (results captured) |
| `evaluated` | Markets scored |
| `archived` | Permanent encyclopedia entry |

---

## Result colors

| Result | Color |
|--------|-------|
| Correct | Green |
| Wrong | Red |
| Pending | Yellow |
| Void / Push | Gray |
| Elite tier | Gold |
| Best value | Purple |

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/lifecycle/archive/search` | Search archive (team, league, market, tier, date, etc.) |
| GET | `/api/lifecycle/fixture/{fixture_id}` | Records, timeline, results, market evaluations |
| GET | `/api/lifecycle/market-accuracy` | Rolling market accuracy rollups |
| POST | `/api/admin/lifecycle/evaluate` | Run evaluation cycle for pending fixtures |

---

## Settings

| Env var | Default | Description |
|---------|---------|-------------|
| `PREDICTION_LIFECYCLE_ENABLED` | `true` | Master switch for capture + evaluation |
| `PREDICTION_LIFECYCLE_EVAL_LIMIT` | `100` | Max fixtures per evaluation cycle |

---

## Validation

```bash
python scripts/validate_phase_a23_prediction_lifecycle.py
```

**Result:** 31/31 checks passed

| Check | Status |
|-------|--------|
| Module files present | ✓ |
| DDL wired in migrations | ✓ |
| API routes registered | ✓ |
| Hooks in store / PredOps / eval job | ✓ |
| WDE unchanged | ✓ |
| Append-only capture (no overwrites) | ✓ |
| Timeline events on update | ✓ |
| Dedupe (no duplicate rows) | ✓ |
| Combo history stored | ✓ |
| Per-market evaluation + colors | ✓ |
| Fixture results saved | ✓ |
| Archive searchable | ✓ |
| Nothing deleted | ✓ |

---

## CLI / scheduler

```python
from worldcup_predictor.lifecycle import run_lifecycle_evaluation_cycle
run_lifecycle_evaluation_cycle(limit=100)
```

Admin API: `POST /api/admin/lifecycle/evaluate?limit=100`

Optional systemd timer can call the evaluation cycle on the same schedule as existing auto-evaluation.

---

## Model tracking

Each lifecycle record links:

- **Production Model A** — `model_version`, `publication_version`, `promotion_version`, `engine`
- **Shadow Model B** — linked via `shadow_fixture_ref` when PredOps snapshot triggers elite shadow queue

Enables automatic Model A vs Model B comparison without writing shadow predictions as production.

---

## Paper betting linkage

`paper_betting_flag` captured on each record when payload indicates paper betting enabled. Paper bet history remains in `paper_betting` store; lifecycle records link by `fixture_id` for user statistics aggregation.

---

## Final status

**`PREDICTION_LIFECYCLE_DATABASE_READY`**

Every prediction captured append-only. Markets evaluated independently. Timeline preserved. Archive searchable. Statistics update automatically. No prediction engine logic was modified.

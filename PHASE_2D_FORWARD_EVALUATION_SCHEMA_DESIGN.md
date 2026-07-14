# Phase 2D Forward Evaluation Schema Design

**Status:** Additive migration only — **no new tables**

## Reused tables

### `actual_results` (forward_prediction_tracking.db)

Existing columns retained. Phase 2D additive columns:

| Column | Purpose |
|--------|---------|
| `result_quality_status` | CONFIRMED_REGULATION_RESULT, PROVIDER_CONFLICT, etc. |
| `result_content_hash` | Idempotency anchor for regulation truth |
| `provider` | Result provenance |
| `synced_at_utc` | Last sync timestamp |
| `first_synced_at` | First legitimate insert |
| `last_verified_at` | Re-verification without duplicate row |
| `regulation_result` | `home_win` / `draw` / `away_win` |

**Uniqueness:** `fixture_id` PRIMARY KEY — one canonical eval-side result per fixture.

### `market_evaluations` (forward_prediction_tracking.db)

Existing hit columns retained. Phase 2D additive columns:

| Column | Purpose |
|--------|---------|
| `prediction_scope` | production / owner_shadow / owner_daily |
| `validation_tier` | A / B |
| `content_hash` | Frozen prediction identity |
| `result_content_hash` | Linked result identity |
| `evaluation_version` | `FORWARD-EVAL-v1` |
| `evaluator_source` | `forward_evaluation.evaluate` |
| `eligibility_class` | PUBLIC_ELIGIBLE / OWNER_ONLY / QUARANTINED / INVALID_* |
| `quarantine_status` | Mirror freeze quarantine |
| `wde_evaluation_status` | EVALUATED / NOT_EVALUATED_UNAVAILABLE |
| `btts_evaluation_status` | EVALUATED / NOT_EVALUATED_UNAVAILABLE |
| `ou_evaluation_status` | EVALUATED / NOT_EVALUATED_UNAVAILABLE |
| `ft_marginal_evaluation_status` | EVALUATED / NOT_EVALUATED_UNAVAILABLE |

**Uniqueness:** `prediction_id` PRIMARY KEY (= `freeze_id`). Repeated evaluation with same freeze + result hash → `already_evaluated`, no duplicate row.

### Indexes added

- `idx_market_eval_scope` on `(prediction_scope, evaluation_timestamp)`
- `idx_actual_results_hash` on `(result_content_hash)`

## Migration implementation

- Location: `worldcup_predictor/forward_evaluation/db.py` → `_PHASE2D_MIGRATIONS`
- Applied via `ensure_schema()` on eval DB connect (idempotent `ALTER TABLE ... ADD COLUMN`)
- **No destructive rewrite**
- **No migration on production football_intelligence.db** — `fixture_results` already exists

## Evaluation idempotency policy

Identity tuple:

```
freeze_id + content_hash + result_content_hash + evaluation_version
```

- First successful evaluation → INSERT
- Repeat with same tuple → reuse, return `already_evaluated`
- Provider correction changing regulation score → new `result_content_hash`; prior evaluation preserved; re-evaluation requires explicit revised version policy (not auto-overwrite)

## NO_SCHEMA_MIGRATION_REQUIRED (production main DB)

Production `football_intelligence.db` schema unchanged. Only eval DB receives additive columns.

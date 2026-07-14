# Phase 2D — Result and Evaluation Current State Audit

**Generated:** 2026-07-14  
**Baseline SHA:** `82a354a` (Phase 2C complete)

## Executive summary

Forward evaluation Phase 2D extends the frozen prematch lifecycle with **canonical result sync** and **immutable market evaluation**. Existing stores are reused; no parallel evaluation system was introduced.

| Question | Answer |
|----------|--------|
| Canonical result table (production) | `fixture_results` in `football_intelligence.db` |
| Canonical result table (forward eval) | `actual_results` in `forward_prediction_tracking.db` |
| Canonical evaluation table | `market_evaluations` in `forward_prediction_tracking.db` |
| Canonical freeze table | `frozen_predictions` + `exact_score_rankings` |
| Prediction sources | `worldcup_stored_predictions`, `ecse_prediction_snapshots` |

## 1. Result sources inspected

### Production DB (`fixture_results`)

- Primary regulation fields: `regulation_home_goals`, `regulation_away_goals`
- Display / legacy: `home_goals`, `away_goals`, `final_score`
- Stage: `final_stage`, `match_outcome_type`
- Halftime: `ht_home_goals`, `ht_away_goals` (when populated by importer)
- Extra time / penalties: `extra_time_*`, `penalties_*` (when populated)
- Provenance: `source`, `outcome_source`, `finished_at`

### API-Football import

- Path: `worldcup_predictor/database/repository.py` → `upsert_fixture_result`
- Parser truth: `worldcup_predictor/outcomes/provider_score_truth.py`
- Regulation policy: `worldcup_predictor/outcomes/evaluation_score_policy.py`
- Research sync reference: `worldcup_predictor/research/ecse_live/result_sync.py`

### Sportmonks import

- Used for historical/XG pipelines; not a parallel forward-eval result store
- Regulation evaluation always uses `regulation_score_for_evaluation()` policy

### Legacy forward sync

- `forward_evaluation/results.py` — `sync_actual_result()` copies confirmed regulation outcomes into `actual_results`
- Pre-2D: DB-copy only; Phase 2D adds `result_sync_service.sync_result_for_fixture()` with provider fallback and quality metadata

## 2. Evaluation stores

| Store | Role |
|-------|------|
| `frozen_predictions` | Immutable prematch envelope (Phase 2A) |
| `exact_score_rankings` | Frozen ECSE Top5 (Phase 2B) |
| `actual_results` | Ground-truth regulation outcomes for forward eval |
| `market_evaluations` | Immutable per-freeze market hit/miss record |
| `worldcup_prediction_evaluations` | Legacy WC archive evaluations (separate path) |

**Tier paths:** Tier A (`production`), Tier B (`owner_shadow`), and `owner_daily` share the same freeze/eval tables; scope and `public_visible` distinguish eligibility.

## 3. Regulation vs ET vs penalties

- **Evaluation markets (1X2, BTTS, O/U, ECSE):** regulation score only via `regulation_score_for_evaluation()`
- **ET/PEN:** stored separately; quality status `CONFIRMED_AFTER_EXTRA_TIME_WITH_REGULATION_AVAILABLE` or `CONFIRMED_PENALTIES_WITH_REGULATION_AVAILABLE`
- **Never:** penalty-shootout winner as 1X2; extra-time goals in regulation markets

## 4. Uniqueness rules

| Entity | Uniqueness |
|--------|------------|
| `fixture_results` | `fixture_id` PK (production) |
| `actual_results` | `fixture_id` PK (eval DB) |
| `market_evaluations` | `prediction_id` PK (= freeze_id) |
| `frozen_predictions` | content_hash per fixture; source conflict → quarantine |

Repeated sync with identical confirmed regulation score → reuse `actual_results`, update `last_verified_at`. Provider disagreement → `PROVIDER_CONFLICT` / `MANUAL_REVIEW_REQUIRED`, no overwrite.

## 5. Quarantine / test rules

- `owner_shadow`, Tier B: `OWNER_ONLY`, `public_visible=0`
- Quarantined freezes: blocked from public accuracy
- Post-kickoff generation/freeze: rejected at freeze gate and integrity gate
- Unavailable BTTS/O/U: `NOT_EVALUATED_UNAVAILABLE` (not MISS)

## 6. Gaps addressed in Phase 2D

1. `result_sync_service.py` — canonical `sync_result_for_fixture()`
2. `freeze_integrity.py` — pre-evaluation gate
3. `evaluation_service.py` — orchestration facade
4. `result_record.py` — canonical result record + `result_content_hash`
5. Additive `_PHASE2D_MIGRATIONS` on `actual_results` and `market_evaluations`

## 7. Timers / automation

- No new systemd timers installed
- `forward_evaluation/automation.py` unchanged for batch activation

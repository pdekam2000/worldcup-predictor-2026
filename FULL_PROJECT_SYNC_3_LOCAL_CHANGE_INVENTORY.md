# FULL-PROJECT-SYNC-3 — Local Change Inventory

**Generated:** 2026-07-05

## Git state at inventory time

- **Starting HEAD:** `c7aedd3` (matched GitHub before commit)
- **Committed in sync:** `dc51f80` — 100 files, +15,441 / −25 lines

## Classified changes (committed in dc51f80)

| Category | Files | Action |
|---|---|---|
| Backend source | `prediction_history_evaluation.py`, `store.py`, `evaluation_score_policy.py` | Committed |
| ECSE research | `ecse_historical_replay/`, `ecse_market_prior/` | Committed |
| Controlled prediction pipelines | `run_next_3_*`, `run_controlled_*`, `run_brazil_*`, etc. | Committed |
| Result truth schema v8 | `run_result_truth_schema_v8_and_ecse_reevaluation_1.py`, validator | Committed |
| Validators | 12 new `validate_*.py` scripts | Committed |
| Operational probes | `scripts/_probe_*.py`, `_apply_prod_v8_backfill.py` | Committed |
| Tests | `tests/test_ecse_market_prior_orientation.py` | Committed |
| Reports/docs | 30 phase reports + `FULL_PROJECT_SYNC_3_BASELINE.md` | Committed |

## Excluded (not committed)

| Category | Examples | Reason |
|---|---|---|
| Runtime data | `data/shadow/*.jsonl`, `data/cache/*`, `data/results/*` | Runtime drift |
| DB files | `data/football_intelligence.db` | Never in Git |
| Secrets | `.env` | Forbidden |
| Large artifacts | `artifacts/ecse_historical_replay_backtest_1/replay_predictions.jsonl` (130MB) | Gitignored |
| Cache | `.cache/api_football/*` | Gitignored |

## Local modified but excluded from commit

- `data/shadow/*`, `data/cache/resolved_seasons.json`, `data/validation/*` — runtime only, left unstaged

## Key modules now in GitHub main

- Result truth (from c7aedd3/71cc6a9): `provider_score_truth.py`, `market_result_resolver.py`, migrations v8
- ECSE evaluation upsert: `store.py` upsert_evaluation
- Regulation outcome resolver fix: `prediction_history_evaluation.py`
- Next-3 + controlled knockout prediction tooling
- ECSE historical replay + market prior shadow research

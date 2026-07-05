# FULL-PROJECT-SYNC-3 — Production Drift Audit

**Generated:** 2026-07-05

## Starting production state

- **HEAD before sync:** `282ef70`
- **Behind GitHub:** 3 commits (`282ef70` → `71cc6a9` → `c7aedd3` → `dc51f80`)

## Tracked source drift (pre-sync)

Modified on production relative to `282ef70`:

| Path | Nature |
|---|---|
| `worldcup_predictor/api/prediction_history_evaluation.py` | Partial result-truth hotfix (superseded by GitHub) |
| `worldcup_predictor/database/migrations.py` | Schema v8 migration work (superseded by GitHub) |
| `worldcup_predictor/outcomes/*` | Result truth modules (superseded by GitHub c7aedd3) |
| `worldcup_predictor/research/ecse_live/evaluator.py`, `store.py` | ECSE re-eval support (superseded by dc51f80) |

## Untracked production source (pre-sync)

- Deployed via SCP: `ecse_historical_replay/`, `ecse_market_prior/`, many `scripts/run_*` — now in GitHub dc51f80
- Erroneous duplicate dirs from bad deploy: `worldcup_predictorapi/`, etc. — cleaned by `git clean`

## Runtime drift (NOT synced to Git)

- `data/sportmonks_dump/**` — thousands of modified JSON files
- `data/shadow/*.jsonl` — promotion shadow logs
- `data/cache/resolved_seasons.json`
- `artifacts/daily_picks_2026-06-27.json`

**Action:** Preserved on disk; excluded from Git. Production patch saved at `backups/source_sync/full_project_sync_3_production_source.patch`.

## Resolution

1. DB backup: `backups/db/football_intelligence_pre_sync3_final.db` (9.5 GB, integrity OK)
2. `git reset --hard origin/main` → `dc51f80`
3. `git clean -fd` (excluding data/backups/artifacts/.env/.venv)
4. Fixed ownership: `chown -R www-data:www-data worldcup_predictor/ scripts/` (API was crash-looping on root-only dirs)

## Production-only fixes preserved

Patch archived before reset. No unique production logic found that wasn't already represented in GitHub `c7aedd3`/`dc51f80`.

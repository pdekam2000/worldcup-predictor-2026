# FULL-PROJECT-SYNC-2 — Production Drift Audit

**Server:** Hetzner `/opt/worldcup-predictor` · baseline commit `9ca89f0`

## HEAD state

- Production HEAD = GitHub main = `9ca89f05ac9c0832fcb5fa858214888448cdc7a2`
- Working tree: **dirty** (tracked + untracked)

## Tracked source drift (uncommitted)

| File | Nature |
|------|--------|
| `worldcup_predictor/owner_daily/predictions.py` | Production hotfixes (fixture_row, strict_fresh_odds, freshness) |
| `worldcup_predictor/owner_daily/cycle.py` | Pipeline integration |
| `worldcup_predictor/owner/euro_c_odds_import.py` | Timestamp canonical write |
| `worldcup_predictor/owner/production_pipeline/runner.py` | Pipeline flags |
| `scripts/run_production_prediction_pipeline.py` | Fixture-id / refresh flags |

Large line-count diffs vs Git — likely full-file SCP replacements during controlled runs.

## Untracked production source (deployed via SCP)

Present on server, consolidated in local workspace:

- `worldcup_predictor/odds/*` (freshness stack)
- `worldcup_predictor/owner_daily/wc_schedule_sync.py`
- `worldcup_predictor/research/ecse_rerank/`, `eval_coverage/`, `top3_endresult_optimizer/`
- Controlled prediction + match eval scripts/validators

## Production-only anomalies (do not commit)

| Path | Action |
|------|--------|
| `freshness_refresh.py` (repo root) | Stray copy — remove after pull |
| `predictions.py` (repo root) | Stray copy — remove after pull |
| `C:UserskamanDesktoppostgres_backup.sql` | Accidental — never commit |
| `sync_wc_upcoming_fixtures.py` (root) | Duplicate of scripts/ — remove |
| `validate_*.py` (root) | Duplicates — remove |

## Production-only unique (review)

- `worldcup_predictor/owner_daily/freshness_metadata.py` — local uses `worldcup_predictor/odds/freshness_metadata.py` instead; no separate commit needed if odds module is canonical
- `scripts/_hetzner_db_probe.py`, `scripts/eslint.critical.config.js`, `scripts/oddalerts_today_gmail_downloader.py` — server-local tooling; not in local sync batch unless already on GitHub from prior work

## Runtime-only drift (ignored)

Thousands of modified `data/sportmonks_dump/**`, shadow JSONL, cache — **not source**; preserved on server.

## Reconciliation plan

1. Backup production patch: `backups/source_sync/full_project_sync_2_production_source.patch`
2. Local consolidated commit → GitHub main
3. Hetzner: reset tracked drift, `git pull --ff-only`, remove stray root copies
4. Re-run production validators (no predictions)

## Verdict

**Drift understood** — not blocking. Local workspace is superset for approved production hotfixes.  
Proceed with dev → GitHub → Hetzner flow.

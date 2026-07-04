# FULL-PROJECT-SYNC-2 — Baseline

**Date:** 2026-07-04  
**Phase:** FULL-PROJECT-SYNC-2

## Last confirmed synchronized commit

**`9ca89f05ac9c0832fcb5fa858214888448cdc7a2`** (`9ca89f0`)  
`feat(ops): add Claude read-only prediction inspection and runbooks`

All three environments were at this commit **before** this sync began.  
Prior full deploy reference: CODEBASE-CONSOLIDATION-2 ending `7b7b08d` (2026-07-01); subsequent commits through `9ca89f0` were already on GitHub/main and production HEAD.

## Current HEAD at sync start

| Environment | HEAD | Matches origin/main |
|-------------|------|---------------------|
| Local PC | `9ca89f05ac9c0832fcb5fa858214888448cdc7a2` | yes |
| GitHub main | `9ca89f05ac9c0832fcb5fa858214888448cdc7a2` | yes |
| Hetzner production | `9ca89f05ac9c0832fcb5fa858214888448cdc7a2` | yes |

## Commit range after last sync point

**0 commits** diverged on branch tips — all work since `9ca89f0` is **uncommitted working-tree changes** (local + production), not unpushed commits.

## Branch divergence

- Local: `main...origin/main` (even, dirty working tree)
- Hetzner: `main...origin/main` (even, dirty working tree)
- No unpushed local commits; no unpulled remote commits at baseline

## Production-only source changes (pre-consolidation)

Yes — significant **uncommitted tracked diffs** on Hetzner in:

- `worldcup_predictor/owner_daily/predictions.py`
- `worldcup_predictor/owner_daily/cycle.py`
- `worldcup_predictor/owner/euro_c_odds_import.py`
- `worldcup_predictor/owner/production_pipeline/runner.py`
- `scripts/run_production_prediction_pipeline.py`

Plus many **untracked** production modules (odds freshness, fixture sync, validators) deployed via SCP during controlled runs.

Local workspace holds the consolidated superset intended for GitHub.

## Runtime-only (not source truth)

- Production DB `data/football_intelligence.db` (~9.5 GB) — canonical on Hetzner only
- `.cache/`, logs, JSONL, sportmonks dumps, pipeline LAST_RUN artifacts

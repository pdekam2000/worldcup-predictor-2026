# CORRECT SCORE ODDS INGESTION REPORT

**Final status:** `CORRECT_SCORE_ODDS_INGESTION_COMPLETE`  
**Generated:** 2026-07-16 04:25:46 UTC

## Summary

Legitimate prematch Correct Score odds were extracted from existing `odds_snapshots` payloads (API-Football / SportMonks shaped bookmaker bets) into additive table `correct_score_odds_lines`.

| Metric | Value |
|---|---|
| Fixtures with CS | 136 |
| Prematch lines | 439131 |
| API calls this run | 0 |
| Providers | api_football, sportmonks, manual_owner_import |

## Storage

- Additive tables only (`correct_score_odds_lines`, ingestion runs, manual imports, forward plan)
- Existing `odds_snapshots` rows are **never overwritten**
- Odds kind: `api_extracted` vs `manual_owner_confirmed` clearly separated

## Daily pipeline

Optional cache-first enrichment after eligibility; does not block prediction, create jobs, modify freezes, or evaluate results.

## Manual fallback

Designed with owner confirmation gate — see `artifacts/correct_score_odds/manual_import_design.json`.

## Forward shadow

Plan windows: first available / 24h / 6h / 1h / final prematch. Never after kickoff.

## Artifacts

See `artifacts/correct_score_odds/`.

## Next

Re-run two-fixture portfolio research using **only real** CS odds for ROI.

STOP constraints respected: no production betting, no formula changes.

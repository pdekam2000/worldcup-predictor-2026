# OddAlerts Lower-Band Watch and Import Report

**Phase:** ODDALERTS-LOWER-BAND-WATCH-PIPELINE  
**Date:** 2026-06-30  
**Generated:** 2026-06-30 23:28:15 UTC  
**Mode:** Owner/internal — Gmail watch, incremental import, readiness recheck — no odds_snapshots writes, no ECSE generation

---

## Summary

Watcher monitored Gmail for OddAlerts lower-band CSV exports, then ran import + readiness pipeline after `stable_rounds_reached`.

**Final recommendation:** `READY_FOR_ODDS_SNAPSHOT_PROMOTION_DRYRUN`

---

## Part A — Watch rounds

**Artifact:** `artifacts\oddalerts_lower_band_watch_20260630.json`  
**Gmail query:** `from:joe@oddalerts.com subject:"Your Probability Export is Ready" after:2026/6/30 before:2026/7/1`  
**Stop reason:** `stable_rounds_reached`  
**Stable rounds:** 2 / 2 required

| Round | New files | Duplicates skipped | Failed | Expired | New sha256 | Stable |
|-------|-----------|-------------------|--------|---------|------------|--------|
| 1 | 7 | 493 | 0 | 0 | 7 | no |
| 2 | 0 | 500 | 0 | 0 | 0 | yes |
| 3 | 0 | 500 | 0 | 0 | 0 | yes |

**Totals:** 7 new files, 1493 duplicates skipped, 0 failed, 0 expired links

---

## Part B — Lower-band market coverage (Gmail)

**Artifact:** `artifacts/oddalerts_lower_band_ecse_market_coverage_20260630.json`

| Outcome | Status | Bands present |
|---------|--------|---------------|
| btts_no | HAS_UPPER_AND_LOWER_BANDS | lower_0_50, upper_50_100 |
| btts_yes | HAS_UPPER_AND_LOWER_BANDS | lower_0_50, upper_50_100 |
| goals_over_2_5 | HAS_UPPER_AND_LOWER_BANDS | lower_0_50, upper_50_100 |
| goals_under_2_5 | HAS_UPPER_AND_LOWER_BANDS | lower_0_50, upper_50_100 |
| match_result_away | HAS_UPPER_AND_LOWER_BANDS | lower_0_50, upper_50_100 |
| match_result_draw | HAS_UPPER_AND_LOWER_BANDS | lower_0_50, upper_50_100 |
| match_result_home | HAS_UPPER_AND_LOWER_BANDS | lower_0_50, upper_50_100 |

Dual-band complete: **7/7**

---

## Part C — Import + readiness

**Import ran:** True

| Metric | Before | After |
|--------|--------|-------|
| Probability rows | 8,742,569 | 8,752,179 |
| ECSE READY_FULL | 197 | 197 |
| ECSE READY_PARTIAL | 364 | 364 |
| odds_snapshots (unchanged) | 2015 | 2015 |
| ecse_prediction_snapshots (unchanged) | 8 | 8 |

**Policy preview would_insert:** 197 (dry-run only — not executed)

---

## Part D — Validation

- **Bookmaker policy:** 16/16 checks passed
- **All-market mapping:** 17/17 checks passed
- **ECSE complete coverage:** 11/12 checks passed

**Remaining missing outcomes:** none

---

## Part E — Odds snapshot promotion dry-run readiness

**Ready for odds snapshot promotion dry-run.**

Policy READY_FULL fixtures: 197

---

## Script execution log

| Script | Exit code |
|--------|-----------|
| import_oddalerts_csv_incremental.py | 0 |
| audit_oddalerts_csv_all_markets.py | 0 |
| validate_oddalerts_all_market_mapping.py | 0 |
| crosswalk_oddalerts_probability_csv_to_fixtures.py | 0 |
| build_oddalerts_policy_market_matrix.py | 0 |
| preview_oddalerts_policy_to_odds_snapshots.py | 0 |
| validate_oddalerts_bookmaker_policy.py | 0 |
| validate_oddalerts_ecse_complete_coverage.py | 1 |

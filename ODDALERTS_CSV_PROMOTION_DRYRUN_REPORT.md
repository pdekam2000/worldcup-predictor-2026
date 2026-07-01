# OddAlerts CSV Promotion Dry-Run Report

**Phase:** ODDALERTS-CSV-PROMOTION-2  
**Date:** 2026-07-01  
**Generated:** 2026-07-01 06:46:07 UTC  
**Mode:** Owner/internal dry-run — no odds_snapshots writes, no ECSE/WDE generation

---

## Summary

Strict dry-run preview of promoting OddAlerts CSV policy-selected probabilities into `odds_snapshots` for **READY_FULL** fixtures only.

**Final recommendation:** `READY_FOR_ODDS_SNAPSHOT_WRITE`

---

## Part A — Candidate counts

| Metric | Value |
|--------|-------|
| READY_FULL fixtures | 197 |
| Candidates previewed | 197 |
| Would insert | 0 |
| Would enrich | 197 |
| Skipped (existing fresh) | 0 |
| Conflict review | 0 |
| Skipped (not READY_FULL) | 364 |

- **Would insert:** 0
- **Would enrich:** 197
- **Skipped (existing fresh):** 0
- **Conflict review:** 0
- **Skipped (not READY_FULL):** 364

**Artifact:** `artifacts/oddalerts_csv_odds_snapshot_promotion_dryrun_20260701.json`

---

## Part B — Sample fixtures

| Fixture ID | Match | Action | Optional markets |
|------------|-------|--------|------------------|
| 1035349 | Manchester City vs Brentford | WOULD_ENRICH | 26 optional |
| 1035385 | Fulham vs Everton | WOULD_ENRICH | 26 optional |
| 1035387 | Nottingham Forest vs Arsenal | WOULD_ENRICH | 26 optional |
| 1035392 | Liverpool vs Chelsea | WOULD_ENRICH | 26 optional |
| 1035393 | Manchester City vs Burnley | WOULD_ENRICH | 26 optional |
| 1035394 | Bournemouth vs Nottingham Forest | WOULD_ENRICH | 26 optional |
| 1035395 | Arsenal vs Liverpool | WOULD_ENRICH | 26 optional |
| 1035396 | Brentford vs Manchester City | WOULD_ENRICH | 26 optional |

---

## Part C — Market completeness

All READY_FULL candidates require complete ECSE markets:

- match_result_home / draw / away
- goals_over_2_5 / goals_under_2_5
- btts_yes / btts_no

Dual-band coverage artifact referenced: `artifacts/oddalerts_lower_band_ecse_market_coverage_20260701.json`

Blockers logged: **100**

---

## Part D — Validation

- Validation artifact not loaded

Checks passed: **?/0**

---

## Part E — Write phase

This run did **not** write to `odds_snapshots`. A separate explicit `--write` phase is required for promotion.

Policy version: `2026-06-30`  
Source: `oddalerts_csv_policy` / `lower_band_complete_coverage`

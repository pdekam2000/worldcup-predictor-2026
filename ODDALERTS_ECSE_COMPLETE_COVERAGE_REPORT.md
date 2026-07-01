# OddAlerts ECSE Complete Coverage Report (Updated)

**Phase:** ODDALERTS-CSV-COMPLETE-COVERAGE-1 + LOWER-BAND IMPORT  
**Date:** 2026-06-30  
**Status:** Lower-band 0–50% exports imported — ECSE READY_FULL achieved for 197 fixtures

---

## Update summary

Following `ODDALERTS-LOWER-BAND-GMAIL` import of **0% - 50%** probability exports:

| Metric | Before lower-band | After lower-band |
|--------|-------------------|------------------|
| Total probability rows | 2,408,831 | **8,742,569** |
| ECSE READY_FULL | **0** | **197** |
| ECSE READY_PARTIAL | 197 | **364** |
| Policy would_insert (dry-run) | 0 | **197** |
| odds_snapshots written | 0 | **0** |

---

## Root cause (confirmed + resolved for 197 fixtures)

Prior exports used **50% – 100%** only, excluding complementary low-probability outcomes (draw, away, under, btts_yes, etc.).

**Lower-band 0% – 50% imports** filled the gap. After fixture crosswalk:

- `match_result_draw`: 12 → **426,696** rows globally
- `goals_under_2_5`: 96,415 → **335,616** rows globally
- All **7 ECSE keys** present for **197** high-confidence fixtures → **READY_FULL**

---

## Probability range coverage (Gmail today)

| Range | Emails |
|-------|--------|
| 0% – 50% | 323 |
| 50% – 100% (duplicates) | 177 |

All 7 ECSE outcomes: **FOUND_0_50**

---

## Final recommendation

**`ODDALERTS_COMPLETE_COVERAGE_READY`**

For the original 197 high-confidence fixtures, complementary outcomes are now present. Next step (owner approval): odds_snapshots promotion dry-run execution — see `ODDALERTS_LOWER_BAND_GMAIL_IMPORT_REPORT.md` (`READY_FOR_ODDS_SNAPSHOT_PROMOTION_DRYRUN`).

No odds_snapshots writes performed. No ECSE/WDE generation. No public changes.

See also: `ODDALERTS_LOWER_BAND_GMAIL_IMPORT_REPORT.md`

# OddAlerts All Market Mapping Report

**Date processed:** 2026-06-30
**Final recommendation:** `DO_NOT_USE_MARKET_DATA_YET`
**Validation:** PASSED

## Summary

- CSV files analyzed: **444**
- Total rows analyzed: **8,752,179**
- Rows inserted: **0**
- Duplicate rows skipped: **8,752,179**
- Mapped rows: **8,752,179**
- Unknown/unmapped rows: **0**

## Markets detected

- **Away Over/Under 0.5 Probability:** 2 outcomes, 406,013 rows
- **Away Over/Under 1.5 Probability:** 2 outcomes, 411,224 rows
- **Both Teams To Score Probability:** 2 outcomes, 483,594 rows
- **Corners Over/Under 10 Probability:** 2 outcomes, 261,109 rows
- **Corners Over/Under 11 Probability:** 2 outcomes, 217,168 rows
- **Corners Over/Under 5 Probability:** 2 outcomes, 186,745 rows
- **Corners Over/Under 6 Probability:** 2 outcomes, 198,941 rows
- **Corners Over/Under 7 Probability:** 2 outcomes, 225,317 rows
- **Corners Over/Under 8 Probability:** 2 outcomes, 260,348 rows
- **Corners Over/Under 9 Probability:** 2 outcomes, 293,716 rows
- **Double Chance Probability:** 3 outcomes, 673,982 rows
- **First Half Winner Probability:** 3 outcomes, 1,069,562 rows
- **Fulltime Result Probability:** 3 outcomes, 1,225,749 rows
- **Home Over/Under 0.5 Probability:** 2 outcomes, 412,706 rows
- **Home Over/Under 1.5 Probability:** 2 outcomes, 410,901 rows
- **Over/Under 1.5 Probability:** 2 outcomes, 484,648 rows
- **Over/Under 2.5 Probability:** 2 outcomes, 635,127 rows
- **Over/Under 3.5 Probability:** 2 outcomes, 469,292 rows
- **Over/Under 4.5 Probability:** 2 outcomes, 426,037 rows

## Bookmakers

- **Bet365:** 3,043,004 rows
- **1xBet:** 2,849,326 rows
- **Pinnacle:** 1,595,655 rows
- **Betfair Exchange:** 570,996 rows
- **WilliamHill:** 566,188 rows
- **Kambi Group:** 121,396 rows
- **Betano:** 4,887 rows
- **FanDuel:** 727 rows

## ECSE-required readiness (strict)

- `btts_no`: **ready** (245,747 rows)
- `btts_yes`: **ready** (237,847 rows)
- `goals_over_2_5`: **ready** (299,511 rows)
- `goals_under_2_5`: **ready** (335,616 rows)
- `match_result_away`: **ready** (412,585 rows)
- `match_result_draw`: **ready** (429,546 rows)
- `match_result_home`: **ready** (383,618 rows)

## Extra coverage

- **goals_ou_all:** 6/6 keys with rows
- **team_totals:** 8/8 keys with rows
- **double_chance:** 3/3 keys with rows
- **first_half:** 3/3 keys with rows
- **corners:** 14/14 keys with rows

## Fixture crosswalk

- Unique fixtures: **429,516**
- High confidence: **561**
- Local fixture missing: **428,925**

## Multi-bookmaker analysis

- Multi-bookmaker groups: **157,445**
- High disagreement groups: **1**

## Artifacts

- `artifacts\oddalerts_all_markets_audit_20260630.json`
- `artifacts\oddalerts_bookmaker_coverage_20260630.json`
- `artifacts\oddalerts_probability_ecse_readiness_dryrun_20260630.json`
- `artifacts\oddalerts_probability_all_market_fixture_crosswalk_20260630.json`
- `artifacts\oddalerts_multi_bookmaker_market_analysis_20260630.json`
- `artifacts\oddalerts_all_market_mapping_validation_20260630.json`

## Notes

- All markets stored in `oddalerts_probability_market_rows` — not promoted to odds_snapshots.
- No ECSE/WDE generation. No public output changes.
- Bookmakers preserved as separate rows.
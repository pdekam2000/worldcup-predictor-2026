# OddAlerts Bookmaker Policy Dry-Run Report

**Date processed:** 2026-06-30
**Final recommendation:** `BOOKMAKER_POLICY_READY_FOR_PROMOTION`
**Validation:** FAILED

## Policy

- Config: `config\oddalerts_bookmaker_policy.json`
- Version: **2026-06-30**
- Priority: Pinnacle, Bet365, Betfair Exchange, WilliamHill, 1xBet, Kambi Group, Betano, FanDuel
- ECSE: median if ≥3 bookmakers, else priority bookmaker
- High disagreement block: **>8.0%** spread

## Bookmakers in source data

- **Bet365:** 3,043,004 rows
- **1xBet:** 2,849,326 rows
- **Pinnacle:** 1,595,655 rows
- **Betfair Exchange:** 570,996 rows
- **WilliamHill:** 566,188 rows
- **Kambi Group:** 121,396 rows
- **Betano:** 4,887 rows
- **FanDuel:** 727 rows

## Policy run stats

- Groups processed: **15,138**
- Selected by median: **188**
- Selected by priority bookmaker: **14,950**
- Blocked by high disagreement: **0**
- High-confidence fixtures: **561**

## ECSE readiness after policy

- **READY_FULL:** 197
- **READY_PARTIAL:** 364
- READY_FULL: **197**
- READY_PARTIAL: **364**

## Sample selected markets

- Fixture: **Union Berlin vs VfB Stuttgart** (bundesliga)
- ECSE status: **READY_PARTIAL**
- Missing ECSE keys: `['btts_no', 'goals_under_2_5', 'match_result_home']`
- `away_goals_over_1_5`: **18.95%** via priority_bookmaker (1 bookmakers, spread 0.0)
- `away_goals_under_0_5`: **49.73%** via priority_bookmaker (1 bookmakers, spread 0.0)
- `btts_yes`: **43.11%** via priority_bookmaker (1 bookmakers, spread 0.0)
- `double_chance_draw_away`: **45.19%** via priority_bookmaker (1 bookmakers, spread 0.0)
- `goals_over_2_5`: **42.95%** via priority_bookmaker (1 bookmakers, spread 0.0)

## Why no READY_FULL fixtures

OddAlerts probability CSV exports are filtered by probability band per export file. High-confidence local fixtures typically have 15–20 of 41 market keys — not all 7 ECSE keys on the same fixture. Policy works correctly; promotion requires complete ECSE key coverage per fixture or relaxed ECSE subset policy.

## Probability consistency

- 1X2 / OU2.5 / BTTS groups normalized proportionally when raw sum is 85–115%.
- Overround and out-of-band sums reported as warnings (not silently forced).

## Coverage

- WC READY_FULL: **56**
- UEFA READY_FULL: **0**

## Odds snapshot preview

- Previews: **561**
- Would insert: **197**
- Would not insert: **364**

## Artifacts

- `artifacts\oddalerts_policy_market_matrix_20260630.json`
- `artifacts\oddalerts_policy_ecse_readiness_20260630.json`
- `artifacts\oddalerts_policy_odds_snapshot_preview_20260630.json`
- `artifacts\oddalerts_bookmaker_policy_validation_20260630.json`

## Notes

- Dry-run only — no odds_snapshots writes.
- Original bookmaker rows unchanged in `oddalerts_probability_market_rows`.
- No ECSE/WDE generation. No public output changes.
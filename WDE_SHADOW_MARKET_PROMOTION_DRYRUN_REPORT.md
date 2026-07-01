# WDE Shadow Market Promotion Dry-Run Report

**Phase:** WDE-SHADOW-3  
**Generated:** 2026-07-01 09:58:15 UTC  
**Mode:** Owner/internal dry-run — no production replacement

## Model

- Path: `models\shadow\wde_historical_csv_shadow_20260701`
- Label: `SHADOW_ONLY`
- Markets: O/U2.5 + BTTS only; 1X2 blocked

## Backtest summary (test split)

| Market | Shadow | Bookmaker | Historical |
|--------|--------|-----------|------------|
| 1X2 | 0.4986 | 0.506 | 0.4273 |
| O/U2.5 | 0.582 | 0.5729 | 0.5282 |
| BTTS | 0.564 | 0.5548 | 0.5385 |

## Why 1X2 is blocked

- Test accuracy: shadow 49.86% vs bookmaker 50.60%
- Shadow underperforms bookmaker baseline on held-out test
- All 1X2 outputs tagged `1X2_PROMOTION_BLOCKED`

## O/U2.5 and BTTS eligibility

- O/U2.5 test: shadow 0.582 vs book 0.5729 — **eligible for owner dry-run**
- BTTS test: shadow 0.564 vs book 0.5548 — **eligible for owner dry-run**

## Upcoming fixture predictions

- Window anchor: 2026-07-01
- Fixtures discovered: 22
- Scored: 6
- Eligible owner signals: 3

- Netherlands vs Morocco: O/U `under_2_5` (0.6608) BTTS `no` (0.5168)
- Ivory Coast vs Norway: O/U `under_2_5` (0.5408) BTTS `yes` (0.5092)
- France vs Sweden: O/U `over_2_5` (0.6889) BTTS `no` (0.5294)
- Mexico vs Ecuador: O/U `under_2_5` (0.5087) BTTS `no` (0.5725)
- Kauno Žalgiris vs Drita: O/U `over_2_5` (0.6981) BTTS `yes` (0.5377)
- Vardar Skopje vs KuPS: O/U `over_2_5` (0.6981) BTTS `yes` (0.5377)

## Segment analysis highlights

- OU25 best segment: `by_country/Portugal` delta=0.1412 n=255
- BTTS best segment: `by_competition/CO1` delta=0.1757 n=165

## Validation

- Checks passed: **14** / 14
- Promotion allowed: **False**

## Final recommendation

### `READY_FOR_OWNER_SHADOW_MARKET_REPORT`

**No production replacement. No public changes.**

Owner report: `reports\owner\wde_shadow_market_owner_report_20260701.md`

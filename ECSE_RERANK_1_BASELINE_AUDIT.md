# ECSE-RERANK-1 — Baseline Audit

Phase: **ECSE-RERANK-1** | Mode: Audit (read-only) | Generated from local DB snapshots

## Scope

- ECSE snapshots (World Cup 2026): **18** fixtures
- Finished with results: **13**
- All evaluated matches are knockout-stage in current dataset

## Exact Score Hit Rates (Baseline ECSE)

| Metric | Hit Rate | Hits / N |
|--------|----------|----------|
| Top 1 | 15.4% | 2/13 |
| Top 3 | 53.8% | 7/13 |
| Top 5 | 76.9% | 10/13 |

## WDE Market Accuracy (same finished set)

- WDE 1X2: **81.8%**
- WDE BTTS: **54.5%**
- WDE O/U 2.5: **54.5%**

## ECSE Distribution Bias

- Clean-sheet Top 1 rate: **92.3%** (12/13)
- Low-score Top 1 (total goals ≤ 2): **92.3%**
- Average absolute goal underestimation (Top 1 vs actual total): **1.15** goals

## WDE vs ECSE Inconsistency Cases

- WDE BTTS=Yes but ECSE Top 1 is clean sheet: **6** / 13
- WDE Over 2.5 but ECSE Top 1 total goals ≤ 2: **4** / 13

## AET / PEN

- Matches with AET or PEN status: **4**
- Evaluation uses **90-minute score** from `fixture_results.home_goals/away_goals`, not penalty winner

## Per-Match Detail

| Match | Actual (90') | ECSE Top1 | Top3 | Top5 | WDE 1X2 | BTTS | O/U | AET | PEN |
|-------|--------------|-----------|------|------|---------|------|-----|-----|-----|
| Australia vs Egypt | 1-1 | 0-1 | Y | Y | away_win | no | under_2_5 | N | Y |
| Belgium vs Senegal | 3-2 | 1-0 | N | N | home_win | yes | over_2_5 | Y | N |
| Brazil vs Japan | 2-1 | 1-0 | N | Y | None | None | None | N | N |
| England vs Congo DR | 2-1 | 2-0 | N | N | home_win | no | under_2_5 | N | N |
| France vs Sweden | 3-0 | 3-0 | Y | Y | home_win | yes | over_2_5 | N | N |
| Germany vs Paraguay | 1-1 | 2-0 | N | N | None | None | None | N | Y |
| Ivory Coast vs Norway | 1-2 | 1-1 | Y | Y | draw | yes | over_2_5 | N | N |
| Mexico vs Ecuador | 2-0 | 1-0 | N | Y | home_win | no | under_2_5 | N | N |
| Netherlands vs Morocco | 1-1 | 1-0 | Y | Y | draw | yes | under_2_5 | N | Y |
| Portugal vs Croatia | 2-1 | 1-0 | N | Y | home_win | yes | under_2_5 | N | N |
| Spain vs Austria | 3-0 | 2-0 | Y | Y | home_win | no | under_2_5 | N | N |
| Switzerland vs Algeria | 2-0 | 1-0 | Y | Y | home_win | yes | over_2_5 | N | N |
| USA vs Bosnia & Herzegovina | 2-0 | 2-0 | Y | Y | home_win | yes | over_2_5 | N | N |

## Root Cause (confirmed)

ECSE compresses toward clean low-score lines (especially **1-0** and **2-0**) even when WDE BTTS=Yes or Over 2.5.
Top 3 / Top 5 already capture many actual results — presentation issue as much as ranking.

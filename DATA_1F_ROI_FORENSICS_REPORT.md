# DATA-1F ROI Forensics Report

**Generated:** 2026-06-29 09:52:30 UTC

## Executive finding

Positive ROI on C/D is likely driven by small sample (~3.5k bets), longshot selection bias, and segment concentration — not a robust edge.

- Strategy C bets: **3527** | ROI **9.09%** | 95% CI **[2.02%, 16.16%]**
- Strategy D bets: **3443** | ROI **7.3%** | 95% CI **[0.5%, 14.1%]**
- Small-sample warning: **True** (<5,000 bets)

## Why positive ROI appears

1. **Tiny longshot slice** — only ~0.17% of join rows have closing odds ≥3.5.
2. **Wide confidence intervals** — true ROI likely spans negative and positive at this N.
3. **Segment concentration** — profit may cluster in a few leagues/markets with low N.
4. **Survivorship** — exports are settled matches only; no cancelled/postponed longshots in band.
5. **Single bookmaker** — Bet365 only; no cross-book arbitrage signal.

## Variance & drawdown

| Metric | Strategy C | Strategy D |
|--------|------------|------------|
| Std profit/bet | 2.1422 | 2.0359 |
| Max drawdown (units) | 118.59 | 108.59 |
| ROI 95% CI | [2.02, 16.16] | [0.5, 14.1] |

## Temporal stability (strategy C)

- Split month: `2025-07`
- First half ROI: -4.44% (1295 bets)
- Second half ROI: 16.93% (2232 bets)

## Bias & integrity audit

| Check | Result |
|-------|--------|
| Survivorship | All rows are post-match settled exports (Status=FT/FT_PEN/AET); no live/unsettled odds in positive-ROI band. |
| Closing timestamp after kickoff (+2h) | 89439 / 2060830 checked |
| Duplicate settlement groups (same fixture/market/selection/odds) | 0 |
| Invalid odds rows skipped | 0 |

## ROI by odds band (strategy C)

| Band | Bets | Hit % | ROI % | CI low | CI high |
|------|------|-------|-------|--------|---------|
| 3.50-4.99 | 2479 | 25.33 | -1.51 | -8.2 | 5.18 |
| 5.00-7.99 | 733 | 20.87 | 21.74 | 4.41 | 39.07 |
| 8.00-12.00 | 231 | 16.88 | 56.06 | 10.99 | 101.13 |
| >12.00 | 84 | 13.1 | 82.14 | -18.71 | 183.0 |

## ROI by selection side (strategy C)

| Side | Bets | ROI % |
|------|------|-------|
| under | 1172 | 20.76 |
| home | 975 | 7.53 |
| away | 830 | 4.4 |
| away_team_ou | 265 | -21.64 |
| home_team_ou | 212 | 18.5 |
| over | 35 | -8.0 |
| yes | 31 | -39.52 |
| draw | 4 | -6.25 |
| no | 2 | -100.0 |
| combined | 1 | 260.0 |

## ROI by month (strategy C)

| Month | Bets | ROI % |
|-------|------|-------|
| 2024-08 | 150 | 1.32 |
| 2024-09 | 156 | 15.87 |
| 2024-10 | 135 | 3.38 |
| 2024-11 | 97 | 10.76 |
| 2024-12 | 76 | -27.39 |
| 2025-01 | 78 | -26.6 |
| 2025-02 | 84 | 1.79 |
| 2025-03 | 89 | -26.74 |
| 2025-04 | 116 | 4.38 |
| 2025-05 | 108 | -6.33 |
| 2025-06 | 92 | 13.89 |
| 2025-07 | 114 | -40.65 |
| 2025-08 | 221 | -1.38 |
| 2025-09 | 181 | -11.53 |
| 2025-10 | 251 | -14.49 |
| 2025-11 | 202 | 10.55 |
| 2025-12 | 142 | -17.92 |
| 2026-01 | 221 | 22.19 |
| 2026-02 | 234 | 40.68 |
| 2026-03 | 246 | 28.8 |
| 2026-04 | 244 | 59.45 |
| 2026-05 | 161 | 34.11 |
| 2026-06 | 129 | 21.13 |
### ROI heatmap — Strategy C (market × league, top leagues)

| Market | Liga Portugal 2 | Botola Pro | Premier League | Kakkonen | UEFA Women's Champions League | Club Friendlies 3 | Friendly International | Europa Conference League |
|--------|------|------|------|------|------|------|------|------|
| btts | — | — | — | — | — | — | — | — |
| corners_over_under | +25% | +25% | — | — | — | — | — | — |
| double_chance | — | — | +10% | — | -7% | -25% | +19% | +9% |
| first_half_winner | — | — | — | — | — | — | — | — |
| ft_result | — | — | -4% | +20% | +146% | -13% | +119% | — |
| over_under | — | — | — | — | +64% | +80% | +44% | — |
| team_over_under | — | — | -52% | +23% | +3% | — | +19% | +20% |

*Cells need ≥5 bets; ROI % shown. Wide empty matrix = sparse high-odds coverage.*

### ROI heatmap — Strategy D (market × league)

| Market | Liga Portugal 2 | Botola Pro | Premier League | Kakkonen | UEFA Women's Champions League | Club Friendlies 3 | Friendly International | Europa Conference League |
|--------|------|------|------|------|------|------|------|------|
| btts | — | — | — | — | — | — | — | — |
| corners_over_under | +22% | +25% | — | — | — | — | — | — |
| double_chance | — | — | +10% | — | -7% | -25% | +19% | +9% |
| first_half_winner | — | — | — | — | — | — | — | — |
| ft_result | — | — | -0% | +20% | +146% | -8% | +119% | — |
| over_under | — | — | — | — | +64% | +80% | +44% | — |
| team_over_under | — | — | -52% | +23% | +3% | — | +19% | +20% |

*Cells need ≥5 bets; ROI % shown. Wide empty matrix = sparse high-odds coverage.*

## Stable profitable segments (C, CI entirely >0, n≥30)

- **Liga Portugal 2**: ROI 25.4% (687 bets, CI 4.68–46.11)

## Unstable / low-N segments

- US Open Cup: 15 bets, ROI -26.67%
- First League: 15 bets, ROI -1.67%
- Club Friendlies 1: 15 bets, ROI -100.0%
- AFC Champions League Two: 15 bets, ROI 37.0%
- Liga De Futbol Prof: 16 bets, ROI -54.69%
- Super League: 17 bets, ROI -34.41%
- Primera Division: 17 bets, ROI -46.59%
- Europa League: 17 bets, ROI 19.12%
- Women's Nations League: 18 bets, ROI -22.22%
- CONCACAF Champions Cup: 18 bets, ROI 42.56%

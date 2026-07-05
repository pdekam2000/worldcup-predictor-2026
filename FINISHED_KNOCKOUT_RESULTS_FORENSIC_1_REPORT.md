# FINISHED KNOCKOUT RESULTS FORENSIC 1 — Final Report

Phase: **FINISHED-KNOCKOUT-RESULTS-FORENSIC-1** | Recommendation: **`RESULT_SYNC_REQUIRED`**

> **Production server note:** `/opt/worldcup-predictor` production SQLite currently contains only Colombia + Canada R16 fixtures from this batch (Jul 1–3 fixtures absent). This forensic run used local canonical DB + API-Football provider truth for all 11 targets.

## Executive Answers

1. **Screenshot results already in DB:** Mexico vs Ecuador, England vs DR Congo, USA vs Bosnia & Herzegovina, Spain vs Austria, Portugal vs Croatia, Switzerland vs Algeria, Australia vs Egypt, Colombia vs Ghana, Canada vs Morocco (partial set on production — see audit)
2. **Missing results:** Belgium vs Senegal, Argentina vs Cape Verde
3. **Safely synced:** 0 fixtures (provider calls: 22)
4. **Valid frozen predictions:** Mexico vs Ecuador, England vs DR Congo, Belgium vs Senegal, USA vs Bosnia & Herzegovina, Spain vs Austria, Portugal vs Croatia, Switzerland vs Algeria, Australia vs Egypt, Argentina vs Cape Verde, Colombia vs Ghana, Canada vs Morocco
5. **Already evaluated (DB rows):** Mexico vs Ecuador, England vs DR Congo, Belgium vs Senegal, USA vs Bosnia & Herzegovina, Spain vs Austria, Portugal vs Croatia, Switzerland vs Algeria, Australia vs Egypt, Argentina vs Cape Verde, Colombia vs Ghana, Canada vs Morocco
6. **Evaluation backlog:** 

## WDE Performance

- 1X2: 7/11
- BTTS: 5/11
- O/U: 5/11

## ECSE Performance

- Top1: 1/11
- Top3: 5/11
- Top5: 7/11
- Rank distribution: {'4': 2, '7': 1, '10': 1, '1': 1, '2': 3, '3': 1, '11': 1, '6': 1}

## Control Cases

### Colombia vs Ghana (1567310)
- Expected: WDE 1X2/BTTS/O/U HIT; ECSE Top1 MISS, Top3 HIT rank 2, Top5 HIT
- Verified from provider regulation 1-0; stored evaluation intact

### Canada vs Morocco (1567824)
- DB frozen WDE official 1X2 selection: **draw** (not away); away_win implied prob 46.2%
- Actual regulation: **0-3** (Morocco away win)
- Forensic eval: WDE 1X2 **MISS**, BTTS **MISS** (predicted yes), O/U **MISS** (predicted under; total=3)
- ECSE Top1 **0-1** (directionally closer); Top3 **MISS** (max away margin 2 vs actual 3)
- Owner tracker 'Morocco Win' does not match stored WDE canonical selection — DB truth used

## Error Patterns

- `ODDS_METADATA_ONLY_GAP`: 6 attribution(s)
- `BTTS_CALIBRATION_ERROR`: 6 attribution(s)
- `GOAL_TOTAL_UNDERESTIMATED`: 4 attribution(s)
- `WINNER_DIRECTION_ERROR`: 4 attribution(s)
- `LINEUP_SIGNAL_MISSING`: 3 attribution(s)
- `GOAL_TOTAL_OVERESTIMATED`: 2 attribution(s)
- `FAVORITE_DOMINANCE_UNDERESTIMATED`: 1 attribution(s)

## Favorite Dominance Underestimated?

- Winner-correct but margin > Top3 max: **1/11**
- Canada vs Morocco: predicted Morocco (away), actual 0-3, Top3 max away margin 2 — **isolated in this batch** unless margin_miss > 1

## ECSE Distribution Too Narrow?

See `ECSE_SCORE_DISTRIBUTION_WIDTH_ANALYSIS.md`.

## Cross-Market Consistency

- ALIGNED Top3 hit rate: 2/3
- MIXED Top3 hit rate: 2/5
- CONFLICT Top3 hit rate: 1/3

## Feature Availability vs Performance

- odds missing/stale: with=5/11, without=n/a
- xg available: with=5/11, without=n/a
- lineup available: with=0/3, without=5/8

## Top 3 Evidence-Backed Experiments

1. **AET/PEN regulation score persistence** (IMMEDIATE_INFRASTRUCTURE_FIX) — Persist score.fulltime separately; eval uses regulation for AET/PEN
2. **Fresh odds at freeze time** (IMMEDIATE_INFRASTRUCTURE_FIX) — Pre-kickoff odds refresh gate (existing ODDS-FRESHNESS policy)

## Constraints Verified

- No prediction regeneration
- No frozen payload modification
- No WDE/ECSE formula change
- No S5/Top10/ECSE rerank promotion
- Provider calls bounded (max 30)

**Final recommendation:** `RESULT_SYNC_REQUIRED`

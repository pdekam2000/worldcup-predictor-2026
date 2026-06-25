# PHASE API Full Utilization — EGIE Report

## Executive Summary

Paid-provider infrastructure is **implemented and wired** into EGIE feature building, agent enrichment, survival dataset columns, and A–F backtest comparison. On this local dataset (Premier League 380 fixtures), **xG, pressure, and PL odds are not stored** — only goal events (94%) reach the feature store. World Cup odds exist in SQLite but do not overlap PL `fixture_id`s.

- **Production promotion safe:** `True`
- **Validation:** 8/8 checks PASS
- **Baseline (A) first-goal-team winrate:** 0.4286

## 1. Audit — API-Football

| Field | Fetched (ingest) | Stored (EGIE PG / SQLite) | Enters prediction | Enters backtest | Survival parquet | Calibration |
|-------|------------------|---------------------------|-------------------|-----------------|------------------|-------------|
| Events / goals | Yes (ingest manifest) | 359/380 fixtures | Via goal-minute history | Yes (baseline A) | first_goal_minute | Indirect (DQ) |
| Fixture statistics | Yes | 0/380 | `provider_features.home_shots` etc. | Strategy F enrichment | Column added | No direct |
| Lineups | Yes | 0/380 | `lineup_goal_impact` agent (strategy F) | Strategy F | Column added | No direct |
| Injuries | Yes | 0/380 | `player_goal_threat` (strategy F) | Strategy F | Column added | No direct |
| Odds | Yes (API) | 0 PL / 1055 WC SQLite | `odds_goal_intelligence` when stored | Strategy D/E/F | Column added | Confidence manifest |

## 2. Audit — Sportmonks

| Field | Stored locally | Enters prediction | Enters backtest | Survival |
|-------|----------------|-------------------|-----------------|----------|
| xG | 0/380 | `provider_features` + pressure/xG agents | Strategy B/E/F | Columns added |
| Pressure Index | 0/380 | `first_goal_pressure` agent | Strategy C/E/F | Columns added |
| Advanced stats | via xG/fixture stats | Shots / SOT / dangerous attacks | Strategy F | Columns added |
| Scores / state / events | Partial (events in PG) | Goal events primary | Baseline | first_goal_minute |
| Odds / predictions | 0 locally | N/A | N/A | N/A |

## 3. EGIE Provider Feature Store

Module: `worldcup_predictor/egie/provider_features/`

Per-fixture vector includes: `home_xg_for`, `away_xg_for`, `home_xg_against`, `away_xg_against`, `pressure_index_home/away`, shots, SOT, dangerous attacks, odds implied probs + movement, lineup strength, injuries impact, recent first-goal rates.

### Coverage (Premier League, n=380)

- **advanced_stats:** 0.0% (0 fixtures)
- **events:** 94.47% (359 fixtures)
- **injuries:** 0.0% (0 fixtures)
- **lineups:** 0.0% (0 fixtures)
- **odds:** 0.0% (0 fixtures)
- **pressure:** 0.0% (0 fixtures)
- **xg:** 0.0% (0 fixtures)

### Feature builder attachment

- `provider_features_attached`: 100.0% (sample n=50)
- `has_reliable_goal_odds`: 0.0%
- `stored_goal_events`: 100.0%

## 4. Survival Dataset Extension

`SurvivalDatasetBuilder` now writes provider columns to `data/egie/survival/survival_dataset.parquet` and uses strategy-F enrichment for `home_goal_rate` / `away_goal_rate`.

## 5. Backtest Strategies A–F

| Strategy | Label | FG Team | Goal Range | Soft Minute | Paid-data fixtures |
|----------|-------|---------|------------|-------------|-------------------|
| A | baseline_current | 0.4286 | 0.306 | 0.3825 | 0/190 |
| B | baseline_plus_xg | 0.4286 | 0.306 | 0.3825 | 0/190 |
| C | baseline_plus_pressure | 0.4286 | 0.306 | 0.3825 | 0/190 |
| D | baseline_plus_odds | 0.4286 | 0.306 | 0.3825 | 0/190 |
| E | baseline_plus_xg_pressure_odds | 0.4286 | 0.306 | 0.3825 | 0/190 |
| F | full_paid_provider | 0.4286 | 0.306 | 0.3825 | 183/190 |

### Per-field impact on winrate

| Paid field | Strategy | Δ vs baseline A | Verdict |
|------------|----------|-----------------|---------|
| xG | B | 0.0 | no data locally |
| Pressure | C | 0.0 | no data locally |
| Odds | D | 0.0 | no data locally |
| xG+Pressure+Odds | E | 0.0 | no data locally |
| Full provider | F | 0.0 | no improvement |

## 6. Pipeline Gaps

- Sportmonks xG stored but not reaching EGIE features for most fixtures
- Pressure Index not available in stored raw data
- Lineups barely ingested into EGIE raw store
- Injuries barely ingested into EGIE raw store
- API-Football fixture statistics rarely in EGIE raw store

## 7. Promotion Decision

- No strategy beat baseline by >1pp — keep production unchanged.

**`EliteGoalTimingEngine` thresholds unchanged.** Production agents use paid data only when `paid_provider_strategy != 'A'` (backtest) or production mode with stored fields present. No deploy until PL/WC ingest backfills xG, pressure, and league-aligned odds.

## Artifacts

- `artifacts/egie_paid_provider_audit.json`
- `artifacts/egie_paid_provider_backtest.json`
- `data/egie/survival/survival_dataset.parquet`

## Commands

```bash
python scripts/egie_paid_provider_utilization_audit.py
python scripts/egie_paid_provider_backtest.py
python scripts/validate_egie_paid_provider_utilization.py
```
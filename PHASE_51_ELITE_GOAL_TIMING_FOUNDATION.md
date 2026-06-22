# Phase 51 — Elite Goal Timing Intelligence Engine (Foundation)

## Product direction

The primary user-facing value shifts from legacy 1X2 archive/accuracy tracking to an **independent Elite Goal Timing** prediction system.

Legacy predictions remain stored and generated unchanged. User-facing Archive and Accuracy UI is hidden (Phase 51A). Admin/debug routes retain access to old evaluation data.

## Core outputs

| Field | Description |
|-------|-------------|
| `first_goal_team` | home / away / none |
| `first_goal_time_range` | One of six minute buckets |
| `estimated_first_goal_minute` | Point estimate (float) |
| `home_team_goal_probability_by_range` | Per-bucket probabilities |
| `away_team_goal_probability_by_range` | Per-bucket probabilities |
| `no_goal_before_minute_probability` | Cumulative no-goal curve by bucket |
| `confidence_score` | 0–1 calibrated confidence |
| `data_quality_score` | 0–1 input reliability |
| `explanation` | Human-readable rationale |
| `specialist_agent_breakdown` | Per-agent signals |

### Minute ranges

- `0-15`
- `16-30`
- `31-45+`
- `46-60`
- `61-75`
- `76-90+`

## Architecture (separate from 1X2 engine)

```
worldcup_predictor/goal_timing/
├── config.py                 # ranges, thresholds, model version
├── models.py                 # domain dataclasses
├── engine.py                 # EliteGoalTimingEngine orchestrator
├── features/builder.py       # point-in-time feature builder
├── models_stat/baseline.py   # statistical baseline
├── models_stat/ml.py         # LightGBM/CatBoost (when data sufficient)
├── calibration.py
├── confidence.py
├── explanation.py
├── evaluation.py               # post-match evaluation (new engine only)
├── agents/                   # 8 specialist agents + orchestrator
├── storage/repository.py     # PostgreSQL persistence
└── backtest/runner.py        # leakage-safe historical backtest
```

## Specialist agents

1. **Goal Timing Pattern** — historical score/concede timing
2. **First Goal Pressure** — early xG, aggression, early goals
3. **Lineup Goal Impact** — striker/creator/GK availability
4. **Player Goal Threat** — scorer likelihood from player stats
5. **Tactical Goal Flow** — style, transitions, pressing
6. **Odds Goal Intelligence** — odds only when reliable
7. **Motivation Goal** — tournament context, must-win, rotation
8. **Data Quality** — reliability scoring, no-prediction gates

## Data sources (existing providers, cached)

- API-Football: fixtures, events, goals, lineups, injuries, team/player stats, H2H, odds
- Sportmonks: xG, shots, player xG, goal timing, advanced stats
- PostgreSQL/SQLite historical imports — reuse first; API only for gaps

## Database tables (PostgreSQL only)

- `goal_timing_predictions`
- `goal_timing_prediction_markets`
- `goal_timing_agent_outputs`
- `goal_timing_features`
- `goal_timing_backtest_runs`
- `goal_timing_backtest_results`
- `goal_timing_evaluations`

## Evaluation (new engine only)

After match finish:

- Compare `first_goal_team` vs actual first scorer team
- Compare `first_goal_time_range` vs actual minute bucket
- Compare `estimated_first_goal_minute` with tolerance bands
- Status: `correct` (green) / `wrong` (red) / `partial` (purple) / `pending` (yellow)

**Do not** use legacy `worldcup_prediction_evaluations` for this engine.

## Backtest (Phase 51C+)

- Window: 2 years → today
- Strict point-in-time features (no future leakage)
- Outputs: accuracy by market, confidence buckets, league/team splits, recommended threshold

## UI (Phase 51A foundation pages)

Navigation section **Elite Goal Timing**:

1. Dashboard — `/goal-timing/dashboard`
2. Today's Picks — `/goal-timing/picks`
3. History — `/goal-timing/history`
4. Backtest — `/goal-timing/backtest`
5. Model Insights — `/goal-timing/insights`

## Implementation phases

| Phase | Scope |
|-------|--------|
| **51A** | Hide legacy Archive/Accuracy UI |
| **51B** | Foundation: schema, module stubs, API status, placeholder UI |
| **51C** | Feature builder + specialist agents wired to providers |
| **51D** | Baseline model + calibration + confidence |
| **51E** | Evaluation pipeline + goal-timing history UI |
| **51F** | Historical backtest (2y, leakage-safe) |
| **51G** | Production picks + ML model if data sufficient |

## Rules

- No deletion of legacy predictions or tables
- No changes to 1X2 prediction generation
- No further work on legacy archive pending display bugs
- Cache provider responses; preserve imported historical data

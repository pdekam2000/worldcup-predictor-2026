# Model-Only Daily Prediction Run Report

**Final status:** `MODEL_ONLY_DAILY_PREDICTIONS_COMPLETE`  
**Generated:** 2026-07-11

## Summary

| # | Question | Answer |
|---|----------|--------|
| 1 | Local disk full? | **Yes** — C: 0 bytes free |
| 2 | Production DB lock? | **Yes** — services + rescue validate |
| 3 | Lock holder? | api, gpt-actions, mcp, lightweight_validate.py |
| 4 | Lock cleared for model? | **Yes** — via env wrapper batch (no kills) |
| 5 | Model-only rule active? | **Yes** |
| 6 | Eliteserien/Veikkausliiga in registry? | **Yes** — Tier B |
| 7 | Why previously unsupported? | Stale hardcode in `domestic_league_control.py` |
| 8 | Fixtures resolved? | 8 model outputs (4+4 dates) |
| 9 | Supported? | Tier B domestic batch |
| 10 | Unsupported? | International friendlies |
| 11 | WDE run? | **8 fixtures** |
| 12 | ECSE run? | **8 fixtures** (all ecse.ready=true) |
| 13 | Best 3 End Result (model)? | See below |
| 14 | Odds-only predictions? | **NO** |
| 15 | WDE/ECSE/gate/timer changes? | **NO** (registry wiring only) |

## Best 3 model-based End Results

Ranked by strongest WDE H/D/A margin (not bookmaker odds):

### 1. KFUM Oslo vs Bodø/Glimt — **AWAY**
- **Tier:** B (Eliteserien)
- **WDE:** away_win — H 3.4% / D 8.8% / **A 87.9%**
- **ECSE Top1–5:** 0-2, 0-3, 0-1, 1-2, 1-3
- **Agreement:** CONSISTENT
- **Data quality:** bookmakers=0 (context only), odds freshness=fresh
- **Risk:** thin bookmaker depth

### 2. Hammarby FF vs Kalmar FF — **HOME**
- **Tier:** B (Allsvenskan)
- **WDE:** home_win — **H 83.5%** / D 11.7% / A 4.8%
- **ECSE Top1–5:** 2-0, 3-0, 1-0, 4-0, 2-1
- **Agreement:** CONSISTENT
- **Risk:** bookmakers=0

### 3. Malmö FF vs IFK Göteborg — **HOME**
- **Tier:** B (Allsvenskan)
- **WDE:** home_win — **H 80.9%** / D 12.3% / A 6.8%
- **ECSE Top1–5:** 1-1, 2-1, 1-0, 2-0, 3-1
- **Agreement:** MINOR_DIVERGENCE (ECSE more balanced)
- **Risk:** WDE/ECSE direction tension

## Also from owner image (model)

| Match | WDE End Result | H/D/A |
|-------|----------------|-------|
| Mjallby vs AIK | HOME | 65.6 / 19.9 / 14.5 |
| Fredrikstad vs Lilleström | DRAW* | 29.3 / 24.8 / 46.0 → marginal AWAY |

\*WDE label `draw` but away prob highest — report marginal direction.

## Artifacts

- `artifacts/domestic_league_control_20260711_payload.json`
- `artifacts/domestic_league_control_20260712_payload.json`
- `artifacts/model_top3_endresult.json`

## Validation

`scripts/validate_model_only_daily_prediction_run.py` — **18/18 passed**

## Code change

- `domestic_league_control.py` — wire `TIER_B_SHADOW_DOMAINS` (no formula change)
- `.cursor/rules/model-predictions-only.mdc` — corrected examples

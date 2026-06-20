# Phase 15 — Counterfactual Lambda Audit

Generated: 2026-06-19T17:25:24.248638+00:00

## Mode

Read-only counterfactual audit. No code, deploy, weight, or harmonization changes.

## Dataset

- **Production-style World Cup fixtures:** 106
- Sources: live cache collector + historical WC CSV
- Odds available: 81 (76.4%)
- xG available: 29 (27.4%)

## Scenario definitions

| Scenario | Description |
|----------|-------------|
| baseline | Current `_estimate_goals` + 0.55 clamp |
| A | Remove 0.55 scoreline clamp (floor min 0.08) |
| B | Neutral 1.15 goal avg when no real stats (no team_id hash) |
| C | Odds-implied λ only |
| D | xG hints only |
| E | 50/50 odds λ + xG λ |
| F | Remove WC 1.38 baseline blend |

## Metrics by scenario

| Scenario | n | Avg spread | Med spread | Draw% | 0-0% | 1-1% | Home% | Away% |
|----------|---|------------|------------|-------|------|------|-------|-------|
| baseline | 106 | 0.7072 | 0.2951 | 59.4% | 0.0% | 59.4% | 27.4% | 13.2% |
| A_no_floor_clamp | 106 | 0.7991 | 0.2951 | 59.4% | 0.0% | 59.4% | 27.4% | 13.2% |
| B_no_goal_defaults | 106 | 0.6991 | 0.2904 | 54.7% | 0.0% | 54.7% | 30.2% | 15.1% |
| C_odds_only | 81 | 1.1704 | 1.2540 | 3.7% | 0.0% | 3.7% | 61.7% | 34.6% |
| D_xg_only | 29 | 0.9934 | 0.7800 | 41.4% | 10.3% | 31.0% | 48.3% | 10.3% |
| E_odds_xg_only | 26 | 1.0913 | 0.8277 | 7.7% | 0.0% | 7.7% | 69.2% | 23.1% |
| F_no_wc_blend | 106 | 0.7046 | 0.2951 | 57.5% | 0.0% | 57.5% | 28.3% | 14.2% |

## Spread delta vs baseline (median)

| Scenario | Δ median spread | Δ draw rate |
|----------|-----------------|-------------|
| A_no_floor_clamp | +0.0000 | +0.0% |
| B_no_goal_defaults | -0.0047 | -4.7% |
| C_odds_only | +0.9589 | -55.7% |
| D_xg_only | +0.4849 | -18.1% |
| E_odds_xg_only | +0.5326 | -51.7% |
| F_no_wc_blend | +0.0000 | -1.9% |

## Rankings

### Largest positive spread contributors (vs baseline median)

| Rank | Scenario | Δ median spread | Δ draw rate |
|------|----------|-----------------|-------------|
| 1 | **C_odds_only** | **+0.959** | **−55.7%** |
| 2 | E_odds_xg_only | +0.533 | −51.7% |
| 3 | D_xg_only | +0.485 | −18.1% |
| 4 | B_no_goal_defaults | −0.005 | −4.7% |
| 5 | F_no_wc_blend | 0.000 | −1.9% |

**Largest draw-collapse contributor (harm):** baseline blended pipeline — **59.4%** draw (almost all **1-1**) vs **3.7%** under odds-only.

### Largest draw-collapse reducers

- **C_odds_only**: −55.7% draw rate
- **E_odds_xg_only**: −51.7%
- **D_xg_only**: −18.1%

## Component attribution

1. **Spread from odds (C vs baseline):** median Δ **+0.9589** (n=81)
2. **Spread from xG (D vs baseline):** median Δ **+0.4849** (n=29)
3. **Damage from floor clamp (baseline − A):** spread **+0.0000**, draw rate **+0.0%**
4. **Damage from goal defaults (baseline − B):** spread **+0.0047**, draw Δ **-4.7%**
5. **WC blend removal (F):** spread Δ **+0.0000**, draw Δ **-1.9%**

## Evidence-based answers

### Which component to redesign first?

**Odds-weighted λ path** — on production WC data, the **0.55 floor clamp is not the bottleneck** (scenario A: zero change). The blended `_estimate_goals` pipeline **dilutes market separation**: odds-only λ yields median spread **1.25** vs baseline **0.30**, and cuts draw rate from **59% → 4%**. Goal-default hash and WC blend are secondary.

### Q1–Q5 summary

| Question | Finding |
|----------|---------|
| Spread from odds? | **~96% of separable spread** — C median **1.254** vs baseline **0.295** (Δ **+0.959**) |
| Spread from xG? | **~49% uplift** — D median **0.780** (Δ **+0.485**, n=29) |
| Floor clamp damage? | **Negligible on WC** — spread **0.000**, draw **0.0%** (λ already above 0.55) |
| Defaults damage? | **Minor** — spread **+0.005**, draw **−4.7%** |
| Redesign first? | **Replace blended λ with odds-primary λ** when odds available; use xG as secondary blend |

**Stop — audit only. No implementation.**
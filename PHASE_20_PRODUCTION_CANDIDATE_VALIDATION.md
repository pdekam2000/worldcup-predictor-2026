# Phase 20 — Production Candidate Validation

Generated: 2026-06-19T18:48:39.010589+00:00

## Mode

- **Read-only validation** — no code, deploy, or production changes
- Identical dataset: **207** finished fixtures (Phase 18/19 replay)

## 1. Baselines

| Baseline | Accuracy | Draw Rate | Override vs Prod | Harmful | Helpful | Net Benefit |
|----------|----------|-----------|------------------|---------|---------|-------------|
| Production (always harmonize) | 30.0% | 91.3% | 0.0% | 63 | 53 | -10 |
| WDE Only | 34.8% | 0.0% | 91.8% | 0 | 0 | +0 |
| Scoreline Only | 30.0% | 91.3% | 0.0% | 63 | 53 | -10 |
| Rule A: No Odds -> WDE, Odds -> Scoreline | 36.7% | 3.9% | 87.4% | 1 | 5 | +4 |

## 2. Full leaderboard (Rules A–J)

| Rank | Rule | Accuracy | d vs Prod | d vs WDE | Draw | Override | Harmful | Helpful | Net |
|------|------|----------|-----------|----------|------|----------|---------|---------|-----|
| 1 | Rule A: No Odds -> WDE, Odds -> Scoreline | 36.7% | +6.8% | +1.9% | 3.9% | 87.4% | 1 | 5 | +4 |
| 2 | Rule C: Low DQ -> WDE, Else Scoreline | 36.7% | +6.8% | +1.9% | 3.9% | 87.9% | 1 | 5 | +4 |
| 3 | Rule E: No Odds OR Low DQ -> WDE, Else Scoreline | 36.7% | +6.8% | +1.9% | 3.9% | 87.9% | 1 | 5 | +4 |
| 4 | Rule F: Odds AND High DQ -> Scoreline, Else WDE | 36.7% | +6.8% | +1.9% | 3.9% | 87.9% | 1 | 5 | +4 |
| 5 | Rule H: Odds AND Consensus -> Scoreline, Else WDE | 36.7% | +6.8% | +1.9% | 3.9% | 87.4% | 1 | 5 | +4 |
| 6 | Rule J: Hybrid (WC OR odds+consensus/sharp+spread>=0.20) -> Scoreline, Else WDE | 36.2% | +6.3% | +1.4% | 4.3% | 87.0% | 2 | 5 | +3 |
| 7 | Rule D: No Odds OR Low Spread -> WDE, Else Scoreline | 35.7% | +5.8% | +1.0% | 1.0% | 90.8% | 0 | 2 | +2 |
| 8 | Rule B: Low Spread -> WDE, Else Scoreline | 35.3% | +5.3% | +0.5% | 1.4% | 90.3% | 1 | 2 | +1 |
| 9 | Rule G: Odds AND Spread > Threshold -> Scoreline, Else WDE | 35.3% | +5.3% | +0.5% | 0.5% | 91.3% | 0 | 1 | +1 |
| 10 | Rule I: Odds AND High DQ AND Spread > Threshold -> Scoreline, Else WDE | 35.3% | +5.3% | +0.5% | 0.5% | 91.3% | 0 | 1 | +1 |

## 3. Cohort analysis (best rule vs Rule A)

| Cohort | n | Rule A | Best Rule | Best Acc | Winner |
|--------|---|--------|-----------|----------|--------|
| World Cup | 27 | 55.6% | Rule A: No Odds -> WDE, Odds -> Scorelin | 55.6% | Rule A |
| Bundesliga | 180 | 33.9% | Rule A: No Odds -> WDE, Odds -> Scorelin | 33.9% | Rule A |
| Odds available | 25 | 52.0% | Rule A: No Odds -> WDE, Odds -> Scorelin | 52.0% | Rule A |
| Odds unavailable | 182 | 34.6% | Rule A: No Odds -> WDE, Odds -> Scorelin | 34.6% | Rule A |
| High DQ (>=60%) | 13 | 61.5% | Rule A: No Odds -> WDE, Odds -> Scorelin | 61.5% | Rule A |
| Low DQ (<45%) | 192 | 34.4% | Rule A: No Odds -> WDE, Odds -> Scorelin | 34.4% | Rule A |

## 4. Override analysis

- Production harmful overrides (always scoreline): **63** on full Phase 18/19 sample
- Rule A harmful overrides: **1**
- Rule A helpful overrides: **5**
- Rule A net override benefit: **+4**

**Safest rule (min harmful overrides):** Rule D: No Odds OR Low Spread -> WDE, Else Scoreline — 0 harmful, 35.7% accuracy

**Most cohort-robust rule (min cohort accuracy):** Rule A: No Odds -> WDE, Odds -> Scoreline — floor accuracy **33.9%**

## 5. Best candidate

**Rule A: No Odds -> WDE, Odds -> Scoreline** — **36.7%** accuracy (+6.8% vs production, +1.9% vs WDE)

## 6. Production recommendation

Proceed to **shadow implementation** of **Rule A** only. No competing rule beats it on this identical dataset. Simplest gate: `use_scoreline = has_odds`.

## Success criteria answers

**Q1 — Best overall?** **Rule A: No Odds -> WDE, Odds -> Scoreline** at **36.7%**.

**Q2 — Any rule beat Rule A?** **NO** (Rule A ties at 36.7%).

**Q3 — Safest for production?** **Rule D: No Odds OR Low Spread -> WDE, Else Scoreline** (0 harmful overrides, 35.7% accuracy).

**Q4 — Most robust across cohorts?** **Rule A: No Odds -> WDE, Odds -> Scoreline** (minimum cohort accuracy **33.9%**).

**Q5 — Implementation justified?** **YES — shadow gate only** — Rule A improves production by **6.8%** with **1** harmful overrides remaining.

**Stop — read-only validation complete. No implementation. No deploy.**

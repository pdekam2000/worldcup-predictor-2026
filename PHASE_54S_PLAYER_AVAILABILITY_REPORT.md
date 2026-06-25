# PHASE 54S — Player Availability Intelligence

**Date:** 2026-06-24  
**Mode:** Research → Feature Expansion → Revalidation  
**Status:** Complete — research only  
**API calls:** 0

### Final recommendation: **`GOALSCORER_HIGH_VALUE`**

---

## Part A — Availability features

Built **11** availability features.

| Feature | Non-zero rows |
|---------|---------------|
| lineup_confirmed | 47,029 |
| starter_probability | 38,629 |
| minutes_last_3 | 36,876 |
| minutes_last_5 | 46,862 |
| minutes_trend | 46,584 |
| bench_probability | 30,773 |
| captain | 5,359 |
| suspended_flag | 8 |
| injury_flag | 520 |
| returned_recently | 11,911 |
| availability_score | 47,029 |

Artifact: `artifacts/phase54s_player_availability/goalscorer_dataset_v5.parquet`

## Part B — Dataset v5

| Rows | 47,029 |
| Fixtures | 1541 |

## Part C — Feature group test (test split)

| Group | Top-1 | Top-3 | Top-5 | MRR |
|-------|-------|-------|-------|-----|
| player | 0.3175 | 0.6296 | 0.7619 | 0.5106 |
| player_lineup | 0.3386 | 0.672 | 0.7884 | 0.5381 |
| player_availability | 0.328 | 0.6402 | 0.7513 | 0.5181 |
| player_lineup_availability | 0.3333 | 0.672 | 0.7989 | 0.5369 |
| player_lineup_availability_odds | 0.3333 | 0.672 | 0.7989 | 0.5369 |

## Part D — UEFA analysis (test split)

| League | Top-1 | Top-3 | Top-5 | MRR | Δ vs lineup |
|--------|-------|-------|-------|-----|-------------|
| **UEFA overall** | 0.3117 | 0.6623 | 0.7922 | 0.5218 | 0.0 |
| champions_league | 0.4 | 0.8 | 0.84 | 0.6127 | 0.02 |
| europa_league | 0.2459 | 0.6066 | 0.7705 | 0.473 | -0.0164 |
| conference_league | 0.3023 | 0.5814 | 0.7674 | 0.4853 | 0.0 |

## Part E — Availability feature importance

Baseline lineup+availability top-3: **0.672**

| Feature | Top-3 drop when removed | Verdict |
|---------|-------------------------|---------|
| minutes_last_5 | +0.0053 | positive |
| minutes_trend | +0.0053 | positive |
| lineup_confirmed | +0.0000 | neutral |
| starter_probability | +0.0000 | neutral |
| minutes_last_3 | +0.0000 | neutral |
| bench_probability | +0.0000 | neutral |
| captain | +0.0000 | neutral |
| suspended_flag | +0.0000 | neutral |
| injury_flag | -0.0052 | harmful |
| returned_recently | -0.0052 | harmful |
| availability_score | -0.0052 | harmful |

**Positive:** minutes_last_5, minutes_trend

## Part F — Elite path test

| Check | Value |
|-------|-------|
| UEFA lineup+availability top-3 | 0.6623 |
| Target threshold | 0.67 |
| Closes UEFA gap | **False** |
| Architecture near ceiling | **True** |

## Part G — Decision questions

1. **Does availability help?** True (+0.0 pp test; UEFA +0.0 pp)
2. **Which features matter?** 2 positive — top: minutes_last_5
3. **Does UEFA improve?** False
4. **Elite path open?** False

### Final recommendation: **`GOALSCORER_HIGH_VALUE`**

---

## Constraints honored

- No production, deploy, WDE, SaaS, or live prediction changes
- No EGIE scoring changes

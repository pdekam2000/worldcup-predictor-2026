# PHASE 54H-1 — Pressure Shadow Backtest Report

**Phase:** 54H-1 (shadow / backtest only)  
**Status:** COMPLETE  
**Validation:** 12/12 PASS  
**Leakage audit:** PASS (5/5 checks)  
**Generated:** 2026-06-24  

---

## Executive summary

Phase 54H-1 evaluated whether Sportmonks Pressure Index features improve EGIE-related markets using **65 UEFA fixtures** (12,676 pressure rows) from the Phase 54H feature store. All work is **shadow-only**: no production predictions, WDE, SaaS, or EGIE scoring changes.

| Area | Finding |
|------|---------|
| Pre-match (rolling history) | **Insufficient sample** for reliable claims (31 fixtures with history; test n≈10 per market) |
| In-play next goal team | Small positive lift (+1.7% accuracy vs baseline) on n=58 test |
| In-play goal minute bucket | Large lift (+27.6% accuracy) — likely driven by minute-correlated pressure windows; needs larger holdout before promotion |
| Pre-match first goal / goal range | No meaningful improvement; pressure hurt first-goal accuracy on tiny test set |

**Recommendation:** `PRESSURE_MEDIUM_VALUE` (in-play research signal) with **pre-match classified as `PRESSURE_INSUFFICIENT_DATA`**. Do **not** promote to production without expanded coverage and out-of-sample confirmation.

---

## 1. Dataset coverage

| Metric | Value |
|--------|-------|
| Fixtures with pressure (DB) | 65 |
| Pressure records | 12,676 |
| Avg rows / fixture | ~195 |
| Leagues | Champions League, Europa League, Conference League |
| Pre-match dataset rows | 65 |
| Pre-match rows with rolling pressure history | 31 (47.7%) |
| In-play dataset rows | 177 (one row per scored goal event) |
| In-play rows with pressure features | 177 (100%) |
| Unusable fixtures | 0 |

**Artifacts:** `artifacts/phase54h1_pressure_shadow_backtest/`

- `pressure_prematch_dataset.parquet`
- `pressure_inplay_dataset.parquet`
- `pressure_dataset_summary.json`
- `unusable_pressure_fixtures.csv`
- `backtest_results.json`
- `leakage_audit.json`
- `feature_importance.json`
- `validation.json`

---

## 2. Sample sizes

### Temporal split

| Split | Pre-match | In-play |
|-------|-----------|---------|
| Train | 44 fixtures | 118 goal events |
| Test | 21 fixtures | 58 goal events |

### ML evaluation (pressure_available filter)

| Market | Train n | Test n | Sufficient? |
|--------|---------|--------|-------------|
| Pre-match first goal team | 20 | 10 | Borderline — **do not overclaim** |
| Pre-match goal range | 20 | 10 | Borderline — **do not overclaim** |
| In-play next goal team | 118 | 58 | Adequate for shadow screening |
| In-play goal minute bucket | 118 | 58 | Adequate for shadow screening |

Minimum thresholds used: train ≥ 8, test ≥ 5.

---

## 3. Pre-match results

Rolling pressure from **strictly prior fixtures** only (no current-match leakage).

### First goal team (binary home/away)

| Arm | Accuracy | Log-loss | Brier | ECE | Test n |
|-----|----------|----------|-------|-----|--------|
| A — EGIE baseline | 0.600 | 2.103 | 0.427 | 0.477 | 10 |
| B — baseline + pressure | 0.500 | 5.105 | 0.500 | 0.493 | 10 |
| C — pressure only | 0.500 | 5.079 | 0.500 | 0.500 | 10 |
| D — pressure-lite | 0.200 | 3.959 | 0.722 | 0.751 | 10 |

**Δ B vs A:** accuracy −10.0% (worse)

### Goal range (0-15 / 16-30 / 31-45+)

| Arm | Accuracy | Log-loss | Test n |
|-----|----------|----------|--------|
| A — baseline | 0.300 | 5.752 | 10 |
| B — baseline + pressure | 0.300 | 5.280 | 10 |
| C — pressure only | 0.300 | 5.220 | 10 |
| D — pressure-lite | 0.300 | 3.980 | 10 |

**Δ B vs A:** accuracy 0.0% (flat); log-loss improved slightly

**Pre-match verdict:** With only **10 test fixtures** and **31** with any pressure history, pre-match markets are **`PRESSURE_INSUFFICIENT_DATA`** for performance claims.

---

## 4. In-play results

Pressure aggregated from minute-level rows with **minute < goal minute** (no post-goal leakage).

### Next goal team

| Arm | Accuracy | Log-loss | Brier | ECE | Test n |
|-----|----------|----------|-------|-----|--------|
| A — baseline | 0.638 | 0.756 | 0.245 | 0.194 | 58 |
| B — baseline + pressure | 0.655 | 1.108 | 0.286 | 0.268 | 58 |
| C — pressure only | 0.638 | 1.136 | 0.294 | 0.282 | 58 |
| D — pressure-lite | 0.638 | 1.123 | 0.299 | 0.251 | 58 |

**Δ B vs A:** accuracy +1.7%

Pressure adds a small accuracy lift for next-goal team but worsens calibration (higher ECE / Brier). Combined arm (B) is marginally better on accuracy only.

### Goal minute bucket

| Arm | Accuracy | Log-loss | Test n |
|-----|----------|----------|--------|
| A — baseline | 0.672 | 1.095 | 58 |
| B — baseline + pressure | **0.948** | 0.345 | 58 |
| C — pressure only | **0.948** | 0.352 | 58 |
| D — pressure-lite | 0.655 | 0.980 | 58 |

**Δ B vs A:** accuracy +27.6%

**Caution:** High accuracy likely reflects that in-play pressure windows (`pressure_first_30`, `pressure_last_5`, spike counts) correlate strongly with elapsed match time, which proxies the goal-minute bucket. Leakage audit passed (features use only minutes before the goal), but this market needs a **held-out league/season** validation before any promotion discussion.

---

## 5. A/B comparison (Arm B vs Arm A)

| Market | Δ Accuracy | Δ Log-loss | Interpretation |
|--------|------------|------------|----------------|
| Pre-match first goal team | −10.0% | +3.00 | Harmful on tiny sample |
| Pre-match goal range | 0.0% | −0.47 | Neutral |
| In-play next goal team | +1.7% | +0.35 | Weak positive (accuracy only) |
| In-play goal minute bucket | +27.6% | −0.75 | Strong but minute-proxy risk |

**Average Δ accuracy (all four):** +4.8% → triggers `PRESSURE_MEDIUM_VALUE` in automated scorer, but **pre-match cells should be excluded** from that average for decision-making.

---

## 6. Pressure-only result (Arm C)

| Market | Accuracy vs A | Notes |
|--------|---------------|-------|
| Pre-match first goal | 0.500 vs 0.600 | Worse than baseline |
| Pre-match goal range | 0.300 vs 0.300 | Tie |
| In-play next goal | 0.638 vs 0.638 | Tie |
| In-play goal minute | 0.948 vs 0.672 | Large lift without EGIE baseline features |

Pressure alone cannot replace EGIE baselines for pre-match markets. In-play goal-minute bucket is the only market where pressure-only matches combined arm — again with minute-proxy caveat.

---

## 7. Pressure-lite result (Arm D)

Lite features: `pressure_first_15_*`, `pressure_dominance`, `pressure_momentum`, `pressure_swing`.

| Market | Accuracy vs A |
|--------|---------------|
| Pre-match first goal | 0.200 vs 0.600 (much worse) |
| Pre-match goal range | 0.300 vs 0.300 (tie) |
| In-play next goal | 0.638 vs 0.638 (tie) |
| In-play goal minute | 0.655 vs 0.672 (slightly worse) |

**Lite arm underperforms** full pressure set on in-play goal-minute bucket. Do not use lite subset for that market.

---

## 8. Feature importance

Pooled from Arm B across all markets (18 pressure features ranked):

| Bucket | Features |
|--------|----------|
| **Strongest positive** | `pressure_spike_count_away`, `pressure_before_first_goal_away` |
| **Weak positive** | `pressure_momentum`, `pressure_first_15_home`, `pressure_before_first_goal_home`, `pressure_spike_count_home`, `pressure_last_5_away`, `pressure_first_30_away`, `pressure_swing`, `pressure_last_5_home` |
| **Neutral** | `home_avg_pressure`, `pressure_difference`, `pressure_first_15_away` |
| **Harmful / low signal** | `away_avg_pressure`, `pressure_first_30_home`, `pressure_last_10_*`, `pressure_dominance` |

### Special attention features

| Feature | Importance sum |
|---------|----------------|
| `pressure_spike_count_away` | 0.661 |
| `pressure_before_first_goal_away` | 0.543 |
| `pressure_momentum` | 0.334 |
| `pressure_first_15_home` | 0.322 |
| `pressure_swing` | 0.171 |
| `pressure_dominance` | 0.026 (low) |

Early-window and spike features dominate; rolling pre-match averages are weaker.

---

## 9. Leakage audit result

**Status: PASS** (65 fixtures audited)

| Check | Result |
|-------|--------|
| No forbidden keys in pre-match features | PASS |
| First fixture per team has no pressure history | PASS |
| In-play uses pressure before target minute only | PASS (139 spot checks) |
| No final score in feature columns | PASS |
| No future fixture leakage | PASS |

---

## 10. Safety compliance

| Rule | Status |
|------|--------|
| No production prediction changes | ✅ Shadow package only |
| No WDE changes | ✅ Not imported by WDE |
| No SaaS changes | ✅ Not imported by SaaS |
| No deploy | ✅ Artifacts only |
| No EGIE scoring changes | ✅ |
| No live pressure use | ✅ |
| No token leaks | ✅ Validated |

---

## 11. Recommendation

### Primary: `PRESSURE_MEDIUM_VALUE` (in-play research)

Continue shadow research on **in-play next goal team** and **goal minute bucket** with expanded fixture coverage (target ≥ 200 pressure fixtures, ≥ 50 test per market).

### Secondary: `PRESSURE_INSUFFICIENT_DATA` (pre-match)

Do **not** claim pre-match first-goal or goal-range improvement until rolling history coverage exceeds ~50% of fixtures and test n ≥ 30.

### Not recommended now

- Production promotion
- Pressure-lite arm
- Pre-match pressure integration

### Suggested next phase

1. Backfill pressure for remaining UEFA cache fixtures (80 → full coverage).
2. Re-run 54H-1 with league-held-out validation for goal-minute bucket.
3. If in-play next-goal lift holds at +2–5% on n≥100 test, design a **shadow live logger** (no user-facing prediction change).

---

## Module map

| Component | Path |
|-----------|------|
| Feature builder | `worldcup_predictor/egie/pressure_backtest/pressure_feature_builder.py` |
| Dataset builder | `worldcup_predictor/egie/pressure_backtest/pressure_dataset_builder.py` |
| Backtest runner | `worldcup_predictor/egie/pressure_backtest/pressure_backtest_runner.py` |
| Leakage audit | `worldcup_predictor/egie/pressure_backtest/pressure_leakage_audit.py` |
| CLI | `scripts/phase54h1_pressure_shadow_backtest.py` |
| Validation | `scripts/validate_phase54h1_pressure_shadow_backtest.py` |

---

**STOP** — Phase 54H-1 complete. No deploy. No live prediction changes.

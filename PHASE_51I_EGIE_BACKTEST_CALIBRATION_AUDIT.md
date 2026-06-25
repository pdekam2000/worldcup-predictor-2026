# PHASE 51I — EGIE Backtest Calibration & Evaluation Policy Audit

**Status:** completed  
**Mode:** READ ONLY — no code changes, no deploy, no database writes  
**Source data:** `artifacts/phase51h_egie_backtest.jsonl` (359 fixtures, Phase 51H)  
**Machine-readable output:** `artifacts/phase51i_egie_calibration_audit.json`

---

## Executive Summary

Phase 51H reports modest First Goal Team accuracy (50.8%) but this headline **overstates** commercial performance. **43.5% of published predictions (152/349) abstain with `first_goal_team = none`**, and current evaluation Policy A excludes those from the win-rate denominator. Under Policy B (count abstentions as wrong when a goal occurs), team win rate **falls to 28.7%**.

Goal Range (27.8%) is only modestly above a 6-bucket random baseline (~16.7%) and suffers from **severe early-goal bias** in predictions. Goal Minute is **not production-viable** at any public tolerance (3.4% exact, 33.8% at ±10).

**Highest-impact findings before Survival Analysis / Recalibration / Multi-LLM:**

1. The `none` abstention rule (`|home_rate − away_rate| < 0.04`) fires on nearly half of fixtures — the dominant performance limiter.
2. Evaluation Policy A materially inflates reported team accuracy.
3. Display confidence is **miscalibrated** (inverted across buckets; 92% of fixtures capped at 0.65).
4. Goal Range predictions cluster in 0–15 / 16–30 while actual first goals are more spread (31–45+ underrepresented).
5. DQ threshold sweep is **non-informative** on this cohort — DQ is bimodal (0.4286 vs 0.5714 only).

---

## Part A — Predicted `none` Audit

### Scale

| Metric | Value |
|--------|-------|
| Total `none` cases (goal occurred) | **152** |
| % of all fixtures (359) | **42.3%** |
| % of published (349) | **43.6%** |

All 152 cases have `first_goal_team_status = pending` under Policy A.

### Why is the engine producing `none`?

**Root cause (code, not data anomaly):**

```128:130:worldcup_predictor/goal_timing/models_stat/baseline.py
        if abs(home_rate - away_rate) < 0.04:
            return "none"
        return "home" if home_rate > away_rate else "away"
```

When empirical first-goal scoring rates (plus small agent nudges from pressure, threat, tactical flow) differ by **less than 4 percentage points**, the baseline model **refuses a directional pick**. This is an intentional abstention rule, not a data-quality failure.

**Supporting evidence from the 152 cases:**

- All have DQ = **0.5714** (same as directional picks) — abstention is **not** caused by low DQ.
- **136/152 (89%)** fall in the 0.65–0.70 confidence bucket (confidence cap artifact).
- Actual first-goal team split: **home 81 (53%)**, **away 71 (47%)** — outcomes are not skewed; the model simply cannot separate sides.
- Range is still published on all 152 cases; **72.4%** have wrong range predictions despite team abstention.

### Distribution

| Dimension | Finding |
|-----------|---------|
| **DQ bucket** | 100% in `dq_0.55_0.60` (DQ = 0.5714) |
| **Confidence** | 0.55–0.60: 7 · 0.60–0.65: 9 · **0.65–0.70: 136** |
| **League** | 100% `premier_league` |
| **Season** | 100% 2023/24 |
| **Actual first-goal team** | home 53% · away 47% |

### Actual first-goal minute histogram (`none` cases)

| Range | Count |
|-------|-------|
| 0–15 | 53 |
| 16–30 | 42 |
| 31–45 | 26 |
| 46–60 | 12 |
| 61–75 | 13 |
| 76–90+ | 6 |

Early goals are common in abstention cases (62% in first 30 minutes), but the engine still publishes a range — creating a product inconsistency (no team edge, but a time edge).

### Most common teams involved (appearances in `none` fixtures)

| Team | Appearances |
|------|-------------|
| Sheffield Utd | 24 |
| Fulham | 18 |
| West Ham | 17 |
| Nottingham Forest, Brentford, Wolves, Newcastle, Man Utd, Everton, Burnley | 16 each |

**Sheffield Utd** (promoted, thin history) appears in 24/152 abstention fixtures — highest single-team involvement.

Full fixture ID list: `artifacts/phase51i_egie_calibration_audit.json` → `part_a_predicted_none.all_fixture_ids`

---

## Part B — Evaluation Policy Audit

### Policy definitions

| Policy | Rule when `predicted = none` and goal occurred |
|--------|------------------------------------------------|
| **A (current)** | `pending` — excluded from denominator |
| **B (strict)** | `wrong` — included in denominator |
| **C (separate market)** | Team pick market excludes `none`; abstention evaluated as separate "no directional edge" product |

### Results — First Goal Team

| Policy | Correct | Wrong | Pending | Denominator | Win rate |
|--------|---------|-------|---------|-------------|----------|
| **A** | 100 | 97 | 152 | 197 | **50.8%** |
| **B** | 100 | 249 | 0 | 349 | **28.7%** |
| **C — directional picks only** | 100 | 97 | 0 | 197 | **50.8%** |
| **C — no-edge market** | 0 | 152 | 0 | 152 | **0.0%** |

### Calibration effect (mean confidence)

| Policy | Mean conf (correct) | Mean conf (wrong) | n |
|--------|---------------------|-------------------|---|
| A | 0.6455 | 0.6491 | 197 |
| B | 0.6455 | 0.6464 | 349 |

Confidence does **not** separate correct from wrong under any policy — confirming miscalibration.

### Trust impact

- **Policy A** inflates headline win rate by excluding 43.5% of published outputs.
- **Policy B** is statistically honest but harsh — treats abstention as failure when any goal occurs.
- **Policy C** is commercially correct: publish two products — **directional pick** (when team ≠ none) and **no-edge / abstain** (when team = none).

**Recommendation:** **Policy C** for user-facing product; **Policy B** for internal model QA.

---

## Part C — DQ Threshold Sweep

> **Cohort limitation:** DQ is bimodal — `0.4286` (10 early-season NO_PICK fixtures) and `0.5714` (349 published). No continuous DQ gradient exists in this backtest. Thresholds ≥ 0.58 exclude the entire cohort. Lowering below 0.45 adds 10 fixtures **without stored predictions** (cannot score markets from artifact alone).

| Threshold | Fixtures ≥ threshold | NO_PICK below | With predictions | Team WR (A) | Range WR | Minute soft | Coverage |
|-----------|----------------------|---------------|------------------|-------------|----------|-------------|----------|
| 0.35 | 359 | 0 | 349 | 50.8% | 27.8% | 33.8% | 97.2% |
| 0.40 | 359 | 0 | 349 | 50.8% | 27.8% | 33.8% | 97.2% |
| **0.45** | **349** | **10** | **349** | **50.8%** | **27.8%** | **33.8%** | **97.2%** |
| 0.50 | 349 | 10 | 349 | 50.8% | 27.8% | 33.8% | 97.2% |
| 0.55 | 349 | 10 | 349 | 50.8% | 27.8% | 33.8% | 97.2% |
| 0.60 | 0 | 359 | 0 | — | — | — | 0% |
| 0.65 | 0 | 359 | 0 | — | — | — | 0% |
| 0.70 | 0 | 359 | 0 | — | — | — | 0% |

**Optimal threshold: 0.45** — correctly gates 10 early-season fixtures with insufficient local history (DQ 0.4286). Raising provides no accuracy gain; lowering adds unscored fixtures.

---

## Part D — Confidence Calibration Audit

| Bucket | Count | Team WR (A) | Range WR | Minute soft | `none` preds |
|--------|-------|-------------|----------|-------------|--------------|
| 0.45–0.50 | 0 | — | — | — | 0 |
| 0.50–0.55 | 0 | — | — | — | 0 |
| 0.55–0.60 | 11 | 75.0% | 18.2% | 27.3% | 7 |
| 0.60–0.65 | 18 | 77.8% | 11.1% | 16.7% | 9 |
| **0.65–0.70** | **320** | **48.9%** | **29.1%** | **35.0%** | **136** |

### Monotonicity: **FAILED**

Higher displayed confidence does **not** predict better team accuracy. The 0.65–0.70 bucket (92% of sample) underperforms smaller low-confidence buckets on team market.

### Root causes

1. **Confidence cap at 0.65** when DQ < 0.70 (`minute_display.py`) — all 349 published fixtures have DQ 0.5714, so nearly all confidence scores cluster at the cap.
2. **Abstention inflation** — 136/320 (42.5%) of the high-confidence bucket are `none` predictions.
3. **Low-confidence buckets are tiny** (n=29 combined) with proportionally fewer abstentions, inflating their win rates.

**Recalibration is required** before confidence can be used for gating, staking, or user trust.

---

## Part E — Goal Range Analysis

| Range | Predictions | Correct | Win rate | Actual count | Actual % |
|-------|-------------|---------|----------|--------------|----------|
| **0–15** | **191** | 61 | **31.9%** | 118 | 33.8% |
| 16–30 | 115 | 30 | 26.1% | 96 | 27.5% |
| 31–45+ | 4 | 1 | 25.0% | 56 | 16.0% |
| 46–60 | 29 | 5 | 17.2% | 40 | 11.5% |
| 61–75 | 6 | 0 | **0.0%** | 24 | 6.9% |
| 76–90+ | 4 | 0 | **0.0%** | 15 | 4.3% |

**Random baseline (6 buckets):** ~16.7%  
**Aggregate win rate:** 27.8%

### Systematic bias

- **Over-predicted:** 0–15 (54.7% of preds vs 33.8% actual), 16–30 (32.9% vs 27.5%)
- **Under-predicted:** 31–45+ (1.1% vs 16.0%), 61–75, 76–90+
- **Strongest range:** 0–15 (31.9% — best but still weak)
- **Weakest ranges:** 61–75 and 76–90+ (0% on tiny samples)

The model's `max(probability)` range selection compresses mass into early buckets because blended team/league priors skew early — it fails to capture the substantial 31–45+ first-goal rate.

---

## Part F — Goal Minute Policy Analysis

| Tolerance | Hit rate | Hits | Sample |
|-----------|----------|------|--------|
| ±3 min | 14.0% | 49 | 349 |
| ±5 min | 22.9% | 80 | 349 |
| ±7 min | 27.8% | 97 | 349 |
| ±10 min | 33.8% | 118 | 349 |
| **Exact (0)** | **3.4%** | **8** | **349** |

Display minute is a **fixed bucket midpoint** (8, 23, 38, 53, 68, 83) — not a distributional estimate.

### Public display recommendation

| Show | Recommendation |
|------|----------------|
| Exact minute | **No** — 3.4% hit rate |
| Goal range (primary) | **Yes** — best honest metric |
| Soft band ±7 | **Yes** — 27.8%, meaningful for power users |
| Soft band ±10 | Optional internal only — 33.8% |

---

## Part G — Team & League Analysis

### Home vs Away (directional picks only, n=197)

| Side | Picks | Win rate |
|------|-------|----------|
| Home | 97 | **58.8%** |
| Away | 100 | **43.0%** |

Home-first-goal picks outperform — likely reflecting home-first-goal base rate, not model superiority.

### Best teams when picked (≥5 picks)

| Team | Picks | Win rate |
|------|-------|----------|
| Arsenal | 12 | 83.3% |
| Newcastle | 11 | 81.8% |
| Manchester City | 15 | 73.3% |
| Bournemouth | 14 | 64.3% |

### Worst teams when picked (≥5 picks)

| Team | Picks | Win rate |
|------|-------|----------|
| Brighton | 7 | 14.3% |
| Sheffield Utd | 10 | 20.0% |
| West Ham | 8 | 25.0% |
| Luton | 8 | 25.0% |

### Promoted teams (2023/24)

| Team | Appearances | `none` rate | Picked WR |
|------|-------------|-------------|-----------|
| Sheffield Utd | 36 | **66.7%** | 20.0% |
| Burnley | 36 | 44.4% | 36.4% |
| Luton | 36 | 38.9% | 25.0% |

**EGIE works best** on established top sides when it commits a directional pick. **EGIE works worst** on promoted/thin-history clubs and any fixture where abstention fires.

---

## Part H — Pre-Survival Analysis Readiness

| Market | Potential gain | Rationale |
|--------|--------------|-----------|
| **Goal Range** | **High** | 27.8% vs 16.7% baseline; severe bucket bias; hazard curves model time-to-first-goal directly |
| **Goal Minute** | **High** | Point estimates from bucket midpoints fail; survival gives full distributional forecasts |
| **First Goal Team** | **Medium** | Abstention rule hides uncertainty; survival/competing-risks can output proper team probabilities instead of binary `none` |

**Highest-ROI next upgrade:** Survival analysis targeting **range + minute** first; team market benefits from replacing `none` with calibrated probabilities.

---

## Final Answers

### 1. Should predicted `none` be counted as wrong?

**Not as a directional pick miss.** Use **Policy C**: evaluate directional picks separately; treat `none` as an abstention product (0% when goals occur under current framing). Use **Policy B** internally for honest model QA.

### 2. Should DQ remain at 0.45?

**Yes.** It correctly excludes 10 early-season fixtures (DQ 0.4286). The backtest cohort has no DQ gradient above 0.45 — further tuning requires richer per-fixture DQ scoring, not threshold changes alone.

### 3. Should confidence be recalibrated?

**Yes — mandatory.** Confidence is inverted across buckets, capped at 0.65 for all published fixtures, and uncorrelated with outcomes. Do not use current confidence for staking or user-facing trust signals.

### 4. Should exact minute remain public?

**No.** Show **goal range** as primary; optional **±7 soft band** for advanced users. Exact minute (3.4%) damages trust.

### 5. Which market is production-ready?

**First Goal Team — directional picks only** (Policy C, n=197, ~51%) — marginal edge, requires abstention reframing. Not ready for automated staking.

### 6. Which market should remain experimental?

**Goal Range** and **Goal Minute** (all tolerances). Range is above random but commercially weak; minute is not viable.

### 7. Is Survival Analysis the highest-ROI next upgrade?

**Yes** — especially for range and minute markets. Medium ROI for team market via probabilistic replacement of `none`. Higher ROI than adding leagues or Multi-LLM layer **before** fixing abstention and calibration fundamentals.

---

## Artifacts

| File | Description |
|------|-------------|
| `artifacts/phase51i_egie_calibration_audit.json` | Full structured audit (152 fixture IDs, all metrics) |
| `artifacts/phase51h_egie_backtest.jsonl` | Source backtest per-fixture records |
| `PHASE_51H_EGIE_HISTORICAL_BACKTEST_REPORT.md` | Phase 51H baseline report |

---

**Phase 51I complete. No implementation. No deploy. No code changes.**

# PHASE 52B — EGIE Ensemble + Confidence Recalibration Audit

**Status:** completed  
**Mode:** READ ONLY / SHADOW ONLY — no production activation  
**Source:** `data/egie/survival/survival_shadow_predictions.jsonl` (359 fixtures, 349 published)  
**Machine-readable output:** `artifacts/phase52b_ensemble_calibration.json`

---

## Executive Summary

The **hybrid ensemble (Strategy C)** — baseline First Goal Team + survival range/minute — **beats both models individually** on timing markets while **preserving baseline team accuracy**. It is the recommended shadow configuration for Phase 52C experimentation.

| Strategy | Team | Goal Range | Soft Minute |
|----------|------|------------|-------------|
| A — Baseline only | **50.8%** | 27.8% | 33.8% |
| B — Survival only | 49.3% | **31.0%** | **38.4%** |
| **C — Hybrid** | **50.8%** | **31.0%** | **38.4%** |
| D — Weighted 70/30 + 40/60 | 49.3% | 27.8% | 33.8% |
| E — Conditional (best th=0.05) | 49.3% | 28.7% | 36.4% |

**Activation gates: NOT MET** — continue shadow only.

| Criterion | Required | Best (C) | Met |
|-----------|----------|----------|-----|
| First Goal Team | ≥50.8% | 50.8% | Borderline (equal, not greater) |
| Goal Range | >35% | 31.0% | **No** |
| Soft Minute | >40% | 38.4% | **No** |
| Confidence monotonic | Yes | **No** | **No** |

**DEPLOY_ALLOWED = False**

---

## Part 1 — Ensemble Audit

### Strategy definitions

| ID | Rule |
|----|------|
| **A** | Baseline EGIE only |
| **B** | Survival shadow only |
| **C** | Baseline `first_goal_team` + Survival `range` + Survival `minute` |
| **D** | Team: baseline if directional else survival; Range: 40% baseline one-hot + 60% survival probs (argmax); Minute from blended range |
| **E** | If survival range margin ≥ threshold → survival range/minute + baseline/survival team; else baseline |

### Results (349 published fixtures)

| Strategy | Team WR | Range WR | Soft Minute | Δ Range vs A | Δ Soft vs A |
|----------|---------|----------|-------------|--------------|-------------|
| A Baseline | 50.8% | 27.8% | 33.8% | — | — |
| B Survival | 49.3% | 31.0% | 38.4% | +3.2pp | +4.6pp |
| **C Hybrid** | **50.8%** | **31.0%** | **38.4%** | **+3.2pp** | **+4.6pp** |
| D Weighted | 49.3% | 27.8% | 33.8% | 0 | 0 |
| E Conditional (0.05) | 49.3% | 28.7% | 36.4% | +0.9pp | +2.6pp |

### Key findings

1. **Strategy C is strictly dominant** over A and B in combination — it inherits baseline team picks (including NONE abstention) and survival timing outputs.
2. **Weighted blend (D) fails** — blending baseline one-hot range with survival probabilities often **reverts to baseline range** (27.8%), eliminating survival's timing gain.
3. **Conditional ensemble (E)** improves modestly over baseline but underperforms C; optimal threshold sweep (0.05–0.25) never reaches survival-only range accuracy.
4. **Brier scores** (team/range probability vectors) are identical across strategies in this cohort (0.504 / 0.800) — ensembles change discrete picks, not underlying probability tensors in shadow data.

### Recommendation

Adopt **Strategy C** as the shadow ensemble reference architecture:

```
first_goal_team      ← EliteGoalTimingEngine (unchanged)
first_goal_time_range ← SurvivalGoalTimingEngine
display_minute       ← SurvivalGoalTimingEngine
range_probabilities  ← Survival (expose in UI internally)
```

---

## Part 2 — Confidence Recalibration

### Current baseline buckets (broken monotonicity)

| Confidence | Count | Team ACC | Range ACC | Soft Minute |
|------------|-------|----------|-----------|-------------|
| 0.55–0.60 | 11 | **75.0%** | 18.2% | 27.3% |
| 0.60–0.65 | 18 | **77.8%** | 11.1% | 16.7% |
| **0.65–0.70** | **320** | **48.9%** | 29.1% | 35.0% |

**92% of fixtures cluster at 0.65 cap** (DQ < 0.70 rule). Higher displayed confidence **underperforms** lower buckets on team market — confirms Phase 51I.

### Calibration methods tested (baseline confidence → hit rate)

| Market | Pairs | Isotonic ECE | Logistic ECE | Mean conf | Mean hit |
|--------|-------|--------------|--------------|-----------|----------|
| First Goal Team | 197 | 0.500 | 0.500 | 0.647 | 0.508 |
| Goal Range | 349 | 0.397 | 0.401 | 0.646 | 0.278 |
| Soft Minute | 349 | 0.443 | 0.448 | 0.646 | 0.338 |

**Interpretation:** Confidence is **poorly calibrated** — mean confidence (~0.65) far exceeds mean hit rate on range (0.28) and minute soft (0.34). Isotonic/logistic on the current single scalar **cannot fix** the cap-induced compression without new features.

### Survival confidence buckets

Survival replicates the same cap structure but shows **better range calibration in low buckets** (0.55–0.60 range ACC 54.5% vs baseline 18.2%) — survival range probabilities carry more signal than the display confidence scalar.

---

## Part 3 — Proposed Confidence Redesign

### Recommended formula (shadow evaluation)

```
display_confidence =
  0.30 × DQ
+ 0.20 × survival_range_margin     # max(prob) - second_max(prob)
+ 0.15 × team_model_agreement      # baseline.team == survival.team
+ 0.15 × range_model_agreement     # baseline.range == survival.range
+ 0.20 × historical_bucket_prior   # backtest bucket hit rate proxy
```

### Components

| Signal | Purpose |
|--------|---------|
| **Model agreement** | High when baseline + survival align → higher trust |
| **Range probability margin** | Survival certainty on timing bucket |
| **DQ** | Data depth / event coverage |
| **Historical bucket performance** | Shrink confidence in weak buckets (e.g. 0–15 over-prediction) |
| **Survival agreement** | Timing layer consensus |

### Prototype evaluation

| Bucket | Count | Team ACC |
|--------|-------|----------|
| b1 (low) | 66 | 51.5% |
| b2 | 72 | 51.4% |
| b3 | 58 | 50.0% |
| b4 | 1 | 0.0% |

**Monotonic: FAILED** — prototype needs hold-out calibration fit, not fixed weights.

### Recalibration path (Phase 52C+)

1. **Remove 0.65 cap** when DQ < 0.70 — replace with continuous DQ-scaled ceiling
2. **Per-market confidence** — team, range, minute separate scores
3. **Isotonic regression** on hold-out set using proposed features (not raw capped scalar)
4. **Bucket calibration table** for UI display bands

---

## Part 4 — Backtest Summary

| Model | Team | Range | Soft Min | Brier Team | Brier Range |
|-------|------|-------|----------|------------|-------------|
| Baseline | 0.508 | 0.278 | 0.338 | 0.504 | 0.800 |
| Survival | 0.493 | 0.310 | 0.384 | 0.504 | 0.800 |
| **Hybrid C** | **0.508** | **0.310** | **0.384** | 0.504 | 0.800 |

**Coverage:** 349 published / 10 NO_PICK (unchanged across strategies using baseline team gating).

---

## Part 5 — Activation Recommendation

| Gate | Status |
|------|--------|
| Goal Range > 35% | **FAIL** (31.0%) |
| Soft Minute > 40% | **FAIL** (38.4%) |
| Team ≥ 50.8% | **FAIL** (equal at 50.8%, not improved) |
| Confidence monotonic | **FAIL** |

### Verdict

- **Production activation: NOT ALLOWED**
- **Shadow promotion: NOT RECOMMENDED** yet
- **Shadow ensemble C: RECOMMENDED** for continued observation — best known combined performance
- **Next phase:** Tune survival range blend + per-market isotonic calibration on hold-out; target 35%/40% gates before any production wiring

---

## Artifacts

| File | Description |
|------|-------------|
| `artifacts/phase52b_ensemble_calibration.json` | Full structured audit |
| `data/egie/survival/survival_shadow_predictions.jsonl` | Phase 52A shadow source |
| `artifacts/phase52a_survival_results.json` | Phase 52A baseline comparison |

---

**Phase 52B complete. No production changes. No deploy.**

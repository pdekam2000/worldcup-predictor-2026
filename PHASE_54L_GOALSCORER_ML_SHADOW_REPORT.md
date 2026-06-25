# PHASE 54L — Goalscorer ML Shadow Engine

**Date:** 2026-06-24  
**Mode:** ML Research → Calibration → Backtest → Report  
**Status:** Complete — validation **16/16 PASS**  
**API calls:** 0

---

## Executive summary

Trained **Logistic Regression**, **LightGBM**, and **Simple Ensemble** on 47,029 player-fixture rows (temporal split preserved). **ML materially improves Anytime Goalscorer ranking** (+4.3pp top-3 vs combined baseline). First Goal and Most Likely show smaller or mixed gains. **Platt/Isotonic calibration** dramatically improves probability quality (ECE 0.36 → 0.01).

### Final recommendation: **`GOALSCORER_MEDIUM_VALUE`**

Goalscorer ML is a credible EGIE research asset for **Anytime** markets; not yet a top-tier production signal without odds integration and larger test coverage.

---

## Dataset (Part A)

| Split | Rows |
|-------|------|
| Train | 32,920 |
| Validation | 7,054 |
| Test | 7,055 |
| Test fixtures | 209 |

Source: `artifacts/phase54k_goalscorer_shadow/goalscorer_dataset.parquet`

---

## Feature sets (Part B)

| Group | Features |
|-------|----------|
| A — Form | goals_last_3/5/10, assists_last_5, recent_form_score |
| B — Shots | shots_last_5, shots_on_target_last_5 |
| C — xG | xg_last_5/10, xg_per_90 |
| D — Lineup | starter_probability, lineup_status, expected_minutes, captain |

**CatBoost:** not installed — skipped (optional).

---

## Models & ranking (Parts C–D)

### Anytime Goalscorer (209 test fixtures)

| Model | Top-1 | Top-3 | Top-5 | P@3 |
|-------|-------|-------|-------|-----|
| combined_baseline | 25.8% | 56.5% | 66.0% | 23.3% |
| lightgbm | 27.3% | 56.0% | 70.3% | 23.9% |
| ensemble | 30.1% | 59.3% | 70.8% | 25.8% |
| **logistic_regression** | **30.6%** | **60.8%** | **71.3%** | **26.0%** |

### First Goalscorer (178 fixtures)

| Model | Top-1 | Top-3 | Top-5 | MRR |
|-------|-------|-------|-------|-----|
| combined_baseline | 12.4% | 33.7% | 43.8% | 0.279 |
| ensemble | 13.5% | 33.7% | 45.5% | 0.300 |
| **logistic_regression** | **16.3%** | **36.5%** | **50.6%** | **0.332** |

### Most Likely Scorer (189 fixtures)

| Model | Top-1 | Top-3 | Top-5 | MRR |
|-------|-------|-------|-------|-----|
| **combined_baseline** | 9.0% | **31.8%** | **43.4%** | 0.262 |
| logistic_regression | 12.2% | 31.8% | 47.1% | 0.293 |
| lightgbm | 7.4% | 22.2% | 31.2% | 0.205 |
| ensemble | 12.2% | 27.0% | 39.2% | 0.261 |

---

## Calibration (Part E)

Ensemble model, test set:

| Market | Method | ECE | Brier |
|--------|--------|-----|-------|
| Anytime | raw | 0.362 | 0.208 |
| Anytime | **platt** | **0.009** | **0.062** |
| Anytime | isotonic | 0.007 | 0.062 |
| First goal | raw | 0.308 | 0.159 |
| First goal | platt | 0.003 | 0.024 |
| Most likely | platt | 0.001 | 0.026 |

**Calibration is highly useful** for research probabilities; raw scores are poorly calibrated.

---

## Feature importance (Part F)

**Most valuable (anytime):**
1. recent_form_score
2. xg_per_90 / xg_last_10 / xg_last_5
3. shots_on_target_last_5
4. starter_probability
5. goals_last_5/10

**Redundant / low value:**
- `shots_last_5` (zero importance — superseded by SOT)
- `expected_minutes` (near-zero; correlates with starter_probability)

**Group importance (normalized):**
- xG: highest
- Form: second
- Lineup: meaningful
- Shots (SOT): moderate

---

## Odds overlay (Part G)

| Metric | Value |
|--------|-------|
| Test fixtures with cached odds | **0** |
| Agreement / disagreement | N/A |
| Worth integrating later | **No** (until odds cache overlaps test fixtures) |

---

## Report answers

### 1. Does ML beat baseline?

**Yes for Anytime and First Goal** (logistic regression best). **No for Most Likely** on top-3 (baseline wins; trees overfit).

### 2. Which model wins?

**Logistic Regression** — best top-3 anytime (60.8%) and first goal (36.5%). LightGBM underperforms on sparse rare targets.

### 3. Which features matter most?

Form + xG dominate; lineup status and starter_probability matter; shots_last_5 redundant.

### 4. Does xG help goalscorers?

**Yes** — xG group is highest importance block; xg_per_90 in top-3 features across markets.

### 5. Does lineup data help goalscorers?

**Yes** — lineup_status_starter and starter_probability consistently rank mid-high; eligibility gating remains essential.

### 6. Is calibration useful?

**Yes** — Platt/isotonic reduce ECE by ~97%; required before any probability interpretation.

### 7. Are odds worth integrating later?

**Potentially**, but **not yet** — zero test-fixture overlap with odds cache; 54M should ingest odds-rich fixtures aligned to test seasons.

### 8. Is goalscorer prediction one of the strongest EGIE assets?

**Emerging medium-value asset** — anytime top-3 ~61% beats many EGIE shadow markets at similar sample sizes, but below mature odds-primary markets. Not top-tier until odds + larger validation.

---

## Validation

**16/16 PASS** (`artifacts/phase54l_goalscorer_ml_shadow/validation.json`)

---

## Artifacts

| Path | Description |
|------|-------------|
| `artifacts/phase54l_goalscorer_ml_shadow/ml_shadow_report.json` | Full results |
| `artifacts/phase54l_goalscorer_ml_shadow/calibration_curves.json` | Calibration bins |
| `artifacts/phase54l_goalscorer_ml_shadow/test_predictions_anytime.parquet` | Test predictions |

---

**Phase 54L complete. No deploy. No live prediction changes. No EGIE scoring changes.**

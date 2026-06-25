# PHASE 54F — EGIE xG Backtest Arm Report

**Date:** 2026-06-23  
**Mode:** Implementation → Backtest → Validation → Report  
**Status:** COMPLETE (backtest only — no production changes, no deploy)

---

## Executive Summary

Phase 54F wired the Sportmonks xG Feature Store (Phase 54E) into EGIE as an **optional backtest arm**. The pipeline is functional, leakage-safe, and validated (**9/9 checks PASS**).

**Answer to “Does xG improve EGIE?”** — **Not demonstrably, on available data.**

With only **6 fixtures (7.5%)** having usable pre-match rolling xG features and **2–4 samples per ML split**, A/B results are statistically unreliable. xG features show signal in feature importance rankings, but Arm B does not beat baseline consistently.

**Recommendation:** `NO_VALUE` for production integration at this time.  
**Next step:** Expand xG coverage (WC 732 server backfill + full team `xg` metrics per fixture) before re-running this backtest — **not** Phase 54G Pressure Index yet.

---

## 1. Coverage

| Metric | Value |
|--------|-------|
| UEFA cache fixtures (EGIE dataset) | 80 |
| Feature store summaries (`fs_sportmonks_xg_fixture_summary`) | 71 |
| Summaries with post-match team `xg` | 8 |
| Fixtures with pre-match rolling xG (`xg_available=true`) | **6 (7.5%)** |
| xG records in store | 442 |
| Leagues | Champions League, Europa League, Conference League |
| Seasons | 10 season IDs (18283, 23616, 23619, 23620, 5308, 5310, 5311, 5321, 5322, 5326) |

### Coverage gap root cause

- 63 of 71 imported summaries lack `home_xg` / `away_xg` because UEFA cache payloads often contain only **xGoT** (`team_metric` / `xgot`) rows, not full team **xG** (`metric_key=xg`).
- Rolling features require **prior matches** with numeric team xG; with only 8 fixtures carrying team xG, most teams never accumulate enough history.
- Backtest evaluates **only** fixtures where `xg_available=true` (both sides have rolling pre-match xG from strictly prior matches).

### Artifacts

- `artifacts/phase54f_egie_xg_backtest/egie_baseline_dataset.parquet`
- `artifacts/phase54f_egie_xg_backtest/egie_baseline_plus_xg_dataset.parquet`
- `artifacts/phase54f_egie_xg_backtest/dataset_coverage.json`

---

## 2. A/B Results

**Arms**

| Arm | Description |
|-----|-------------|
| **A** | EGIE baseline features (`home_goal_rate_proxy`, `away_goal_rate_proxy`, `data_quality_score`, history samples) |
| **B** | Baseline + 20 Sportmonks rolling xG features |

**Method:** GradientBoostingClassifier, temporal split, xG-available fixtures only.  
**Markets tested:** First Goal Team, Goal Range, Team Goals (Over 2.5).  
**Not tested:** Live Goal Probability, Goal Minute (blocked — no pressure/event stores).

### First Goal Team (home vs away)

| Metric | Arm A (Baseline) | Arm B (+ xG) | Δ (B − A) |
|--------|------------------|--------------|-----------|
| Train / Test (xG rows) | 3 / 2 | 3 / 2 | — |
| Accuracy | 1.000 | 0.500 | **−0.500** |
| Log Loss | 0.0034 | 3.0360 | +3.0326 |
| Brier | 0.0000 | 0.5529 | +0.5529 |
| Calibration (ECE) | 0.0034 | 0.6661 | +0.6627 |
| ROI proxy | 0.000 | −0.500 | −0.500 |

### Goal Range (0–15 / 16–30 / 31–45+)

| Metric | Arm A | Arm B | Δ |
|--------|-------|-------|---|
| Train / Test | 3 / 2 | 3 / 2 | — |
| Accuracy | 1.000 | 0.500 | **−0.500** |
| Log Loss | 0.0034 | 3.0360 | +3.0326 |
| Precision / Recall | 1.0 / 1.0 | 1.0 / 0.5 | — |

### Team Goals (Over 2.5)

| Metric | Arm A | Arm B | Δ |
|--------|-------|-------|---|
| Train / Test | 4 / 2 | 4 / 2 | — |
| Accuracy | 0.500 | 1.000 | **+0.500** |
| Log Loss | 4.3917 | 0.0000 | −4.3917 |
| Brier | 0.4999 | 0.0000 | −0.4999 |
| Calibration (ECE) | 0.4986 | 0.0000 | −0.4986 |

### EGIE rule-based baseline (test set, xG fixtures)

On the 2 xG-available test fixtures, the existing EGIE rule engine achieved **50% first-goal accuracy** and **50% goal-range accuracy** (confidence band 0.50–0.65). This is reported for context only; ML arms above use separate feature sets.

---

## 3. Improvement Table (summary)

| Market | Δ Accuracy | Δ Log Loss | Δ Brier | Δ Calibration | Verdict |
|--------|------------|------------|---------|---------------|---------|
| First Goal Team | −0.50 | +3.03 | +0.55 | +0.66 | xG hurts |
| Goal Range | −0.50 | +3.03 | — | — | xG hurts |
| Team Goals | +0.50 | −4.39 | −0.50 | −0.50 | xG helps |
| **Average Δ accuracy** | **−0.17** | — | — | — | **Inconclusive / NO_VALUE** |

> **Caveat:** Test sets contain **2 fixtures per market**. Any single misclassification swings accuracy by 50%. Results must not be interpreted as production guidance.

---

## 4. Feature Importance (Top xG signals)

Pooled importance across all three markets (Arm B):

| Rank | Feature | Importance (sum) |
|------|---------|------------------|
| 1 | `home_recent_xg` | 1.031 |
| 2 | `rolling_xg_10_home` | 0.652 |
| 3 | `rolling_xg_10_away` | 0.354 |
| 4 | `rolling_xg_5_away` | 0.245 |
| 5 | `rolling_xg_3_home` | 0.137 |
| 6 | `rolling_xga_10_home` | 0.129 |
| 7 | `away_recent_xg` | 0.112 |
| 8 | `xg_difference` | 0.107 |
| 9 | `rolling_xg_5_home` | 0.105 |
| 10 | `rolling_xga_3_home` | 0.059 |
| 11 | `home_recent_xga` | 0.035 |
| 12 | `xg_momentum_difference` | 0.017 |
| 13 | `rolling_xg_3_away` | 0.015 |
| 14 | `attack_strength_difference` | 0.001 |
| 15 | `defensive_weakness_difference` | 0.001 |

**Baseline EGIE proxies** (`home_goal_rate_proxy`, `data_quality_score`, etc.) contributed **0.0** importance in Arm B — the model leaned entirely on xG rolling features when present.

**Interpretation:** Long-window home xG (`rolling_xg_10_home`, `home_recent_xg`) and xG difference are the strongest signals in-tree, but sample size prevents reliable generalization.

---

## 5. Leakage Audit

**Status: PASS** (71 fixture summaries audited)

| Check | Result |
|-------|--------|
| No post-match `home_xg` / `away_xg` in feature dict | PASS |
| First-match teams have no rolling without history | PASS |
| Temporal ordering (strictly prior matches) | PASS |
| No future events / pressure joined | PASS |
| Rolling ≠ current-match xG | PASS |

Artifact: `artifacts/phase54f_egie_xg_backtest/leakage_audit.json`

---

## 6. Validation

`python scripts/validate_phase54f_xg_backtest.py` → **9/9 PASS**

| Check | Status |
|-------|--------|
| xG backtest module imports | PASS |
| Feature store readable (442 records) | PASS |
| Dataset enriched | PASS |
| Coverage reported | PASS |
| A/B test completed (3 markets) | PASS |
| Leakage audit PASS | PASS |
| Feature importance generated (top 20) | PASS |
| No production changes | PASS |
| No deploy | PASS |

---

## 7. Recommendation

### xG integration value: **NO_VALUE**

**Rationale:**

1. **Coverage failure** — 7.5% of fixtures usable; cannot answer “Does xG improve EGIE?” with statistical confidence.
2. **Mixed A/B deltas** — First Goal and Goal Range regress with xG; Team Goals improves on 2 test rows only.
3. **Average accuracy delta negative** (−0.17 across markets with deltas).
4. **Pipeline is sound** — leakage-safe, feature store integrated, backtest arm ready for re-run when data improves.

### Production safety

- No changes to WDE, SaaS predictions, confidence, or live paths.
- All code lives under `worldcup_predictor/egie/xg_backtest/` (backtest-only).
- No deployment performed.

---

## 8. Next Phase Recommendation

### Do **not** proceed to Phase 54G (Pressure Index) yet.

Pressure features would face the same coverage and sample-size wall. Adding another feature store before xG proves value would increase complexity without evidence.

### Required before re-test

1. **Server backfill** — `phase54e_sportmonks_xg_backfill.py --league-id 732` (and UEFA leagues) with valid Sportmonks token to import full `team_xg` / `team_metric` xG rows per fixture.
2. **Re-import UEFA cache** — ensure normalizer captures `metric_key=xg` (not only `xgot`) for all 80 cached fixtures.
3. **Re-run Phase 54F** — target ≥40% `xg_available` coverage and ≥30 xG-evaluable fixtures before any promotion decision.
4. **If xG shows MEDIUM_VALUE or higher on expanded set** → then consider Phase 54G Pressure Index Feature Store.

---

## Deliverables

| Item | Path |
|------|------|
| xG feature builder | `worldcup_predictor/egie/xg_backtest/xg_feature_builder.py` |
| Dataset builder | `worldcup_predictor/egie/xg_backtest/egie_xg_dataset_builder.py` |
| A/B runner | `worldcup_predictor/egie/xg_backtest/xg_backtest_runner.py` |
| Leakage audit | `worldcup_predictor/egie/xg_backtest/xg_leakage_audit.py` |
| Main script | `scripts/phase54f_egie_xg_backtest.py` |
| Validation | `scripts/validate_phase54f_xg_backtest.py` |
| Artifacts | `artifacts/phase54f_egie_xg_backtest/` |

---

*Phase 54F complete. STOP — no deploy, no live prediction changes.*

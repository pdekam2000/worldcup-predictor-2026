# PHASE 54F-6 — Expanded xG Validation Report

**Date:** 2026-06-24  
**Mode:** Dataset Expansion → Coverage Audit → A/B Revalidation → Report  
**Status:** COMPLETE (backtest only — no production, WDE, SaaS, or frontend changes)

---

## Executive Summary

Phase 54F-6 expanded the modern EGIE xG backtest dataset from **126** to **763–1,004 usable fixtures** (server peak **1,004**), exceeding the **300 minimum** and **500 preferred** targets.

| Metric | 54F-5 | 54F-6 (local A/B) | 54F-6 (server DB) |
|--------|-------|-------------------|-------------------|
| Fixtures scanned | 238 | 908 | 1,154 |
| Usable fixtures | 126 | **763** | **1,004** |
| Rolling xG coverage | 52.9% | **84.0%** | **87.0%** |
| Conference usable | 5 | **44** | **192** |

**A/B on 763 fixtures (238 test per market):** Mixed results — xG **helps Team Goals (+2.8%)**, is neutral on Goal Range (+0.8%), and **hurts First Goal Team (−4.6%)**.

**Final value tier:** `LOW_VALUE` (market-specific; aggregate `NO_VALUE`)  
**Final recommendation:** `CONTINUE_XG_RESEARCH` — not ready for production or Phase 54G.

---

## 1. Is xG useful for EGIE?

**Not universally.** On the expanded dataset (763 usable fixtures, ~250 test per market), Sportmonks rolling xG features do **not** provide a consistent lift across all EGIE markets.

| Market | Arm A (baseline) | Arm B (+ xG) | Δ accuracy | Δ logloss | Δ Brier | Verdict |
|--------|------------------|--------------|------------|-----------|---------|---------|
| First Goal Team | 60.1% | 55.5% | **−4.6%** | +0.10 | +0.039 | xG hurts |
| Goal Range | 31.5% | 32.4% | **+0.8%** | +0.06 | — | neutral |
| Team Goals (O2.5) | 55.5% | 58.3% | **+2.8%** | +0.02 | +0.003 | modest help |

Average accuracy delta across markets: **−0.3%** → aggregate recommendation remains **`NO_VALUE`** by Phase 54F rules, but **Team Goals** alone approaches **`LOW_VALUE`** (+2.8% on n=254 test).

**Conclusion:** xG is **not useless** — it shows signal for goal-volume markets — but it is **not ready** for blanket EGIE production integration.

---

## 2. Which markets benefit?

| Market | Benefits from xG? | Evidence |
|--------|-------------------|----------|
| **Team Goals (Over 2.5)** | **Yes (modest)** | +2.8% accuracy, 254 test fixtures, better calibration ECE |
| **Goal Range** | **Marginal** | +0.8% accuracy (within noise) |
| **First Goal Team** | **No** | −4.6% accuracy, worse logloss and Brier |

---

## 3. Which markets do not benefit?

- **First Goal Team** — xG features degrade performance vs rolling-xG-derived baseline proxies. Likely cause: baseline proxies (`home_goal_rate_proxy` from rolling xG) already encode much of the signal; adding full xG feature set introduces noise/overfit for this label.

---

## 4. Which xG features matter?

### Strongest (pooled Arm B importance)

| Feature | Share % | Role |
|---------|---------|------|
| `away_recent_xga` | 14.8% | Defensive xG against — stable |
| `home_recent_xga` | 13.2% | Defensive xG against — stable |
| `rolling_xg_10_away` | 10.9% | Long-window attack form |
| `xg_momentum_difference` | 10.0% | Trend signal |
| `rolling_xg_3_away` | 9.4% | Short-window attack form |

### Stable features (appear across ≥2 markets, share ≥5%)

`away_recent_xga`, `home_recent_xga`, `rolling_xg_10_away`, `xg_momentum_difference`, `rolling_xg_3_away`, `rolling_xg_10_home`, `defensive_weakness_difference`, `rolling_xg_3_home`, `attack_strength_difference`

### Noisy / weak features

`home_recent_xg`, `away_recent_xg`, `rolling_xg_5_home`, `rolling_xg_5_away` — lower pooled importance; raw rolling xG levels less informative than xGA and momentum.

### Features that hurt (inferred)

Full 20-feature xG stack appears to **hurt First Goal Team** while helping Team Goals — suggests **market-specific feature subsets** rather than one-size-fits-all xG bundle.

---

## 5. Should xG enter production later?

**Not yet.**

| Criterion | Status |
|-----------|--------|
| Sample size adequate | **YES** (763–1,004 usable) |
| Consistent cross-market lift | **NO** |
| Leakage-safe pipeline | **YES** |
| Clear production ROI | **NO** |

**Path to production (if pursued):**

1. Use xG features **only for Team Goals / volume markets** initially.
2. Exclude or redesign xG features for First Goal Team.
3. Prefer **xGA + momentum + rolling_xg_10** over raw xG levels.
4. Run holdout validation on next 200+ fixtures before any WDE touch.

---

## 6. Should Phase 54G begin?

**NO** — `READY_FOR_54G` is **not** recommended.

Phase 54G (Pressure Index) should not start until EGIE xG value is clearer. Current evidence supports **continued xG research** on market-specific arms, not pressure-index work.

---

## Part A — Fixture Source Expansion

### Included (proven xG ≥30%)

| League | ID | Usable (local) | Usable (server) |
|--------|-----|----------------|-----------------|
| World Cup | 732 | 21 | 23 |
| Champions League | 2 | 354 | 399 |
| Europa League | 5 | 344 | 390 |
| Conference League | 2286 | **44** | **192** |

### Investigated — excluded (0% xG in Phase 54F-3)

| League | ID | Reason |
|--------|-----|--------|
| Euro Championship | 1326 | No seasons / 0% sample xG |
| Nations League | 1538 | Not in coverage matrix with xG |
| Euro Qualification | 1325 | Not in coverage matrix with xG |

---

## Part B — Season Expansion

Eligible seasons (coverage ≥30%, 2024+):

| Season ID | Competition | Usable (server) |
|-----------|-------------|-----------------|
| 26618 | WC 2026 | 23 |
| 23619 | CL 2024/25 | 185 |
| 25580 | CL 2025/26 | 214 |
| 23620 | EL 2024/25 | 183 |
| 25582 | EL 2025/26 | 207 |
| 25581 | Conference 2025/26 | 192 |

Skipped: all pre-2024 seasons with proven 0% xG (CL/EL/Conference 2023 and earlier).

---

## Part C — Dataset Build

**Artifacts:** `artifacts/phase54f6_expanded_dataset/`

| File | Description |
|------|-------------|
| `expanded_egie_dataset.parquet` | 763 usable rows (local build) |
| `expanded_egie_dataset.csv` | CSV export |
| `expanded_egie_dataset_summary.json` | Coverage summary |
| `expanded_egie_unusable_fixtures.csv` | 145 skipped fixtures + reasons |
| `leakage_audit.json` | PASS |
| `ab_test_results.json` | A/B metrics |
| `feature_importance_analysis.json` | Feature stability report |

Requirements met: leakage-safe, finished only, type 5304 xG, rolling xG available, goal outcomes from cache events/scores.

---

## Part D — Coverage Report

| Metric | Value |
|--------|-------|
| Fixtures scanned | 908 (local) / 1,154 (server) |
| Fixtures usable | **763** / **1,004** |
| Coverage % | **84.0%** / **87.0%** |
| Rolling xG 3/5/10 | 763 each (100% of usable) |
| First goal labeled | 722 |
| Goal range labeled | 722 |
| Team goals labeled | 763 |
| Leakage-safe | 763 |

### Usable by league (local)

| League | Usable |
|--------|--------|
| Champions League | 354 |
| Europa League | 344 |
| Conference League | 44 |
| World Cup | 21 |

---

## Part E — A/B Revalidation

**Threshold met:** usable ≥ 300 → **executed**

Train/test: temporal split, ~484 train / ~238–254 test per market.

Full metrics in `artifacts/phase54f6_expanded_dataset/ab_test_results.json`.

---

## Part F — Feature Importance Summary

See Section 4. Key finding: **xGA and momentum features dominate**; raw xG levels are weaker. No features classified as universally noisy across all three markets.

---

## Part G — Final Decision

| Tier | Assignment |
|------|------------|
| VERY_HIGH_VALUE | No |
| HIGH_VALUE | No |
| MEDIUM_VALUE | No |
| **LOW_VALUE** | **Team Goals market only** (+2.8%) |
| NO_VALUE | Aggregate / First Goal Team |

---

## Part H — Final Recommendation

### `CONTINUE_XG_RESEARCH`

| Option | Status |
|--------|--------|
| READY_FOR_54G | **NO** |
| **CONTINUE_XG_RESEARCH** | **YES** — market-specific xG arms, feature selection |
| XG_NOT_USEFUL_FOR_EGIE | **NO** — Team Goals shows modest positive signal |
| NEED_MORE_FIXTURE_TARGETS | Partially addressed; server at 1,004 usable |

### Next actions

1. Build **Team Goals–only xG arm** with trimmed feature set (xGA, momentum, rolling_xg_10).
2. Remove xG from First Goal Team arm until features are redesigned.
3. Complete Conference League cache sync (server 192 vs local 44) for fuller UEFA coverage.
4. Re-evaluate after 1,000+ holdout fixtures or next competition phase.

---

## Expansion Execution

- Server expanded backfill: 6 league-seasons, max 350 calls × 25 pages each
- Server DB after expansion: **1,154 summaries**, **46,500 records**
- Cache files: 545 → **1,554** on server
- Validation: **12/12 PASS** (`scripts/validate_phase54f6_expanded_dataset.py`)

**STOP** — Phase 54F-6 complete. No deploy. No live prediction changes.

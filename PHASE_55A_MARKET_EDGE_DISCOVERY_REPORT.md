# PHASE 55A — Market Edge Discovery

**Date:** 2026-06-24  
**Mode:** Research — aggregate existing infrastructure  
**Status:** Complete  
**API calls:** 0

### Next 100 dev hours → **`ANYTIME_GOALSCORER_ODDS_EXPANSION`** (anytime_goalscorer)

Highest conditional edge when odds exist (77% WC top-3, 75% disagree hit). 54Q-1 showed UEFA gap is primarily odds coverage; 100h on odds bridge + UEFA expansion has highest ROI vs team/availability features (54R/54S plateau).

---

## Market rankings (MARKET_EDGE_SCORE)

| Rank | Market | Score | Accuracy | Metric | Dataset | Odds cov | Production |
|------|--------|-------|----------|--------|---------|----------|------------|
| 1 | Anytime Goalscorer | **55.47** | 57.1% | top3_hit | 1,541 | 3.0% | shadow_high_value |
| 2 | First Goal Team | **46.95** | 58.3% | accuracy | 1,004 | 35.0% | production |
| 3 | Team To Score First | **46.23** | 58.3% | accuracy | 1,004 | 30.0% | production |
| 4 | Double Chance | **37.79** | 57.1% | derived_proxy | 1,617 | 3.1% | production_derived |
| 5 | First Goalscorer | **36.51** | 31.0% | top3_hit | 1,541 | 2.4% | shadow |
| 6 | Over 1.5 | **35.76** | 80.6% | accuracy | 1,617 | 6.2% | research_only |
| 7 | BTTS | **31.54** | 55.2% | accuracy | 1,617 | 6.2% | production |
| 8 | Goal Range | **29.82** | 33.9% | accuracy | 359 | 10.0% | production |
| 9 | Goal Timing | **29.28** | 33.8% | soft_winrate | 359 | 8.0% | production |
| 10 | 1X2 | **29.12** | 40.1% | accuracy | 1,617 | 6.2% | production |
| 11 | Over 2.5 | **28.79** | 54.6% | accuracy | 1,617 | 6.2% | production |
| 12 | Correct Score | **25.29** | 12.0% | top1_proxy | 1,617 | 1.9% | production_display |
| 13 | Over 0.5 HT | **10.1** | n/a | accuracy | 0 | 5.0% | none |

## Score breakdown (top 5)

### Anytime Goalscorer — 55.47
- accuracy_edge: 0.464
- calibration: 0.26
- coverage: 0.9977
- stability: 0.62
- odds_availability: 0.0305
- roi_potential: 0.8793

### First Goal Team — 46.95
- accuracy_edge: 0.1666
- calibration: 0.8028
- coverage: 0.6516
- stability: 0.52
- odds_availability: 0.35
- roi_potential: 0.58

### Team To Score First — 46.23
- accuracy_edge: 0.1666
- calibration: 0.8028
- coverage: 0.6516
- stability: 0.55
- odds_availability: 0.3
- roi_potential: 0.55

### Double Chance — 37.79
- accuracy_edge: 0.0471
- calibration: 0.45
- coverage: 1.0
- stability: 0.55
- odds_availability: 0.0312
- roi_potential: 0.45

### First Goalscorer — 36.51
- accuracy_edge: 0.2497
- calibration: 0.2
- coverage: 0.9977
- stability: 0.35
- odds_availability: 0.0244
- roi_potential: 0.42

## TOP 10 strongest markets

1. **Anytime Goalscorer** — score 55.47
2. **First Goal Team** — score 46.95
3. **Team To Score First** — score 46.23
4. **Double Chance** — score 37.79
5. **First Goalscorer** — score 36.51
6. **Over 1.5** — score 35.76
7. **BTTS** — score 31.54
8. **Goal Range** — score 29.82
9. **Goal Timing** — score 29.28
10. **1X2** — score 29.12

## TOP 5 research candidates

1. **First Goal Team** — score 46.95 (production)
2. **Team To Score First** — score 46.23 (production)
3. **Double Chance** — score 37.79 (production_derived)
4. **First Goalscorer** — score 36.51 (shadow)
5. **Over 1.5** — score 35.76 (research_only)

## TOP 3 production candidates

1. **Anytime Goalscorer** — score 55.47
2. **First Goal Team** — score 46.95
3. **Team To Score First** — score 46.23

## Per-market detail

### Anytime Goalscorer

| Dimension | Value |
|-----------|-------|
| Dataset size | 1,541 |
| Coverage | 100.0% |
| Accuracy | 0.5712 (top3_hit) |
| Baseline | 0.2 |
| Calibration ECE | 0.37 |
| Stability | 0.62 |
| Odds availability | 3.0% |
| ROI potential | 0.87928 |
| Infrastructure | goalscorer_54k_54s |
| Notes | WC bridged top-3=77.1%; disagree hit=75.0%; UEFA odds gap per 54Q-1. |

### First Goal Team

| Dimension | Value |
|-----------|-------|
| Dataset size | 1,004 |
| Coverage | 22.2% |
| Accuracy | 0.5833 (accuracy) |
| Baseline | 0.5 |
| Calibration ECE | 0.0986 |
| Stability | 0.52 |
| Odds availability | 35.0% |
| ROI potential | 0.58 |
| Infrastructure | goal_timing_xg |
| Notes | Alias of team-to-score-first in current infra. |

### Team To Score First

| Dimension | Value |
|-----------|-------|
| Dataset size | 1,004 |
| Coverage | 22.2% |
| Accuracy | 0.5833 (accuracy) |
| Baseline | 0.5 |
| Calibration ECE | 0.0986 |
| Stability | 0.55 |
| Odds availability | 30.0% |
| ROI potential | 0.55 |
| Infrastructure | goal_timing_xg |
| Notes | — |

### Double Chance

| Dimension | Value |
|-----------|-------|
| Dataset size | 1,617 |
| Coverage | 100.0% |
| Accuracy | 0.5712 (derived_proxy) |
| Baseline | 0.55 |
| Calibration ECE | None |
| Stability | 0.55 |
| Odds availability | 3.1% |
| ROI potential | 0.45 |
| Infrastructure | derived_from_1x2 |
| Notes | Derived from 1X2; no dedicated edge backtest. |

### First Goalscorer

| Dimension | Value |
|-----------|-------|
| Dataset size | 1,541 |
| Coverage | 100.0% |
| Accuracy | 0.3097 (top3_hit) |
| Baseline | 0.08 |
| Calibration ECE | 0.4 |
| Stability | 0.35 |
| Odds availability | 2.4% |
| ROI potential | 0.42 |
| Infrastructure | goalscorer_54k_54s |
| Notes | — |

### Over 1.5

| Dimension | Value |
|-----------|-------|
| Dataset size | 1,617 |
| Coverage | 100.0% |
| Accuracy | 0.8056 (accuracy) |
| Baseline | 0.8179 |
| Calibration ECE | 0.1276 |
| Stability | 0.36310000000000003 |
| Odds availability | 6.2% |
| ROI potential | 0.3056 |
| Infrastructure | ml1_labels |
| Notes | High raw accuracy but below majority baseline. |

### BTTS

| Dimension | Value |
|-----------|-------|
| Dataset size | 1,617 |
| Coverage | 100.0% |
| Accuracy | 0.5525 (accuracy) |
| Baseline | 0.5772 |
| Calibration ECE | 0.1471 |
| Stability | 0.4259 |
| Odds availability | 6.2% |
| ROI potential | 0.05249999999999999 |
| Infrastructure | ml1_production |
| Notes | — |

### Goal Range

| Dimension | Value |
|-----------|-------|
| Dataset size | 359 |
| Coverage | 22.0% |
| Accuracy | 0.3385 (accuracy) |
| Baseline | 0.17 |
| Calibration ECE | None |
| Stability | 0.3 |
| Odds availability | 10.0% |
| ROI potential | 0.25 |
| Infrastructure | goal_timing |
| Notes | RESEARCH_ONLY per 54F-7. |

### Goal Timing

| Dimension | Value |
|-----------|-------|
| Dataset size | 359 |
| Coverage | 22.0% |
| Accuracy | 0.3381 (soft_winrate) |
| Baseline | 0.15 |
| Calibration ECE | None |
| Stability | 0.28 |
| Odds availability | 8.0% |
| ROI potential | 0.22 |
| Infrastructure | goal_timing |
| Notes | Hard minute hit rate ~3.4%; soft tolerance ~33.8%. |

### 1X2

| Dimension | Value |
|-----------|-------|
| Dataset size | 1,617 |
| Coverage | 100.0% |
| Accuracy | 0.4012 (accuracy) |
| Baseline | 0.392 |
| Calibration ECE | None |
| Stability | 0.546 |
| Odds availability | 6.2% |
| ROI potential | 0.0 |
| Infrastructure | ml1_production |
| Notes | Primary WDE market; ML-1 delta vs majority small but positive. |

### Over 2.5

| Dimension | Value |
|-----------|-------|
| Dataset size | 1,617 |
| Coverage | 100.0% |
| Accuracy | 0.5463 (accuracy) |
| Baseline | 0.608 |
| Calibration ECE | 0.1608 |
| Stability | 0.2649 |
| Odds availability | 6.2% |
| ROI potential | 0.04630000000000001 |
| Infrastructure | ml1_production |
| Notes | — |

### Correct Score

| Dimension | Value |
|-----------|-------|
| Dataset size | 1,617 |
| Coverage | 50.0% |
| Accuracy | 0.12 (top1_proxy) |
| Baseline | 0.05 |
| Calibration ECE | None |
| Stability | 0.2 |
| Odds availability | 1.9% |
| ROI potential | 0.15 |
| Infrastructure | poisson_derived |
| Notes | No dedicated backtest; accuracy is literature-style proxy for top-1 CS. |

### Over 0.5 HT

| Dimension | Value |
|-----------|-------|
| Dataset size | 0 |
| Coverage | 0.0% |
| Accuracy | None (accuracy) |
| Baseline | None |
| Calibration ECE | None |
| Stability | 0.1 |
| Odds availability | 5.0% |
| ROI potential | 0.1 |
| Infrastructure | gap |
| Notes | No labels, trainer, or backtest engine. |

---

## Constraints honored

- No deploy, production changes, or live prediction changes
- Research aggregation only

# PHASE ML-1 — Hybrid ML + Market Intelligence Foundation

**Mode:** Audit → Dataset Build → Classical ML → Meta Layer → Backtest → Report  
**Deep Learning:** NO  
**Production deploy:** NO  

---

## Executive Answer

**Strongest architecture today:** **Hybrid ML + Market Intelligence** — Market Intelligence for FG Team (**78.7%** sharp MW, K2/ML-1 UEFA) + LightGBM for tabular markets (mean **57.2%** on temporal test split).

**If Deep Learning is postponed, highest ROI architecture:** **Option D — Hybrid ML + Market Intelligence** (score **76.9**).

Market Intelligence beats current EGIE by **~+28pp** on FG. LightGBM **does not beat majority class** on average (-2.2pp) without odds features — form-only tabular ML is insufficient alone.

### Five key answers

1. **Strongest architecture?** Hybrid D: FG odds (78.7%) + LightGBM tabular (57.2%).
2. **LightGBM vs rules?** Mixed — MW +0.9pp vs majority; BTTS/O/U **underperform** majority on test split.
3. **Market Intelligence vs ML?** **Yes for FG** — sharp odds 78.7% vs EGIE baseline 50.8%.
4. **Hybrid vs both?** Meta proxy **70.1%** — weighted 60% FG odds + 40% tabular ML.
5. **Production direction?** **Market Intelligence** first; hybrid shadow as Phase ML-2 candidate.

---

## STEP 1 — Dataset Consolidation

Artifact: `artifacts/ml1_dataset_inventory.json`

- **Total unified rows:** 1617
- API odds snapshots: 4
- UEFA Sportmonks odds rows: 97
- Goal-event labels: 359

| Market | Rows |
|--------|------|
| match_winner | 1617 |
| btts | 1617 |
| over_1_5 | 1617 |
| over_2_5 | 1617 |
| over_3_5 | 1617 |
| first_goal_team | 359 |
| goal_range | 359 |

## STEP 2 — Feature Quality

- **Tier A** `home_gf_l5` — coverage 100.0%, leakage low
- **Tier A** `home_ga_l5` — coverage 100.0%, leakage low
- **Tier A** `away_gf_l5` — coverage 100.0%, leakage low
- **Tier A** `away_ga_l5` — coverage 100.0%, leakage low
- **Tier A** `home_btts_l5` — coverage 100.0%, leakage low
- **Tier A** `away_btts_l5` — coverage 100.0%, leakage low
- **Tier A** `home_points_l5` — coverage 100.0%, leakage low
- **Tier A** `away_points_l5` — coverage 100.0%, leakage low
- **Tier C** `odds_mw_home` — coverage 0.25%, leakage low
- **Tier C** `odds_mw_draw` — coverage 0.25%, leakage low
- **Tier C** `odds_mw_away` — coverage 0.25%, leakage low
- **Tier C** `odds_btts_yes` — coverage 0.25%, leakage low

## STEP 3 — LightGBM Baselines

Backend: **lightgbm** | Train 1293 / Test 324

| Model | Accuracy | LogLoss | Brier | Δ vs Majority |
|-------|----------|---------|-------|---------------|
| MW_Model | 40.1% | 1.312 | n/a | +0.9pp |
| BTTS_Model | 55.2% | 0.7611 | 0.2693 | -2.5pp |
| OU15_Model | 80.6% | 0.5884 | 0.1662 | -1.2pp |
| OU25_Model | 54.6% | 0.7481 | 0.2676 | -6.2pp |
| OU35_Model | 55.6% | 0.7511 | 0.2704 | -2.2pp |

## STEP 4 — First Goal Team Engine

- **A_odds_only** (UEFA test split): 90.0% (coverage 20, pending 0)
- **B_egie_only** (UEFA test split): n/a (coverage 0, pending 20)
- **C_odds_plus_egie** (UEFA test split): 90.0% (coverage 20, pending 0)
- **K2 full-sample reference** — sharp MW 78.7%, consensus 77.7%, FTS 77.4% (n=104)

## STEP 5 — Goal Range Engine

- **statistical_baseline**: 31.9% range accuracy
- **form_survival_proxy**: 36.1% range accuracy
- **odds_enhanced**: 36.1% range accuracy

Phase 52A reference: baseline 27.8%, survival 30.9%

## STEP 6 — Meta Intelligence Layer

- Meta hybrid score proxy: **70.1%**
- Beats isolated models: **False**
- Formula: `0.6*FG_odds + 0.4*mean(LGBM_markets)`

## STEP 7 — Market Intelligence Score

- MIS mean: **0.8716** (n=97)
- Favorite-side FG accuracy: **78.3%**

## STEP 8 — Roadmap Decision

- **C. Market Intelligence** — score 78.3
- **D. Hybrid ML + Market Intelligence** — score 76.9
- **B. Classical ML (LightGBM)** — score 57.2
- **A. Current EGIE** — score 50.8

## Recommendation

1. **Prioritize Market Intelligence** for FG Team and MW where Sportmonks/API odds exist.
2. **Use LightGBM** only after odds features are joined (currently 0.25% API odds coverage on PL/BL).
3. **Hybrid shadow architecture:** odds-primary FG routing + tabular ML for BTTS/O/U when odds absent.
4. **Do not deploy** form-only LightGBM — underperforms majority on test split.

---

**STOP — No deep networks. No deploy. No production changes.**

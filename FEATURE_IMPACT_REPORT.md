# Phase 47A — Feature Impact Audit

**Mode:** Read-only  
**Date:** 2026-06-21  
**Goal:** Measure the real predictive value of every major intelligence layer added to the WorldCup Predictor platform.

**Constraints honored:** No code changes. No deployment. No weight or calibration modifications.

---

## Executive Summary

The platform’s **published 1X2 pick** is driven by the **scoreline λ path + harmonization**, not by WDE alone. On the largest offline replay (**n=207**), **WDE-only accuracy (34.8%) beats harmonized final (30.0%) by 4.8 percentage points** — meaning the full production stack currently **reduces** 1X2 accuracy versus WDE on that sample.

Among **additive intelligence layers**, only **sparse, odds-related signals** (Odds Market, Market Consensus, Sharp Money — ~12–13% fixture coverage) show measurable lift when present (~52% final accuracy vs ~30% overall). **Weather** shows positive correlation (+0.20) but appears on **≤7%** of fixtures. **Odds Movement**, **Phase 46D supplemental bundles** (Advanced Match Intelligence, Player Intelligence, Provider Fusion), and **shadow promotion layers** (24A–24C) show **no measurable improvement** to published 1X2 accuracy in available evidence.

**Most valuable feature (conditional):** Odds cluster — Sharp Money / Market Consensus / Odds Market when data exists.  
**Least valuable feature:** Odds Movement intelligence (negative correlation; 0% lean hit rate on replay).

---

## Methodology

| Source | n | What it measures |
|--------|---|------------------|
| Phase 17 attribution replay | 207 | Per-signal lean accuracy, WDE vs final, ablation estimates |
| Phase 18 harmonization truth | 207 | Override help/harm, cohort splits (WC, Bundesliga, with/without odds) |
| Phase 25 shadow replay | 32 | Baseline vs promotion stacks — winner flip rate, Brier, confidence |
| Phase 26 real-world validation | 32 settled | Production-style WC accuracy, calibration OK rate |
| Phase 46D validation | 13 checks | Confirms 46D layers do **not** change WDE weights or picks |
| Phase 15 counterfactual λ | 106 WC | Odds-only vs xG-only spread/draw behavior (λ path, not WDE stack) |

**ROI estimate:** Flat-stake proxy at even money (decimal 2.0):  
`ROI% = (accuracy − 0.50) × 200`  
This is **not** true market ROI — the platform explicitly disclaims profit tracking. Used here only for relative comparison.

**Calibration:** Brier score and `confidence_calibration_ok` where available (Phase 25/26). High confidence (≥65) should correlate with correctness; low (<45) with incorrect.

**Confidence quality:** Separation between average confidence on correct vs wrong predictions.

### Architecture note (critical for interpretation)

```
Specialists → ScoringEngine (λ baseline) → WDE (9 weighted factors) → Harmonization → Published 1X2
Phase 46D provider_utilization → supplemental_sources only (trace / analytics)
Phase 24A–24C promotions → shadow mode (confidence deltas only when gated; 0% winner flips in replay)
```

Layers 4–6 in this audit (46D) are **validated supplemental-only** — they cannot change accuracy until explicitly promoted into WDE or scoring.

---

## Configuration Audit

### 1. Base WDE Only

| Metric | Value |
|--------|-------|
| **Sample size** | 207 fixtures (12 WC demo CSV + 15 live WC + 180 Bundesliga DB) |
| **1X2 accuracy** | **34.8%** (72/207) |
| **ROI estimate** | **−30.4%** (flat @ evens) |
| **Calibration (Brier)** | Not isolated for WDE-only layer; full-stack Brier on WC subset = **0.237** (Phase 25, n=32) |
| **Confidence quality** | WDE exceeds harmonized final by **+4.8 pp** on same sample — WDE is better calibrated to outcomes than published pick |

**Role:** Nine WDE factors (`data_quality`, `team_form`, `injuries_suspensions`, `lineup_strength`, `tactics_matchup`, `player_quality`, `odds_market_signal`, `motivation_psychology`, `weather_referee_context`). Resolves markets before harmonization overrides to scoreline-implied 1X2.

**Verdict:** Best offline 1X2 layer in Phase 17/18 evidence. Not what users see as final pick after harmonization.

---

### 2. WDE + Weather

| Metric | Value |
|--------|-------|
| **Sample size** | 207 full replay; **2** fixtures with weather lean (1.0%); Phase 43 expands collection but WC live sample still sparse |
| **1X2 accuracy** | **34.8%** on full WDE stack (weather slot always present in factor math at **6%** weight); weather-lean cohort n=2 → **50.0%** lean hit rate (not statistically meaningful) |
| **ROI estimate** | Full stack: **−30.4%**; weather-present cohort: **0.0%** (n=2) |
| **Calibration** | Phase 17 correlation **+0.200** (best sparse 1X2 correlate); severe-weather O/U penalty active in WDE |
| **Confidence quality** | Weather appears on **1/62** correct and **1/145** wrong predictions in Phase 17 leaderboard — negligible separation |

**What weather adds:** `weather_referee_context` factor (6%), `weather_impact_score`, severe-weather Over 2.5 reduction (−15 confidence cap), Phase 43 payload (`weather_intelligence` block), cache-first provider layer.

**Verdict:** **Conditional helper** — positive correlation when data exists, primarily for **O/U and risk narrative**, not proven 1X2 lift at current coverage. Low complexity relative to 46D stacks.

---

### 3. WDE + Odds Movement

| Metric | Value |
|--------|-------|
| **Sample size** | 207 replay; **2** fixtures with odds-movement lean (1.0%) |
| **1X2 accuracy** | **34.8%** (movement does **not** enter WDE factor weights); movement-lean cohort: **0%** hit rate on 2 leans |
| **ROI estimate** | **−30.4%** (no measurable change to published pick) |
| **Calibration** | Phase 17 correlation **−0.300** (worst among measured signals) |
| **Confidence quality** | `OddsMovementAgent` `impact_score` unchanged in 46D — informational only |

**What odds movement adds:** Steam/volatility detection, opening vs current implied delta (Phase 46D `odds_movement_intelligence`), specialist supplemental fields. Phase 23: **Fusion only, weak weight** — not in WDE `_build_factors`.

**Verdict:** **No measurable predictive value** on 1X2 in replay. Adds pipeline complexity and API/cache cost. Candidate for demotion to audit-only unless live WC sample proves otherwise.

---

### 4. WDE + Advanced Match Intelligence

| Metric | Value |
|--------|-------|
| **Sample size** | 207 (offline) + 32 (Phase 25/26); **0** fixtures where this layer changed published 1X2 |
| **1X2 accuracy** | **Unchanged** — same as full system (30.0% on n=207 final; 40.6% on n=32 WC settled) |
| **ROI estimate** | **No delta** vs full system |
| **Calibration** | No Brier change (Phase 46D: `wde_factor_weights_unchanged`) |
| **Confidence quality** | No confidence delta (supplemental `advanced_match_intelligence` key only) |

**What it adds:** Sportmonks xG/xGA, attacking/defensive edge, shot quality, efficiency metrics → `supplemental_sources.advanced_match_intelligence`.

**Verdict:** **Analytics-only today.** xG family already partially consumed via `tactics_matchup` / `xg_chance_quality` in WDE; 46D bundle duplicates enrichment without pick impact. **Complexity without current 1X2 value.**

---

### 5. WDE + Player Intelligence

| Metric | Value |
|--------|-------|
| **Sample size** | 207 + 32; **0** pick changes validated |
| **1X2 accuracy** | **Unchanged** (30.0% / 40.6% as above) |
| **ROI estimate** | **No delta** |
| **Calibration** | No change |
| **Confidence quality** | No change; goalscorer/first-goal hints not wired to scoring engine |

**What it adds:** Recent goals/assists, form, minutes, availability, lineup confidence, top scorer candidates → `player_intelligence` supplemental.

**Verdict:** **Potential value for goalscorer / first-goal markets** (Phase 46C evaluators), **not for 1X2**. Lineups agent alone showed **13.3%** lean accuracy (n=15) in Phase 17 — harmful when used as 1X2 signal.

---

### 6. WDE + Provider Fusion

| Metric | Value |
|--------|-------|
| **Sample size** | 207 + 32; fusion runs at enrichment; **0** validated 1X2 pick changes |
| **1X2 accuracy** | **Unchanged** on prediction; **improves post-match evaluation** (unified events, score/event gap-fill) |
| **ROI estimate** | **No delta** on pre-match 1X2 |
| **Calibration** | No change |
| **Confidence quality** | No change |

**What it adds:** API-Football → Sportmonks → cache merge for events/scores/lineups; `fixture_unified_events` persistence; `provider_utilization_v1` bundle.

**Verdict:** **High operational value for data quality and evaluation**, **zero proven pre-match prediction lift**. Complexity justified for archive/accuracy pipeline, not for 1X2 ROI.

---

### 7. Full System (Production)

| Metric | Value |
|--------|-------|
| **Sample size** | **207** offline replay; **32** settled WC (Phase 25/26); **27** WC cohort (Phase 18); **2** local SQLite eval (Phase 35/42B — too small) |
| **1X2 accuracy** | **30.0%** (207 harmonized final); **40.6%** (32 WC settled); **51.9%** (27 WC with richer odds context, Phase 18) |
| **ROI estimate** | **−40.1%** (207 @ evens); **−18.8%** (32 WC @ 40.6%); **+3.8%** (27 WC odds-rich cohort @ 51.9%) |
| **Calibration** | Brier **0.237** (Phase 25, n=32); calibration OK **62.5%** (Phase 26); overconfidence rate **3.1%** |
| **Confidence quality** | Avg conf **48.6**; correct **49.9** vs wrong **47.8** — **weak separation** (~2 pp) |

**Stack includes:** All specialists (22+), WDE, harmonization, weather, odds cluster, shadow promotions (24A–24C), Phase 46D supplemental, scoring engine λ path, Fusion V2 confidence cap.

**Phase 25 promotion impact on full stack:**

| Metric | Baseline | Shadow / Gated full |
|--------|----------|---------------------|
| 1X2 accuracy | 40.6% | 40.6% |
| Winner flip rate | — | **0.0%** |
| Avg confidence delta | — | −0.19 (Sportmonks disagreement) |
| Disagreement rate | 0% | 6.2% |

**Verdict:** Full system accuracy is **dominated by scoreline harmonization and odds availability**, not by 46D or shadow promotion layers. Harmonization **hurts** vs WDE on Bundesliga-heavy replay (33.2% harmful overrides vs 27.9% helpful).

---

## Comparative Summary Table

| Configuration | n | 1X2 Accuracy | ROI Proxy | Brier / Calibration | Confidence Quality | Predictive Lift |
|---------------|---|--------------|-----------|---------------------|-------------------|-----------------|
| 1. Base WDE only | 207 | **34.8%** | −30.4% | n/a (layer) | Better than final (+4.8 pp) | **Best offline 1X2 layer** |
| 2. WDE + Weather | 207 (2 w/ lean) | 34.8% | −30.4% | +0.20 corr | Sparse; O/U focus | **Marginal / conditional** |
| 3. WDE + Odds Movement | 207 (2 w/ lean) | 34.8% | −30.4% | −0.30 corr | Informational only | **None measured** |
| 4. WDE + Advanced Match Intel | 207 / 32 | 30.0% / 40.6% | Same as full | Unchanged | Unchanged | **Zero (supplemental)** |
| 5. WDE + Player Intel | 207 / 32 | 30.0% / 40.6% | Same as full | Unchanged | Unchanged | **Zero on 1X2** |
| 6. WDE + Provider Fusion | 207 / 32 | 30.0% / 40.6% | Same as full | Unchanged | Unchanged | **Zero on 1X2; eval++** |
| 7. Full system | 207 / 32 | 30.0% / 40.6% | −40.1% / −18.8% | 0.237 / 62.5% cal OK | Weak (2 pp gap) | **Odds-rich WC ↑** |

---

## Feature Rankings

### Most valuable (predictive evidence)

| Rank | Feature | Evidence |
|------|---------|----------|
| 1 | **Odds cluster** (Sharp Money, Market Consensus, Odds Market) | ~52% final accuracy when present (n=25–27) vs 30% overall; correlations +0.06 to +0.15 |
| 2 | **Base WDE decision layer** | 34.8% vs 30.0% harmonized final on n=207 — should not be overridden blindly |
| 3 | **Weather intelligence** | +0.20 correlation; severe-weather O/U guard; low coverage limits proof |
| 4 | **Scoreline λ odds path** (Phase 15) | Odds-only λ collapses draw bias (+0.96 median spread); primary calibration lever |
| 5 | **Provider fusion / unified events** | No 1X2 lift; **high value for evaluation accuracy** (46C goal-minute, archive) |

### Least valuable (predictive evidence)

| Rank | Feature | Evidence |
|------|---------|----------|
| 1 | **Odds Movement intelligence** | −0.30 correlation; 0% lean accuracy; not in WDE weights |
| 2 | **Always-on duplicate agents** (Team Form, Tournament, Motivation, Player Quality, xG lean) | ~29% lean accuracy ≈ baseline; appear on 93%+ of wrong picks because they always emit |
| 3 | **Phase 46D Advanced Match + Player Intel bundles** | Validated zero pick/confidence change |
| 4 | **Shadow promotions 24A–24C** | 0% winner flip; 0 helped / 0 harmful / 32 unknown usefulness |
| 5 | **Lineups / Sportmonks enrichment as 1X2 signals** | 13.3% and 0% lean accuracy when available |

---

## Features Helping Prediction

| Feature | How it helps | Caveat |
|---------|--------------|--------|
| **Odds Market / Consensus / Sharp Money** | Strongest conditional lift when data exists (~52% vs ~30%) | Only ~12–13% fixture coverage in replay |
| **WDE (pre-harmonization)** | Outperforms published final on offline sample | Overridden 91.8% of time — value destroyed by harmonization |
| **Weather (severe conditions)** | O/U over penalty; positive sparse 1X2 correlation | n=2 lean fixtures in replay — need WC live accumulation |
| **Odds-implied λ (scoreline path)** | Largest spread/draw calibration lever (Phase 15) | Not a separate “layer” in WDE stack — core engine math |
| **Provider fusion (post-match)** | Better events/scores for evaluation markets | Pre-match 1X2 unchanged |

---

## Features Adding Complexity Without Measurable Value

| Feature | Complexity cost | Measured 1X2 lift |
|---------|-----------------|-------------------|
| **Odds Movement agent + 46D movement intel** | Snapshots, RapidAPI prematch, circular-import surface | **None / negative correlation** |
| **Advanced Match Intelligence (46D)** | Sportmonks parsing, supplemental bundle | **Zero** (duplicate of partial xG path) |
| **Player Intelligence (46D)** | Lineups + events + injuries merge | **Zero on 1X2** (eval markets only) |
| **22-agent always-on cluster** (form, motivation, tournament, player quality) | Orchestrator time, correlated noise | **~0 pp** above baseline |
| **Shadow promotions 24A–24C** | Confidence delta machinery, JSONL stores | **0% flip rate** in 32-case replay |
| **Harmonization override (WDE → scoreline)** | 91.8% override rate | **−4.8 pp** vs WDE on n=207 |

---

## Calibration & Confidence Deep Dive

| Cohort | n | Accuracy | Brier | Cal OK % | Avg Conf (correct) | Avg Conf (wrong) |
|--------|---|----------|-------|----------|-------------------|------------------|
| Phase 25 all stacks | 32 | 40.6% | 0.237 | — | 49.9 | 47.8 |
| Phase 26 settled | 32 | 40.6% | 0.242 | 62.5% | 49.9 | 47.8 |
| Phase 17 final | 207 | 30.0% | — | — | — | — |
| Phase 17 WDE | 207 | 34.8% | — | — | — | — |
| With Odds Market | 25 | 52.0% | — | — | — | — |
| With Sharp Money | 27 | 51.9% | — | — | — | — |

**Finding:** Confidence scores **do not strongly separate** correct from wrong predictions (~2 pp gap). Calibration OK rate (62.5%) exceeds raw accuracy (40.6%) because the rule partially fires on low-confidence wrong picks — system is **under-confident on winners** and **over-trusts harmonization** on draws.

---

## Data Limitations

1. **Small WC settled sample (n=32)** — Phase 25/26 bootstrap; promotion usefulness all `unknown`.
2. **Bundesliga-heavy replay (87%)** — harmonization always forces scoreline; not representative of WC odds-rich environment.
3. **46D layers deployed 2026-06-21** — no forward-settled WC sample with provider_utilization yet.
4. **Weather / Odds Movement** — ≤2 fixtures with leans in Phase 17 replay; conclusions provisional.
5. **Production SQLite eval** — 0–2 rows at report time; live accuracy dashboard correctly shows empty/zero state.
6. **ROI proxy** — flat evens only; true CLV/market ROI not tracked.

---

## Recommendations (Audit-Only — No Action Taken)

1. **Stop harmonization from overriding WDE when WDE confidence exceeds scoreline** — largest single accuracy leak on offline evidence (+4.8 pp recoverable).
2. **Invest in odds coverage** before adding agents — Sharp Money / Consensus path is the only repeatable lift signal.
3. **Demote or gate Odds Movement** to audit-only until live WC sample shows positive correlation.
4. **Keep 46D bundles supplemental** until A/B promotion study shows lift on goalscorer/first-goal or 1X2 — current evidence does not justify WDE wiring.
5. **Accumulate Phase 26 shadow captures** through WC 2026 group stage before any gated promotion enable.
6. **Recalibrate always-on λ inputs** (form/xG defaults) rather than adding parallel intelligence layers.

---

## Sources

| Artifact | Path |
|----------|------|
| Phase 17 attribution | `PHASE_17_PREDICTION_ATTRIBUTION_AUDIT.md`, `data/shadow/phase17_attribution_replay.jsonl` |
| Phase 18 harmonization | `PHASE_18_HARMONIZATION_TRUTH_AUDIT.md` |
| Phase 25 replay | `PHASE_25_CALIBRATION_SHADOW_REPLAY_REPORT.md`, `data/shadow/phase25_promotion_metrics.json` |
| Phase 26 validation | `PHASE_26_REAL_WORLD_VALIDATION_REPORT.md`, `data/validation/real_world_validation.jsonl` |
| Phase 46D utilization | `PHASE_46D_PROVIDER_UTILIZATION_REPORT.md`, `artifacts/phase46d_provider_utilization_validation.json` |
| Phase 43 weather | `PHASE_43_WEATHER_INTELLIGENCE_REPORT.md` |
| Phase 23 architecture | `PHASE_23_MASTER_DECISION_AUDIT.md` |
| Phase 15 λ counterfactual | `PHASE_15_COUNTERFACTUAL_LAMBDA_AUDIT.md` |

---

**Phase 47A complete. Read-only audit — no code, no deploy.**

**PHASE_47A_STATUS = REPORT_COMPLETE**

# PHASE 54K — Goalscorer Shadow Engine V1

**Date:** 2026-06-24  
**Mode:** Shadow Engine → Backtest → Validation → Report  
**Status:** Complete — validation **15/15 PASS**  
**API calls:** 0 (cache-first; PostgreSQL feature store only)

---

## Executive summary

Built a **research-only Goalscorer Shadow Engine** ranking eligible players per fixture using rolling features from Phase 54J. Simple combined baseline **beats naive uniform by +32.5pp top-3 anytime hit** on temporal test split (209 fixtures).

### Final recommendation: **`GOALSCORER_MEDIUM_VALUE`**

Shadow engine shows meaningful lift over naive ranking and is ready for deeper ML experimentation. Goalscorer odds alignment remains **blocked by sparse cache overlap** (3 fixtures in test ∩ odds cache).

---

## Architecture

| Module | Role |
|--------|------|
| `feature_builder.py` | Load DB rows, enrich proxies, eligibility filter |
| `dataset_builder.py` | Targets + temporal split + parquet/csv export |
| `scoring.py` | Four baseline scores + per-fixture ranking |
| `backtest.py` | Top-k / precision@k / MRR metrics |
| `calibration.py` | Softmax probabilities + confidence tiers (research only) |
| `validation.py` | Optional odds alignment from UEFA cache |

**Package:** `worldcup_predictor/egie/goalscorer_shadow/`

---

## Dataset (Part C)

| Metric | Value |
|--------|-------|
| Total player-fixture rows | 69,503 |
| **Eligible rows** | **47,029** |
| Unusable rows | 22,474 (no minutes history, GK, not in lineup) |
| Fixtures | 1,541 |
| Anytime scorer positives | 3,480 |
| First goal positives | 1,243 |
| Train / val / test | 32,920 / 7,054 / 7,055 |
| Date range | 2007-03-07 → 2026-06-23 |

**Artifacts:** `artifacts/phase54k_goalscorer_shadow/`
- `goalscorer_dataset.parquet` / `.csv`
- `goalscorer_dataset_summary.json`
- `unusable_goalscorer_rows.csv`

---

## Baseline models (Part D)

| Model | Formula (simplified) |
|-------|---------------------|
| `goals_per_90_score` | goals_per_90 × starter_probability |
| `xg_per_90_score` | xg_per_90 × starter_probability |
| `starter_weighted_score` | recent_form + goals_last_5 weight |
| `combined_score` | Normalized blend of goals, xG, form, team proxy |
| `naive_uniform` | Equal weight all eligible players |

---

## Backtest results (Part E) — test split (209 fixtures)

### Anytime Goalscorer

| Model | Top-1 | Top-3 | Top-5 | P@3 |
|-------|-------|-------|-------|-----|
| naive_uniform | 6.2% | 23.4% | 35.9% | 7.8% |
| goals_per_90 | 22.5% | 53.6% | 62.7% | 21.9% |
| xg_per_90 | 28.2% | 51.7% | 62.7% | 20.6% |
| starter_weighted | 25.8% | 52.2% | 64.6% | 21.9% |
| **combined** | **25.8%** | **56.0%** | **66.0%** | **23.1%** |

### First Goalscorer (178 fixtures with first-goal event in cache)

| Model | Top-1 | Top-3 | Top-5 | MRR |
|-------|-------|-------|-------|-----|
| naive_uniform | 3.4% | 9.3% | 15.2% | 0.125 |
| goals_per_90 | 11.2% | 29.2% | 41.0% | 0.259 |
| **combined** | **12.9%** | **33.2%** | **43.8%** | **0.282** |

### Most Likely Scorer (189 fixtures)

| Model | Top-1 | Top-3 | Top-5 | MRR |
|-------|-------|-------|-------|-----|
| naive_uniform | 2.9% | 10.3% | 16.4% | 0.128 |
| **combined** | **9.5%** | **31.8%** | **43.4%** | **0.265** |

---

## Calibration (Part F — research only)

Softmax per-fixture probabilities with tiers (`high` / `medium` / `low` / `minimal`).

| Bin (prob) | Rows | Actual scorer rate | Mean prob |
|------------|------|-------------------|-----------|
| 0.00–0.05 | 45,150 | 7.4% | 3.0% |
| 0.05–0.12 | 1,648 | 7.1% | 6.7% |
| 0.12–0.25 | 133 | 11.3% | 16.1% |
| 0.25–1.00 | 78 | 9.0% | 40.7% |

High-confidence bins are sparse; calibration needs more data before production use (not planned in this phase).

---

## Odds alignment (Part G — optional)

| Metric | Value |
|--------|-------|
| Test fixtures with cached goalscorer odds | **3** |
| Player name mapping success | 0% (insufficient overlap) |
| Mapping blocker | Not forced — sample too small |

**Conclusion:** Goalscorer odds **not usable yet** for validation at scale. UEFA odds-rich cache does not overlap test-split fixtures sufficiently. Name-mapping research deferred to 54L.

---

## Report answers

### 1. Can we predict Anytime Goalscorer better than naive baseline?

**Yes.** Combined baseline **top-3 hit 56.0%** vs naive **23.4%** (+32.5pp) on 209 test fixtures.

### 2. Can we rank First Goalscorer candidates?

**Partially.** Combined top-3 hit **33.2%** vs naive **9.3%**. First goal remains hard (MRR 0.28).

### 3. Which features matter most?

Correlation proxy with anytime target:

| Feature | Correlation |
|---------|-------------|
| recent_form_score | 0.225 |
| goals_last_5 | 0.223 |
| lineup_status (starter) | 0.174 |
| xg_per_90 | 0.112 |
| goals_per_90 | 0.098 |
| starter_probability | 0.096 |

### 4. Is player xG useful?

**Yes, supplementary.** `xg_per_90` alone achieves **28.2%** top-1 anytime (best single baseline). Combined model benefits modestly from xG blend.

### 5. Is lineup status useful?

**Yes.** Starter vs bench correlation **0.174** — eligibility gating is critical (99.6% lineup coverage from 54J).

### 6. Are goalscorer odds usable yet?

**Not at backtest scale.** Only 3 test fixtures had cached odds; name mapping untested. Per 54I, odds exist on UEFA deep cache but need dedicated ingest + mapping pipeline.

### 7. Is the engine ready for deeper ML?

**Yes — research track.** 47k eligible rows, temporal split, clear baselines, and combined score beats naive. Ready for gradient boosting / calibration on 54L without production touch.

---

## Validation

**15/15 PASS** (`artifacts/phase54k_goalscorer_shadow/validation.json`)

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/phase54k_goalscorer_shadow.py` | Build dataset + backtest |
| `scripts/validate_phase54k_goalscorer_shadow.py` | Validation gate |

---

**Phase 54K complete. No deploy. No live prediction changes. No EGIE scoring changes.**

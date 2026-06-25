# PHASE 34A — GERMANY vs IVORY COAST CONFIDENCE AUDIT

**Fixture:** 1489393 — Germany vs Ivory Coast  
**Kickoff:** 2026-06-20 20:00 UTC (BMO Field, Toronto)  
**Mode:** Audit only — no code changes, no deploy  
**Data sources:** Production API (`footballpredictor.it.com`), production SQLite (`worldcup_stored_predictions`), local live pipeline comparison  

---

## Executive Summary

The UI showing **Confidence = 3%** is **not a frontend rendering bug**. The API and SQLite both store **`confidence: 3.0`**, and the UI displays that value correctly.

The 3% value is the **final post-adaptive confidence** after multiple pipeline stages. The stored audit trace shows **WDE final = 11.5%** and **ScoringEngine baseline (pre-WDE) = 27.5%**, but the **adaptive confidence layer** (applied after WDE in `_finalize_prediction`) further reduced confidence to **3.0%** — and that step is **not reflected** in `audit_trace.confidence.final`.

Phase 33B uses the **correct field** (`prediction.confidence_score`). Caution tier behavior is working as designed.

**Root issue:** Stale background-cached prediction (generated 2026-06-20 15:09 UTC with `placeholder_data` flag) combined with **hidden adaptive penalty** and **probability vs selection mismatch** creates a misleading user experience — not a simple UI typo.

---

## Question 1 — Why does UI show Confidence = 3%?

### UI code path

```122:125:base44-d/src/pages/PredictionDetail.jsx
function roundPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return null;
  return Math.round(Number(value) * 10) / 10;
}
```

```305:305:base44-d/src/pages/PredictionDetail.jsx
  const confidence = roundPercent(result?.confidence) ?? 0;
```

### Production API response (cached)

| Field | Value |
|-------|-------|
| `confidence` | **3.0** |
| `cache_source` | `sqlite_store` |
| `pick_tier` | `caution` |
| `no_bet` | `true` |
| `caution_reason` | `WDE flagged elevated uncertainty; confidence 3.0 below 60` |
| `confidence_gap_to_threshold` | **57.0** (60 − 3) |

**Answer:** UI shows 3% because `roundPercent(3.0) → 3.0`. The frontend faithfully renders the API field.

---

## Question 2 — What is actual WDE confidence?

From stored `audit_trace.confidence` in production SQLite:

| Metric | Value |
|--------|-------|
| **WDE baseline** (ScoringEngine output entering WDE) | **27.5** |
| **WDE final** (after WDE caps/reductions) | **11.5** |
| Caps applied | `national_intelligence_boost_plus_1.0` |
| Reductions | `specialist_conflicts_high_minus_12`, `odds_model_disagreement_minus_5` |
| No-bet reasons | `confidence_level_unavailable`, `placeholder_data`, `confidence_below_60` |

**Math check:** 27.5 + 1.0 − 12 − 5 = **11.5** ✓

**Answer:** Actual WDE confidence for this cached prediction is **11.5%**, not 3%.

WDE reductions come from `weighted_decision_engine.py`:
- Specialist conflict penalty (≥ high threshold): −12
- Odds vs model disagreement: −5
- Placeholder data flag forces no-bet

---

## Question 3 — What is actual ScoringEngine confidence?

The audit trace field `baseline` (27.5) is set from `baseline.confidence_score` at the **start** of `WeightedDecisionEngine.decide()` — i.e. the ScoringEngine output **before WDE adjustments**, after ScoringEngine's own caps and specialist delta.

**Answer:** ScoringEngine confidence entering WDE = **27.5%** for this cached run.

> Full per-component ScoringEngine breakdown was **not persisted** in SQLite (`confidence_breakdown: null`). Components below are reconstructed from stored `national_team_intelligence` and pipeline behavior.

### Local live comparison (same fixture, fresh run — NOT cached)

Running the pipeline locally **right now** (non-placeholder intelligence):

| Stage | Confidence |
|-------|------------|
| ScoringEngine breakdown total | 68.7 |
| WDE baseline | 61.7 |
| WDE final | 62.7 |
| Adaptive base → final | 62.7 → **73.1** (+10.4 bonus) |
| Final API confidence | **71.4** |

This proves the **3% cached value is stale/degraded**, not an inherent property of Germany vs Ivory Coast.

---

## Question 4 — What confidence is stored in SQLite?

Production row (`worldcup_stored_predictions`, fixture 1489393):

| Field | Value |
|-------|-------|
| `source` | `background_daily` |
| `predicted_at` | `2026-06-20T15:09:04.074979Z` |
| **`confidence`** | **3.0** |
| `no_bet` | `true` |
| `pick_tier` | `caution` |
| `data_quality` | 65.0 |
| `confidence_breakdown` | `null` |
| `audit_trace.confidence.final` | **11.5** (WDE only) |

**Answer:** SQLite stores **3.0** as top-level confidence (post-adaptive). WDE trace (11.5) is embedded in `audit_trace` but does not match the displayed value.

---

## Question 5 — Is Phase 33B using the wrong field?

Phase 33B `enrich_pick_visibility()` uses:

```49:49:worldcup_predictor/api/pick_visibility.py
    confidence = float(prediction.confidence_score or 0.0)
```

API serialization:

```146:146:worldcup_predictor/api/routes/predictions.py
        "confidence": prediction.confidence_score,
```

Market ranking WDE input:

```330:330:worldcup_predictor/api/market_ranking_engine.py
    wde = min(1.0, max(0.0, float(prediction.confidence_score or 0) / 100.0))
```

Production `rank_inputs.wde_confidence` = **0.03** (= 3.0 / 100) — consistent.

**Answer:** Phase 33B uses the **correct field**. It is **not** reading market probability, `match_winner.confidence`, or specialist score by mistake.

Caution tier is correct: 3.0 < 60 threshold → `pick_tier: caution`, `no_bet: true`, gap 57 pts.

---

## Question 6 — Full scoring breakdown

### A. Stored National Team Intelligence (production SQLite)

| Component | Score | Notes |
|-----------|-------|-------|
| **Consensus** | **45.0** | `consensus_strength_score` |
| **Form** | **47.2** | `national_form_score` |
| **H2H** | **61.1** | `national_h2h_score` |
| **Injuries** | **65.0** | `injury_impact_score` |
| **Squad** | **62.8** | `squad_strength_score` |
| **Data Quality** | **65.0** | API `data_quality` |

Coverage: 5 home recent matches, 5 away recent matches, 3 H2H meetings.

### B. ScoringEngine weights (reference)

| Factor | Weight |
|--------|--------|
| Form | 0.22 |
| H2H | 0.18 |
| Injuries | 0.15 |
| Lineups | 0.10 |
| Odds | 0.15 |
| Data Quality | 0.20 |

### C. WDE factor penalties (this cached run)

| Signal | Effect |
|--------|--------|
| National intel boost | +1.0 |
| Specialist conflicts (high) | −12.0 |
| Odds vs model disagreement | −5.0 |
| **Net WDE adjustment** | **−16.0** (27.5 → 11.5) |

### D. Adaptive confidence layer (inferred)

| Stage | Confidence |
|-------|------------|
| WDE final | 11.5 |
| Adaptive penalty (inferred) | **≈ −8.5** |
| **Stored/API final** | **3.0** |

Adaptive engine runs in `_finalize_prediction()` after WDE and **overwrites** `confidence_score`:

```406:408:worldcup_predictor/adaptive_confidence/engine.py
        return replace(
            prediction,
            confidence_score=adjustment.final_confidence,
```

`MAX_TOTAL_PENALTY = -15.0` — a −8.5 learning-memory penalty is within bounds.

### E. Specialist consensus

| Metric | Value |
|--------|-------|
| Aggregated specialist score | 50.5 |
| Specialist agreement (market rank) | 0.505 |

---

## Question 7 — Why Germany Home Win = 51.7%?

Production probabilities:

| Outcome | Probability |
|---------|-------------|
| **Home Win (Germany)** | **51.7%** |
| Draw | 23.6% |
| Away Win (Ivory Coast) | 24.7% |

Yet **`prediction: draw`** and headline 1X2 selection is **Draw**.

### Explanation

These are **two different concepts**:

1. **Full-time 1X2 probability distribution** — from extended markets / scoreline-harmonized model (`extended_markets_ft_1x2`). Germany leads at 51.7% because strength/xG models favor Germany.

2. **Official 1X2 selection** — resolved by WDE `_resolve_1x2()` which can override to **draw** when:
   - `home_edge_total` is within balanced threshold (`balanced_edge_max`)
   - Live calibration `should_prefer_draw()` returns true (draw implied prob ≥ threshold)
   - Scoreline harmonization aligns 1X2 to primary scoreline (e.g. 1-1 → draw)

Stored no-bet reasons include **`placeholder_data`** — intelligence was flagged placeholder at background job time, triggering conservative draw-leaning behavior and low confidence.

### Why not higher?

- WDE did not commit to Home Win despite 51.7% lean — balanced edge + draw calibration + placeholder caution
- Confidence penalties (conflicts, odds disagreement, placeholder) suppress official recommendation
- Germany is favored probabilistically but **not confidently** enough for official tier

### Why not lower?

- National H2H (61.1), squad (62.8), injuries (65.0) support Germany
- Double Chance **Home or Away** ranked top caution pick at **76.4%**
- Data quality 65% is medium — not catastrophic

### Local fresh run contrast

| Metric | Cached (production) | Fresh local run |
|--------|---------------------|-----------------|
| 1X2 selection | draw | **home_win** |
| Home win prob (extended) | 51.7% | **84.6%** |
| Final confidence | 3.0% | **71.4%** |
| Placeholder flag | yes (at job time) | no |

---

## Question 8 — Is confidence display a bug?

### Verdict: **Not a UI bug — a pipeline transparency + cache staleness issue**

| Layer | Bug? | Detail |
|-------|------|--------|
| **UI `roundPercent`** | ❌ No | Correctly displays API `confidence: 3.0` |
| **Phase 33B field** | ❌ No | Uses `confidence_score` correctly |
| **API ↔ SQLite** | ❌ No | Both store 3.0 consistently |
| **Audit trace completeness** | ⚠️ Yes | Shows WDE final 11.5 but **omits adaptive** step that produces 3.0 |
| **Stale background cache** | ⚠️ Yes | Job at 15:09 UTC used `placeholder_data`; fresh run → 71.4% |
| **Probability vs selection** | ⚠️ Yes | `match_winner.confidence: 58.6` stale — WDE changed selection to draw without updating `one_x_two.probability` |
| **UX confusion** | ⚠️ Yes | 3% model confidence shown next to 51.7% home win with no explanation |

### Confidence pipeline (this fixture, cached)

```
ScoringEngine (27.5)
    ↓
WDE caps/reductions (→ 11.5)
    ↓
Adaptive Confidence Engine (→ 3.0)   ← NOT in audit_trace.final
    ↓
API / SQLite / UI (3.0%)
```

### What users see vs what happened

| User sees | Actual meaning |
|-----------|----------------|
| Confidence 3% | Final adaptive model certainty (very low) |
| Home Win 51.7% | Extended-market probability lean (informational) |
| Prediction: Draw | WDE official 1X2 selection (overridden) |
| Caution pick: DC Home/Away 76.4% | Best available market under low confidence |

---

## Additional finding — `match_winner.confidence: 58.6`

Production `detailed_markets.match_winner`:

```json
{
  "selection": "draw",
  "probabilities": { "home_win": 51.7, "draw": 23.6, "away_win": 24.7 },
  "confidence": 58.6
}
```

`confidence: 58.6` comes from `_pct(prediction.one_x_two.probability)` — but selection is **draw** (23.6%). The 58.6% appears to be a **stale probability** from before WDE changed the 1X2 selection. This adds to user confusion but is separate from the top-level 3% confidence display.

---

## Recommendations (audit only — not implemented)

1. **Expose adaptive confidence in audit trace** — show `adaptive_base`, `adaptive_final`, `learning_bonus` alongside WDE baseline/final
2. **Refresh stale placeholder predictions** — background job flagged `placeholder_data` but fixture row now shows `is_placeholder: 0`
3. **Sync `one_x_two.probability` when WDE changes selection** — fix match_winner confidence mismatch
4. **UI label clarity** — distinguish "Model confidence" (3%) from "Home win probability" (51.7%)
5. **Do not treat as Phase 33B field bug** — caution tier logic is correct for confidence 3.0

---

## Evidence summary

| Source | Key finding |
|--------|-------------|
| Production API POST `/api/predict/1489393` | `confidence: 3.0`, `cache_source: sqlite_store` |
| Production SQLite | Same payload, `source: background_daily`, `predicted_at: 2026-06-20T15:09:04Z` |
| Stored `audit_trace.confidence` | baseline 27.5, final 11.5 |
| Local fresh pipeline | confidence 71.4 (same fixture, current data) |
| Phase 33B `pick_visibility.py` | Uses `prediction.confidence_score` — correct |

---

**STOP — Audit complete. No code changes. No deploy.**

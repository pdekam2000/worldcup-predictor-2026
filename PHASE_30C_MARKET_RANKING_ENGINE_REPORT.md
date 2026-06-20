# Phase 30C — Market Ranking Engine

**Status:** Implementation complete — validation passed locally. **Not deployed** (awaiting approval).

---

## Executive Summary

Phase 30C replaces the fixed `1X2 → O/U → BTTS` recommendation order with a **cross-market ranking engine** that scores all available markets and assigns **Safe / Value / Aggressive** picks.

**Key outcome:** When Home Win is 61% but Home or Draw (Double Chance) is 82%, the system now recommends **Double Chance** as the Safe Pick and primary `recommended_bets` entry.

**Validation:** 26/26 Phase 30C checks passed, including Phase 29 and Phase 30A regression.

---

## Problem (Phase 30B Finding)

| Before (Phase 30A) | After (Phase 30C) |
|--------------------|-------------------|
| Slot 1 always 1X2 (global confidence) | Safe Pick = highest-ranked safe market |
| Slot 2 O/U before BTTS (fixed order) | Value Pick = highest-ranked value market |
| Double Chance shown but never recommended | Double Chance can outrank 1X2 |
| No aggressive tier | Aggressive Pick for HT / scorer / correct score |

### Example — Brazil vs France (fixture 1539007)

| Market | Probability | Phase 30A | Phase 30C |
|--------|-------------|-----------|-----------|
| Home Win | 61% | **Recommended #1** | Ranked #2 |
| Home or Draw (DC) | 82% | Not recommended | **Safe Pick + Recommended #1** |
| Over 2.5 | 64% | Recommended #2 | **Value Pick + Recommended #2** |

---

## Files Changed

| File | Change |
|------|--------|
| `worldcup_predictor/api/market_ranking_engine.py` | **New** — candidate inventory, `market_rank_score`, bucket assignment |
| `worldcup_predictor/api/prediction_output.py` | Integrates ranking; `recommended_bets` now derived from ranked picks |
| `worldcup_predictor/api/routes/predictions.py` | Exposes `market_ranking`, `safe_pick`, `value_pick`, `aggressive_pick`, `accuracy_tracking` |
| `base44-d/src/pages/PredictionDetail.jsx` | Ranked Picks section (Safe / Value / Aggressive) above Recommended Bets |
| `base44-d/src/api/worldcupApi.js` | Normalizes Phase 30C fields |
| `scripts/validate_phase30c_market_ranking_engine.py` | **New** validation (26 checks) |

**Unchanged:** WDE, calibration, promotion modes, Phase 29 history evaluation, Match Center routes, subscription UI, database schema.

---

## Ranking Logic

### Step 1 — Market candidate inventory

Built from `detailed_markets` + `MatchPrediction`. Skips unavailable markets safely.

| Market key | Bucket | Min probability |
|------------|--------|-------------------|
| `double_chance` | safe | 52% |
| `1x2` | safe | 52% |
| `over_under_2_5` | value | 55% |
| `btts` | value | 55% |
| `ht_result` | aggressive | 32% |
| `first_goal_team` | aggressive | 32% |
| `first_half_team_to_score` | aggressive | 32% |
| `correct_score` | aggressive | 32% |
| `goalscorer` | aggressive | 32% |
| `first_goal_minute` | aggressive | 32% |

### Step 2 — `market_rank_score` (0.0 → 1.0)

```
raw = 0.48×probability + 0.18×WDE_conf + 0.14×data_quality
    + 0.12×specialist_agreement + 0.08×consistency_factor
    + odds_consensus_adj (±0.05 if market consensus high/low)

market_rank_score = clamp(raw × bucket_multiplier, 0, 1)
```

Bucket multipliers: safe `1.0`, value `0.96`, aggressive `0.84`.

Each ranked entry includes `rank_inputs` and a human-readable `reasoning` explanation.

### Step 3 — Bucket assignment

- **SAFE_PICK** — highest `market_rank_score` among safe-bucket candidates
- **VALUE_PICK** — highest among value-bucket candidates (excluding correlated picks)
- **AGGRESSIVE_PICK** — highest among aggressive-bucket candidates (excluding correlated picks)

Correlation rules prevent e.g. Home Win + Home/Draw from both being selected.

### Step 4 — `recommended_bets` (backward compatible)

Derived from **Safe Pick + Value Pick** (max 2), preserving Phase 30A JSON shape. No Bet logic unchanged (WDE flag + confidence ≥ 55% + data quality ≥ 45%).

---

## API Payload Changes

### New fields (additive)

```json
{
  "market_ranking": [
    {
      "market": "Double Chance",
      "market_key": "double_chance",
      "pick": "Home or Draw",
      "selection": "home_or_draw",
      "probability": 0.82,
      "market_rank_score": 0.786,
      "bucket": "SAFE",
      "reasoning": "model probability 82.0%; WDE confidence 72%; ...",
      "rank_inputs": { "probability": 0.82, "wde_confidence": 0.72, "...": "..." }
    }
  ],
  "safe_pick": { "...": "..." },
  "value_pick": { "...": "..." },
  "aggressive_pick": { "...": "..." },
  "accuracy_tracking": {
    "schema_version": "1.0",
    "no_bet": false,
    "safe_pick": { "market_key": "double_chance", "selection": "home_or_draw", "...": "..." },
    "value_pick": { "...": "..." },
    "aggressive_pick": { "...": "..." },
    "recommended_bets_slots": []
  }
}
```

### Preserved fields

- `recommended_bets`, `probabilities`, `detailed_markets`, `primary_recommendation`, `no_bet`, `risk_level`, `specialist_summary`, legacy `prediction` / `confidence`

Cached payloads missing `market_ranking` are backfilled via `enrich_cached_prediction_output()`.

---

## Frontend Changes

**Prediction Detail** layout (top to bottom):

1. Match header
2. **Ranked Picks** — Safe / Value / Aggressive cards (Phase 30C)
3. **Recommended Bets** — existing card (now reflects ranked picks)
4. **Detailed Probabilities** — unchanged collapsible sections
5. Specialist analysis — unchanged

---

## Accuracy Future-Proofing

`accuracy_tracking` stores stable `market_key` + `selection` identifiers for:

- `safe_pick`, `value_pick`, `aggressive_pick`
- `recommended_bets_slots`

Schema version `1.0` — ready for future winrate evaluation without modifying Phase 29 history evaluation.

---

## Validation Results

```
python scripts/validate_phase30c_market_ranking_engine.py
```

| Check | Result |
|-------|--------|
| Double Chance outranks 1X2 | PASS |
| BTTS can outrank O/U in value bucket | PASS |
| `market_rank_score` generated for all ranked markets | PASS |
| safe / value / aggressive picks returned | PASS |
| Phase 29 regression | PASS |
| Phase 30A regression | PASS |
| Legacy API fields present | PASS |
| Cache backfill for `market_ranking` | PASS |

**Total: 26/26 passed**

---

## Deployment Checklist (Phases 29 + 30A + 30C)

**Do not deploy until approved.**

### Files to deploy

| Layer | Files |
|-------|-------|
| Backend | `worldcup_predictor/api/market_ranking_engine.py` (new) |
| Backend | `worldcup_predictor/api/prediction_output.py` |
| Backend | `worldcup_predictor/api/routes/predictions.py` |
| Frontend | `base44-d/src/pages/PredictionDetail.jsx` |
| Frontend | `base44-d/src/api/worldcupApi.js` |

Phase 29 files (if not already deployed):

- `worldcup_predictor/api/prediction_history_evaluation.py`
- `worldcup_predictor/api/routes/user.py`
- `base44-d/src/pages/PredictionHistoryPage.jsx`
- `base44-d/src/api/saasApi.js`

### Migrations required

**None.** All changes are API response + frontend only. No PostgreSQL schema changes.

### Environment changes

**None.** No new env vars.

### Deployment order

1. **Backend API** — deploy Python changes; restart `worldcup-api`
2. **Verify API** — `POST /api/predict/{fixture_id}` returns `market_ranking`, `safe_pick`, `value_pick`, `aggressive_pick`
3. **Verify cache backfill** — `GET` cached prediction enriches missing ranking fields
4. **Frontend build** — `npm run build` in `base44-d/`
5. **Deploy frontend** — static assets / nginx
6. **Smoke test UI** — Prediction Detail shows Ranked Picks + Recommended Bets + Detailed Markets
7. **Regression** — Phase 29 prediction history filters still work

### Rollback plan

| Step | Action |
|------|--------|
| 1 | Revert frontend to previous build (Ranking section disappears; old Recommended Bets still works if backend reverted) |
| 2 | Revert backend to pre-30C commit — restores fixed 1X2-first `recommended_bets` |
| 3 | No DB rollback needed |
| 4 | Cached predictions self-heal on next pipeline run or via backfill on read |

**Safe partial rollback:** Revert frontend only — backend adds new fields harmlessly; old UI ignores them.

---

## Post-Deploy Verification Commands

```bash
# Backend validation (on server or locally)
python scripts/validate_phase30c_market_ranking_engine.py
python scripts/validate_phase30a_prediction_output_completeness.py
python scripts/validate_phase29_prediction_history_results.py

# API smoke (replace fixture_id and token)
curl -s -X POST "https://YOUR_DOMAIN/api/predict/1539007" \
  -H "Authorization: Bearer TOKEN" | jq '.safe_pick, .value_pick, .recommended_bets'
```

---

## STOP

Implementation and validation complete. **Awaiting deployment approval.**

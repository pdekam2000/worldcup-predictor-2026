# Phase 30A — Prediction Output Completeness + Bet Recommendation UI

**Status:** Implementation complete — validation passed locally. **Not deployed** (awaiting approval).

---

## Executive Summary

Prediction Detail now leads with a clear **Recommended Bet** card (or **No Bet** when confidence/data quality is weak), with all raw probabilities moved into collapsible **Detailed Probabilities** sections.

**Root cause of missing Over/Under 2.5:** `_extract_probabilities()` in `predictions.py` returned early when `extended_markets_ft_1x2` metadata existed, emitting **only** 1X2 percentages and **dropping** `over_under_2_5`. The frontend correctly read `probabilities.over_under_2_5` — the backend simply stopped sending it for most live predictions.

---

## Root Cause Analysis

### Over/Under 2.5 missing

| Layer | Finding |
|-------|---------|
| Pipeline | `MatchPrediction.over_under` always populated by WDE |
| Metadata | `attach_extended_markets_to_prediction()` sets `extended_markets_ft_1x2` (home/draw/away only) |
| API bug | `_extract_probabilities()` hit `extended_markets_ft_1x2` branch → returned `{home_win, draw, away_win}` only |
| Frontend | `PredictionDetail.jsx` reads `result.probabilities.over_under_2_5` → `null` → "Extended market data not returned" |

**Not caused by:** odds agent stripping, worldcupApi mapping, or Streamlit-only payloads.

### Other markets

Extended markets (BTTS, HT, first goal, goalscorer) were built in `extended_markets.py` and stored in metadata JSON but **never exposed** in the public API response.

---

## Files Changed

| File | Change |
|------|--------|
| `worldcup_predictor/api/prediction_output.py` | **New** — `detailed_markets`, `recommended_bets`, unified `probabilities` |
| `worldcup_predictor/api/routes/predictions.py` | `_success_payload()` adds Phase 30A fields; fixed probability extraction |
| `worldcup_predictor/api/display_helpers.py` | Backfills Phase 30A fields on cached payloads |
| `base44-d/src/pages/PredictionDetail.jsx` | Recommendation card + collapsible market details |
| `base44-d/src/api/worldcupApi.js` | `normalizePredictionPayload()` helper |
| `scripts/validate_phase30a_prediction_output_completeness.py` | **New** validation |

**Unchanged:** WDE, calibration, promotion modes, Phase 29 history, Match Center routes.

---

## API Payload

### Before (typical live response)

```json
{
  "status": "ok",
  "fixture_id": 1539007,
  "prediction": "home",
  "confidence": 72.4,
  "probabilities": {
    "home_win": 52.1,
    "draw": 24.3,
    "away_win": 23.6
  },
  "data_quality": 68.0,
  "specialist_summary": { "...": "..." }
}
```

Note: **no** `over_under_2_5`, **no** BTTS/HT, **no** recommendation structure.

### After (Phase 30A)

```json
{
  "status": "ok",
  "fixture_id": 1539007,
  "prediction": "home",
  "confidence": 72.4,
  "risk_level": "medium",
  "no_bet": false,
  "recommended_bets": [
    {
      "market": "1X2",
      "pick": "Home Win",
      "display_text": "Bet on Home Win",
      "confidence": 0.724,
      "risk_level": "medium",
      "reasoning": "Primary match winner signal from weighted decision engine.",
      "source_agents": ["WDE", "Form", "Odds"],
      "status": "recommended"
    },
    {
      "market": "Over/Under 2.5",
      "pick": "Over 2.5",
      "display_text": "Bet on Over 2.5",
      "confidence": 0.64,
      "status": "recommended"
    }
  ],
  "primary_recommendation": { "...first item..." },
  "detailed_markets": {
    "match_winner": { "selection": "home_win", "probabilities": { "home_win": 52.1, "draw": 24.3, "away_win": 23.6 } },
    "over_under_25": { "selection": "over_2_5", "probabilities": { "over_2_5": 64.0, "under_2_5": 36.0 } },
    "btts": { "selection": "yes", "probabilities": { "yes": 58.0, "no": 42.0 } },
    "halftime": { "...": "..." },
    "first_goal": { "team": "Brazil", "minute_range": "16-30" },
    "goalscorer": { "available": true, "player": "..." },
    "double_chance": { "home_or_draw": 76.4, "home_or_away": 75.7, "draw_or_away": 47.9 }
  },
  "probabilities": {
    "home_win": 52.1,
    "draw": 24.3,
    "away_win": 23.6,
    "over_under_2_5": { "selection": "over_2_5", "probability": 0.64, "probabilities": { "over_2_5": 64.0, "under_2_5": 36.0 } },
    "btts": { "selection": "yes", "probability": 0.58, "probabilities": { "yes": 58.0, "no": 42.0 } }
  }
}
```

Legacy fields preserved for backward compatibility.

---

## Recommendation Logic

Thresholds (no WDE changes):

| Rule | Value |
|------|-------|
| Min confidence | 55% |
| Min data quality | 45% |
| Secondary market min prob | 58% |
| Max recommended picks | 2 |

Flow:

1. If `no_bet_flag` or below thresholds → single **No Bet** entry (`status: no_bet`)
2. Always recommend primary **1X2** pick when thresholds pass
3. Add **O/U 2.5** or **BTTS** only if probability ≥ 58% and slot available
4. Future winrate tracking should use `recommended_bets` only (not raw `probabilities`)

---

## Frontend UX

**Prediction Detail (`/prediction/:id`):**

1. **Top — Recommendation card**
   - Green/primary styling for picks; yellow for No Bet
   - Shows confidence, risk level, data quality, reasoning, source agents
   - Multi-pick chips when 2 markets recommended

2. **Middle — Detailed Probabilities (collapsible)**
   - Match Winner 1X2
   - Over/Under 2.5
   - BTTS
   - Half Time
   - First goal team + minute range
   - Likely goalscorer (when data exists)
   - Double chance

3. **Below — unchanged**
   - Specialist Analysis grid
   - Promotion Trace panel

Cached payloads backfilled via `enrich_cached_prediction_output()` on read.

---

## Validation

```text
python scripts/validate_phase30a_prediction_output_completeness.py
→ All 19 Phase 30A checks passed

python scripts/validate_phase29_prediction_history_results.py
→ All 16 Phase 29 checks passed (regression)
```

---

## Deploy Instructions (after approval)

1. Deploy backend + rebuild frontend (`base44-d`)
2. Fix production cache ownership if needed (see Phase 28B ops note)
3. Run predict on a WC fixture — verify API includes `recommended_bets` and `probabilities.over_under_2_5`
4. Open Prediction Detail — confirm recommendation card + O/U in collapsible section
5. Old cached predictions auto-backfill on read; force refresh for full extended markets from live pipeline

**No database migration required.**

---

## STOP

Awaiting approval before production deploy.

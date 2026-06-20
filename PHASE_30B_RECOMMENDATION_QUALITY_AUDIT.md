# Phase 30B — Recommendation Quality Audit

**Status:** Audit complete — **no code changes, no deploy.**

**Goal:** Verify that `recommended_bets` truly selects the strongest betting market available.

**Scope:** Pipeline (`extended_markets.py`, WDE, `scoring_engine.py`), API (`prediction_output.py`), UI (`PredictionDetail.jsx`), accuracy tracking (`accuracy/metrics.py`), local prediction history (`data/predictions/prediction_history.jsonl`).

---

## Executive Summary

Phase 30A introduced structured recommendations, but the engine **does not rank markets by strength**. It uses a **fixed priority order**:

1. **Slot 1 — always 1X2** (uses global `confidence_score`, not per-market probability)
2. **Slot 2 — O/U 2.5 if ≥ 58%**, else **BTTS if ≥ 58%** (max 2 picks total)

**Verdict:** `recommended_bets` can **miss stronger markets** in several common scenarios. The system exposes many markets in API/UI that are **never eligible** for recommendation. Two markets (Draw No Bet, Over/Under 3.5) are **not predicted at all**.

| Finding | Severity |
|---------|----------|
| 1X2 always occupies primary slot regardless of per-market edge | **High** |
| Double Chance / HT / goalscorer never recommendable despite being shown | **High** |
| O/U checked before BTTS — not highest-probability secondary | **Medium** |
| Raw probability compared across market types without odds/EV normalization | **Medium** |
| No Bet thresholds differ between WDE (60/50) and Phase 30A (55/45) | **Low** (mostly aligned via `no_bet_flag`) |
| No historical winrate data to validate ranking | **Info** |

---

## 1. Market Inventory

### 1.1 Full market matrix

| Market | Predicted (pipeline) | API (`detailed_markets`) | UI (`PredictionDetail`) | Can become `recommended_bet`? |
|--------|---------------------|--------------------------|-------------------------|-------------------------------|
| **1X2 (Match Winner)** | Yes — WDE + `MatchPrediction.one_x_two` | Yes — `match_winner` | Yes — "Match Winner (1X2)" | **Yes — always slot 1** |
| **Double Chance** | Derived — sum of 1X2 probs in API (`_double_chance()`) | Yes — `double_chance` | Yes — collapsible section | **No** |
| **Draw No Bet (DNB)** | **No** — not computed anywhere | **No** | **No** | **No** |
| **BTTS** | Yes — `extended_markets.py` (Poisson model) | Yes — `btts` | Yes — "Both Teams To Score" | **Yes — slot 2 if ≥ 58% and O/U did not fill slot** |
| **Over/Under 2.5** | Yes — WDE + baseline scoring engine | Yes — `over_under_25` | Yes — "Over / Under 2.5" | **Yes — slot 2 if ≥ 58%** |
| **Over/Under 3.5** | **No** | **No** | **No** | **No** |
| **HT Result (1X2)** | Yes — `extended_markets.halftime_1x2` | Yes — `halftime` | Yes — "Half Time Result" | **No** |
| **First Team To Score** | Yes — `MatchPrediction.first_goal.team` | Yes — `first_goal.team` | Yes — inside "First Goal & Timing" | **No** |
| **Team To Score First Half** | Derived — alias of HT leader in API | Yes — `first_half_team_to_score` | **Partial** — HT section only, no dedicated label | **No** |
| **Goalscorer** | Yes — `extended_markets.top_scorer` | Yes — `goalscorer` | Yes — "Likely Goalscorer" (when data available) | **No** |
| **First Goal Minute** | Yes — minute band + expected minute | Yes — `first_goal.minute_range` | Yes — inside "First Goal & Timing" | **No** |
| **Correct Score** | Yes — top 3 scorelines in extended markets | Yes — `correct_scores` | **No** — Streamlit only | **No** |
| **Halftime Goals (total)** | Yes — `HalftimePrediction.estimated_total_goals` | Partial — embedded in HT probs | Indirect via HT section | **No** |

**Other markets:** No Asian handicap, corners, cards, or additional goal lines exist in the codebase.

### 1.2 Prediction sources

| Layer | Markets produced |
|-------|-------------------|
| `scoring_engine.py` | 1X2, O/U 2.5, HT goals estimate, first goal team/player/minute, scoreline |
| `extended_markets.py` | Full FT 1X2 distribution, O/U 2.5, BTTS, HT 1X2, first goal time, goalscorers, correct scores |
| `weighted_decision_engine.py` | Final 1X2 selection, O/U selection, HT/first-goal **informational** `MarketDecision` objects (not used by Phase 30A ranking) |
| `prediction_output.py` | Double chance (derived), first-half-to-score (derived), recommendation assembly |

---

## 2. Recommendation Engine Logic (Current)

Source: `worldcup_predictor/api/prediction_output.py` — `build_recommended_bets()`.

### Thresholds

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `_MIN_CONFIDENCE` | 55% | Global confidence gate |
| `_MIN_DATA_QUALITY` | 45% | Data quality gate |
| `_MIN_SECONDARY_PROB` | 58% (0.58) | O/U or BTTS secondary pick |
| `_MAX_RECOMMENDED` | 2 | Max picks returned |

### Algorithm

```
IF no_bet_flag OR confidence < 55 OR data_quality < 45:
    RETURN single "No Bet" entry

ALWAYS append 1X2 pick (confidence = global confidence_score)

IF over_under_25.probability >= 0.58 AND len(picks) < 2:
    append O/U 2.5

IF btts.probability >= 0.58 AND len(picks) < 2:
    append BTTS

RETURN picks[:2]
```

**Key properties:**

- No cross-market comparison — fixed slot assignment
- 1X2 confidence is **model-wide** `confidence_score`, not `max(home, draw, away)` nor selected-outcome probability
- Secondary slot is **first qualifying market in priority order** (O/U before BTTS), not strongest secondary
- Double chance, HT, DNB, goalscorer, first goal — **never considered**

---

## 3. Ranking Audit — Can Stronger Markets Be Missed?

### 3.1 Double Chance stronger than Home Win

**Yes — structurally missed.**

Double chance probabilities are sums of two 1X2 outcomes (`home_or_draw = home + draw`, etc.). For almost every fixture, the best double-chance line exceeds the best single 1X2 outcome by 15–30 percentage points.

**Example (France vs Senegal, fixture 1489383, local history):**

| Market | Model probability | Recommended? |
|--------|-------------------|----------------|
| Home Win | 58.8% | Yes — slot 1 (if thresholds pass) |
| Home or Draw | **82.2%** | No — not eligible |
| Under 2.5 | 53.6% | No — below 58% |
| BTTS No | 52.9% | No — below 58% |

**Local sample:** Of 16 predictions with extended markets JSON, **16/16 (100%)** had best double-chance probability > selected 1X2 outcome + 5pp.

**Caveat:** Higher raw probability ≠ stronger *bet* without odds. Double chance pays ~1.2–1.5x vs home win ~1.7–2.5x. A proper ranking needs **implied edge vs book odds**, not probability alone. The engine compares neither odds nor normalized edge today.

### 3.2 DNB stronger than Home Win

**Not applicable — DNB is not predicted.**

DNB could be derived from 1X2 (`P(home DNB) ≈ P(home) / (1 - P(draw))`) but no module computes or exposes it. Users cannot see or receive DNB recommendations.

### 3.3 Under 3.5 stronger than Over 2.5

**Not applicable — O/U 3.5 is not predicted.**

Only the 2.5 line exists. When totals model is low-scoring, Under 2.5 may qualify (≥ 58%) but Under 3.5 — often an even safer play at similar fixtures — is unavailable.

### 3.4 BTTS No stronger than 1X2

**Yes — can be missed.**

BTTS No can exceed 58% while the 1X2 pick uses global confidence (often 55–65 range). BTTS No only gets slot 2 if O/U did not already fill it, even when BTTS No has higher probability than O/U.

**Example pattern (common in low-scoring predictions):**

| Market | Probability | Slot |
|--------|-------------|------|
| Draw (1X2 pick) | 26.5% | Slot 1 (confidence 56.5% global) |
| BTTS No | 53.0% | Not recommended (< 58%) |
| Under 2.5 | 55.6% | Not recommended (< 58%) |

When BTTS No **does** exceed 58%, it still loses to O/U in slot 2 if both qualify, regardless of which has higher probability.

### 3.5 HT Result / First Goal / Goalscorer stronger than 1X2

**Yes — always missed.**

These markets are exposed in `detailed_markets` and UI but excluded from `build_recommended_bets()`. WDE assigns them lower confidence multipliers (HT: 0.85×, first goal team: 0.9×) suggesting they are considered secondary — yet they cannot displace a weak 1X2 primary pick.

### 3.6 Summary of ranking gaps

| Scenario | Can occur? | Root cause |
|----------|------------|------------|
| DC shown as 80%+ but Home Win recommended | **Always** (when actionable) | DC not in recommendation pool |
| BTTS No > 1X2 outcome prob, only 1X2 recommended | **Yes** | 1X2 locked to slot 1 |
| BTTS > O/U prob but O/U gets slot 2 | **Yes** | Fixed O/U-before-BTTS order |
| Strong Under 2.5 missed because 1X2 used weak global confidence | **Partially** | 1X2 uses global score not outcome prob |
| User sees "No Bet" but detailed markets show 70%+ DC | **Yes** | No Bet gate vs informational markets decoupled |

---

## 4. Ranking Table

### 4.1 Model-side averages (local sample)

Source: `data/predictions/prediction_history.jsonl` — 105 records, 16 with `extended_markets_json`.

| Market | Avg confidence / probability | Historical winrate | Risk level | Current recommendation priority |
|--------|------------------------------|-------------------|------------|--------------------------------|
| **1X2** | Global confidence **55.2%** (avg across all preds) | **N/A** — 0 finished evals in accuracy tracker | medium–high (62% preds flagged no-bet) | **1 (forced primary)** |
| **Double Chance (best line)** | **~67–82%** (derived; avg Home/Draw **67.2%**) | **Not tracked** | Lower variance than single 1X2 | **Not eligible** |
| **O/U 2.5** | Avg Over **45.6%** / Under **54.4%** | **N/A** | medium | **2 (if ≥ 58%)** |
| **BTTS** | Avg Yes **53.4%** / No **46.6%** | **Not tracked** | medium | **3 (if ≥ 58%, slot 2 if O/U absent)** |
| **HT Result** | ~33/34/33% typical three-way | **N/A** (bucket eval exists but no data) | high | **Not eligible** |
| **First Goal Team** | Team name only; no % in recommendation path | **N/A** | high | **Not eligible** |
| **Goalscorer** | Player pick; confidence when available | **Not tracked** | very high | **Not eligible** |
| **First Goal Minute** | Band (e.g. 16–30) | **Not tracked** | very high | **Not eligible** |
| **Correct Score** | Top scoreline ~10–18% typical | **N/A** (exact score eval exists) | very high | **Not eligible** |
| **Draw No Bet** | — | — | — | **Not available** |
| **O/U 3.5** | — | — | — | **Not available** |

### 4.2 Historical winrate availability

`AccuracyTrackerService.refresh()` returned **all null** metrics locally — no finished matches with stored predictions have been evaluated yet. Tracked when data exists:

- 1X2, O/U 2.5, HT bucket, exact scoreline, first goal team
- **Not tracked:** BTTS, double chance, DNB, goalscorer, minute bands

**Implication:** Recommendation quality cannot be validated against realized outcomes today. Any ranking improvement should be paired with BTTS/DC outcome logging in a future phase.

### 4.3 Recommended ranking order (ideal vs current)

**If the goal is highest win probability for the user** (ignoring odds/EV):

| Rank | Market type | Rationale |
|------|-------------|-----------|
| 1 | Best **Double Chance** line | Highest raw model probability most fixtures |
| 2 | Best **1X2** outcome (if ≥ threshold) | When DC edge over 1X2 is small or odds-adjusted EV favors 1X2 |
| 3 | **O/U 2.5** or **BTTS** (whichever prob highest ≥ 58%) | Secondary uncorrelated market |
| 4 | **HT Result** / **First Goal** | Lower calibration; informational only |
| 5 | **Goalscorer** / **Correct Score** | High variance; never primary |

**If the goal is highest expected value** (proper betting optimization):

| Rank | Approach |
|------|----------|
| 1 | Compute **edge = model_prob − implied_prob_from_odds** per market |
| 2 | Rank all eligible markets by edge × confidence |
| 3 | Cap at 2 picks with correlation penalty (don't recommend Home + Home/Draw) |

**Current engine rank:** `1X2 (forced) → O/U 2.5 → BTTS` — does not match either ideal order.

---

## 5. No Bet Logic Verification

### 5.1 Three layers

| Layer | Trigger conditions | Thresholds |
|-------|-------------------|------------|
| **Scoring engine** (`scoring_engine.py`) | `no_bet_flag = True` when | data quality < **45%**, confidence level LOW/UNAVAILABLE, or all placeholder data |
| **WDE** (`weighted_decision_engine.py`) | Adds/overrides no bet when | data quality < **50%**, confidence level LOW/UNAVAILABLE, placeholder, confidence < **60%** |
| **Phase 30A** (`build_recommended_bets`) | Returns "No Bet" when | `no_bet_flag` **OR** confidence < **55%** **OR** data quality < **45%** |

Default WDE thresholds from `config/model_weights.py`:

```python
"analysis_ready_confidence_minimum": 60.0,
"no_bet_confidence_minimum": 60.0,
"data_quality_no_bet_threshold": 50.0,
```

Phase 30A thresholds:

```python
_MIN_CONFIDENCE = 55.0
_MIN_DATA_QUALITY = 45.0
```

### 5.2 Alignment analysis

| Case | WDE `no_bet_flag` | Phase 30A result | Aligned? |
|------|-------------------|------------------|----------|
| confidence 58, dq 55 | **True** (< 60) | No Bet (flag) | Yes |
| confidence 62, dq 48 | **True** (< 50 dq) | No Bet (flag) | Yes |
| confidence 62, dq 55, flag false | False | **Recommend** (62 ≥ 55, dq ≥ 45) | Yes — WDE allows |
| confidence 56, dq 70, flag false* | False* | **Recommend** (56 ≥ 55) | **Risk** — WDE would usually set flag at < 60 |

\*In practice WDE sets `no_bet_flag=True` when confidence < 60, so the 56/70 case normally returns No Bet via flag before Phase 30A's 55 threshold matters.

**Local stats:** 105 predictions, **64.8%** (`68/105`) have `no_bet_flag=true`. Average confidence **55.2%** — barely above Phase 30A floor. **Zero** predictions in extended-market sample would have received recommendations under Phase 30A rules (all flagged no-bet or below thresholds).

### 5.3 No Bet UX consistency

- API sets `no_bet: true` when first recommended entry has `status: "no_bet"`
- UI shows "No Bet — confidence too low" card when primary recommendation is no-bet
- **Gap:** Detailed markets still show full probability bars (including 80%+ double chance) below the No Bet card — may confuse users who interpret high percentages as betting signals

### 5.4 Verdict on No Bet logic

No Bet is **conservative and mostly consistent** with WDE via `no_bet_flag`. Minor threshold mismatch (WDE 60 vs Phase 30A 55) is **masked** because WDE sets the flag first. No evidence of recommending when WDE explicitly flags no-bet in local data.

---

## 6. Strongest Markets Currently Available

Ranked by typical model probability strength (when extended markets present):

1. **Double Chance (Home/Draw or Draw/Away)** — routinely 65–85%
2. **1X2 favorite** — typically 45–65% for picked side
3. **Under 2.5** or **BTTS No** — often 52–58% in low-scoring fixtures
4. **Over 2.5** or **BTTS Yes** — variable, often 45–55%
5. **HT favorite** — similar to 1X2 but noisier (~35–45% for leader)
6. **Goalscorer / Correct score** — low single-digit to high teens %

**Strongest markets actually recommendable today:** 1X2 + (O/U 2.5 **or** BTTS) only.

---

## 7. Markets Missing from Recommendation Engine

| Missing from recommendations | Status |
|------------------------------|--------|
| Double Chance | Computed + shown, **never recommended** |
| HT Result | Computed + shown, **never recommended** |
| First Team To Score | Computed + shown, **never recommended** |
| Team To Score First Half | API only, **never recommended** |
| Goalscorer | Computed + shown, **never recommended** |
| First Goal Minute | Computed + shown, **never recommended** |
| Correct Score | API only (Streamlit UI), **never recommended** |
| Draw No Bet | **Not computed** |
| Over/Under 3.5 (and other lines) | **Not computed** |

---

## 8. Expected Impact on User Winrate

**Current state (no finished-match validation data):**

| Factor | Estimated impact |
|--------|------------------|
| Forced 1X2 primary | **Negative to neutral** — users bet lowest-probability eligible outcome when DC or DNB would win more often |
| O/U-before-BTTS ordering | **Small negative** when BTTS edge exceeds O/U but O/U fills slot 2 |
| 58% secondary threshold | **Neutral** — filters weak secondary picks; may skip valid 55–57% edges |
| 62% no-bet rate locally | **Positive** — avoids recommending on uncertain fixtures |
| No odds/EV normalization | **Unknown** — may recommend low-value favorites |

**Qualitative estimate (pending backtest):**

- Adding **Double Chance as a rankable market** when it beats 1X2 on odds-adjusted edge: **+5–15 pp** hit-rate improvement on primary pick (DC wins whenever either covered outcome wins)
- Replacing fixed order with **probabilistic ranking** across 1X2/O/U/BTTS: **+2–5 pp** on secondary pick selection
- Enabling **DNB** for draw-heavy fixtures: **+3–8 pp** vs raw Home Win when draw prob > 25%

These ranges are **hypotheses** — require Phase 26-style replay with outcome labels. No quantitative claim is validated in this audit.

---

## 9. Recommendations (Future Phase — Not Implemented)

For a future **Phase 30C** (requires explicit approval):

1. **Unified market pool** — Include DC, and optionally DNB (derived), in ranking with correlation rules (no Home Win + Home/Draw together)
2. **Per-market confidence** — Use selected-outcome probability for 1X2, not global `confidence_score`
3. **Rank by strength** — Sort all qualifying markets by probability (or odds-edge if odds agent available) descending; take top 2
4. **Secondary threshold review** — Consider 55% aligned with primary gate, or dynamic threshold by market type
5. **Accuracy tracking** — Add BTTS + double chance evaluation to `accuracy/metrics.py`
6. **UI clarity** — When No Bet, annotate that detailed probabilities are informational only

---

## 10. Audit Conclusion

| Question | Answer |
|----------|--------|
| Does `recommended_bets` select the strongest market? | **No** — fixed 1X2-first priority, no cross-market ranking |
| Are all predicted markets recommendable? | **No** — 6+ market types shown but excluded |
| Are all requested market types available? | **No** — DNB and O/U 3.5 absent |
| Is No Bet logic sound? | **Mostly yes** — conservative, WDE-aligned via flag |
| Can we validate with winrate data? | **Not yet** — zero evaluated finished matches locally |

**Audit status:** Complete. No deploy. No code changes per Phase 30B scope.

---

## Appendix A — Key file references

| File | Role |
|------|------|
| `worldcup_predictor/api/prediction_output.py` | Recommendation engine (`build_recommended_bets`) |
| `worldcup_predictor/prediction/extended_markets.py` | BTTS, HT, goalscorer, correct score computation |
| `worldcup_predictor/decision/weighted_decision_engine.py` | WDE no-bet + market decisions |
| `worldcup_predictor/prediction/scoring_engine.py` | Baseline no-bet flag |
| `worldcup_predictor/config/model_weights.py` | WDE threshold defaults (60/50) |
| `worldcup_predictor/accuracy/metrics.py` | Historical winrate (when data exists) |
| `base44-d/src/pages/PredictionDetail.jsx` | Recommendation card + detailed markets UI |
| `PHASE_30A_PREDICTION_OUTPUT_COMPLETENESS_REPORT.md` | Phase 30A implementation context |

## Appendix B — Local prediction history snapshot

| Metric | Value |
|--------|-------|
| Total stored predictions | 105 |
| No-bet flagged | 68 (64.8%) |
| Average confidence | 55.2% |
| Average data quality | 71.0% |
| Records with extended markets JSON | 16 |
| 1X2 distribution | home_win 62, draw 28, away_win 15 |
| Accuracy metrics (evaluated finished) | All null |

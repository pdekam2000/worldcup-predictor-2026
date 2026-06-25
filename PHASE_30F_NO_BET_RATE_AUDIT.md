# PHASE 30F — NO BET RATE AUDIT

**Mode:** Audit only — no code changes, no deploy.

**Audit date:** 2026-06-20  
**Production reference:** commit `267812e` (Phase 29 + 30A + 30C + 30E deployed)

---

## Executive Summary

| Question | Answer |
|----------|--------|
| Is the system correctly conservative? | **Partially** — gates behave as coded, but outcomes are harsher than product intent for WC 2026 pre-kickoff fixtures. |
| Are thresholds too strict? | **Yes for current UX** — especially WDE confidence floor **60** on a WC sample where most live confidences sit **26–55**. |
| Primary No Bet rate (105-record sample) | **61.9%** No Bet / **38.1%** recommended |
| Production WC upcoming (40 fixtures, live API) | **100%** No Bet / **0%** ranked picks |
| Business impact risk | **HIGH** for World Cup match browsing |

**Verdict: B — Thresholds (primarily WDE confidence ≥ 60) are suppressing too many consumer-facing recommendations**, while still allowing raw probabilities (O/U, BTTS) to display. Phase 30C gate (55/45) is largely redundant because WDE binds first.

**Recommendation:** Thresholds **should be reviewed** via calibrated replay (Phase 31) before any production change. Do not lower blindly.

---

## Task 1 — Prediction Sample Audit

### Sources scanned

| Source | Records | Unique fixtures | Usable for No Bet audit |
|--------|--------:|----------------:|-------------------------|
| `data/predictions/prediction_history.jsonl` | **105** | 26 | **Yes** — `no_bet_flag`, `confidence_score`, `data_quality_score` |
| `data/validation/real_world_validation.jsonl` | 58 | 58 | Partial — settled replay; different `no_bet_flag` semantics (44.8% flagged) |
| `data/shadow/phase25_promotion_replay.jsonl` | 288 | 32 | WDE baseline only; 100% `no_bet_flag` in replay stack |
| Production SQLite `predictions` table | 17 | 17 | Too small |
| **Production live API** (WC upcoming, 2026-06-20) | **40** | 40 | **Yes** — full Phase 30A/30C payload with `no_bet`, picks |

### Primary sample (Task 2–6)

**105 stored prediction records** from `prediction_history.jsonl` — largest single prediction archive meeting the ≥100 target.

> Note: 105 rows span **26 unique fixtures** (multiple prediction versions: `early_24h`, refresh, etc.). Deduped-latest-per-fixture view: **25/26 No Bet (96.2%)**.

### Production spot-check (explains consecutive UX)

| Fixture | Competition context | Confidence | No Bet | Safe/Value/Aggressive |
|---------|---------------------|------------|--------|------------------------|
| 1539007 Netherlands vs Sweden | WC 2026 friendly | 51.2 | **Yes** | None |
| 1378970 Aston Villa vs Newcastle | Domestic league | 61.5 | **No** | Double Chance / O-U 2.5 / First Goal |

WC upcoming batch (n=40): **40/40 No Bet (100%)** — all blocked by sub-60 confidence despite DQ often ≥ 55.

---

## Task 2 — No Bet Statistics

### Primary sample — 105 prediction records

| Metric | Count | Rate |
|--------|------:|-----:|
| **Total predictions** | 105 | 100% |
| **No Bet** | 65 | **61.9%** |
| **Recommended (bet-eligible)** | 40 | **38.1%** |

### Cross-checks

| Sample | No Bet | Recommendation rate |
|--------|-------:|--------------------:|
| Deduped latest per fixture (n=26) | 25 | **3.8%** |
| Production WC upcoming live API (n=40) | 40 | **0%** |
| Real-world validation (n=58) | 26 | 55.2% |

The deduped and live-production numbers show that **current WC browsing experiences near-zero ranked picks**, matching production tester reports.

---

## Task 3 — Confidence Distribution

**Sample:** 105 prediction records

| Bucket | Count | % |
|--------|------:|--:|
| 0–40 | 24 | 22.9% |
| 40–50 | 19 | 18.1% |
| **50–60** | **19** | **18.1%** |
| 60–70 | 3 | 2.9% |
| 70–80 | 33 | 31.4% |
| 80+ | 7 | 6.7% |

### Finding

- **59.1%** of records sit **below 60** confidence (0–40 + 40–50 + 50–60 buckets).
- The **50–60 band** (18.1%) is the highest-leverage group: above Phase 30C floor (55) but below WDE floor (60).
- Production WC upcoming confidences cluster even lower (**~16–55**, median ~27–38), explaining **100% No Bet** on that slice.

---

## Task 4 — Data Quality Distribution

**Sample:** 105 prediction records

| Bucket | Count | % |
|--------|------:|--:|
| 0–40 | 16 | 15.2% |
| 40–50 | 0 | 0.0% |
| 50–60 | 1 | 1.0% |
| 60–70 | 10 | 9.5% |
| 70–80 | 37 | 35.2% |
| 80+ | 41 | 39.0% |

### Finding

- **84.8%** of records have DQ **≥ 60** — data quality is **not** the primary No Bet driver in stored history.
- Production WC upcoming DQ values: **{40, 45, 50, 55}** — lower than stored history but still often above Phase 30C DQ floor (45); **confidence** remains the binding constraint.

---

## Task 5 — No Bet Reasons

### Stored history (105 records, inferred from confidence/DQ + WDE rules)

| Cause | Count | % of No Bet (n=65) |
|-------|------:|-------------------:|
| **confidence_below_threshold** (< 60) | 62 | **95.4%** |
| other / multi-factor | 3 | 4.6% |
| data_quality_below_threshold (< 50) | 0 | 0.0% |
| missing_lineups | 0 | 0.0% (not a direct No Bet gate) |
| missing_odds | 0 | 0.0% |
| agent_conflict | 0 | 0.0% |
| insufficient_markets | 0 | 0.0% |

### Production WC upcoming (40 records)

| Cause | Count | % |
|-------|------:|--:|
| **confidence_below_threshold** | 40 | **100%** |

Audit trace `no_bet_reasons` was empty in API payloads (reasons exist in WDE trace server-side but are not always surfaced on the public predict response). Inferred cause aligns with WDE `confidence_below_60`.

---

## Task 6 — Threshold Sensitivity (simulation only)

**Simulated gate:** `No Bet = confidence < CONF_T OR data_quality < DQ_T`  
**Sample:** 105 prediction records  
**No thresholds were changed.**

### Phase 30C-style gate in isolation (WDE flag not applied)

| Conf ↓ / DQ → | 40 | 45 | 50 | 55 |
|---------------|---:|---:|---:|---:|
| **50** | 41.0% NB | 41.0% | 41.0% | 41.0% |
| **55** | 52.4% NB | 52.4% | 52.4% | 52.4% |
| **60** | 59.0% NB | 59.0% | 59.0% | 59.0% |

*DQ columns collapse because stored history rarely has DQ < 50.*

| Confidence threshold | Est. No Bet rate | Est. recommendation rate |
|---------------------|-----------------:|-------------------------:|
| 50 | 41.0% | 59.0% |
| 55 (current Phase 30C) | 52.4% | 47.6% |
| 60 (current WDE) | 59.0% | 41.0% |
| **Actual WDE flags in data** | **61.9%** | **38.1%** |

### Interpretation

| Change | Estimated impact on 105-record sample |
|--------|---------------------------------------|
| Lower Phase 30C only (55→50, 45→40) | **Minimal** while WDE stays at 60/50 |
| Lower WDE confidence 60→55 | **~+7 pp** recommendation rate (52.4% vs 59.0% gate simulation) |
| Lower WDE confidence 60→50 | **~+18 pp** recommendation rate (41.0% vs 59.0%) |
| Lower DQ thresholds alone | **Negligible** on stored history (DQ already high) |

---

## Task 7 — Recommended Pick Yield

### Production WC upcoming (n=40, post Phase 30E)

| Pick type | Frequency | % of all predictions | % of bet-eligible |
|-----------|----------:|---------------------:|------------------:|
| Safe Pick | 0 | 0% | n/a |
| Value Pick | 0 | 0% | n/a |
| Aggressive Pick | 0 | 0% | n/a |
| Avg market rank score | n/a | — | — |

### Reference bet-eligible fixture (not in WC upcoming batch)

Fixture **1378970** (Aston Villa vs Newcastle, confidence 61.5):

- Safe: Double Chance — Home or Draw (rank score ~0.75)
- Value: Over/Under 2.5 — Under 2.5 (~0.62)
- Aggressive: First Team To Score — Aston Villa

**Conclusion:** Ranking engine works when confidence clears 60; WC product surface currently never reaches that bar.

---

## Task 8 — Business Impact

| Dimension | Assessment | Risk |
|-----------|------------|------|
| WC match browsing UX | Users see probabilities but **no ranked picks** on consecutive fixtures | **HIGH** |
| Recommendation availability (WC upcoming) | **0%** | **HIGH** |
| Recommendation availability (stored 105) | **38.1%** (inflated by early high-confidence versions) | **MEDIUM** |
| Trust / transparency | "No Bet" message is technically correct but feels broken next to detailed O/U & BTTS | **MEDIUM** |
| Accuracy trade-off if thresholds lowered | 50–60 confidence band has weaker 1X2 calibration | **MEDIUM** |

### If current thresholds remain

- **Expected WC recommendation availability:** ~0–5% for pre-kickoff friendlies with confidences in the high-20s to mid-50s.
- **User perception:** Product appears non-committal despite rich market output — aligns with tester feedback.
- **Risk level:** **HIGH** for engagement; **MEDIUM** for model integrity (conservative bias reduces wrong public picks).

---

## System Gate Stack (reference)

```
ScoringEngine
  → baseline no_bet if DQ < 45 OR confidence_level LOW

WeightedDecisionEngine (WDE)
  → no_bet if confidence < 60 OR DQ < 50 OR LOW level
  → emits no_bet_reasons (e.g. confidence_below_60)

Phase 30C market_ranking_engine
  → no_bet if no_bet_flag OR confidence < 55 OR DQ < 45

API recommended_bets
  → "No Bet — confidence or data quality too low"
```

**Binding constraint today:** WDE **confidence ≥ 60** on WC fixtures.

---

## Recommendation — Should thresholds be reviewed?

**Yes — review is warranted**, with these guardrails:

1. **Do not deploy threshold changes in Phase 30F** — audit only.
2. **Primary candidate:** WDE `no_bet_confidence_minimum` (60) — not Phase 30C (55/45), which is redundant.
3. **Consider product decoupling:** Allow sub-market ranked picks (DC, O/U, BTTS) when 1X2 confidence is flat but sub-market scores exceed safe/value floors — without forcing a 1X2 recommendation.
4. **Validate with Phase 31 replay** on settled fixtures before any change; measure accuracy vs recommendation rate trade-off in the 50–60 band.
5. **Context-aware thresholds:** WC pre-lineup friendlies may need a different gate than domestic league fixtures with full data (evidence: 1378970 passes, 1539007 fails).

---

## Appendix — Key code thresholds (unchanged)

| Layer | Confidence | Data quality |
|-------|------------|--------------|
| WDE | 60 | 50 |
| Phase 30C | 55 | 45 |
| ScoringEngine baseline | LOW level cap | 45 |

Files: `worldcup_predictor/config/model_weights.py`, `worldcup_predictor/api/market_ranking_engine.py`, `worldcup_predictor/decision/weighted_decision_engine.py`, `worldcup_predictor/prediction/scoring_engine.py`

---

*End of Phase 30F audit. No code changes. No deploy.*

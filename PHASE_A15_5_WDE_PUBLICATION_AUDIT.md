# PHASE A15.5 — WDE Decision & Publication Audit

**Mode:** Audit → Analysis → Report  
**Date:** 2026-06-25  
**Constraints:** No model changes · No calibration changes · No WDE logic changes · No deploy

**Audit script:** `scripts/audit_phase_a15_5_wde_publication.py`  
**Production data:** `data/validation/phase_a15_5_wde_publication_audit.json` (56 latest PredOps snapshots)

---

## Executive Answers

| Question | Answer |
|----------|--------|
| **Why are so many predictions `no_bet`?** | Primarily **fixture-level confidence below 60** after WDE scoring. 93% of stored fixtures (52/56) are below the official publication threshold. WDE explicitly flags `confidence_below_60` and `confidence_level_low`. |
| **Is `no_bet` fixture-wide or market-specific?** | **Fixture-wide flag, market-specific data underneath.** 100% of `no_bet` fixtures (42/42) still have at least one market with `prediction` status in snapshots. The flag is applied at publication, not because markets lack output. |
| **Can a Best Available Pick be published safely?** | **Yes, with caution tier.** 64% of `no_bet` fixtures (27/42) already contain `best_available_pick` in the payload. UI currently suppresses it when `no_bet=true` (Phase A13A draw-guard). |
| **Can Bet Quality be implemented without changing WDE?** | **Yes.** All required signals exist in `market_ranking`, `detailed_markets`, `probabilities`, and audit metadata. Bet Quality should be a **read-only publication/orchestration layer** above existing outputs. |

---

## Part 1 — Decision Flow (Publication Pipeline)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. PREDICTION GENERATED                                                 │
│    PredictPipeline → Intelligence + Specialists → ScoringEngine         │
│    • Baseline 1X2, O/U, HT, first goal                                  │
│    • Initial no_bet_flag if: DQ<45 OR confidence_level LOW/UNAVAILABLE  │
│      OR all_placeholder (scoring_engine.py)                             │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. VALIDATION / ENRICHMENT (no publication gate)                        │
│    • Market consistency guard, fusion, extended markets, xG, weather    │
│    • Rule A gate, promotions (shadow modes), specialist orchestrator    │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. WDE DECISION (WeightedDecisionEngine.decide)                         │
│    • Recomputes confidence with factor weights + caps/reductions        │
│    • Sets no_bet_flag = TRUE if ANY:                                    │
│      - data_quality < 50 (data_quality_no_bet_threshold)                │
│      - confidence_level LOW or UNAVAILABLE                              │
│      - placeholder_data                                                 │
│      - confidence < 60 (no_bet_confidence_minimum)                      │
│    • Records no_bet_reasons[] in audit trace                            │
│    • Outputs per-market MarketDecision objects (always populated)       │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. PUBLICATION (build_prediction_output → build_market_ranking)         │
│    • Builds market candidates from detailed_markets + probabilities     │
│    • SECOND GATE — internal_no_bet if ANY:                              │
│      - prediction.no_bet_flag (from WDE)                                │
│      - confidence < 60 (OFFICIAL_CONFIDENCE_THRESHOLD)                  │
│      - data_quality < 45 (_MIN_DATA_QUALITY)                           │
│    • If internal_no_bet:                                                │
│      - safe/value/aggressive picks = NULL                                 │
│      - caution_pick = market_ranking[0]                                 │
│      - best_available_pick = market_ranking[1] (or [0])                 │
│      - no_bet = TRUE on API payload                                     │
│    • enrich_pick_visibility reinforces same thresholds on payload         │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. STORAGE GUARD (evaluate_prediction_storage)                          │
│    • Blocks provider-missing / placeholder downgrade                    │
│    • Can reject store → unpublished (provider_env_missing)              │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 6. SNAPSHOT (PredOps — Phase A15)                                       │
│    • Immutable snapshot with full payload + per-market status           │
│    • coverage_state = no_bet if payload.no_bet                          │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 7. UI (Match Center / Combo / Detail)                                   │
│    • load_prediction_payloads prefers latest snapshot                   │
│    • extract_prediction_summary: if no_bet → best_pick = NULL             │
│      (prevents false Draw display — Phase A13A)                         │
│    • Combo: comboReadiness returns no_bet / waiting                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### Gates that produce `no_bet`, `unpublished`, or `unavailable`

| Gate | Location | Condition | Effect |
|------|----------|-----------|--------|
| Scoring baseline | `scoring_engine.py` | DQ < 45, LOW confidence, placeholder | `no_bet_flag` on MatchPrediction |
| WDE confidence floor | `weighted_decision_engine.py` | confidence < 60 | `no_bet` + reason `confidence_below_60` |
| WDE confidence level | `weighted_decision_engine.py` | level LOW/UNAVAILABLE | `no_bet` + `confidence_level_*` |
| WDE data quality | `weighted_decision_engine.py` | DQ < 50 | `no_bet` + `data_quality_below_50` |
| WDE placeholder | `weighted_decision_engine.py` | `is_placeholder` | `no_bet` + `placeholder_data` |
| Publication confidence | `market_ranking_engine.py` | confidence < 60 | `internal_no_bet` → payload `no_bet=true` |
| Publication DQ | `market_ranking_engine.py` | DQ < 45 | `internal_no_bet` |
| Pick visibility | `pick_visibility.py` | same thresholds | reinforces `no_bet` on API block |
| Storage guard | `prediction_store_guard.py` | missing API key / placeholder | **unpublished** (not stored) |
| Stale quality | `stale_prediction_policy.py` | corrupt/low-confidence cache | treated as stale → refresh |
| UI summary | `match_center_helpers.py` | `no_bet=true` | **hides** best_pick (display gate) |
| Per-market unavailable | `predops/markets.py` | field absent in payload | `market_status=unavailable` |
| EGIE / goal timing | separate engine | league not enabled / no_pick | `unavailable` or `no_pick` |

**Key insight:** There are **three stacked fixture-level `no_bet` gates** (WDE → market ranking → pick visibility) using overlapping thresholds (60% confidence, 45–50% DQ). Markets are still ranked and stored; only official publication is suppressed.

---

## Part 2 — `no_bet` Analysis (Production, 56 snapshots)

### Aggregate reasons (fixtures can have multiple)

| Reason category | Fixture count | % of no_bet (42) |
|-----------------|---------------|------------------|
| **Insufficient confidence** | 42 | 100% |
| **Publication threshold** (< 60 conf) | 27 | 64% |
| **Missing provider data** (DQ < 50) | 6 | 14% |
| Model disagreement | 0 | — |
| Missing odds | 0 | — |
| Missing lineup | 0 | — |
| Missing injuries | 0 | — |
| Weather dependency | 0 | — |
| EV threshold | 0 | — |

### WDE audit reasons (raw, from `audit_trace.confidence.no_bet_reasons`)

| WDE reason | Fixtures |
|------------|----------|
| `confidence_below_60` | 39 |
| `confidence_level_low` | 23 |
| `confidence_level_unavailable` | 3 |
| `placeholder_data` | 3 |
| `data_quality_below_50` | 3 |

### Production averages

| Metric | Value |
|--------|-------|
| Mean confidence | **42.6** |
| Mean data quality | **61.8** |
| `no_bet` rate | **75%** (42/56) |
| Officially published | **25%** (14/56) |

**Root cause:** World Cup fixtures are scoring **well below the 60-point official threshold**. WDE is working as designed — it refuses to endorse fixture-level bets when confidence is LOW. This is **not** primarily missing odds, lineups, or model conflict in the current snapshot set.

---

## Part 3 — Market Breakdown (Production)

Counts are across all 56 snapshots (including both published and `no_bet` fixtures).

| Market group | Published | no_pick | Unavailable |
|--------------|-----------|---------|-------------|
| **1X2** | 56 | 0 | 0 |
| **BTTS** | 44 | 4 | 8 |
| **Over/Under** | 54 | 0 | 2 |
| **Correct Score** | 0 | 0 | 56 |
| **Goal Timing (EGIE)** | 0 | 0 | 56 |
| **Goalscorer** | 34 | 10 | 12 |

**Interpretation:**
- Core markets (1X2, BTTS, O/U) have strong model output even when fixture is `no_bet`.
- Correct Score and EGIE blocks are absent from standard WC pipeline payloads → always `unavailable`.
- Goalscorer has partial data with mixed `no_pick` / `unavailable`.

---

## Part 4 — Best Available Pick (Hidden Candidates)

Even when **fixture `no_bet = true`**:

| Metric | Value |
|--------|-------|
| Fixtures with `best_available_pick` in payload | **27 / 42** (64%) |
| With quality/strong candidate (prob ≥ 52%) | **26 / 42** (62%) |
| Fixtures with ≥1 market `published` while fixture `no_bet` | **42 / 42** (100%) |

### Example pattern (typical production fixture)

```
Fixture overall:     no_bet = true, confidence = 34.5
1X2:                 published (probabilities exist)
BTTS:                published
Over 2.5:            published (strong candidate in market_ranking)
best_available_pick: present in payload (e.g. BTTS or O/U leg)
UI best_pick:        NULL (suppressed by no_bet guard)
Combo:               excluded (no_bet)
```

**Conclusion:** The system **already computes** viable per-market picks. The fixture-wide `no_bet` flag and UI suppression hide them from Match Center and Combo.

---

## Part 5 — Threshold Impact (Statistics Only)

How many of 56 production fixtures would be rejected by each rule (rules can overlap):

| Rule | Fixtures affected |
|------|-------------------|
| WDE: confidence < 60 | **52** (93%) |
| Publication: confidence < 60 | **52** (93%) |
| WDE: `confidence_below_60` reason recorded | 39 |
| WDE: `confidence_level_low` | 23 |
| WDE: data quality < 50 | 14 |
| Publication: data quality < 45 | 13 |
| WDE: placeholder_data | 3 |

### Default thresholds (unchanged — reference only)

| Threshold | Value | Source |
|-----------|-------|--------|
| `no_bet_confidence_minimum` | 60 | `config/model_weights.py` |
| `analysis_ready_confidence_minimum` | 60 | same |
| `OFFICIAL_CONFIDENCE_THRESHOLD` | 60 | `pick_visibility.py` |
| `data_quality_no_bet_threshold` | 50 | WDE |
| `_MIN_DATA_QUALITY` (publication) | 45 | `market_ranking_engine.py` |
| Scoring engine DQ no_bet | 45 | `scoring_engine.py` |

**93% of fixtures fail the confidence gate.** Lowering publication visibility without touching WDE would affect the majority of current WC predictions.

---

## Part 6 — Bet Quality Readiness

### Signals already available (no WDE change)

| Signal | Source in payload |
|--------|-------------------|
| Per-market probability | `market_ranking[].probability`, `detailed_markets` |
| Market rank score | `market_ranking[].market_rank_score` |
| Bucket (safe/value/aggressive) | `market_ranking[].bucket` |
| Caution / best available picks | `caution_pick`, `best_available_pick` |
| Fixture confidence & DQ | `confidence`, `data_quality` |
| WDE no_bet reasons | `audit_trace.confidence.no_bet_reasons` |
| 1X2 probabilities | `probabilities.match_winner` |
| O/U, BTTS | `probabilities.over_under_2_5`, `probabilities.btts` |
| Specialist agreement | `specialist_summary.agents.market_consensus_agent` |
| Odds block (when present) | `odds` / `betting_intelligence` |

### Bet Quality formula (proposed — orchestration only)

```
bet_quality_score = f(
  market_rank_score,
  market_probability,
  fixture_confidence,
  data_quality,
  bucket_tier,
  odds_value_edge?,      # optional if odds present
  specialist_agreement?
)
```

### Additional signals that would strengthen Bet Quality (optional)

| Signal | Status | Notes |
|--------|--------|-------|
| Implied probability / EV | Partial | Needs consistent odds in payload; not always present |
| Per-market DQ | Not explicit | Could proxy from fixture DQ + market type |
| Historical hit rate per market | Available offline | Accuracy center / archive — not in live payload |
| EGIE confidence | Missing for WC | Separate engine; not in standard payload |
| Explicit `publishable_caution` flag | **Not present** | Would simplify UI without touching WDE |

**Verdict:** Bet Quality **can be derived today** from `market_ranking` + `detailed_markets` for core markets. Full EV-based quality needs reliable odds snapshots per fixture.

---

## Part 7 — Recommendations (Safest Implementation Path)

### 1. Do NOT change WDE or calibration

Keep `no_bet_flag` as the **fixture-level risk gate**. It correctly reflects low analytical confidence for WC fixtures (avg 42.6).

### 2. Introduce Bet Quality as a publication overlay (Phase A16+)

| Layer | Responsibility |
|-------|----------------|
| WDE | Fixture risk / `no_bet_flag` (unchanged) |
| Market ranking | Per-market candidates (unchanged) |
| **Bet Quality** | Score and rank markets independently |
| **Publication policy** | Decide what users see |

### 3. Split fixture status from market visibility

| Field | Meaning |
|-------|---------|
| `fixture_recommendation` | `official` / `caution` / `no_bet` (from WDE) |
| `best_available_market` | Top market from `market_ranking` regardless of fixture `no_bet` |
| `bet_quality_tier` | A/B/C from orchestration thresholds |

### 4. UI changes (orchestration only)

- When `no_bet` but `best_available_pick` exists: show **"Caution — Best Available"** with clear tier badge (not Draw, not official).
- Combo: optional **"Caution combo"** mode using `market_ranking` legs with `bet_quality >= threshold` — separate from official combo.
- Keep Phase A13A guard: never map `no_bet` → Draw.

### 5. Phased rollout

1. **Read-only Bet Quality** in owner dashboard (compute from snapshots, no user exposure).
2. **Match Center caution row** — show best market with disclaimer when fixture `no_bet`.
3. **Combo caution tier** — after owner validation of quality thresholds.
4. Monitor accuracy by `bet_quality_tier` before promoting to official.

### 6. What NOT to do

- Do not lower WDE `no_bet_confidence_minimum` without calibration study.
- Do not expose raw `prediction` field when `no_bet` (Draw bias risk).
- Do not conflate `model_tier` with `bet_quality_tier`.

---

## Summary Diagram

```
                    ┌──────────────┐
                    │ WDE no_bet   │  ← Fixture risk (KEEP)
                    └──────┬───────┘
                           │
         ┌─────────────────┴─────────────────┐
         ▼                                   ▼
  official picks=null              market_ranking FULL
  no_bet=true on payload           best_available_pick SET
         │                                   │
         ▼                                   ▼
  UI hides best_pick                 Bet Quality CAN read this
  Combo excluded                     (proposed Phase A16)
```

---

## Artifacts

| File | Purpose |
|------|---------|
| `scripts/audit_phase_a15_5_wde_publication.py` | Reproducible audit |
| `data/validation/phase_a15_5_wde_publication_audit.json` | Production metrics |

---

## STOP

Audit complete. No code, model, calibration, or deployment changes made.

**Recommended next phase:** Bet Quality overlay (orchestration + UI gating only) using existing `market_ranking` and `best_available_pick` data.

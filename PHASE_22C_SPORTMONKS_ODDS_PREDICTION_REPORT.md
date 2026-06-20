# PHASE 22C — Sportmonks Odds + Prediction Intelligence Report

**Status:** COMPLETE (local)  
**Date:** 2026-06-19  
**Scope:** World Cup 2026 — Sportmonks league **732**, season **26618**  
**Deploy:** NOT performed  
**Prediction weights:** UNCHANGED  
**Internal model authority:** PRESERVED

---

## 1. Objective

Integrate Sportmonks **odds** and **prediction model** as supplemental intelligence signals — external benchmark, consensus/conflict detector, and WDE audit trace — without replacing API-Football or internal predictions.

---

## 2. Endpoints / Includes Used

Extended unified fixture fetch (`GET /fixtures/{id}`) includes:

| Include | Purpose |
|---------|---------|
| `odds` | Supplemental 1X2 implied probabilities |
| `predictions` | Sportmonks prediction model benchmark |
| `metadata` | Prediction eligibility flags |
| *(22B base)* | `scores`, `participants`, `state`, `statistics`, `lineups`, `events`, `formations`, `sidelined.sideline` |

**No new HTTP endpoints** — same Phase 22B unified path with expanded include string.

---

## 3. Architecture

```
EnrichmentService (22B unified fetch with 22C includes)
  └─ apply_sportmonks_consumption
       └─ supplemental.sportmonks_odds_prediction  ← parsed odds + predictions

SpecialistOrchestrator
  └─ … MarketConsensusAgent, OddsMovementAgent, SharpMoneyIntelligenceAgent
  └─ SportmonksPredictionAgent  ← NEW (after market agents)
       └─ build_sportmonks_prediction_intelligence
            ├─ internal reference: market_consensus → odds_market → team_form
            ├─ disagreement_vs_internal
            ├─ consensus_with_internal
            ├─ conflict_level / recommendation
            └─ odds vs API-Football disagreement

MasterAnalysisAgent
  └─ reads sportmonks conflicts/adjustments (synthesis notes only)

WeightedDecisionEngine
  └─ audit.limitations sportmonks_benchmark_trace (trace only — no weight change)
```

**Authority chain unchanged:** API-Football primary → internal WDE/scoring → Sportmonks benchmark read-only.

---

## 4. SportmonksPredictionAgent Outputs

| Field | Description |
|-------|-------------|
| `sportmonks_home_probability` | SM prediction model home prob |
| `sportmonks_draw_probability` | SM draw prob |
| `sportmonks_away_probability` | SM away prob |
| `sportmonks_expected_score` | e.g. `1.4-1.1` when goals in payload |
| `sportmonks_confidence` | Model confidence or max prob |
| `disagreement_vs_internal` | L1 distance vs internal reference (0–1) |
| `consensus_with_internal` | Agreement score 0–100 |
| `conflict_level` | `low` / `medium` / `high` |
| `recommendation` | `support_internal` / `caution` / `no_bet_review` |
| `raw_odds` / `raw_predictions` | Normalized blocks + samples (not full HTTP dump) |

---

## 5. Consensus / Conflict Logic (Examples)

### Example A — Support internal
- Internal (market consensus): home 50%, draw 28%, away 22% → lean `home_win`
- Sportmonks prediction: home 48%, draw 27%, away 25% → lean `home_win`
- L1 disagreement ≈ 0.03 → **conflict_level: low**, **consensus: ~85**, **recommendation: support_internal**

### Example B — Caution
- Internal: home 40%, away 35%, draw 25%
- Sportmonks: home 30%, away 40%, draw 30%
- L1 disagreement ≈ 0.12 → **conflict_level: medium**, **recommendation: caution**

### Example C — No bet review
- Internal lean: `home_win`
- Sportmonks lean: `away_win`
- L1 disagreement ≥ 0.45 → **conflict_level: high**, **recommendation: no_bet_review**

### Odds vs API-Football
- Compares Sportmonks implied 1X2 vs market consensus probabilities
- If L1/2 ≥ 0.22 → note in agent + MasterAnalysis conflict string

**Thresholds:**
- High conflict: disagreement ≥ 0.45 (or odds divergence ≥ 0.45)
- Medium: ≥ 0.22
- Low: below 0.22

---

## 6. Cache Behavior

| Mechanism | Behavior |
|-----------|----------|
| SQLite `sportmonks_fixture_enrichment` | Reused; rows missing `odds;predictions;metadata` in `include_params` treated as **stale** → one refetch |
| TTL | Unchanged: 30 min live / 24 h finished |
| API calls | Same 22B budget; include expansion may slightly increase payload size per call |
| Odds-specific fetch | **None** — odds ride on unified fixture include |

---

## 7. Quota Impact

| Scenario | Impact |
|----------|--------|
| Warm cache with 22C includes | **0 extra calls** |
| Stale 22B-only cache | **1 refetch** per fixture (upgrade to full includes) |
| Cold path | Still max 2 calls (lookup + fixture by ID) |
| Per-card polling | **Not added** |

---

## 8. Database Impact

- **No schema migration** — reuses `sportmonks_fixture_enrichment`
- `include_params` column now records `odds;predictions;metadata`
- `raw_json` stores normalized odds/predictions arrays from Sportmonks
- PostgreSQL-compatible (existing migration)

---

## 9. Prediction Impact

| Area | Change |
|------|--------|
| WDE factor weights | **None** |
| Scoring engine | **None** |
| Final 1X2 selection | **None** |
| Confidence auto-boost | **None** |
| API-Football odds | **Primary — never overwritten** |
| Audit trace | `limitations.sportmonks_benchmark_trace` added when SM data present |
| Master synthesis | Informational conflicts/adjustments only |

---

## 10. Files Changed

| File | Change |
|------|--------|
| `worldcup_predictor/intelligence/sportmonks_odds_prediction_engine.py` | **NEW** — parsers + benchmark builder |
| `worldcup_predictor/agents/specialists/sportmonks_prediction_agent.py` | **NEW** — specialist agent |
| `worldcup_predictor/providers/sportmonks_enrichment.py` | Extended includes + stale-cache detection |
| `worldcup_predictor/providers/sportmonks_consumption.py` | Parse odds/predictions into supplemental |
| `worldcup_predictor/agents/specialists/orchestrator.py` | Register agent after market agents |
| `worldcup_predictor/agents/specialists/agents.py` | MasterAnalysis reads SM benchmark |
| `worldcup_predictor/decision/weighted_decision_engine.py` | Trace-only audit limitation |
| `scripts/validate_phase22c_sportmonks_odds_prediction.py` | **NEW** — offline validation |

---

## 11. Validation Results

```bash
python scripts/validate_phase22c_sportmonks_odds_prediction.py
python scripts/validate_phase8_sportmonks_consumption.py
python scripts/validate_phase22b_unified_fixture.py
```

Expected: all checks pass offline.

---

## 12. Next Recommended Phase

**Phase 22D — xG Intelligence Integration**

- Add `xGFixture` include (plan-gated)
- Create `XGIntelligenceAgent`
- Compare internal xG vs Sportmonks xG
- Cache-first; near-kickoff fetch gate

---

**PHASE 22C COMPLETE — STOPPED FOR APPROVAL BEFORE 22D**

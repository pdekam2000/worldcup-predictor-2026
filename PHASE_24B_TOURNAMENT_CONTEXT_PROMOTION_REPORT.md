# Phase 24B — Tournament Context Promotion Report

**Status:** Complete (local only — no deployment)  
**Scope:** World Cup 2026 (`world_cup_2026`)  
**Default mode:** `shadow` (production-safe; set `TOURNAMENT_CONTEXT_PROMOTION_MODE=gated` to apply)

---

## Objective

Promote `TournamentContextAgent` from trace-only (Phase 22E) into **controlled** influence on the existing **`motivation_psychology` WDE factor (8%)** — with **tactics/O-U context recorded as trace-only** — via the Promotion Adapter Layer, without changing factor weights.

---

## Promotion Architecture

```
TournamentContextAgent (22E)
        ↓
compute_tournament_context_promotion()  ← gates + bounded motivation blend + edge nudges
        ↓
apply_context_promotion_to_factor()     ← gated mode only (motivation_psychology)
        ↓
WeightedDecisionEngine._build_factors() → motivation_psychology (8% weight unchanged)
        ↓
decide() → confidence_delta (gated only, bounded; cumulative cap with 24A)
        ↓
audit.trace + prediction.metadata + shadow JSONL

Secondary (trace-only in 24B):
  tactics_over_trace_delta + tactics_trace_notes → audit.trace / limitations (NOT applied to tactics_matchup)
```

**Feature flag:** `TOURNAMENT_CONTEXT_PROMOTION_MODE`

| Mode | Motivation apply | Tactics O/U apply | Confidence apply | Shadow log |
|------|------------------|-------------------|------------------|------------|
| `off` | No | No | No | No |
| `shadow` | No (compute only) | No (trace only) | No | Yes |
| `gated` | Yes | No (trace only) | Yes (bounded) | Yes |

**Rollback:** Set `TOURNAMENT_CONTEXT_PROMOTION_MODE=off` — instant revert to Phase 22E trace behavior.

---

## Delta Limits (Enforced)

| Limit | Value |
|-------|-------|
| Max motivation score delta | ±6.0 |
| Max motivation edge delta | ±0.025 |
| Max context confidence boost | +1.5 |
| Max context confidence reduction | −2.0 |
| Cumulative promotion confidence cap (24A+24B) | ±6.0 |
| Min group context strength gate | 36.0 |

**Motivation blend weights (sum = 1.0):**

- 50% `motivation_psychology_agent` average  
- 30% `tournament_intelligence_agent` pressure  
- 20% `tournament_context_agent` motivation average  

**Edge nudges (bounded, deduplicated):**

| Signal | Edge nudge |
|--------|------------|
| Home must-win | +0.015 (50% if tour_intel `must_win_match` flag) |
| Away must-win | −0.015 (deduped) |
| Draw acceptability | −0.01 toward draw |
| Elimination risk diff ≥ 20 | ±0.01 toward lower-risk side |
| Internal disagreement | Halve score + edge nudges |

**Tactics trace (not applied in 24B):**

| Signal | Trace O/U delta |
|--------|-----------------|
| High aggression | +0.04 |
| High conservatism | −0.04 |
| High rotation risk | +0.03 |
| Critical importance | +0.02 |
| Knockout cap | ±0.05 total |

**Not allowed (by design):**

- Direct 1X2 winner override  
- Auto no-bet creation from promotion  
- Confidence spikes above +1.5 from context alone  
- WDE weight changes  
- Tactics_matchup factor modification in 24B  

---

## Required Outputs

| Output | Location |
|--------|----------|
| `context_delta_score` | `audit.trace`, `prediction.metadata` |
| `context_promotion_active` | `audit.trace`, `prediction.metadata` |
| `context_promotion_reason` | `audit.trace`, `prediction.metadata` |
| `context_promotion_confidence` | `audit.trace`, `prediction.metadata` |
| `must_win_influence` | `audit.trace`, `prediction.metadata` |
| `rotation_context_influence` | `audit.trace`, `prediction.metadata` |
| `draw_acceptability_influence` | `audit.trace`, `prediction.metadata` |
| `tactics_trace_notes` / `tactics_over_trace_delta` | `audit.trace`, shadow JSONL, limitations |

---

## Files Changed

| File | Change |
|------|--------|
| `worldcup_predictor/promotion/config.py` | 24B constants (delta caps, blend weights, agent keys) |
| `worldcup_predictor/promotion/models.py` | `TournamentContextPromotionResult` dataclass |
| `worldcup_predictor/promotion/tournament_context_adapter.py` | **New** — compute/apply promotion adapter |
| `worldcup_predictor/promotion/shadow_store.py` | `TournamentContextPromotionShadowRecord` + store |
| `worldcup_predictor/promotion/__init__.py` | Export 24B symbols |
| `worldcup_predictor/config/settings.py` | `TOURNAMENT_CONTEXT_PROMOTION_MODE`, shadow path |
| `worldcup_predictor/decision/audit_report.py` | `FinalDecisionTrace` context promotion fields |
| `worldcup_predictor/decision/weighted_decision_engine.py` | Hook after motivation block; audit/metadata/confidence |
| `scripts/validate_phase24b_tournament_context_promotion.py` | **New** — offline validation |
| `PHASE_24B_TOURNAMENT_CONTEXT_PROMOTION_REPORT.md` | **New** — this report |

**Unchanged:** WDE factor weights (15/15/12/12/12/10/10/8/6), calibration, deployment configs.

---

## Prediction Impact (Offline Simulation)

Test fixture: Brazil vs Morocco (WC 2026, must-win home context, group strength 54).

| Mode | Motivation score | Delta | Applied | 1X2 selection |
|------|------------------|-------|---------|---------------|
| `off` | 61.5 | 0.0 | No | unchanged |
| `shadow` | 61.5 (factor) / 62.9 (computed) | +1.4 | No | unchanged |
| `gated` | 62.9 | +1.4 | Yes | unchanged |

**Influence breakdown (gated):**

- `must_win_influence`: +0.015  
- `rotation_context_influence`: +0.03 (trace metric)  
- `draw_acceptability_influence`: 0.0  
- `tactics_over_trace_delta`: +0.07 (trace only — tactics factor untouched)  

Motivation edge receives bounded must-win nudge; no winner flip in test scenario.

---

## Cache Impact

**None.** Promotion adapter reads existing specialist signals from orchestrator memory — no new API calls, no cache TTL changes, no Sportmonks/API-Football quota consumption beyond Phase 22E enrichment already in place.

Shadow JSONL writes to `data/shadow/tournament_context_promotion_shadow.jsonl` (configurable via `TOURNAMENT_CONTEXT_PROMOTION_SHADOW_PATH`).

---

## Rollback Strategy

1. **Instant:** `TOURNAMENT_CONTEXT_PROMOTION_MODE=off` — adapter returns empty result; WDE motivation path identical to pre-24B.  
2. **Shadow default:** Production-safe default computes deltas without applying.  
3. **Independent from 24A:** `EXPECTED_LINEUP_PROMOTION_MODE` remains separate; both can be rolled back independently.  
4. **No schema migration:** Audit fields are additive; older consumers ignore new trace keys.

---

## Validation Results

| Validator | Result |
|-----------|--------|
| `validate_phase24b_tournament_context_promotion.py` | **28/28 passed** |
| `validate_phase24a_expected_lineup_promotion.py` (regression) | **24/24 passed** |
| `validate_phase22e_tournament_context.py` (regression) | **27/27 passed** |

**24B checks include:** off/shadow/gated modes, bounded deltas, shadow store write, tactics trace-only (factor unchanged), required audit fields, WDE weights unchanged.

---

## WDE Weights (Unchanged)

| Factor | Weight |
|--------|--------|
| data_quality | 15% |
| team_form | 15% |
| injuries_suspensions | 12% |
| lineup_strength | 12% |
| tactics_matchup | 12% |
| player_quality | 10% |
| odds_market_signal | 10% |
| motivation_psychology | 8% |
| weather_referee_context | 6% |

---

Phase 24B complete. **Phase 24C (xG + Sportmonks) not started** — awaiting approval.

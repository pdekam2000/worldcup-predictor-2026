# Phase 46D — Provider Utilization Report

**Status:** PRODUCTION_ACTIVE  
**Date:** 2026-06-21  
**Mode:** Audit → Implement → Validate → Deploy → Report

---

## Executive Summary

Phase 46D extends the World Cup Predictor to maximize API-Football and Sportmonks data usage without altering prediction weights, WDE factor scores, evaluation logic, billing, weather, or history/archive behavior. All new intelligence is **supplemental-only** — attached to `supplemental_sources` and specialist signals for analytics and future promotion.

---

## Part A — Provider Field Inventory

**Deliverable:** `PROVIDER_FIELD_INVENTORY.md`

Full field-by-field audit covering:

| Provider | Domains Audited |
|----------|-----------------|
| API-Football | fixtures, events, lineups, injuries, standings, statistics, odds, H2H, players, teams |
| Sportmonks | scores, state, events, xG, advanced statistics, player data, timelines |

**Key gaps closed in 46D:**

- Cards, substitutions, penalties, own goals → unified event layer
- Sportmonks events/scores → fusion gap-fill
- Odds opening/current/implied delta → odds movement intelligence
- xG / shot quality / efficiency → AdvancedMatchIntelligence
- Player form / availability → PlayerIntelligence

---

## Part B — Unified Event Intelligence Layer

**Module:** `worldcup_predictor/intelligence/provider_utilization/unified_event_layer.py`

| Capability | Detail |
|------------|--------|
| Normalized schema | `UnifiedEvent` — goals, cards, subs, penalties, own goals, assists |
| API-Football parser | `parse_api_football_events()` |
| Sportmonks parser | `parse_sportmonks_events()` |
| Fusion | `provider_fusion.merge_event_layers()` — API-Football primary |
| Persistence | SQLite table `fixture_unified_events` (PHASE46D_DDL) |
| Cache-first | Reads cached rows before re-fetch; writes after enrichment |

---

## Part C — Odds Movement Intelligence

**Module:** `worldcup_predictor/intelligence/provider_utilization/odds_movement_intelligence.py`

| Output Field | Description |
|--------------|-------------|
| `odds_movement_score` | 0–100 composite from implied deltas + snapshot confidence |
| `odds_movement_direction` | `toward_home` / `away_from_draw` / `flat` etc. |
| `market_confidence_shift` | Absolute implied probability shift (%) |
| `sharp_movement_detected` | Steam / ≥8% line move |
| `consensus_drift` | Bookmaker consensus narrative |
| Opening/current implied | Per-side implied probability |

**Integration:**

- `OddsMovementAgent` attaches intelligence fields to specialist signal
- `impact_score` unchanged (WDE-safe)
- Cached bundle key: `odds_movement_intelligence` in supplemental sources

---

## Part D — Advanced Match Intelligence

**Module:** `worldcup_predictor/intelligence/provider_utilization/advanced_match_intelligence.py`

Derived from Sportmonks xG and advanced statistics:

| Output | Use |
|--------|-----|
| `attacking_edge` | Relative attacking strength |
| `defensive_edge` | Relative defensive strength |
| `xg_momentum` | xG trend signal |
| `expected_scoring_pressure` | Combined pressure index |
| Shot quality / efficiency | Attack & defensive efficiency metrics |

**Feed path:** Specialists supplemental only — no scoring engine override.

---

## Part E — Player Intelligence

**Module:** `worldcup_predictor/intelligence/provider_utilization/player_intelligence.py`

| Signal | Source |
|--------|--------|
| Recent goals / assists | Unified events + fixture events |
| Form / minutes | Lineups + player blocks |
| Availability | Injuries + sidelined |
| Lineup confidence | StartXI completeness |
| Top goalscorer / first-goal candidates | Event-weighted ranking |

Improves goalscorer and first-goal analytics; does not alter 1X2 prediction engine output.

---

## Part F — Provider Fusion

**Deliverable:** `PROVIDER_FUSION_POLICY.md`  
**Module:** `worldcup_predictor/intelligence/provider_utilization/provider_fusion.py`

Priority: **API-Football → Sportmonks → Cache**

Entities covered: fixture, event, score, player, lineup, odds.

---

## Orchestration

**Entry point:** `apply_provider_utilization()` in `apply.py`

Wired in `enrichment_service.py` after Sportmonks consumption.

**Runtime bundle keys on intelligence report:**

```
provider_utilization_v1
unified_events
odds_movement_intelligence
advanced_match_intelligence
player_intelligence
```

**WDE:** Informational `DataLimitation` for `provider_utilization_v1` only — factor weights verified unchanged.

---

## Part G — Validation

**Script:** `scripts/validate_phase46d_provider_utilization.py`

| Environment | Result |
|-------------|--------|
| Local | 13/13 PASS |
| Production | 13/13 PASS |

**Verified unchanged:**

- WDE factor weights (0.1 baseline)
- Core 1X2 evaluation
- Goal minute evaluation
- No scoring engine hooks in utilization layer
- Inventory and fusion policy docs present

---

## Part H — Deployment

See `PHASE_46D_PRODUCTION_DEPLOY_REPORT.md`.

**Production smoke:** 7/7 PASS (post circular-import fix)

---

## Files Added / Modified

| Path | Role |
|------|------|
| `worldcup_predictor/intelligence/provider_utilization/*` | New intelligence package |
| `worldcup_predictor/providers/enrichment_service.py` | Wire apply step |
| `worldcup_predictor/odds/odds_movement_agent.py` | Attach 46D intel fields |
| `worldcup_predictor/decision/weighted_decision_engine.py` | Trace-only limitation |
| `worldcup_predictor/database/migrations.py` | `fixture_unified_events` DDL |
| `worldcup_predictor/database/repository.py` | Event CRUD |
| `scripts/validate_phase46d_provider_utilization.py` | Validation |
| `scripts/phase46d_production_smoke.py` | Production smoke |
| `scripts/deploy_phase46d_production.sh` | Deploy automation |
| `PROVIDER_FIELD_INVENTORY.md` | Field audit |
| `PROVIDER_FUSION_POLICY.md` | Fusion rules |

---

## Known Limitations (By Design)

- No new specialist agents registered in orchestrator (preserve predictions)
- Player/scorer hints supplemental — not wired into scoring engine
- Frontend unchanged; data available via intelligence supplemental for future UI

---

**PHASE_46D_STATUS = PRODUCTION_ACTIVE**

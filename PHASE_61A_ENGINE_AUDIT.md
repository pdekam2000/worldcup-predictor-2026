# PHASE 61A — Engine Audit

**Date:** 2026-06-20  
**Scope:** Classic, EGIE, Elite Shadow, provider data, merge safety  
**Mode:** Read-only audit — no production logic changed  

---

## 1. Executive summary

The platform runs **two parallel production stacks**:

| Stack | Entry | Markets | Storage |
|-------|-------|---------|---------|
| **Classic** | `PredictPipeline` → `ScoringEngine` → **WDE** | 1X2, O/U, BTTS, DC, CS, HT, first goal team (heuristic) | `worldcup_stored_predictions` (SQLite) |
| **EGIE** | `GoalTimingPredictionService` → `EliteGoalTimingEngine` | First goal team, time range, minute, team goals, next goal | `goal_timing_predictions` (PostgreSQL) |

**Elite Shadow** (58C/A22) fuses cache-only proxies in JSONL — not wired to live WDE or EGIE.

**Safest merge:** Orchestration layer that **calls specialists as read-only adapters**, merges at a **Hybrid Decision Layer**, rolls out via **feature flags** (default OFF for public).

---

## 2. Classic engine

### Key files

| File | Role |
|------|------|
| `orchestration/predict_pipeline.py` | `PredictPipeline.run()` — full predict flow |
| `prediction/scoring_engine.py` | `ScoringEngine.predict()` — baseline Poisson/heuristics |
| `decision/weighted_decision_engine.py` | **WDE** — weighted factor fusion (**protected**) |
| `prediction/extended_markets.py` | BTTS, HT, correct score, first goal minute heuristics |
| `intelligence/first_goal_intelligence_v2.py` | First goal team v2 overlay |
| `adaptive_confidence/engine.py` | Classic adaptive confidence tiers |
| `agents/specialists/orchestrator.py` | Specialist signals into pipeline |

### Pipeline flow

```
DataCollectorAgent → MatchIntelligenceBuilder (API-Football)
  → SpecialistOrchestrator → PredictionAgent → ScoringEngine
  → WDE (if use_weighted_decision=True, default)
  → post: first_goal_v2, extended_markets, fusion, Sportmonks xG, weather
```

### Markets owned by Classic/WDE

| Market | Owner | Notes |
|--------|-------|-------|
| **1X2** | WDE `_resolve_1x2()` | Rule A harmonization in finalize |
| **Over/Under 2.5** | WDE `_resolve_over_under()` | Weather cap possible |
| **Halftime goals** | WDE | Estimate from total × 0.45 |
| **First goal team** | WDE baseline + fg_v2 | Strength comparison — **overlaps EGIE** |
| **First goal player** | WDE + scorer_candidates | Lineup cap when missing |
| **BTTS** | `extended_markets.py` | Poisson — **not in WDE** |
| **HT 1X2** | `extended_markets.py` | Derived |
| **Correct score** | `scoreline_engine.py` | Poisson candidates |
| **First goal minute band** | ScoringEngine heuristic + fg_v2 | **Not EGIE statistical model** |

### WDE factors (unchanged)

data_quality, team_form, injuries, lineup_strength, tactics_matchup, player_quality, odds_market_signal, motivation_psychology, weather_referee_context — plus shadow promotion hooks (lineup, tournament, xG, Sportmonks prediction).

---

## 3. EGIE (Elite Goal Intelligence Engine)

### Naming

- **Production EGIE** = `goal_timing/` package (`EliteGoalTimingEngine`)
- **`egie/` package** = research, survival, goalscorer ML, backtests — **not** the live PL API engine

### Key files

| File | Role |
|------|------|
| `goal_timing/engine.py` | `EliteGoalTimingEngine` |
| `goal_timing/prediction_service.py` | `GoalTimingPredictionService.predict_fixture()` |
| `goal_timing/features/builder.py` | Feature build from stored + provider store |
| `goal_timing/models_stat/baseline.py` | Statistical baseline |
| `goal_timing/calibration.py` | Calibrator |
| `goal_timing/confidence.py` | EGIE confidence |
| `egie/confidence/hybrid_engine.py` | Hybrid confidence (team/range/minute) |
| `egie/confidence/production_service.py` | Attached in prediction service |
| `egie/survival/` | Kaplan-Meier, hazard — **shadow only** |

### EGIE markets (`predops/constants.py` → `EGIE_MARKET_IDS`)

- `first_goal_team`, `first_goal_time_range`, `estimated_first_goal_minute`
- `next_goal_team`, `team_goals_home`, `team_goals_away`
- `goal_timing_confidence`, `goal_timing_tier`

### API isolation

- `/api/predict/{id}` — Classic only
- `/api/goal-timing/predictions/{id}` — EGIE only
- **No unified bundle in production today**

---

## 4. Elite shadow / orchestrator

### Phase 57A (design)

`elite_orchestrator/runner.py`, `inventory.py`, `graph.py` — artifacts only, **0 API calls**, explicitly no WDE/pipeline changes.

### Phase 58C runtime

`elite_orchestrator/shadow_runtime.py` → `data/shadow/elite_orchestrator_predictions.jsonl`

Shadow markets: `1x2`, `first_goal_team`, `team_to_score_first`, `anytime_goalscorer`, `first_goalscorer`, `goal_timing`

**Gap:** `goal_timing` in shadow is a **static proxy** (`16-30`, minute 25) — not live EGIE.

### Admin

`/api/admin/elite-shadow/*` — super_admin only.

---

## 5. Provider data

### API-Football (primary Classic)

`agents/match_intelligence_builder.py` — form, H2H, injuries, lineups, odds, events, stats.

### Sportmonks (paid enrichment)

| Capability | Path |
|------------|------|
| xG | `feature_store/sportmonks_xg_store.py`, `providers/sportmonks_xg_extraction.py` |
| Pressure | `feature_store/pressure_store/`, `egie/provider_features/` |
| Lineups/injuries | `egie/provider_features/store.py` |
| Odds | SQLite `odds_snapshots` + parsers |
| Standings/form | enrichment + intelligence modules |

### EGIE provider feature store

`egie/provider_features/store.py` — `EgieProviderFeatureStore.build()` — **DB/cache only**, no live API per call.

Fields: odds implied probs, xG for/against, pressure index, lineup strength, injuries impact, shots, dangerous attacks (when available).

### Rules already in codebase

- Cache-first (`quota/prediction_cache.py`, prefetch cycles)
- Enrichment never overwrites API-Football populated fields (`providers/enrichment_service.py`)
- PredOps prefetch for daily batch generation

---

## 6. Duplicated logic

| Domain | Classic | EGIE | Shadow | Risk |
|--------|---------|------|--------|------|
| First goal team | WDE + fg_v2 | Baseline model | fuse_pick | **High disagreement** |
| First goal minute | Heuristic bands | Calibrated ranges | Hardcoded 16-30 | **Quality gap** |
| Goalscorer | scorer_candidates | goalscorer_intelligence | parquet ML | Medium |
| xG usage | chance_quality, extended_markets | provider store | inventory rejected blend | Low if read-only |
| Confidence | AdaptiveConfidence | HybridConfidence | compute_tier | **Display fragmentation** |
| Odds signal | WDE odds factor | odds_intelligence | implied 1x2 proxy | Medium |

---

## 7. Missing links (Classic ↔ EGIE)

1. **Separate APIs and payloads** — match center shows classic `prediction_summary`; EGIE on separate pages.
2. **Different feature pipelines** — live API-Football vs SQLite/PG history.
3. **League scope** — EGIE PL-gated; Classic WC + multi-league.
4. **Survival not in production** — research only despite hybrid confidence in EGIE service.
5. **PredOps split** — `CORE_MARKET_IDS` from classic; `EGIE_MARKET_IDS` from separate store.
6. **No single confidence/tier** — UI shows multiple scales.

---

## 8. Safest merge plan (Phase 61 implementation)

### Principles

1. **Do not modify** `ScoringEngine`, `WeightedDecisionEngine`, or `EliteGoalTimingEngine` internals.
2. **Orchestrate** via `UnifiedHybridPredictionEngine` calling specialists.
3. **Read cache first** — never trigger API per UI card.
4. **Feature flags** — public stays on production until backtest approves.
5. **Disagreement visible** — lower confidence, explain conflict.

### Architecture

```
Provider Feature Store (cache/DB)
  → ClassicSpecialist (stored prediction / WDE output)
  → EGIESpecialist (goal_timing repository)
  → OddsMarketSpecialist (odds snapshots)
  → LineupInjurySpecialist (provider store)
  → HybridDecisionLayer (market-weighted fusion)
  → UnifiedConfidenceEngine (A/B/C/D tiers)
  → UnifiedPredictionOutput
```

### Market fusion weights (Hybrid Decision Layer)

| Market | Dominant sources |
|--------|------------------|
| 1X2 | Classic 50%, odds 25%, form/lineups 25% |
| O/U | Classic 40%, xG 35%, odds 25% |
| BTTS | Classic 45%, xG 35%, team stats 20% |
| Double Chance | Classic 55%, odds 45% |
| Correct Score | Classic 70%, xG 30% |
| First Goal Team | EGIE 50%, Classic 20%, xG/pressure 30% |
| Goal Timing Range | EGIE 75%, events profile 25% |
| Goalscorer | Lineups 40%, player xG 35%, Classic 25% |

On disagreement: confidence × 0.85, `engine_agreement: "partial"` in output.

### Rollout stages

| Stage | Action | Public impact |
|-------|--------|---------------|
| 61A | Audit (this doc) | None |
| 61B | Unified engine + flags OFF | None |
| 61C | Admin preview + compare API | Admin only |
| 61D | Backtest A/B/C/D | None |
| 61E | UI unified panel (reads unified when flag) | Gated |
| 61F | Public rollout | Owner approval only |

---

## 9. Feature flag defaults (Phase 61L)

| Flag | Default | Purpose |
|------|---------|---------|
| `UNIFIED_ENGINE_ENABLED` | `false` | Master switch |
| `UNIFIED_ENGINE_ADMIN_PREVIEW` | `true` | Admin API + UI preview |
| `UNIFIED_ENGINE_PUBLIC` | `false` | Replace public production output |
| `UNIFIED_ENGINE_COMPARE_MODE` | `true` | Classic vs EGIE vs Unified side-by-side |

---

## 10. What NOT to do

- Merge `ScoringEngine` and `GoalTimingBaselineModel` into one class
- Route `/api/predict` through elite shadow JSONL
- Enable survival in production without backtest gate
- Blend rejected inventory components (pressure pre-match, full xG blend into WDE)
- Expose shadow JSONL to public users

---

## 11. File index for Phase 61

```
Classic:     orchestration/predict_pipeline.py, prediction/scoring_engine.py, decision/weighted_decision_engine.py
EGIE:        goal_timing/engine.py, goal_timing/prediction_service.py
Shadow:      elite_orchestrator/shadow_runtime.py
Providers:   egie/provider_features/store.py, providers/enrichment_service.py
PredOps:     predops/markets.py, predops/constants.py, predops/egie_snapshot.py
Phase 61:    unified_hybrid/* (new orchestration)
API:         api/routes/unified_hybrid.py (new, admin-gated)
Flags:       config/settings.py
```

---

**Audit complete.** Proceed to `UnifiedHybridPredictionEngine` implementation with feature flags defaulting to safe OFF/public-false state.

# PHASE 22D — xG Intelligence Integration Report

**Status:** COMPLETE (local)  
**Date:** 2026-06-19  
**Scope:** World Cup 2026 — Sportmonks league **732**, season **26618**  
**Deploy:** NOT performed  
**WDE / prediction weights:** UNCHANGED

---

## 1. Objective

Build a dedicated **Sportmonks xG Intelligence Layer** with normalized ratings, internal comparison, and plan-access verification — benchmark/trace only.

---

## 2. xG Endpoints / Includes Discovered

| Source | Endpoint / Include | When populated | Priority |
|--------|-------------------|----------------|----------|
| **xGFixture** | `GET /fixtures/{id}?include=xGFixture` | Post-match (Basic ~12h delay); Standard/Advanced sooner / live | **Primary** |
| **statistics** | Same fixture include (existing) | In-match / post-match generic stats | Fallback |
| **expected/fixtures** | `GET /v3/football/expected/fixtures` | Team xG rows (not wired — avoid extra calls in 22D) | Future prefetch |
| **lineups.xGLineup** | Nested include | Player-level xG | Future (Phase 22+ ) |

**22D wired include:** `xGFixture` added to unified `WORLD_CUP_FIXTURE_INCLUDES`.

**xGFixture payload shape:** `expected[]` with `location` (home/away), `type_id` (5304=xG, 5305=xG on target), `data.value`.

---

## 3. Plan Support Verification

`verify_xg_plan_access()` infers support from cached/live fixture payload:

| Status | Meaning |
|--------|---------|
| **full** | xGFixture `expected` rows with numeric values |
| **partial** | xGFixture key empty OR statistics-only xG |
| **none** | No xG fields |
| **unknown** | No Sportmonks payload |

**Probe file:** `{api_cache_dir}/sportmonks/sportmonks_xg_plan_probe.json` — updated after each successful API enrichment fetch.

---

## 4. Can Sportmonks Provide Enough xG for World Cup 2026?

### Answer: **Partial — yes with fallback; full value requires xG add-on**

| Scenario | Coverage estimate | Notes |
|----------|-------------------|-------|
| **xG add-on active (Standard+)** | **~70–90%** of WC fixtures post-kickoff | Match-level home/away xG via `xGFixture`; strong for O/U + BTTS calibration |
| **Pre-match (upcoming NS)** | **~0–10%** | xGFixture typically empty until match progresses |
| **Basic plan only** | **~40–60%** post-match | Delayed xG; may lack live/pre-match |
| **No xG add-on** | **~10–30%** | statistics include only when match has xG stat types |

### Fallback strategy (implemented)

1. **Primary:** `xGFixture.expected` (type_id 5304)
2. **Fallback:** generic `statistics` expected-goals labels (existing Phase 8 path)
3. **Internal reference:** `extract_real_xg` + API-Football team expected-goals rolling metrics
4. **Comparison:** Sportmonks vs internal — trace only, no WDE weight change

---

## 5. Architecture

```
Unified fixture fetch (+ xGFixture include)
  └─ apply_sportmonks_consumption
       └─ supplemental.sportmonks_xg_intelligence

SpecialistOrchestrator
  └─ XGChanceQualityIntelligenceAgent (internal)
  └─ … market agents …
  └─ SportmonksPredictionAgent
  └─ XGIntelligenceAgent  ← NEW
       └─ build_sportmonks_xg_intelligence
            ├─ normalize Sportmonks xG
            ├─ ratings + advanced rolling from API-Football team stats
            └─ agreement vs internal xG

MasterAnalysisAgent
  └─ informational adjustments only (no WDE change)
```

---

## 6. XGIntelligenceAgent Outputs

| Field | Description |
|-------|-------------|
| `home_xg` / `away_xg` | Sportmonks normalized match xG |
| `xg_difference` | home − away |
| `xg_total` | home + away |
| `xg_attack_rating_*` | 0–100 from xG for |
| `xg_defense_rating_*` | 0–100 from opponent xG allowed |
| `xg_strength_rating` | Average of attack/defense ratings |
| `xg_confidence` | Source + plan based (0–100) |
| `rolling_xg_for/against_*` | From API-Football team expected-goals |
| `xg_form_*` / `xg_momentum_*` | Derived rolling metrics |
| `expected_goal_range` | e.g. `1.9-3.3` from xg_total |
| `agreement_score` / `disagreement_score` | vs internal xG |
| `xg_supports_internal` | bool |

---

## 7. Comparison Logic (Examples)

**Example A — Supports internal**
- Sportmonks: 1.65 / 0.92 (total 2.57)
- Internal: 1.55 / 0.88 (total 2.43)
- Avg diff ≈ 0.07 → **agreement ~95%**, `xg_supports_internal: true`

**Example B — Divergence**
- Sportmonks: 2.10 / 0.50
- Internal: 1.20 / 1.10
- Avg diff ≈ 0.65 → **disagreement ~0.43**, `xg_supports_internal: false`

---

## 8. Cache Behavior

| Layer | Change |
|-------|--------|
| SQLite `sportmonks_fixture_enrichment` | Reused; stale if `include_params` missing `xGFixture` |
| TTL | Unchanged (30 min live / 24 h finished) |
| Plan probe | File cache at `api_cache_dir/sportmonks/sportmonks_xg_plan_probe.json` |
| Extra HTTP | **None** — xG rides unified fixture include |

---

## 9. Quota Impact

| Scenario | Calls |
|----------|-------|
| Warm 22D cache | 0 |
| Stale 22C cache (no xGFixture) | 1 refetch per fixture |
| Cold path | Still max 2 (lookup + fixture) |

Payload size increases slightly due to `expected[]` array.

---

## 10. Database Impact

- **No schema migration**
- `include_params` now includes `xGFixture`
- `raw_json` may contain `xGFixture` / `expected` arrays
- PostgreSQL-compatible

---

## 11. Prediction Impact

| Area | Change |
|------|--------|
| WDE weights | **None** (explicitly not modified) |
| Scoring engine | **None** |
| Confidence auto-boost | **None** |
| O/U / BTTS / scoreline | **No direct change yet** — benchmark ready for Phase 22E+ |
| Master synthesis | Informational adjustment notes only |

---

## 12. Files Changed

| File | Change |
|------|--------|
| `worldcup_predictor/intelligence/sportmonks_xg_intelligence_engine.py` | **NEW** |
| `worldcup_predictor/agents/specialists/xg_intelligence_agent.py` | **NEW** |
| `worldcup_predictor/providers/sportmonks_enrichment.py` | `xGFixture` include + cache gate + plan probe |
| `worldcup_predictor/providers/sportmonks_consumption.py` | `sportmonks_xg_intelligence` supplemental |
| `worldcup_predictor/agents/specialists/orchestrator.py` | Register agent after market + SM prediction |
| `worldcup_predictor/agents/specialists/agents.py` | MasterAnalysis trace notes |
| `scripts/validate_phase22d_xg_intelligence.py` | **NEW** |

---

## 13. Validator Results

```bash
python scripts/validate_phase22d_xg_intelligence.py
python scripts/validate_phase22c_sportmonks_odds_prediction.py
python scripts/validate_phase22b_unified_fixture.py
```

---

## 14. Recommendations

1. **Confirm xG add-on** on Sportmonks dashboard for league 732 — probe file will show `plan_support: full` after first live WC fetch.
2. **Near-kickoff + post-match** are the highest-value windows for xGFixture population.
3. **Phase 22E** — standings/form context can combine with xG for motivation-adjusted goal priors (still trace-first).
4. **Future:** optional daily `expected/fixtures` prefetch for rolling WC team xG (admin-only, not per-card).

---

**PHASE 22D COMPLETE — STOPPED FOR APPROVAL BEFORE 22E**

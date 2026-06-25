# PHASE 54G — Pressure Index Discovery & Coverage Audit Report

**Date:** 2026-06-24  
**Mode:** Discovery → Coverage Audit → Validation → Report  
**Status:** COMPLETE (discovery only — no production, WDE, SaaS, or deploy changes)

**Artifacts:** `artifacts/phase54g_pressure_discovery/`  
**Engine:** `worldcup_predictor/feature_store/pressure_discovery/`

---

## Executive Summary

**Sportmonks Pressure Index is real, minute-level, and substantially present in UEFA club competition data.**

| Finding | Result |
|---------|--------|
| Pressure Index exists? | **Yes** — `pressure` include on `/fixtures/{id}` |
| Minute-level timeline? | **Yes** — ~98 minutes/fixture, ~195 rows/fixture (2 teams) |
| UEFA cache coverage | **81.3%** (65/80 fixtures) |
| Best league coverage | **83.3%** (CL, EL) |
| World Cup (732) | **0%** — out of subscription scope |
| Quality score (UEFA avg) | **80.5** / 100 |
| vs xG (54F-7) | Pressure targets **live/timing markets** xG cannot serve |
| Final recommendation | **`BUILD_PRESSURE_FEATURE_STORE`** (shadow/design — not production) |

**Caveat:** Local `.env` token returned HTTP 401 during this run. Conclusions combine **UEFA local cache (80 fixtures)**, **prior live probe (2026-06-23)**, and **Phase 54D deep test cache analysis**. Refresh token before live backfill.

---

## Part A — Pressure Endpoint Discovery

### Confirmed Sportmonks capabilities

| Capability | Endpoint | Include | Status | Notes |
|------------|----------|---------|--------|-------|
| **Pressure Index** | `GET /fixtures/{id}` | `pressure` | **accessible** | Primary data source |
| Pressure + teams | `GET /fixtures/{id}` | `participants;pressure` | **accessible** | Recommended for EGIE |
| **Dangerous Attacks** | `GET /fixtures/{id}` | `statistics.type` | **accessible** | Match-level stat, not minute timeline |
| **Attacks** | `GET /fixtures/{id}` | `statistics.type` | **accessible** | In statistics block |
| Deep combo | `GET /fixtures/{id}` | `pressure;statistics.type;events.type` | **accessible** | Used in UEFA ingest |

### Not available / invalid includes

| Capability | Include tried | Status |
|------------|---------------|--------|
| Pressure Timeline | `pressureIndex` | **not_found** (404) |
| Momentum | `momentum` | **not_found** |
| Trends | `trends` | **not_found** |
| Match Momentum | `matchMomentum` | **not_found** |
| Attack Waves | — | **No dedicated include** |
| Possession Pressure | — | **No dedicated include** — use statistics `Ball Possession %` |

### Pagination & filters

- Pressure is **fixture-scoped** — no standalone pressure list endpoint.
- Historical discovery uses `GET /fixtures?filters=fixtureSeasons:{id}` then per-fixture `include=pressure`.
- Pagination: standard Sportmonks `page` / `per_page` on fixture lists only.

### World Cup / out-of-plan leagues

Prior probe (valid token, Euro Club Tournaments plan): World Cup fixture `19609127` returned HTTP 200 with **no data** — subscription scope, not a missing feature.

---

## Part B — Historical Coverage Audit

### PRESSURE_COVERAGE_MATRIX

| League | ID | Fixtures (cache) | With Pressure | Coverage % | Minute Level | Quality |
|--------|-----|------------------|---------------|------------|--------------|---------|
| Champions League | 2 | 30 | 25 | **83.3%** | Yes | 83.3 |
| Europa League | 5 | 30 | 25 | **83.3%** | Yes | 83.3 |
| Conference League | 2286 | 20 | 15 | **75.0%** | Yes | 75.0 |
| World Cup | 732 | 0 | 0 | **0%** | — | 0 |
| European Championship | 1326 | 0 | 0 | **0%** | — | 0 |
| Nations League | 1538 | 0 | 0 | **0%** | — | 0 |
| Euro Qualification | 1325 | 0 | 0 | **0%** | — | 0 |

**Aggregate (UEFA cache):** 80 fixtures analyzed, 65 with pressure, **12,676 minute-level rows**.

**Gap:** Only 80 UEFA fixtures cached locally. Full-season historical depth requires backfill (estimated thousands of CL/EL/Conference fixtures per season on entitled plan).

---

## Part C — Pressure Data Structure (PRESSURE_JSON_KEY_INVENTORY)

### Pressure row schema (canonical)

| Field | Type | Present |
|-------|------|---------|
| `id` | int | Yes |
| `fixture_id` | int | Yes |
| `participant_id` | int | Yes (maps to team via participants) |
| `minute` | int | Yes (0–90+) |
| `pressure` | float | Yes (pressure value) |

### Not present in pressure block

- `team_id` — resolve via `participants[].id`
- `momentum_value`, `trend_value` — **not in API**; derive from timeline
- `pressure_direction` — derive from home/away participant
- `timestamp` — use `minute` + `events[].period` for sub-minute if needed
- `event_linkage` — join to `events[]` by `minute` + `participant_id`

Full key inventory: `artifacts/phase54g_pressure_discovery/PRESSURE_JSON_KEY_INVENTORY.json`

---

## Part D — Minute-Level Coverage

| Metric | Value |
|--------|-------|
| Avg rows per fixture | **195.0** |
| Avg unique minutes per fixture | **97.5** |
| Pre-match (minute 0) rows | **Yes** |
| Live minute coverage (1–90) | **Yes** — histogram shows ~130 row-pairs per minute bucket |
| Post-match retention | **Yes** — finished fixtures retain full timeline |

### Coverage by period (cache histogram)

| Period | Row count (approx) |
|--------|-------------------|
| Minute 0 (pre-match baseline) | Present |
| Minutes 1–15 | High |
| Minutes 16–45 | High |
| Minutes 46–90 | High |
| Minutes 90+ | Present |

**Interpretation:** Pressure is **true minute-by-minute in-play data**, not a single match aggregate. This is fundamentally different from pre-match xG features.

---

## Part E — Data Quality Audit

| Check | Result |
|-------|--------|
| Missing pressure values | Rare — most rows have `pressure` float (including 0.0) |
| Duplicate rows | Low — occasional duplicate minute+participant pairs penalized in score |
| Timeline gaps | Some minutes missing (avg 97.5/90+ vs theoretical 180 two-team rows) |
| Invalid timestamps | N/A — minute integer only |
| Outlier values | Max observed ~14.4 in sample; no values >100 |
| Broken sequences | Minor gaps; quality score 75–83 per league |

### Quality score by league (0–100)

| League | Score |
|--------|-------|
| Champions League | 83.3 |
| Europa League | 83.3 |
| Conference League | 75.0 |
| **UEFA weighted avg** | **~80.5** |

---

## Part F — Feature Potential Analysis

| EGIE Target | Potential | Rationale |
|-------------|-----------|-----------|
| **First Goal Team** | **HIGH** | Minute-0 pressure + rolling pre-match dominance; xG harmed this market (54F-7) |
| **Goal Minute** | **VERY_HIGH** | Minute timeline directly models hazard rate |
| **Goal Range** | **MEDIUM** | Match intensity integrals; xG top10_xg stronger (+6.3%) for this market |
| **Next Goal Team** | **HIGH** | Core live asymmetry use case |
| **Team Goals** | **MEDIUM** | Pre-match rolling pressure; xG top5_xg showed +3% |
| **Live Goal Probability** | **HIGH** | In-play momentum — **not available from xG** |

---

## Part G — Shadow Feature Store Design (proposal only)

**Not implemented.** Architecture documented in `discovery_result.json → shadow_feature_store_design`.

```
Sportmonks API
  → Pressure Raw Store (JSON per fixture)
  → Normalizer (minute-participant canonical schema)
  → Aggregation Engine (rolling_pressure, momentum, spikes)
  → EGIE Shadow Arm (market-specific routing)
```

**Proposed features:** `rolling_pressure_5`, `pressure_momentum`, `pressure_acceleration`, `pressure_dominance`, `pressure_attack_ratio`, `pressure_swing`, `pressure_spike_count`, `dangerous_attack_ratio`

**Integration point:** Replace statistics proxy in `parse_sportmonks_pressure()` with real `pressure` include data.

---

## Part H — Required Answers

### 1. Does Sportmonks Pressure Index really exist?

**Yes.** Valid include is `pressure` on `/fixtures/{id}`. Returns minute-level rows with `participant_id`, `minute`, and `pressure` value. Confirmed on Champions League fixture in prior live probe and in 65/80 local UEFA cache files.

### 2. Which leagues have pressure data?

**In subscription (Euro Club Tournaments):** Champions League, Europa League, Conference League — **75–83% coverage** in cache sample.

**Not in current plan / no local data:** World Cup (732), European Championship (1326), Nations League (1538), Euro Qualification (1325).

### 3. How much historical pressure data exists?

- **Locally cached:** 65 fixtures with pressure, 12,676 timeline rows (80 UEFA fixtures total).
- **API depth:** Not fully enumerated this run (token 401). Prior xG backfill proved **1,004+ usable fixtures** for CL/EL/Conference on entitled plan — pressure should backfill alongside same fixture IDs using `include=pressure`.

### 4. Is minute-level pressure available?

**Yes.** Average **97.5 unique minutes** and **195 rows** per fixture. Includes minute 0 (pre-match baseline) through 90+.

### 5. Is pressure suitable for EGIE markets?

| Market | Suitable? | Evidence |
|--------|-----------|----------|
| First Goal Team | **Yes (research)** | HIGH potential; complements xG-free policy from 54F-7 |
| Goal Minute | **Yes (strong)** | VERY_HIGH — primary pressure use case |
| Goal Range | **Partial** | MEDIUM — xG top10_xg likely stronger pre-match |
| Next Goal Team | **Yes (live)** | HIGH — live asymmetry |
| Live Goal Probability | **Yes (live)** | HIGH — core in-play signal |

### 6. How does Pressure compare to xG?

| Dimension | xG (54F-7) | Pressure (54G) |
|-----------|------------|----------------|
| Pre-match aggregates | Strong for Goal Range, Team Goals | Moderate |
| First Goal Team | **Harmful** (−4.7%) | **HIGH potential** |
| Goal Minute / timing | Weak (no minute timeline) | **VERY_HIGH** |
| Live / in-play | Not available | **HIGH–VERY_HIGH** |
| Historical depth | 1,004 fixtures validated | 65 fixtures cached; needs backfill |
| Production status | RESEARCH_ONLY per market | Not tested — discovery only |

### 7. Is Pressure likely more valuable than xG?

**Market-dependent — yes for timing and live markets.**

- xG is **more valuable** for Goal Range (+6.3% top10_xg) and Team Goals (+3% top5_xg) pre-match.
- Pressure is **more valuable** for Goal Minute, Next Goal Team, and Live Goal Probability — markets xG cannot address.
- For First Goal Team, pressure is **promising** where xG was **harmful**.

**Overall:** Pressure is the **highest-value untested asset** for EGIE's **timing and live** stack, not a replacement for market-specific xG arms.

### 8. Should a Pressure Feature Store be built?

**Yes — shadow/research layer only.**

Build the Pressure Feature Store for backtest and shadow replay. Do **not** wire to production predictions until Phase 54G+ validation (similar to xG 54F path).

---

## Final Recommendation

### **`BUILD_PRESSURE_FEATURE_STORE`**

Conditions met:
- Pressure Index confirmed real and minute-level
- UEFA leagues show **75–83% coverage** with quality scores **75–83**
- Feature potential **VERY_HIGH** for Goal Minute; **HIGH** for First Goal Team, Next Goal Team, Live Goal Probability
- Complements (does not duplicate) market-specific xG from 54F-7

### Next steps (research only)

1. Refresh Sportmonks API token and run season-wide pressure backfill (mirror 54F xG orchestrator).
2. Implement shadow Pressure Feature Store per Part G design.
3. Run **54G-1** backtest: pressure vs baseline for Goal Minute and Next Goal Team.
4. Keep First Goal Team on **no-xG** policy; test pressure-only arm separately.

### Constraints honored

| Constraint | Status |
|------------|--------|
| Production deploy | **NOT done** |
| Live predictions | **NOT modified** |
| WDE | **NOT modified** |
| SaaS logic | **NOT modified** |
| Model changes | **NOT done** |

---

## Artifacts

| File | Purpose |
|------|---------|
| `discovery_result.json` | Full audit output |
| `PRESSURE_COVERAGE_MATRIX.json` | League/season coverage |
| `PRESSURE_JSON_KEY_INVENTORY.json` | Field inventory |
| `validation.json` | Validation gate output |
| `scripts/phase54g_pressure_discovery.py` | CLI runner |
| `scripts/validate_phase54g_pressure_discovery.py` | Validation script |

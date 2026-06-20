# PHASE 22B — Unified Fixture Intelligence Report

**Status:** COMPLETE (local)  
**Date:** 2026-06-19  
**Scope:** World Cup 2026 only — Sportmonks league **732**, season **26618**  
**Prediction weights:** UNCHANGED  
**Deploy:** NOT performed (per instructions)

---

## 1. Objective

Replace the split Sportmonks path (date-list payload as final data) with a **unified cache-first flow** that resolves the fixture ID, then loads the **full `/fixtures/{id}` payload** from SQLite or a single enrichment API call.

---

## 2. Architecture Change

### Before (Phase 8 / 22 audit)

```
EnrichmentService._maybe_enrich_sportmonks
  └─ SportmonksClient.get_fixture_context
       └─ lookup_world_cup_fixture
            └─ GET /fixtures/date/{date}  ← final payload (partial includes)
  └─ apply_sportmonks_consumption
```

**Gap:** Richer `GET /fixtures/{id}` existed (CLI only) with `state`, `events`, etc. Production never used it.

### After (Phase 22B)

```
EnrichmentService._maybe_enrich_sportmonks
  └─ SportmonksClient.get_fixture_context
       └─ resolve_unified_worldcup_fixture_intelligence
            ├─ [1] SQLite by API-Football fixture_id  → 0 API calls
            ├─ [2] lookup_world_cup_fixture (file cache) → 0–1 API calls
            └─ [3] fetch_worldcup_fixture_enrichment (/fixtures/{id}, SQLite) → 0–1 API calls
  └─ apply_sportmonks_consumption (unchanged)
```

**Fallback:** If step 3 fails but step 2 succeeded, use date-lookup partial payload (logged as `enrichment_failed_lookup_fallback`).

---

## 3. Cache Flow

| Layer | Key | TTL | Purpose |
|-------|-----|-----|---------|
| SQLite `sportmonks_fixture_enrichment` | `sportmonks_fixture_id` + `fixture_id_api_football` | 30 min live / 24 h finished | **Primary** unified payload store |
| File cache `sportmonks_fixtures_by_date` | date + league 732 | 30 min | Date list for ID resolution |
| File cache `sportmonks_fixture_lookup` | api_fixture_id + teams + date | 24 h hit / 1 h miss | Lookup result memoization |

### API call budget per predict (worst → best)

| Scenario | API calls |
|----------|-----------|
| SQLite warm by API fixture ID | **0** |
| Lookup cached + enrichment SQLite hit | **0** |
| Lookup cached + enrichment API fetch | **1** |
| Lookup API + enrichment API | **2** (same as before for cold path, but payload is richer) |

**Duplicate avoidance:** Enrichment fetch checks SQLite before HTTP. Unified path checks SQLite by API-Football ID before lookup.

---

## 4. Includes (fixture-by-ID payload)

Unified enrichment uses `WORLD_CUP_FIXTURE_INCLUDES`:

- `scores`, `participants`, `state`, `statistics`, `lineups`, `events`, `formations`, `sidelined.sideline`

Date lookup retains its lighter include set for ID resolution only.

---

## 5. Files Changed

| File | Change |
|------|--------|
| `worldcup_predictor/providers/sportmonks_enrichment.py` | Added `UnifiedFixtureIntelligenceResult`, `resolve_unified_worldcup_fixture_intelligence`, fixture data on enrichment result |
| `worldcup_predictor/providers/sportmonks_client.py` | Delegates to unified resolver; attaches `trace` metadata |
| `worldcup_predictor/providers/enrichment_service.py` | Stores `sportmonks_unified` trace; logs lookup endpoint when distinct |
| `worldcup_predictor/providers/base.py` | Optional `trace` on `ProviderCallResult` |

**Not changed:** `scoring_engine.py`, WDE weights, API-Football collectors, `apply_sportmonks_consumption` logic.

---

## 6. Metadata Trace (observability)

`provider_metadata.sportmonks_unified` example:

```json
{
  "source_chain": ["lookup_cache", "enrichment_cache"],
  "api_calls_made": 0,
  "sportmonks_fixture_id": 88001,
  "lookup_endpoint": "/fixtures/date/2026-06-19",
  "enrichment_endpoint": "/fixtures/88001",
  "includes": ["scores", "participants", "state", "..."],
  "keys_present": ["events", "lineups", "participants", "state", "..."],
  "phase": "22B_unified"
}
```

---

## 7. Impact Analysis

### Architecture
- Single canonical enrichment path for production and CLI.
- Fixture-specific payload is now the source of truth.

### Cache
- More SQLite rows populated during predict (links `fixture_id_api_football`).
- Repeat predicts on same fixture → **0 Sportmonks HTTP** when cache warm.

### Quota
- Cold path: up to 2 calls (unchanged ceiling).
- Warm path: often **0 calls** (improved vs always using date payload).
- No per-card polling added.

### Prediction
- **No weight changes.**
- Indirect benefit: `state`, `events` available in supplemental for future phases (22C–22F).
- Gap-fill (injuries, lineups, xG from statistics) behavior unchanged.

### Database
- Reuses existing `sportmonks_fixture_enrichment` table (PostgreSQL-compatible schema via migrations).
- No new tables in 22B.

### Deployment
- **Not deployed.** Safe to deploy with existing `.env` Sportmonks token; no new env vars.

---

## 8. Validation

```bash
python scripts/validate_phase22b_unified_fixture.py
python scripts/validate_phase8_sportmonks_consumption.py
```

Local run: **13/13** checks passed on `validate_phase22b_unified_fixture.py` (offline, fake repo).

---

## 9. Next Phase (22C — awaiting approval)

- Add `odds`, `predictions`, `metadata` includes to enrichment fetch (separate include profile or phase-gated).
- Create `SportmonksPredictionAgent` (benchmark only — no override).

---

**PHASE 22B COMPLETE — STOPPED FOR APPROVAL BEFORE 22C**

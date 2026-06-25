# PHASE API-G — Sportmonks Real Coverage Audit

**Mode:** AUDIT ONLY  
**Date:** 2026-06-22  
**Code changes:** NONE  
**Production deploy:** NONE

---

## Executive Summary

Sportmonks **does have cached Premier League fixture payloads** (192 file-cache hits for league 8), but **almost none of it reaches EGIE**. The zero xG/pressure/odds coverage in EGIE audits is **not proof that Sportmonks lacks data globally** — it proves:

1. Application code is **WC-scoped** (league 732 hard guard) for production enrichment.
2. **No PL → Sportmonks fixture_id mapping** exists in SQLite (0 PL rows; 24 WC rows).
3. **Premium includes are plan-blocked** (xGFixture, odds, predictions → 403).
4. EGIE ingest for Sportmonks was **schema-ready only** until Phase API-F backfill module (not production-wired).

---

## STEP 1 — Sportmonks Capability Audit

| Component | In plan? | API endpoint | Integrated? | Local store | PostgreSQL | SQLite | EGIE | Survival | Backtest | Confidence |
|-----------|----------|--------------|-------------|-------------|------------|--------|------|----------|----------|------------|
| xG Match | **No** (403) | `GET /fixtures/{id}` + `xGFixture` include | Yes (`sportmonks_xg_extraction.py`) | File cache | EGIE raw (new backfill) | `xg_snapshots` | Read via `EgieProviderFeatureStore` | Columns | Strategy B/E/F | Via agents |
| Pressure Index | **Unknown** (needs include) | Fixture statistics includes | Parser in `extractors.py` | File cache | EGIE raw | enrichment | Read | Columns | Strategy C/E/F | Via `first_goal_pressure` |
| Match Centre | Base includes | `/fixtures/{id}` | `sportmonks_enrichment.py` | Cache | — | enrichment | No | No | No | No |
| Odds | **No** (403) | Fixture odds include | `sportmonks_consumption.py` | WC cache | — | enrichment flag | No | No | No | No |
| Prediction Model | **No** (403) | predictions include | `sportmonks_prediction_agent.py` | WC | promotion shadow | enrichment | No | No | No | No |
| Head2Head | Base? | H2H endpoints | Partial in enrichment | Cache | — | — | No | No | No | No |
| Team Season Statistics | Base? | team stats | `sportmonks_standings_service.py` | Cache | — | — | No | No | No | No |
| Team Recent Form | Base? | form includes | enrichment | Cache | — | — | No | No | No | No |
| Lineup | Base includes | lineups include | enrichment | Cache | — | enrichment | No (SM path) | No | No | No |
| Injuries & Suspensions | Base? | sidelined include | enrichment | Cache | — | — | No | No | No | No |
| Events Timeline | Base includes | events include | enrichment | Cache | — | enrichment | No (uses API-F events) | first_goal_minute | Baseline A | Indirect |
| Team Squad | Base? | squad include | enrichment | Cache | — | — | No | No | No | No |
| Topscorers | Base? | topscorers | — | — | — | — | No | No | No | No |
| Group Standings | WC | standings | `sportmonks_standings_service.py` | Cache | — | — | No | No | No | No |
| Trends | Unknown | trends include | — | — | — | — | No | No | No | No |
| Referee Statistics | Unknown | referee include | — | — | — | — | No | No | No | No |
| Player Profile | Base? | player include | enrichment | Cache | — | — | No | No | No | No |
| Live Standings | Base? | standings live | standings service | Cache | — | — | No | No | No | No |

**Plan probe source:** `.cache/api_football/sportmonks/sportmonks_xg_plan_probe.json` (2026-06-21)

```json
{
  "base_enrichment": true,
  "odds_include": false,
  "predictions_include": false,
  "xg_fixture_include": false
}
```

---

## STEP 2 — Data Coverage Report (PL EGIE Cohort, n=380)

| Feature | Provider rows available* | Stored locally | Enters EGIE | Coverage % |
|---------|-------------------------|----------------|-------------|------------|
| xG Match | PL cache hits (192 files) | 0 SQLite PL / 0 `xg_snapshots` | 0 | **0%** |
| Pressure Index | Unknown in PL cache | 0 | 0 | **0%** |
| Odds | Plan blocked | 85 WC odds snapshots | 0 PL | **0%** |
| Lineups | API-F + SM cache | 12 EGIE PG (API-F) | 12 | **3.16%** |
| Injuries | API-F ingest | 0 EGIE PG | 0 | **0%** |
| Recent Form | Not ingested for PL | 0 | 0 | **0%** |
| Head2Head | Not ingested for PL | 0 | 0 | **0%** |
| Prediction Model | Plan blocked | 0 PL | 0 | **0%** |

\*Provider rows = evidence from file cache scan (`scripts/sportmonks_coverage_audit_readonly.py`), not live API.

**SQLite snapshot (`artifacts/_api_g_sqlite_stats.json`):**

| Store | Count |
|-------|-------|
| PL fixtures | 380 |
| `sportmonks_fixture_enrichment` league 732 (WC) | 24 |
| `sportmonks_fixture_enrichment` league 8 (PL) | **0** |
| `xg_snapshots` | **0** |
| PL `odds_snapshots` | **0** |
| WC/non-PL `odds_snapshots` | 85 |

---

## STEP 3 — Fixture Mapping Audit

**Artifact:** `artifacts/egie_provider_fixture_mapping_audit.json`

| Check | Result |
|-------|--------|
| EGIE `fixture_id` | API-Football id (canonical) |
| Sportmonks id present | 0 / 380 |
| Mapping success rate | **0.0%** |
| Incorrect mapping | None observed (all missing, not wrong) |
| WC odds id collision | 85 odds rows use non-PL ids (no PL overlap) |

**Sample:**

| EGIE fixture_id | API-Football | Sportmonks | Status |
|-----------------|--------------|------------|--------|
| 1035037 | 1035037 | null | api_football_only |
| 1035038 | 1035038 | null | api_football_only |

---

## STEP 4 — Data Flow Audit

### xG Match

```
Provider: YES (cached PL files exist; live xG include BLOCKED)
    ↓
Storage: NO (0 PL enrichment rows, 0 xg_snapshots)
    ↓
Feature Store: YES (reader exists)
    ↓
EGIE: NO (0% coverage)
    ↓
Backtest B/E/F: NO-OP
    ↓
Confidence: NO
```

### Pressure Index

```
Provider: UNKNOWN (likely in stats blob if entitled)
    ↓
Storage: NO
    ↓
Feature Store: YES (parser exists)
    ↓
EGIE: NO
    ↓
Backtest C/E/F: NO-OP
```

### Odds

```
Provider: YES (WC); PL cache unobserved
    ↓
Storage: YES (85 WC snapshots) — WRONG fixture_ids for PL
    ↓
Feature Store: YES
    ↓
EGIE: NO (has_reliable_goal_odds 0%)
    ↓
Backtest D/E/F: NO-OP
```

### Lineups (API-Football path)

```
Provider: YES
    ↓
Storage: PARTIAL (12/380 EGIE PG)
    ↓
Feature Store: YES
    ↓
EGIE: PARTIAL (3.16%)
    ↓
Backtest F: minimal impact (metrics = A)
```

### Goal Events (API-Football)

```
Provider: YES
    ↓
Storage: YES (359/380)
    ↓
Feature Store: YES
    ↓
EGIE: YES (94.47%)
    ↓
Backtest A: YES (baseline)
```

### Sportmonks production enrichment (WC)

```
Provider: YES (league 732)
    ↓
Storage: YES (24 SQLite rows)
    ↓
EGIE PL backtest: NO (wrong league / no mapping)
    ↓
World Cup prediction pipeline: YES (separate path)
```

---

## STEP 5 — Value Analysis (EGIE Goal Timing)

### Tier S — Expected highest impact

| Feature | Rationale |
|---------|-----------|
| **PL-aligned pre-match odds** | Direct signal for first-goal team & goal-range markets; currently 0% due to fixture_id mismatch |
| **xG Match (home/away)** | Strong prior for first-goal team; blocked by plan + no PL mapping |

### Tier A — Medium impact

| Feature | Rationale |
|---------|-----------|
| Pressure Index | Complements xG for live-style first-goal timing; parser exists |
| API-Football fixture statistics | Shots/SOT/dangerous attacks — 3.16% today |
| Lineups / injuries | Player availability — sparse ingest |

### Tier B — Low impact for EGIE timing

| Feature | Rationale |
|---------|-----------|
| Sportmonks predictions | Different model; plan blocked |
| Head2Head / form | Redundant with API-Football history already in baseline |
| Topscorers / referee / trends | Weak direct link to first-goal minute |

---

## STEP 6 — Missing / Blocked Integrations

| Gap | Type | Evidence |
|-----|------|----------|
| PL Sportmonks fixture_id map | Missing integration | 0% mapping rate |
| `sportmonks_fixture_lookup` PL support | Blocked by WC guard in production path | `lookup_world_cup_fixture` only |
| xGFixture include | **Plan blocked** | probe `premium_xg_access_denied` |
| Odds / predictions includes | **Plan blocked** | probe flags |
| EGIE Sportmonks ingest (1C) | Was schema-only; API-F added backfill module, not production | `egie/config.py` notes |
| PL odds in SQLite | **Mapping broken** | 85 WC ids, 0 PL ids |

---

## Evidence-Based Conclusions

| # | Conclusion | Verdict for PL EGIE |
|---|------------|---------------------|
| 1 | Data exists and is used | **Only for WC** (league 732), not PL backtest |
| 2 | Data exists but not imported | **YES** — PL file-cache (192 hits), not in SQLite/EGIE |
| 3 | Data exists but mapping broken | **YES** — odds fixture_ids; Sportmonks ids |
| 4 | Data never reaches EGIE | **YES** — xG, pressure, PL odds |

**Estimated impact if Tier S gaps fixed:** Strategies B–E could diverge from A; prior Phase API work estimated 1–3pp FG-team lift **if** xG+odds coverage >50%. Not observable today.

---

## Artifacts & Commands (read-only)

- `scripts/sportmonks_coverage_audit_readonly.py` — plan + cache scan
- `artifacts/egie_paid_provider_audit.json` — EGIE utilization
- `artifacts/egie_provider_fixture_mapping_audit.json` — mapping
- `artifacts/_api_g_sqlite_stats.json` — SQLite counts

**STOP — no implementation, no deploy.**

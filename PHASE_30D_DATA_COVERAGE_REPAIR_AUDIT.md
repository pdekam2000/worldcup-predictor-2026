# Phase 30D — Data Coverage Repair Audit

**Mode:** Audit only — no code changes, no deploy  
**Date:** 2026-06-20  
**Fixture:** `1539007` — Netherlands vs Sweden (kickoff `2026-06-20T17:00:00` UTC)  
**Production:** https://footballpredictor.it.com  
**Deployed commit:** `77e038d` (Phase 29 / 30A / 30C)

---

## Executive Summary

Production Prediction Detail for fixture **1539007** shows **Medium data 55%**, **Missing lineups**, **No odds data**, and **No Bet**. This is misleading for a paid SaaS: **API-Football odds are live and cached (14 bookmakers, 60+ markets)**, specialist agents report lineup and odds intelligence as available/partial, and Sportmonks base enrichment is mapped and cached.

| Symptom | Primary root cause | Severity |
|--------|-------------------|----------|
| **No odds data** (UI badge) | **Frontend/API display bug** — `data_signals` looks up wrong agent keys and rejects `partial` odds | **P0 — false negative** |
| **Missing lineups** (UI badge) | **Frontend/API display bug** — same wrong agent keys; ignores `expected_lineup_agent` | **P0 — false negative** |
| **Data quality 55%** | **Scoring policy** — official lineups (15 pts) and injuries (10 pts) not credited pre-kickoff; not a provider outage | **P1 — UX/policy** |
| **No Bet** | **Confidence gate** (`51.2 < 60`), not data quality; lineup cap also applied | **P1 — expected WDE behavior** |
| **Sportmonks xG/odds/predictions** | **Plan limit (HTTP 403)** — premium includes blocked; base enrichment works | **P2 — subscription** |
| **SQLite fixture row** | **Persistence gap** — `home_team_id`, `away_team_id`, `league_id`, `season` never written by `upsert_fixture` | **P1 — data layer** |

**Bottom line:** The paid APIs have data. The worst user-visible failures are **display-layer false negatives**, not missing provider responses.

---

## 1. Production Snapshot (fixture 1539007)

Live `POST /api/predict/1539007` on production (2026-06-20 ~12:30 UTC):

```json
{
  "confidence": 51.2,
  "data_quality": 55.0,
  "no_bet": true,
  "data_signals": {
    "tier": "medium",
    "data_quality_pct": 55.0,
    "missing_lineups": true,
    "missing_injuries": false,
    "odds_available": false
  },
  "audit_trace": {
    "confidence": {
      "baseline": 56.3,
      "final": 56.3,
      "caps_applied": ["missing_official_lineups_first_goal_player_cap_30"],
      "reductions": ["high_injury_absence_team_strength_reduced"],
      "no_bet_reasons": ["confidence_below_60"]
    }
  }
}
```

**Specialist agents (same response):**

| Agent | Status | Impact | Notes |
|-------|--------|--------|-------|
| `lineup_agent` | **available** | 55.0 | `live_data_available` |
| `expected_lineup_agent` | **available** | 84.0 | projected XI intelligence |
| `odds_market_agent` | **partial** | 54.9 | implied probs from API-Football odds |
| `market_consensus_agent` | **available** | 96.9 | strong consensus signal |
| `injury_suspension_agent` | partial | 54.0 | `heuristic_partial` |
| `sportmonks_prediction_agent` | unavailable | 50.0 | `sportmonks_plan_no_predictions_access` |
| `xg_intelligence_agent` | unavailable | 0.0 | `sportmonks_plan_no_xg_access` |

**Contradiction:** Backend specialists say lineups and odds context exist; `data_signals` says the opposite.

---

## 2. API-Football Data Availability

Verified on production SQLite cache (`api_response_cache`) and `odds_snapshots`:

| Endpoint | Cached? | Payload size | Loaded? | Notes |
|----------|---------|--------------|---------|-------|
| `fixtures` (by id) | via predict pipeline | — | Yes at runtime | Resolves team IDs when DB row lacks them |
| `odds` | Yes | **~308 KB** | **Yes** | **14 bookmakers**, first BM **60 markets** (1X2, O/U, AH, BTTS, etc.) |
| `predictions` | Yes | ~9 KB | Yes | API-Football prediction reference available |
| `fixtures/lineups` | **No** | — | **Skipped** | `should_fetch_lineups()` — **4.4 h > 4.0 h** gate |
| `injuries` | Mixed | ~2 B (empty) | Partial | Early call `league=1`; later `injuries/skip` with `missing_league_id` |
| `fixtures/statistics` | Yes | ~2 B (empty) | Empty | Expected pre-match (`NS`) |
| `fixtures/events` | Yes | ~2 B (empty) | Empty | Expected pre-match |
| `fixtures/players` | Yes | ~2 B (empty) | Empty | Pre-match |
| `standings` | via builder | — | Yes | Used in intelligence build |
| H2H | — | — | Depends on team IDs | Blocked when IDs null in local-first path before resolve |
| Team form / recent | — | — | Yes when IDs resolved | `_fetch_recent_fixtures` |

**Bookmakers / markets (odds_snapshots latest):**

- Bookmakers: **14**
- Markets (first bookmaker): **60** including Match Winner, Goals O/U, Asian Handicap, HT/FT, BTTS

**Quota:** Not exhausted — live/cache hits present; large odds payload proves successful fetch.

---

## 3. Sportmonks Data Availability

**Mapping:** Present and correct.

```
fixture_id_api_football: 1539007
sportmonks_fixture_id:   19609176
league_id:               732 (World Cup)
season_id:               26618
```

**Cache row (`sportmonks_fixture_enrichment`):**

| Flag | Value |
|------|-------|
| `base_enrichment_available` | 1 |
| `premium_odds_available` | 0 |
| `premium_predictions_available` | 0 |
| `premium_xg_available` | 0 |
| `premium_odds_access_denied` | 1 |
| `premium_predictions_access_denied` | 1 |
| `premium_xg_access_denied` | 1 |

**Raw payload keys:** participants, statistics, **lineups**, sidelined, metadata, `has_odds`, `has_premium_odds` — premium odds/predictions/xG **not in payload** (403 on premium includes per Phase 28B design).

| Capability | Available? | Source |
|------------|------------|--------|
| Fixture enrichment cache | Yes | SQLite `sportmonks_fixture_enrichment` |
| Base lineups / sidelined | Likely in base include | Consumption via `apply_sportmonks_consumption` |
| xG | No | Plan 403 |
| Sportmonks odds | No | Plan 403 |
| Predictions | No | Plan 403 |
| Pressure / trends | Not in current include set | Out of scope for this fixture row |
| Team form / H2H / standings | Partial via base stats/participants | Not premium-blocked |

**Mapper status:** **Not missing** for this fixture. Global table still has only **1 row** — mapping works when predict runs, but bulk backfill absent (see Phase 31A).

---

## 4. Cache / Database Issues

### 4.1 `fixtures` table — incomplete persistence

Production row for 1539007:

```
home_team_id: NULL
away_team_id: NULL
league_id:      NULL
season:         NULL
source:         cache
updated_at:     2026-06-13
```

**Root cause:** `FootballIntelligenceRepository.upsert_fixture()` inserts/updates name, kickoff, venue, etc., but **never writes** `home_team_id`, `away_team_id`, `league_id`, or `season` even though schema columns exist (`schema.py` + migrations).

**Impact:**

- `load_fixture_api_item_from_db()` returns team IDs as `null` → local-first path starts degraded.
- `get_injuries()` can hit `injuries/skip` when league cannot be resolved from stale row (cached skip at 10:47 UTC).
- `TournamentFixture` schedule model has **no team ID fields** — schedule sync never captures IDs at import time.

Runtime predict **partially compensates** via `_resolve_fixture()` → `get_fixture_by_id()`, but SQLite remains stale and skip caches persist.

### 4.2 `fixture_enrichment` — empty for this fixture

`SELECT COUNT(*) … WHERE fixture_id=1539007` → **0 rows**.

Per-fixture enrichment (events, lineups, statistics, odds JSON columns) is **not persisted** for upcoming WC matches in the hot path. Odds **do** exist in `odds_snapshots` (separate table).

### 4.3 API response cache — healthy for odds

```
endpoint=odds, params={"fixture": 1539007}, payload ~308014 bytes
endpoint=predictions, ~8998 bytes
endpoint=injuries/skip, reason=missing_league_id
```

Data **is** fetched and cached; failures are **selective** (lineups gate, injuries skip, empty pre-match stats).

---

## 5. Provider Mapping (API-Football ↔ Sportmonks)

| Check | Result |
|-------|--------|
| Mapping row exists | **Yes** — SM `19609176` ↔ AF `1539007` |
| Mapping used at predict time | **Yes** — enrichment fetched 2026-06-20 12:28 UTC |
| Lookup fallback needed | **No** for this fixture |
| Global coverage | **Poor** — only 1 SM enrichment row total in DB |

**Classification:** Mapping logic works; **coverage breadth** is the gap, not ID resolution for 1539007.

---

## 6. Frontend / API Display Issue (Critical)

### 6.1 `data_signals_from_specialist_summary()` — wrong agent keys

File: `worldcup_predictor/api/display_helpers.py`

```python
lineup = _agent_signal(agents, "lineup")      # actual key: lineup_agent
injury = _agent_signal(agents, "injury")      # actual key: injury_suspension_agent
odds   = _agent_signal(agents, "odds")        # actual key: odds_market_agent
```

Specialist summary uses agent **names** from orchestrator (`lineup_agent`, `odds_market_agent`, etc.) — see `predictions.py` `_specialist_summary()`.

When keys are missing:

- `lineup_status` → `""` → `missing_lineups = True`
- `odds_status` → `""` → `odds_available = False`

**Reproduced on production** with live specialist payload:

```
lineup_agent status=available
odds_market_agent status=partial
recomputed_data_signals → missing_lineups=True, odds_available=False
```

### 6.2 Odds requires `available`, not `partial`

Even after key fix, odds display requires:

```python
odds_available = odds_status == "available" and odds_reason in (LIVE_DATA_AVAILABLE, CACHE_HIT, "")
```

`OddsMarketAgent` intentionally sets status **`partial`** when real odds exist (`agents.py` ~752) because odds are contextual, not a direct bet signal. **`market_consensus_agent`** is `available` at 96.9 impact — but is **not consulted** by `data_signals`.

### 6.3 Frontend consumes `data_signals` verbatim

File: `base44-d/src/components/match/DataQualityBadge.jsx`

- Renders **Missing lineups** when `signals.missing_lineups`
- Renders **No odds data** when `!signals.odds_available`

No secondary check against `specialist_summary` or `detailed_markets`.

**Classification:** **Frontend/API display bug** (backend has data; flags wrong).

---

## 7. Data Quality = 55 — Exact Breakdown

Scoring engine: `worldcup_predictor/data_quality/intelligence_scoring.py` + `transparency.py` (`CORE_WEIGHTS`, max pre-match core = **100**).

### 7.1 Core weights

| Component | Max pts | Fixture 1539007 (production) | Reason |
|-----------|---------|------------------------------|--------|
| `fixture_identity` | 10 | **10** | Names + fixture id present |
| `team_ids` | 10 | **10** | Resolved live via `get_fixture_by_id` at predict time |
| `standings_context` | 10 | **10** | Standings loaded for WC competition |
| `recent_form` | 15 | **15** | Both teams have recent fixtures when IDs resolved |
| `injuries` | 10 | **0** | `injuries/skip` or empty; not credited despite partial injury agent |
| `odds` | 10 | **10** | `report.odds.available == True` (308 KB cache) |
| `stats` | 10 | **0** | Pre-match `fixtures/statistics` empty |
| `lineups` | 15 | **0** | `lineups.available == False` — fetch skipped >4 h pre-kickoff |
| `weather` | 5 | **0** | Not in fixture payload |
| `referee` | 5 | **0** | Not credited in score (referee may exist on fixture) |
| **Total** | **100** | **55** | |

**Formula check:** 10 + 10 + 10 + 15 + 10 = **55** ✓

### 7.2 Supplemental / Sportmonks contribution

| Component | Max | Fixture 1539007 |
|-----------|-----|-----------------|
| `supplemental_xg` | 10 | 0 — SM premium 403 |
| `supplemental_odds` | 5 | 0 — not RapidAPI supplemental path |
| `supplemental_player_stats` | 8 | 0 |
| `supplemental_squad` | 5 | 0 |
| Sportmonks base (not separate DQ column) | — | Consumed in agents, not extra DQ points |

**Sportmonks contribution to `data_quality` numeric score:** **0 points** (premium blocked; base lineups/sidelined not wired into `CORE_WEIGHTS["lineups"]` unless `lineups.available`).

### 7.3 Transparency reason text

Built from components below max — flags **official lineups**, **injuries**, **weather** as missing. Does not explain that odds exist or that projected lineups are available.

---

## 8. Near-Kickoff Rule Audit

**Policy:** `worldcup_predictor/quota/cache_policy.py`

```python
LINEUPS_FETCH_MAX_HOURS_BEFORE = 4.0

def should_fetch_lineups(kickoff_utc):
    return hours_until <= 4.0  # or match started
```

At audit time: **~4.4 hours** to kickoff → **`should_fetch=False`** → `_collect_lineups` returns:

```python
{"items": [], "available": False, "skipped": "far_from_kickoff"}
```

**Current behavior:**

| Layer | Behavior | User-facing label |
|-------|----------|-------------------|
| API fetch | Skips official lineups API | — |
| DQ scoring | 0/15 lineups | "Medium 55%" |
| `lineup_agent` | Can still be **available** via predicted/projected data | — |
| `expected_lineup_agent` | **available** (84 impact) | — |
| `data_signals` | **Missing lineups** (bug + no near-kickoff nuance) | **Missing lineups** |
| WDE | Cap: `missing_official_lineups_first_goal_player_cap_30` | Contributes to lower confidence |

**Gap vs product requirement (item 7):** System treats pre-kickoff absence as **severe missing data** in UI and DQ, instead of **"Official lineup pending"** with projected lineup/squad/injuries credited.

---

## 9. No Bet — Root Cause

| Gate | Threshold | Fixture 1539007 | Triggered? |
|------|-----------|-----------------|------------|
| `data_quality_no_bet_threshold` | 50 | 55 | **No** |
| `no_bet_confidence_minimum` | 60 | 51.2 | **Yes** |
| `_MIN_DATA_QUALITY` (market ranking) | 45 | 55 | No |
| `_MIN_CONFIDENCE` (market ranking) | 55 | 51.2 | **Yes** |

**Primary reason:** `no_bet_reasons: ["confidence_below_60"]`

Contributing factors (not primary):

- `missing_official_lineups_first_goal_player_cap_30`
- `high_injury_absence_team_strength_reduced`

**No Bet is not caused by missing odds API data.** Market ranking returns empty picks because `no_bet=True`, not because odds are absent.

---

## 10. Root Cause Summary by Symptom

### No odds data (UI)

1. **Primary:** `display_helpers.py` agent key mismatch (`odds` vs `odds_market_agent`) → always false.
2. **Secondary:** Even with fix, `partial` status excluded; should treat `market_consensus_agent` or `report.odds.available` as signal.

**Not caused by:** API quota, missing API-Football odds, or cache failure.

### Missing lineups (UI)

1. **Primary:** Same agent key mismatch (`lineup` vs `lineup_agent`).
2. **Secondary:** No fallback to `expected_lineup_agent` status.
3. **Policy:** Official lineups intentionally not fetched >4 h out; projected lineups exist but UI label is binary "Missing".

**Not caused by:** Sportmonks mapping failure (base lineups in SM cache).

### Data quality 55%

1. **By design:** −15 official lineups, −10 injuries, −10 stats, −5 weather, −5 referee (partial credit only on loaded core).
2. **Amplified by:** injuries skip cache, no projected-lineup credit in DQ scorer.

### No Bet

1. **Confidence 51.2 < 60** — WDE and market ranking gates.
2. Lineup/injury caps reduce confidence further.

---

## 11. Problem Classification Matrix

| Layer | Issue? | Details |
|-------|--------|---------|
| API-Football quota | No | Odds + predictions cached; large payloads |
| API-Football endpoint | Partial | Lineups gated by time; injuries empty/skipped |
| Sportmonks plan | Yes (premium) | 403 on odds/predictions/xG — expected per Phase 28B |
| Sportmonks mapper | No (this fixture) | ID 19609176 mapped |
| SQLite persistence | **Yes** | Team IDs / league / season not upserted; no fixture_enrichment row |
| Cache read path | Partial | Local-first serves null team IDs before live resolve |
| Backend intelligence | Mostly OK | Odds + consensus available; official lineups deferred |
| API `data_signals` | **Yes — bug** | Wrong agent keys |
| Frontend display | **Yes — bug** | Trusts broken `data_signals` |

---

## 12. Files Requiring Changes (Phase 30E)

### P0 — False "Missing lineups" / "No odds data"

| File | Change |
|------|--------|
| `worldcup_predictor/api/display_helpers.py` | Fix agent keys; add fallback chain (`lineup_agent`, `expected_lineup_agent`, `odds_market_agent`, `market_consensus_agent`); treat `partial` odds as available when consensus exists; add `lineup_status_label` enum (`official` / `projected` / `pending`) |
| `base44-d/src/components/match/DataQualityBadge.jsx` | Show "Official lineup pending" vs "Missing lineups"; show "Odds available" when backend signals consensus |
| `worldcup_predictor/api/routes/predictions.py` | Optionally expose `data_quality_breakdown` in API for transparency |

### P1 — Data quality score / persistence

| File | Change |
|------|--------|
| `worldcup_predictor/data_quality/intelligence_scoring.py` | Credit projected lineups (expected lineup / SM base) at partial weight; don't penalize full 15 pts when `skipped=far_from_kickoff` |
| `worldcup_predictor/data_quality/transparency.py` | Update reason text for near-kickoff pending official lineups |
| `worldcup_predictor/quota/cache_policy.py` | Document or adjust `LINEUPS_FETCH_MAX_HOURS_BEFORE`; align with UX copy |
| `worldcup_predictor/database/repository.py` | Extend `upsert_fixture()` to persist `home_team_id`, `away_team_id`, `league_id`, `season` |
| `worldcup_predictor/domain/schedule.py` | Add optional team ID fields to `TournamentFixture` |
| `worldcup_predictor/schedule/worldcup_schedule_service.py` | Capture team IDs from API fixtures list |
| `worldcup_predictor/quota/local_first.py` | Hydrate IDs from live fixture fetch when DB null |
| `worldcup_predictor/clients/api_football.py` | Ensure injuries never skip when competition `league_id` is known (comp fallback before skip cache) |
| `worldcup_predictor/providers/sportmonks_consumption.py` | Ensure base SM lineups/sidelined promote `lineups.available` for DQ when official AF lineups skipped |

### P2 — Sportmonks premium / enrichment breadth

| File | Change |
|------|--------|
| `worldcup_predictor/providers/sportmonks_enrichment.py` | Operational: upgrade plan OR document premium unavailable |
| `worldcup_predictor/ingestion/` or predict warm-up | Backfill `sportmonks_fixture_enrichment` for upcoming WC fixtures |

### P3 — No Bet UX (optional, separate from coverage)

| File | Change |
|------|--------|
| `worldcup_predictor/decision/weighted_decision_engine.py` | Review cap when projected lineups available |
| `worldcup_predictor/api/market_ranking_engine.py` | Surface informational picks vs hard no-bet when DQ ≥ 55 |

---

## 13. Recommended Phase 30E Implementation Plan

**Goal:** Paid SaaS detail page reflects real provider coverage; DQ score matches product rules for pre-kickoff matches.

### 30E-1 — Display truth fix (ship first, ~1 day)

1. Fix `data_signals_from_specialist_summary()` agent keys and odds/lineup logic.
2. Add fields:
   - `lineup_coverage: "official" | "projected" | "pending" | "missing"`
   - `odds_coverage: "available" | "partial" | "missing"`
3. Update `DataQualityBadge.jsx` labels per near-kickoff rule.
4. Add API test: fixture with `odds_market_agent=partial` → `odds_available=true`.

### 30E-2 — SQLite identity repair (~1 day)

1. Extend schedule import + `upsert_fixture` to persist team IDs and league/season.
2. One-time backfill script: for upcoming WC fixtures, call `fixtures?id=X`, update rows.
3. Invalidate `injuries/skip` cache keys for affected fixtures.

### 30E-3 — Data quality scoring alignment (~1 day)

1. When `lineups.skipped == far_from_kickoff` and `expected_lineup_agent` available → award **8–12/15** lineups points.
2. When Sportmonks sidelined fills injuries → award injuries points.
3. Expose `data_quality_breakdown` on predict API (read-only).

### 30E-4 — Enrichment persistence (~2 days)

1. On successful predict, upsert `fixture_enrichment` odds/lineups slice from report.
2. Warm Sportmonks mapping for next N upcoming fixtures (scheduled job).

### 30E-5 — Validation

- `scripts/validate_phase30e_data_coverage_repair.py` — fixture 1539007 assertions:
  - `odds_available == true`
  - `lineup_coverage != "missing"` when expected lineup available
  - `data_quality >= 65` pre-kickoff with odds + projected lineups
  - `data_signals` matches specialist summary
- Re-run production verify on https://footballpredictor.it.com/api/predict/1539007

### Out of scope for 30E

- WDE threshold tuning (confidence 60 no-bet gate)
- Sportmonks plan upgrade (business decision)
- Calibration / promotion mode changes

---

## 14. Audit Commands Used

Production read-only scripts (temporary, not deployed):

- `_phase30d_fixture_audit.py` — DB + predict sample
- `_phase30d_deep_audit.py` — DQ breakdown + SM flags
- `_phase30d_cache_audit.py` — `api_response_cache` inspection
- `_phase30d_predict_keys.py` — audit_trace / no_bet reasons

---

## 15. Stop Condition

**Audit complete. No code changes. No deploy.**

Await approval for **Phase 30E** implementation.

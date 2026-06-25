# PHASE 32A — Sportmonks xG Data Extraction Fix

**Status:** COMPLETE (local)  
**Date:** 2026-06-20  
**Scope:** World Cup 2026 — Sportmonks league **732**, season **26618**  
**Deploy:** NOT performed  
**WDE / prediction weights:** UNCHANGED (expose-only)

---

## 1. Objective

Correctly fetch, parse, cache, and **expose** Sportmonks xG Match data via the predict API — without injecting into the Weighted Decision Engine.

---

## 2. Audit — Current Sportmonks Provider (Before 32A)

| Item | Finding |
|------|---------|
| **Primary endpoint** | `GET /v3/football/fixtures/{sportmonks_fixture_id}` |
| **Unified enrichment includes** | Base: `scores;participants;state;statistics;lineups;events;formations;sidelined.sideline;metadata` |
| **Premium includes** | `odds;predictions;xGFixture` (split fetch, 403-safe) |
| **xGFixture requested?** | Yes — in `PREMIUM_WORLD_CUP_FIXTURE_INCLUDES` since Phase 22D |
| **lineups.xGLineup requested?** | **No** — flat `lineups` only; no nested xG player include |
| **xGFixture.type requested?** | **No** — type labels not fetched |
| **Parsing** | Partial — `parse_sportmonks_xg_from_fixture()` read xG (5304) + xGoT (5305) from `xGFixture.expected`; statistics fallback; **ignored** xPTS, penalties, free kicks, player xG |
| **SQLite cache** | 23 WC rows cached; all `premium_xg_available=0`; `xGFixture` key absent in raw JSON |
| **Live plan test** | HTTP **403** — `"You do not have access to the 'xgfixture' include"` (code 5002) |

**Root cause:** Parser and includes were incomplete; cached payloads never contained xG because the **xG add-on is not licensed** on the current Sportmonks plan. Upcoming WC fixtures also have empty xG pre-kickoff.

---

## 3. Implementation (Phase 32A)

### New module

`worldcup_predictor/providers/sportmonks_xg_extraction.py`

| Capability | Detail |
|------------|--------|
| **XG-rich includes** | `participants;league;venue;state;scores;events.type;events.period;events.player;xGFixture.type;lineups.player;lineups.xGLineup.type;lineups.details.type` |
| **403 fallback includes** | `participants;league;venue;state;scores;statistics;lineups;lineups.details.type` |
| **Cache-first resolution** | xg_match file store → SQLite enrichment → unified WC intelligence → dedicated API fetch |
| **Store** | `{API_CACHE_DIR}/sportmonks/xg_match/{sportmonks_fixture_id}.json` — raw fixture + parsed fields |
| **Team metrics parsed** | xG (5304), xGoT (5305), xPTS (7939), xG penalties (7940), xG free kicks (7941), + extended type map |
| **Player metrics** | `lineups.xGLineup` per player; top-5 summary |
| **API block** | `build_sportmonks_xg_api_block()` |
| **WDE** | **Not wired** — supplemental attach + API expose only |

### Wiring (expose-only)

| Location | Change |
|----------|--------|
| `sportmonks_consumption.py` | Calls `attach_sportmonks_xg_to_report()` after consumption |
| `predict_pipeline.py` | Stores `sportmonks_xg` on prediction metadata |
| `api/routes/predictions.py` | Adds `sportmonks_xg` to predict response |
| `api/display_helpers.py` | Backfills `sportmonks_xg` on cached GET payloads (cache-only) |

---

## 4. Exact Endpoint / Includes

**Primary (xG Match):**

```
GET https://api.sportmonks.com/v3/football/fixtures/{id}
?include=participants;league;venue;state;scores;events.type;events.period;events.player;xGFixture.type;lineups.player;lineups.xGLineup.type;lineups.details.type
```

**Fallback (plan without xG add-on):**

```
GET .../fixtures/{id}
?include=participants;league;venue;state;scores;statistics;lineups;lineups.details.type
```

---

## 5. Raw Response Availability

| Source | Result |
|--------|--------|
| **Offline sample (synthetic)** | Full xGFixture + xGLineup — parser verified |
| **SQLite WC cache (23 rows)** | Raw fixture present; `xGFixture` **null**; lineups without `xGLineup` |
| **Live API — xG includes** | **403** — xGFixture add-on not on plan |
| **Live API — fallback includes** | WC fixture **19609165** (Mexico vs South Africa) — payload OK, 52 lineup rows, **no xG values** (NS / no add-on) |
| **Dashboard demo fixture 18882619** | Fixture not returned (invalid/expired ID for this token) |

---

## 6. Parsed Fields

### Team-level (when xGFixture present)

| Field | Type ID | API key |
|-------|---------|---------|
| Expected Goals | 5304 | `home_xg` / `away_xg` |
| Expected Goals on Target | 5305 | `home_xgot` / `away_xgot` |
| Expected Points | 7939 | `home_xpts` / `away_xpts` |
| Expected Goals Penalties | 7940 | `home_xg_penalties` / `away_xg_penalties` |
| Expected Goals Free Kicks | 7941 | `home_xg_free_kicks` / `away_xg_free_kicks` |

Full parsed object also retains `team_metrics`, `xg_fixture_fields[]`, and statistics fallback map.

### Player-level

`player_xg_summary`: `{ player_count, players_with_xg, top_scorers_by_xg[] }` from `lineups.xGLineup`.

---

## 7. API Output Example

From offline validation (synthetic payload):

```json
{
  "sportmonks_xg": {
    "available": true,
    "home_xg": 1.65,
    "away_xg": 0.92,
    "home_xgot": 1.1,
    "away_xgot": 0.7,
    "home_xpts": 1.8,
    "away_xpts": 0.9,
    "home_xg_penalties": 0.12,
    "away_xg_penalties": null,
    "home_xg_free_kicks": null,
    "away_xg_free_kicks": 0.05,
    "player_xg_summary": {
      "player_count": 1,
      "players_with_xg": 1,
      "top_scorers_by_xg": [
        {
          "player_id": 101,
          "player_name": "Demo Striker",
          "team_side": "home",
          "xg": 0.88,
          "xgot": 0.55
        }
      ]
    },
    "source": "sportmonks",
    "data_source": "xGFixture",
    "raw_xg_fixture_present": true,
    "expected_row_count": 8
  }
}
```

**Live WC mapped fixture (1489386 → SM 19609165):**

```json
{
  "sportmonks_xg": {
    "available": false,
    "home_xg": null,
    "away_xg": null,
    "player_xg_summary": { "player_count": 52, "players_with_xg": 0, "top_scorers_by_xg": [] },
    "source": "sportmonks",
    "data_source": "none",
    "raw_xg_fixture_present": false
  }
}
```

---

## 8. Plan / Endpoint Access

| Check | Result |
|-------|--------|
| **Base fixture endpoint** | ✅ Allowed |
| **xGFixture include** | ❌ **403** — add-on not licensed |
| **lineups.xGLineup include** | ❌ Blocked with xGFixture (same 403 path) |
| **statistics fallback** | ✅ Allowed — generic expected-goals when populated post-match |
| **World Cup league 732** | ✅ Fixtures resolve and cache |

**Conclusion:** Current Sportmonks subscription supports WC fixture enrichment but **not** the dedicated xG Match add-on. Full xGFixture + player xGLineup values require plan upgrade.

---

## 9. Validation

**Script:** `scripts/validate_phase32a_sportmonks_xg_extraction.py`

| Mode | Result |
|------|--------|
| **Offline** | **18/18 PASS** |
| **Live (`--live`)** | Parser + WC mapping OK; xG values empty due to plan + pre-match state |

**Artifacts:** `artifacts/phase32a_xg_extraction_validation.json`

**Mapped WC test fixture:**

| API-Football ID | Sportmonks ID | Match |
|-----------------|---------------|-------|
| 1489386 | 19609165 | Mexico vs South Africa |

---

## 10. Next Step — Integrate xG into Confidence / Model

Recommended sequence (post–plan upgrade):

1. **Upgrade Sportmonks plan** — enable `xGFixture` + `lineups.xGLineup` for league 732.
2. **Re-warm cache** — run enrichment on finished WC group matches; verify `premium_xg_available=1` in SQLite.
3. **Phase 32B — shadow promotion** — feed `sportmonks_xg` into `XGIntelligenceAgent` benchmark trace; compare vs internal xG before any WDE delta.
4. **Conditional WDE hook** — only when `available=true` and `plan_support=full`; cap via existing `MAX_SPORTMONKS_CONFIDENCE_BOOST=0` until shadow replay passes.
5. **O/U + BTTS calibration** — use `home_xg + away_xg` total and xPTS draw signal as reduce-only harmonization inputs first.

**Do not deploy or enable WDE injection until xG add-on is active and post-match WC samples validate.**

---

## 11. Files Changed / Created

| File | Action |
|------|--------|
| `worldcup_predictor/providers/sportmonks_xg_extraction.py` | **Created** |
| `worldcup_predictor/providers/sportmonks_consumption.py` | Modified — attach xG extraction |
| `worldcup_predictor/orchestration/predict_pipeline.py` | Modified — metadata attach |
| `worldcup_predictor/api/routes/predictions.py` | Modified — API output |
| `worldcup_predictor/api/display_helpers.py` | Modified — cached backfill |
| `scripts/validate_phase32a_sportmonks_xg_extraction.py` | **Created** |
| `PHASE_32A_SPORTMONKS_XG_EXTRACTION_REPORT.md` | **Created** |

**Deploy:** NOT performed (per scope).

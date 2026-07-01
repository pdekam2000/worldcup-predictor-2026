# European Leagues Prediction Coverage Audit

**Date:** 2026-06-30  
**Mode:** Audit only — no prediction, ECSE baseline, WDE, EGIE, billing, or public UI changes  
**Database:** `data/football_intelligence.db` (SQLite, ~14 GB)  
**PostgreSQL:** Not configured in local environment (`DATABASE_URL` unset). SaaS PostgreSQL holds user/billing data; football intelligence fixtures, predictions, ECSE, and odds live in SQLite.

---

## Executive Summary

European league **competition keys are stored correctly** in the main `fixtures` table (the old “everything → `international`” bug is **not** present in current SQLite data). However, **live prediction pipelines remain World Cup–scoped in practice**: ECSE snapshots/evaluations, WDE stored predictions, result sync, and owner shadow tooling all run for `world_cup_2026` only.

European SQLite data is **historical and stale** (no upcoming European fixtures; UEFA cup rows lack `fixture_results`). PredOps and Match Center **can** address European competitions at the code level, but without fresh fixture import and pipeline wiring they do not produce European predictions today.

### Final Recommendation

**`PARTIAL_COVERAGE_NEED_PIPELINE_WIRING`**

Mapping is largely fixed and historical league rows exist, but automation (ECSE live, result sync, WDE daily jobs, evaluations, owner lab) is wired for World Cup. European coverage also needs **fixture/result import** (secondary: `NEED_DATA_IMPORT`) before pipelines can run.

---

## 1. Competition Key Audit

### Registry (`worldcup_predictor/config/competitions.py`, `league_registry.py`)

| Key | In registry | API-Football league ID | Enabled |
|-----|-------------|------------------------|---------|
| `bundesliga` | Yes | 78 | Yes |
| `premier_league` | Yes | 39 | Yes |
| `champions_league` | Yes | 2 | Yes |
| `europa_league` | Yes | 3 | Yes |
| `conference_league` | Yes | 848 | Yes |
| `world_cup_2026` | Yes | 1 | Yes |
| `international` | No (not a registry key) | — | — |
| `international_friendlies` | Yes | 667 | **Disabled** |
| `euro_club_tournaments` | **No** | — | — |

`euro_club_tournaments` is not a canonical key. UEFA club coverage is split across `champions_league`, `europa_league`, `conference_league` (see `worldcup_predictor/egie/uefa_club/config.py` for Sportmonks IDs 2 / 5 / 2286).

### `_competition_key()` — `historical_loader.py`

```370:382:worldcup_predictor/backtesting/historical_loader.py
def _competition_key(competition: str) -> str:
    lowered = competition.lower()
    if "world cup" in lowered or "world_cup" in lowered:
        return "world_cup_2026"
    if "bundesliga" in lowered:
        return "bundesliga"
    if "premier" in lowered or "premier_league" in lowered:
        return "premier_league"
    if "champions" in lowered or "champions_league" in lowered:
        return "champions_league"
    if "europa" in lowered or "europa_league" in lowered:
        return "europa_league"
    return lowered.replace(" ", "_")
```

**Status:** Fixed vs. the known bug (no blanket `international` return).  
**Gap:** `conference_league` is not explicit; display names like `"UEFA Conference League"` become `uefa_conference_league` (not in registry). `europa` substring also matches Europa Conference League strings — potential mis-map.

### Places still World Cup–defaulted or WC-only

| Location | Behavior |
|----------|----------|
| `ecse_live/result_sync.py` | `SUPPORTED_ECSE_COMPETITIONS = ("world_cup_2026",)` — European ECSE result sync **blocked** |
| `ecse_live/scheduler.py` | Calls `refresh_ecse_snapshot_results(..., competition_key="world_cup_2026")` hardcoded |
| `ecse_live/fixture_resolver.py` | API-Football resolve uses `get_competition("world_cup_2026")` + WC date window |
| `automation/worldcup_background/daily_prediction_job.py` | Default `competition_key="world_cup_2026"` |
| `automation/worldcup_background/*` (result refresh, evaluation, accuracy) | Defaults to `world_cup_2026` |
| `scripts/owner_today_10_exact_scores.py` | `_load_wde()` queries `world_cup_2026` only; API fetch limited to WC + Bundesliga + PL |
| `database/migrations.py` | `competition_type` column defaults to `'world_cup_finals'` for **all** fixtures (metadata leak on league rows) |

### Places that **do** support European keys

| Location | Behavior |
|----------|----------|
| `ecse_live/runner.py` | `discover_upcoming_fixture_rows()` loops `list_competition_keys(enabled_only=True)` |
| `autonomous/fixture_discovery.py` | Same pattern — all enabled competitions |
| `predops/engine.py` | `PREDOPS_COMPETITIONS` includes PL, Bundesliga, UCL, UEL, UECL |
| `api/match_center_aggregator.py` | Loads all enabled competitions via schedule service |
| `api/match_center_helpers.py` | Logos/emojis for European keys |
| `owner_ecse_shadow_lab.py` | `league` query filter on shadow rows (not competition registry) |

### `international` key in SQLite

**0 fixtures** with `competition_key = 'international'`. The historical mis-label issue is **not** present in current `fixtures` data.

---

## 2. Database Availability Audit (SQLite)

### Fixture counts by `competition_key`

| Competition | Total | Upcoming | Finished | w/ `fixture_results` | w/ WDE (`worldcup_stored_predictions`) | w/ ECSE snapshots | w/ ECSE evals | w/ odds |
|-------------|------:|---------:|---------:|---------------------:|---------------------------------------:|------------------:|--------------:|--------:|
| `bundesliga` | 1,232 | 0 | 1,232 | 1,232 | 0* | 0 | 0 | 1 |
| `premier_league` | 380 | 0 | 380 | 380 | 0 | 0 | 0 | 380 |
| `champions_league` | 90 | 0 | 90 | **0** | 0 | 0 | 0 | 34 |
| `europa_league` | 65 | 0 | 65 | **0** | 0 | 0 | 0 | 26 |
| `conference_league` | 65 | 0 | 65 | **0** | 0 | 0 | 0 | 25 |
| `world_cup_2026` | 332 | 12 | 320 | 320 | 48 | 8 | 3 | 328 |
| `international` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 12† |

\*One join matched a Bundesliga `fixture_id` to a row stored under `world_cup_2026` in `worldcup_stored_predictions` (cross-key contamination).  
†Orphan `odds_snapshots` rows with `competition_key='international'` and no matching fixtures.

### Date ranges (kickoff_utc)

| Key | Min kickoff | Max kickoff |
|-----|-------------|-------------|
| `bundesliga` | 2021-08-13 | 2025-05-26 |
| `premier_league` | 2023-08-11 | 2024-05-19 |
| `champions_league` | 2007-02-20 | 2024-07-17 |
| `europa_league` | 2005-09-14 | 2024-08-01 |
| `conference_league` | 2021-07-06 | 2024-07-18 |
| `world_cup_2026` | 2010-06-11 | 2026-06-30 |

**Critical:** No European competition has **upcoming** fixtures in SQLite. ECSE live T-60 discovery and autonomous prediction discovery read `fixtures` with `status IN ('NS','TBD',...)` and `kickoff_utc > now` — European competitions return **empty**.

### Other tables

| Table | European coverage |
|-------|-------------------|
| `predictions` | 17 rows, all `world_cup_2026` |
| `worldcup_prediction_evaluations` | 34 rows, all `world_cup_2026` |
| `worldcup_accuracy_summary` | 1 row, `world_cup_2026` |
| `ecse_training_dataset` | Uses display `league` names (`Premier League`, etc.), not `competition_key` |
| `historical_fixture_registry` | ~223k rows; league column is **display name**, not canonical key |
| `league_sync_state` | **Empty** — no incremental sync state for European leagues |
| `sportmonks_fixture_enrichment` | 28 rows, all joined to `world_cup_2026` fixtures |

### PostgreSQL

Not audited with live counts (no `DATABASE_URL` locally). Production PG does not appear to host the football intelligence fixture/prediction tables; those are SQLite-backed via `FootballIntelligenceRepository`.

---

## 3. Provider / API Coverage Audit

### API-Football (`competitions.py` league IDs)

| Competition | API-Football ID | Fixture discovery path | Odds | Lineups/injuries | Notes |
|-------------|----------------:|------------------------|------|------------------|-------|
| Premier League | 39 | `WorldCupScheduleService` / Match Center | Strong in SQLite (379/380) | Via standard API-Football endpoints | Season resolver active |
| Bundesliga | 78 | Same | Almost none in SQLite (1) | Same | Historical import only |
| Champions League | 2 | Same | Partial (34 fixtures) | Same | Results not synced to `fixture_results` |
| Europa League | 3 | Same | Partial (26) | Same | Results not synced |
| Conference League | 848 | Same | Partial (25) | Same | Results not synced |
| World Cup 2026 | 1 | Primary focus | Strong | Strong | Full pipeline |

### Sportmonks (read-only audit: `scripts/sportmonks_coverage_audit_readonly.py`)

| Competition | SM league ID | Cached evidence | xG / pressure in app |
|-------------|-------------:|-----------------|----------------------|
| Premier League | 8 | `observed_in_cache` (192 file-cache hits) | Not wired to live enrich |
| Bundesliga | 82 | `not_observed` | Not wired |
| Champions League | 2 | `not_observed` | EGIE UEFA config exists, not fetched live |
| Europa League | 5 | `not_observed` | Same |
| Conference League | 2286 | `not_observed` | Same |
| World Cup | 732 | **Confirmed** — 28 SQLite enrichment rows | Active |

**API-Football vs Sportmonks ID mismatch** is expected (e.g. Europa: API-Football `3` vs Sportmonks `5`; Conference: `848` vs `2286`). Mapping exists in `egie/uefa_club/config.py` but **application Sportmonks fetch is hard-guarded to league 732** per audit limitations.

### OddAlerts

Used by ECSE live prematch path; WC smoke targets in `fixture_resolver.py`. No evidence of European league OddAlerts mapping at scale in SQLite (`oddalerts_fixture_map` not counted per competition in this audit).

---

## 4. ECSE Pipeline Audit (European)

| Competition | Can generate snapshots? | Odds/lambda inputs? | Snapshots stored? | Shadow enhancer? | Result sync? | Evaluations? |
|-------------|------------------------|---------------------|-------------------|------------------|--------------|--------------|
| Bundesliga | Theoretically yes (odds path) | 1/1232 with odds | **0** | No European rows in shadow JSONL | **Blocked** (`SUPPORTED_ECSE_COMPETITIONS`) | **0** |
| Premier League | Yes if upcoming + odds | 380/380 historical odds | **0** | No | **Blocked** | **0** |
| Champions League | Yes if upcoming + odds | Partial | **0** | No | **Blocked** | **0** |
| Europa League | Same | Partial | **0** | No | **Blocked** | **0** |
| Conference League | Same | Partial | **0** | No | **Blocked** | **0** |
| World Cup 2026 | **Working** | Strong | **8** | 8 WC rows in shadow artifact | **Working** | **3** |

**Root causes for missing ECSE European coverage:**

1. No upcoming European fixtures in SQLite → T-60 runner never eligible.
2. `SUPPORTED_ECSE_COMPETITIONS` and scheduler hardcode `world_cup_2026` for result sync.
3. Shadow shortlist artifact (`artifacts/ecse_x2_m6_shadow_live_shortlists.jsonl`) contains 8× `world_cup_2026` and assorted minor leagues — **no** PL/Bundesliga/UCL rows.
4. `build_ecse_live_prediction()` can fall back to live odds, but European fixtures lack fresh odds snapshots for upcoming matches.

---

## 5. WDE Pipeline Audit (European)

| Competition | Can generate? | Stored predictions? | Finished evaluated? | Owner reports? | No-bet flags? |
|-------------|--------------|--------------------|--------------------|----------------|---------------|
| Bundesliga | Code supports via `PredictPipeline(competition_key=...)` | **0** | **0** | Owner script loads WDE as WC only | N/A |
| Premier League | Same | **0** | **0** | Partial via API fixture fetch for “today” | N/A |
| UCL / UEL / UECL | Same | **0** | **0** | Not in `SUPPORTED_API_LEAGUES` | N/A |
| World Cup 2026 | **Working** | **48** stored | **34** evaluations | **Working** | Stored in payload |

`run_daily_worldcup_prediction()` defaults to `world_cup_2026`. PredOps lists European competitions but queue sync requires stored/upcoming fixtures in DB.

---

## 6. Owner Lab / Owner Report Audit

### `/owner/ecse-shadow-lab`

- API supports `league` filter (substring match on shadow row `league`/`tournament` fields).
- Data source: `read_shadow_shortlists()` JSONL + WC shadow replay artifacts — **no European league shadow rows**.
- WC shadow evaluation summary is merged (`load_wc_shadow_evaluation_rows()`).
- **European fixtures do not appear** in practice.

### `scripts/owner_today_10_exact_scores.py`

- `SUPPORTED_API_LEAGUES`: World Cup (1), Bundesliga (78), Premier League (39) only.
- **Not included:** Champions League, Europa League, Conference League.
- `_load_wde()` hardcodes `competition_key="world_cup_2026"`.
- Can discover same-day PL/BL via API-Football even if not in SQLite, but WDE/ECSE will still be missing for those IDs.

### Match Center

- `aggregate_all_competitions()` loads all enabled registry competitions.
- Predictions shown from `worldcup_stored_predictions` per `competition_key`.
- European competitions will show **fixtures from provider schedule cache** but **no stored WDE** unless predictions are generated and stored.

### Result / evaluation summaries

- `worldcup_accuracy_summary` and `worldcup_prediction_evaluations`: **WC only**.

---

## 7. Sample Test

### Upcoming European fixtures

**None available** in SQLite (0 upcoming across all five European keys). Cannot run a meaningful 3-fixture upcoming European sample without live API import (out of scope for this audit).

For contrast, World Cup upcoming (from SQLite):

| fixture_id | competition_key | Teams | kickoff_utc | WDE | ECSE | odds | result | eval | Missing step |
|-----------:|-----------------|-------|-------------|-----|------|------|--------|------|--------------|
| 1562345 | world_cup_2026 | Netherlands vs Morocco | 2026-06-30T01:00 | varies | possible | yes | pending | pending | — |
| 1564789 | world_cup_2026 | Ivory Coast vs Norway | 2026-06-30T17:00 | varies | possible | yes | pending | pending | — |
| 1565177 | world_cup_2026 | France vs Sweden | 2026-06-30T21:00 | varies | possible | yes | pending | pending | — |

### Finished European fixtures (3 samples)

| fixture_id | competition_key | Teams | kickoff_utc | WDE | ECSE | odds | result | eval | Missing step |
|-----------:|-----------------|-------|-------------|-----|------|------|--------|------|--------------|
| 1375863 | bundesliga | SV Elversberg vs 1. FC Heidenheim | 2025-05-26T18:30 | No | No | No | Yes | No | WDE job, ECSE snapshot, odds refresh, evaluation pipeline |
| 1035552 | premier_league | Manchester City vs West Ham | 2024-05-19T15:00 | No | No | Yes | Yes | No | WDE generation/storage, ECSE snapshot, evaluation |
| 19135227 | champions_league | Larne vs Rigas FS | 2024-07-17T19:00 | No | No | Yes | No‡ | No | Result sync to `fixture_results`, WDE, ECSE, evaluation |

‡Fixture `status=FT` in `fixtures` but no row in `fixture_results` — result sync gap for UEFA competitions.

---

## 8. What Works vs What Does Not

### Works (World Cup path)

- Correct `competition_key` on WC fixtures
- ECSE snapshots (8) and evaluations (3) for WC
- WDE stored predictions (48) and evaluations (34)
- Automated WC result sync and ECSE evaluation loop
- Owner shadow lab and today report for WC
- Match Center multi-competition schedule **loading**

### Does not work (European path)

- Live ECSE snapshots/evaluations for European competitions
- ECSE result sync for European competitions (explicitly blocked)
- WDE daily automation for European competitions
- European upcoming fixture feed in SQLite (blocks all T-60 / discovery)
- UEFA cup `fixture_results` population
- Sportmonks enrichment beyond WC (league 732)
- Owner shadow lab European rows
- Champions/Europa/Conference in owner today API league list

---

## Root Causes (Prioritized)

1. **Pipeline wiring defaults to World Cup** — `SUPPORTED_ECSE_COMPETITIONS`, scheduler result sync, daily WDE job, owner WDE loader, evaluation tables.
2. **Stale / historical SQLite fixtures** — no upcoming European matches; seasons not advanced to 2025/26.
3. **UEFA result sync gap** — fixtures marked FT but `fixture_results` empty for UCL/UEL/UECL.
4. **Sportmonks scope** — production enrichment hard-guarded to WC; European provider features not ingested live.
5. **Residual metadata issues** — `competition_type` default `world_cup_finals` on league rows; `historical_loader` conference naming edge case.
6. **No `euro_club_tournaments` umbrella key** — must filter three separate keys.

---

## Recommended Fix Phases (Report Only — Not Implemented)

### Phase A — Data import (prerequisite)

- Run league fixture import/sync for 2025/26 seasons (PL, Bundesliga, UCL, UEL, UECL).
- Populate `league_sync_state`.
- Backfill `fixture_results` for UEFA competitions.
- Refresh odds snapshots for upcoming European fixtures.

### Phase B — Mapping hardening

- Add explicit `conference_league` branch in `_competition_key()`.
- Fix `competition_type` default on league imports (use `league` / `cup` not `world_cup_finals`).
- Extend `SUPPORTED_API_LEAGUES` in owner today script for UCL/UEL/UECL.

### Phase C — Pipeline wiring

- Expand `SUPPORTED_ECSE_COMPETITIONS` to European keys (or derive from enabled registry).
- Parameterize `run_ecse_live_cycle()` result sync per competition (not hardcoded WC).
- Extend `run_daily_worldcup_prediction()` (or parallel job) to iterate `EUROPEAN_LEAGUE_KEYS`.
- Wire owner `_load_wde()` to use fixture’s actual `competition_key`.

### Phase D — Provider expansion (optional, EGIE)

- Remove or relax Sportmonks league-732-only guard where subscription allows.
- Use `egie/uefa_club/config.py` Sportmonks IDs for enrichment backfill.

### Phase E — Owner lab

- Include European ECSE shadow rows once snapshots exist.
- Add competition_key filters aligned with registry keys (not display league strings).

---

## Audit Artifacts

- `artifacts/_european_audit_db.json` — SQLite cross-table counts
- `artifacts/_european_audit_extended.json` — extended table/schema notes
- `artifacts/_sportmonks_european_audit.json` — read-only Sportmonks coverage
- Helper script used: `scripts/_audit_european_coverage_tmp.py` (read-only, may be deleted)

---

## Sign-off

| Question | Answer |
|----------|--------|
| Do European leagues work end-to-end today? | **No** |
| Is the old `international` mapping bug still active in SQLite? | **No** (0 fixtures) |
| Is competition registry correct? | **Yes** for individual leagues |
| Is WC pipeline healthy? | **Yes** (partial ECSE eval catch-up still in progress) |
| Recommended action | **`PARTIAL_COVERAGE_NEED_PIPELINE_WIRING`** (+ data import before live use) |

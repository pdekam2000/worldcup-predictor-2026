# listTodayMatches Production Root Cause

Date: 2026-07-10  
Regression date: 2026-07-10 (Europe/Vienna)

## Symptom

`listTodayMatches` returned **1** fixture (Spain vs Belgium) while forensic API-Football audit showed **216** fixtures for the date.

## Call chain (pre-fix)

```
GET /matches/list
  → app.list_today_matches_route
    → delegation.list_today_matches_broad
      → SQL: fixtures table ONLY (no competition filter, but DB had 1 row)
      → enrich_unified_fixture + listing_status
      → response
```

## Root causes (proven)

| Classification | Applies? | Evidence |
|----------------|----------|----------|
| `LISTING_STILL_DB_ONLY` | **YES** | `list_today_matches_broad` queried local SQLite only |
| `PROVIDER_FALLBACK_NOT_WIRED` | **YES** | No `ApiFootballClient fixtures?date=` in GPT delegation path |
| `REGISTRY_FILTER_STILL_PRESENT` | **NO** for list | List SQL had no registry IN clause — but DB only had registry fixture |
| `CLASSIFICATION_FILTER_TOO_EARLY` | **NO** | All DB rows classified; problem was source emptiness |
| `DATE_FILTER_WRONG` | **NO** | Vienna window correct |
| `TIMEZONE_WINDOW_WRONG` | **NO** | `vienna_day_utc_bounds` verified in forensic audit |
| `SERIALIZATION_DROPS_UNSUPPORTED` | **NO** | Nothing to drop — only 1 source row |
| `CACHE_SOURCE_INCOMPLETE` | **PARTIAL** | API cache existed but list path never read provider layer |

**Primary:** `LISTING_STILL_DB_ONLY` + `PROVIDER_FALLBACK_NOT_WIRED`

## Contrast: discoverTodayMatches (pre-fix)

```
discover_today_matches
  → competition_keys_for_scope (registry only)
  → discover_fixtures_from_db (SQL IN registry)
  → fixture_allowed_for_discovery (drops unsupported/friendlies)
```

Discovery was **registry-filtered DB-only** — conflated listing with prediction eligibility.

## Intended vs actual

| Endpoint | Intended | Actual (pre-fix) |
|----------|----------|------------------|
| `listTodayMatches` | Broad provider+DB visibility | DB-only, 1 row |
| `discoverTodayMatches` | Tier A+B candidates after classification | Registry DB query |

## Fix architecture

New module: `worldcup_predictor/gpt_actions/broad_fixture_discovery.py`

```
API-Football fixtures?date= (cached, single call)
  → parse + Vienna window filter
  → merge with local DB window rows
  → dedupe by fixture_id
  → classify (TRUSTED / TEST_PHASE / FRIENDLY / UNSUPPORTED / ODDS_MISSING)
  → listTodayMatches returns all classified

discoverTodayMatches
  → broad discovery + sync Tier A/B to DB
  → filter fixture_allowed_for_discovery(scope)
  → prediction candidates only
```

Listing and prediction eligibility are now **separate contracts**.

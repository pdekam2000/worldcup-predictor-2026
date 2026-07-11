# Production Drift Semantic Review

**Date:** 2026-07-11  
**Canonical base:** `e16b2bf`  
**Artifacts:** `artifacts/_prod_drift_audit/`

---

## 1. `worldcup_predictor/data_import/european_result_backfill.py`

| Block | Change | Classification |
|-------|--------|----------------|
| `_DateApiCache` key `(league_id, date_part, season)` | Season-aware cache prevents cross-season date collisions during UEFA rescue | **REQUIRED_PROVEN_FIX** |
| `force_refresh` bypass in cache | Allows live provider fetch when stale cache would block rescue | **REQUIRED_PROVEN_FIX** |
| Date fetch via `_safe_get(fixtures, {league, season, from, to})` | API-Football requires season for reliable league+date fixture lists | **REQUIRED_PROVEN_FIX** |
| `resolve_provider_match` passes `season_year` + `force_refresh` to date cache | Aligns date lookups with fixture season context | **REQUIRED_PROVEN_FIX** |
| `date_only` fallback (`fixtures?date=` filtered by league) | Recovers matches when league+date path returns empty (220-target backfill) | **REQUIRED_PROVEN_FIX** |
| Existing `league_season` historical path | Unchanged; retained as secondary resolver | **SAFE_OPERATIONAL_IMPROVEMENT** |
| Resume/checkpoint logic | **Not changed** — lives in production rescue scripts | **RUNTIME_ONLY** |
| Transaction handling | **Not changed** — uses existing `upsert_fixture_result` guards | **DUPLICATE_OF_CANONICAL** |
| Score parsing / terminal status | **Not changed** — existing `_fixture_from_provider_item` + `classify_status` | **DUPLICATE_OF_CANONICAL** |
| Overwrite protection (`skipped_existing` unless `force`) | **Not changed** | **DUPLICATE_OF_CANONICAL** |

**Safety guards preserved:** `MIN_PERSIST_CONFIDENCE`, `skipped_ambiguous`, `skipped_low_confidence`, `require_goals=True`, no `--force` by default.

---

## 2. `worldcup_predictor/database/repository.py`

| Block | Change | Classification |
|-------|--------|----------------|
| `count_fixtures_for_league_season()` alias | Delegates to `count_fixtures_for_competition_season` | **REQUIRED_PROVEN_FIX** |
| Result insert/update behavior | **Not changed** | **DUPLICATE_OF_CANONICAL** |
| Transaction rollback | **Not changed** | **DUPLICATE_OF_CANONICAL** |
| Existing row overwrite | `upsert_fixture_result` still requires finished status + goals; backfill skips existing unless `force` | **DUPLICATE_OF_CANONICAL** |

**Required by:** `league_history_importer.py`, `ui/league_import_center_page.py`, `validate_historical_import.py` — canonical callers already reference the alias name but method was missing.

---

## 3. `worldcup_predictor/ingestion/league_history_importer.py`

| Block | Change | Classification |
|-------|--------|----------------|
| `_resolve_competition` Tier B fallback via `TIER_B_SHADOW_DOMAINS` | Synthesizes `CompetitionConfig` for shadow domains not in `get_competition()` | **REQUIRED_PROVEN_FIX** |
| Result parsing | **Not changed** | **DUPLICATE_OF_CANONICAL** |
| Terminal status handling | **Not changed** | **DUPLICATE_OF_CANONICAL** |
| Duplicate prevention | **Not changed** — importer uses existing repo upserts | **DUPLICATE_OF_CANONICAL** |
| Provider provenance | **Not changed** | **DUPLICATE_OF_CANONICAL** |

**Aligns with:** `domestic_league_control.py` registry wiring (`0666116`) — import path parity for Tier B domains.

---

## Rejected / omitted

| Item | Classification | Action |
|------|----------------|--------|
| Untracked production rescue scripts (`scripts/rescue_*.py`) | **RUNTIME_ONLY** | Not copied into canonical source |
| Untracked reports under production root | **RUNTIME_ONLY** | Not committed |
| `worldcup_predictor/rescue/` module | **EXPERIMENTAL** | Not in drift scope; remains production-local |
| Full-file SCP overwrite | **UNSAFE_OR_UNKNOWN** | Rejected — selective diff applied |

---

## Approval summary

All three tracked drift files contain **only REQUIRED_PROVEN_FIX** and **SAFE_OPERATIONAL_IMPROVEMENT** blocks. No **UNSAFE_OR_UNKNOWN** blocks identified.

**Proceed to canonicalization:** Yes

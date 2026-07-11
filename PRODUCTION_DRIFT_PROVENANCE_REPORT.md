# Production Drift Provenance Report

**Date:** 2026-07-11  
**Canonical base:** `e16b2bf`

---

## Origin summary

| File | Created by | Validated | Executed in production | Referenced by |
|------|------------|-----------|------------------------|---------------|
| `european_result_backfill.py` | UEFA 220-target result rescue (2026-07-11) | `validate_provider_rescue_lightweight.py --before 220` (FT-without-result 220→12) | Yes — 208 results inserted, checkpoint complete | Provider rescue runner + backfill ledger |
| `repository.py` | Same rescue session (AttributeError on missing alias) | `validate_historical_import.py` callers; league import UI | Yes — import/rescue scripts executed | `league_history_importer`, UI, validators |
| `league_history_importer.py` | Tier B import/rescue alignment | Model-only 16/16 PASS; registry fix `0666116` | Yes — Tier B domain resolution during rescue | `TIER_B_SHADOW_DOMAINS` registry |

---

## Per-file provenance

### `european_result_backfill.py`

**Phase:** Provider rescue — UEFA FT-without-result gap (220 targets, batch 2 continuation)

**Why required:**
- Batch 1 repaired 86; batch 2 needed team+date matching for remaining 134
- Stale `fixtures?id=` cache and season-less date queries returned empty pools
- `date_only` fallback proved necessary in production ledger (379 API calls, 208 inserts)

**Evidence:**
- `PRODUCTION_RESULT_BACKFILL_BATCH2_CONFIRMATION_REPORT.md`
- `artifacts/provider_rescue/checkpoint.json` on production (`result_targets_done`: 208)
- Lightweight validation: duplicate fixtures 0, orphan results 0

**Not duplicated elsewhere:** Season-aware `_DateApiCache` and `date_only` fallback are unique to this module.

---

### `repository.py`

**Phase:** Rescue session hotfix when scripts called `count_fixtures_for_league_season`

**Why required:** Canonical renamed method to `count_fixtures_for_competition_season` but callers still use old name.

**Evidence:** Grep shows 4 canonical callers of `count_fixtures_for_league_season`; method was missing at `e16b2bf`.

**Not duplicated elsewhere:** Alias is the minimal backward-compatible bridge.

---

### `league_history_importer.py`

**Phase:** Tier B shadow domain import during rescue / registry alignment

**Why required:** `get_competition()` raises `KeyError` for Tier B domains; importer returned `None` and skipped valid leagues.

**Evidence:**
- `0666116` wired `TIER_B_SHADOW_DOMAINS` in `domestic_league_control.py`
- Production importer needed same registry for rescue imports

**Not duplicated elsewhere:** Fallback is importer-specific; registry is shared.

---

## Unknown / unsafe blocks

**None identified.** All changed blocks are traced to production rescue operations with validation evidence.

**Status:** Proceed — not `CANONICALIZATION_BLOCKED_UNKNOWN_DRIFT`

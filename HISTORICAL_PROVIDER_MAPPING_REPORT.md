# MAP-1 — Historical Provider Mapping Report

**Method:** `MAP-1-v1`  
**Build batch:** `MAP-1-20260629_132135`  
**Generated:** 2026-06-29 13:21:53 UTC  
**Mode:** Read-only local matching (no API calls)

## Summary

- Registry rows scanned: **223,215**
- Mappings written: **1,928**
- Skipped (existing equal/better): **0**
- Unmatched registry rows (all providers): **221,345**
- Ambiguous mappings: **3**

## Provider candidate pools (local)

- **api_football:** 2,161 candidates
- **sportmonks:** 1,588 candidates
- **oddalerts:** 6 candidates

## Mapping coverage

- **api_football**: 356 mappings, avg confidence 0.9558, score-validated 346, ambiguous 0
- **oddalerts**: 3 mappings, avg confidence 0.65, score-validated 0, ambiguous 3
- **sportmonks**: 1,569 mappings, avg confidence 0.9662, score-validated 45, ambiguous 0

- Distinct registry fixtures mapped: **1,870**
- ECSE fixtures with ≥1 mapping: **1,867** (0.8583% of 217,518)

## Match methods

| Method | Count |
|--------|-------|
| exact_datetime_teams | 1,410 |
| prelinked_internal_fixture_id | 242 |
| exact_datetime_fuzzy_teams | 133 |
| fuzzy_date_teams | 104 |
| exact_datetime_teams_score | 36 |
| ambiguous_multiple_candidates | 3 |

## Duplicate / ambiguity checks

- Provider fixture ID reused across registry rows: **10** pairs (sample in JSON)

---

*Staging table `historical_provider_mapping` only. No production prediction changes.*
# Tier B Structured Persistence — Backfill Dry Run

**Generated:** 2026-07-14T08:00:30.405733+00:00
**JSONL path:** `C:\Users\kaman\Desktop\Footbal\data\shadow\tier_b_domestic_predictions.jsonl`

## Classification counts

| Classification | Count |
|---|---:|
| `already_fully_structured` | 6 |
| `partially_structured` | 0 |
| `jsonl_only` | 0 |
| `freeze_only` | 0 |
| `wsp_only` | 0 |
| `ecse_only` | 0 |
| `malformed` | 0 |
| `missing_provenance` | 0 |
| `LEGACY_TIER_B_INCOMPLETE_NOT_BACKFILLED` | 0 |

## Sample fixture IDs

- **already_fully_structured:** [1514244, 1514200, 1514244, 1514200, 1514244]

## Policy

- No automatic broad backfill in Phase 2C
- Only `partially_structured` / `jsonl_only` with pre-kickoff timestamps and complete evidence are backfill candidates
- Mark unsupported: `LEGACY_TIER_B_INCOMPLETE_NOT_BACKFILLED`

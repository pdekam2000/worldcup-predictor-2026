# API-GAP-1 — Final Coverage Report

## Before vs after

| Metric | Before | After | Δ |
|--------|--------|-------|---|
| xg_snapshots rows | 0 | 26 | +26 |
| prematch ft_draw rows | 0 | 0 | +0 |
| oddalerts draw rows | 24 | 24 | +0 |
| ECSE missing ft_draw | 217,518 | 217,518 | +0 |

## ECSE tables (must be unchanged)

- `ecse_training_dataset`: 217,518 → 217,518 **OK**
- `ecse_lambda_features`: 168,233 → 168,233 **OK**
- `ecse_score_distributions`: 10,935,145 → 10,935,145 **OK**
- `ecse_score_distributions_dc`: 10,935,145 → 10,935,145 **OK**

## Harvest summary

```json
{
  "sportmonks": {
    "cache_import": {
      "provider": "sportmonks",
      "cache_files_scanned": 1634,
      "cache_hits": 24,
      "api_calls": 0,
      "xg_snapshots_created": 24,
      "xg_snapshots_skipped_existing": 0,
      "xg_unmapped_cache": 1610,
      "raw_staged": 24,
      "skipped_quota": 0,
      "errors": []
    },
    "api_fetch": {
      "provider": "sportmonks",
      "cache_files_scanned": 0,
      "cache_hits": 0,
      "api_calls": 25,
      "xg_snapshots_created": 2,
      "xg_snapshots_skipped_existing": 0,
      "xg_unmapped_cache": 0,
      "raw_staged": 25,
      "skipped_quota": 1,
      "errors": []
    },
    "xg_snapshots_after": 26
  },
  "oddalerts": {
    "provider": "oddalerts",
    "candidates": 0,
    "api_calls": 0,
    "cache_hits": 0,
    "odds_rows_inserted": 0,
    "odds_rows_skipped_duplicate": 0,
    "draw_rows_found": 0,
    "correct_score_rows_found": 0,
    "raw_staged": 0,
    "provider_no_draw": 0,
    "errors": [
      "oddalerts_not_configured"
    ]
  },
  "api_football": {
    "cache_import": {
      "provider": "api_football",
      "fixtures_targeted": 1842,
      "cache_rows_imported": 1842,
      "api_calls": 0,
      "raw_staged": 1842,
      "enrichment_filled": 391,
      "odds_snapshots_created": 519,
      "skipped_existing": 192,
      "skipped_sportmonks_present": 0,
      "errors": []
    },
    "live_fetch": {
      "provider": "api_football",
      "fixtures_targeted": 0,
      "cache_rows_imported": 0,
      "api_calls": 0,
      "raw_staged": 0,
      "enrichment_filled": 0,
      "odds_snapshots_created": 0,
      "skipped_existing": 0,
      "skipped_sportmonks_present": 0,
      "errors": []
    },
    "statistics_staged_after": 109
  }
}
```
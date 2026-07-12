# Provider Feature Store Design

## Canonical prematch record (shadow)

```json
{
  "fixture_id": "int|string",
  "provider_fixture_ids": {"api_football": 0, "sportmonks": 0, "oddalerts": 0},
  "prediction_cutoff_utc": "ISO-8601",
  "kickoff_utc": "ISO-8601",
  "feature_version": "provider_fusion_v1",
  "source_versions": {"odds_snapshot_id": null, "xg_snapshot_id": null},
  "home_xg_for": null,
  "away_xg_for": null,
  "odds_home": 1.95,
  "implied_home": 0.48,
  "bookmaker_count": 14,
  "market_entropy": 0.92,
  "data_quality": "OK",
  "missingness_mask": {"odds": 1, "xg": 0, "lineup": 0}
}
```

## Requirements (met in shadow path)

- Snapshot-based, timestamped, immutable after freeze
- No provider calls during model execution or backtest
- Cache-first from `odds_snapshots`, CSV staging, enrichment
- Missing values explicit via `missingness_mask`
- No silent zero fill (median imputation logged in experiment config only)
- Feature provenance in `source_versions`

## Storage (shadow only)

- Dataset: `artifacts/provider_feature_fusion/shadow_dataset.parquet`
- Shadow outputs: `artifacts/provider_feature_fusion/shadow_outputs/*.jsonl`
- Isolated table: `provider_feature_fusion_shadow` (separate SQLite artifact DB)

**No production DB migration in this phase.**

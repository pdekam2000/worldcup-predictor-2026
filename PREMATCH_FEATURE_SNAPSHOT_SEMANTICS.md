# Prematch Feature Snapshot Semantics

Required condition: `feature_available_at_utc <= prediction_cutoff_utc < kickoff_utc`

| Field | Semantics |
|-------|-----------|
| feature_available_at_utc | Provider publication or verified enrichment update time |
| fetched_at_utc | Ingest time (always set) |
| prediction_cutoff_utc | Default T-3h before kickoff |
| leakage_status | SAFE_PREMATCH, FUTURE_SNAPSHOT_ONLY, POST_MATCH_ONLY, REJECTED |

Historical rows without defensible availability timestamp remain non-promotable.

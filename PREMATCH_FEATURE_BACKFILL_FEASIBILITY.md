# Prematch Feature Backfill Feasibility

| Family | Classification | Notes |
|--------|----------------|-------|
| xG (SportMonks) | FUTURE_SNAPSHOT_ONLY (WC) / NOT_AVAILABLE (Tier B) | No domestic SM mapping |
| lineup | HISTORICAL_PARTIAL_SAFE | enrichment.updated_at < kickoff |
| injury | FUTURE_SNAPSHOT_ONLY | Live API for upcoming |
| form | HISTORICAL_PREMATCH_SAFE | API-Football team stats with cutoff |
| standings | HISTORICAL_PREMATCH_SAFE | Prior matchday only |
| pressure | LIVE_ONLY | Not for prematch backfill |
| referee | HISTORICAL_PARTIAL_SAFE | OddAlerts CSV where mapped |

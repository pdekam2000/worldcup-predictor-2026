# Prematch Feature Backfill Call Plan

## Staged budgets (pilot)

| Provider | Cap | Usage |
|----------|-----|-------|
| API-Football | 50 | Lineups + injuries for upcoming pilot fixtures |
| SportMonks | 50 | WC xGFixture probes only |

## Dry-run estimate (pilot)

- ~45 fixtures targeted (15 × 3 competitions)
- Stored enrichment: 0 API calls (completed lineup from DB)
- Upcoming: up to 2 calls/fixture (lineups + injuries)
- Cache-first via existing `api_response_cache`

**Approval required before exceeding caps.**

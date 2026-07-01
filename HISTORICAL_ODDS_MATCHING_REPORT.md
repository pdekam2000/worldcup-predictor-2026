# Historical Odds Matching Report (DATA-1C)

**Odds rows linked to registry:** 2063334
**Registry keys set on odds rows:** 2063334

## Matching strategy

1. Registry key = `sha256(match_date | league_normalized | home_norm | away_norm)`
2. One `historical_fixture_registry` row per unique registry key
3. Production `fixtures` table is read-only — links stored as optional `internal_fixture_id`
4. Ambiguous production matches (multiple fixtures same date+teams) are logged, not forced

## Ambiguous / variant sample (first 40)

| Type | Date | League / Teams | Detail |
|------|------|----------------|--------|

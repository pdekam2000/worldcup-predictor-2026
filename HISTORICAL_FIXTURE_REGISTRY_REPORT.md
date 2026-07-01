# Historical Fixture Registry Report (DATA-1C)

**Backup:** `C:\Users\kaman\Desktop\Footbal\data\backups\football_intelligence_pre_data1c_20260629_084258.db`

## Schema reuse audit

- Reused production `fixtures` for optional read-only linking (no inserts).
- Reused `historical_csv_odds_imports` (DATA-1B) — extended with `registry_key` + `registry_fixture_id`.
- Did **not** reuse `oddalerts_fixture_map` (API fixture IDs; CSV uses selection row IDs).
- Created staging `historical_fixture_registry` (one row per unique CSV match identity).

## Registry build

| Metric | Value |
|--------|-------|
| Odds rows total | 2063334 |
| Registry candidates (unique match keys) | 223215 |
| Registry rows inserted | 223215 |
| Registry skipped (duplicate rerun) | 0 |
| Production pre-linked (from DATA-1B) | 242 |
| Production linked (date+teams) | 0 |
| Ambiguous production matches | 0 |
| Duplicate team name flags | 1 |
| Team name spelling variants merged | 0 |

## Errors

- none

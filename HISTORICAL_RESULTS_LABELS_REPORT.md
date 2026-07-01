# Historical Results Labels Report (DATA-1D)

**Backup:** `C:\Users\kaman\Desktop\Footbal\data\backups\football_intelligence_pre_data1d_20260629_090902.db`

## CSV result field audit

- **Fields present:** True
- **Required columns:** Status, Home Goals, Away Goals
- **Optional columns used:** Corners, HT Score, Outcome

## Schema reuse

- Production `fixture_results` — not modified (API-Football fixtures only).
- Staging `historical_fixture_results` — one row per `registry_fixture_id` + source.

## Build results

| Metric | Value |
|--------|-------|
| Registry fixtures | 223215 |
| Odds rows scanned | 2063334 |
| Settled fixtures with labels | 222985 |
| Result rows inserted | 222985 |
| Skipped (duplicate rerun) | 0 |
| Skipped (unsettled) | 71 |
| Skipped (no score) | 158 |
| Skipped (ambiguous tie) | 1 |
| Ambiguous score variants logged | 2 |
| No-result fixtures logged | 229 |

## Settled statuses used

`FT`, `FT_PEN`, `AET`, `AWARDED`

## Derived labels

- `result_1x2` — home / draw / away
- `btts_actual` — both teams scored
- `over_15_actual`, `over_25_actual`, `over_35_actual`
- `corners_total`, `corners_over_85/95/105_actual` (when Corners in CSV)

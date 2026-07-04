# ECSE-RERANK-1 — Odds Freshness Audit

Phase: **ECSE-RERANK-1** | Audit only — no new odds fetched

## Metadata Fields (per prediction)

- `odds_snapshot_at` — from `odds_snapshots.snapshot_at`
- `prediction_generated_at` — from `ecse_prediction_snapshots.generated_at`
- `odds_age_hours` — hours between snapshot and prediction (or now if unknown pred time)
- `odds_source` — parsed from odds payload or `odds_snapshots`
- `stale_odds` — boolean vs threshold
- `freshness_flag` — `FRESH_ODDS` | `STALE_ODDS` | `ODDS_FRESHNESS_UNKNOWN`

## Thresholds Applied

- Knockout: stale if **> 6 hours**
- Normal matches: stale if **> 24 hours**

## Summary

| Flag | Count |
|------|-------|
| STALE_ODDS | 18 |

- Stale odds flagged: **18** / 18
- Unknown freshness: **0** / 18
- Age range (known): 14.28 – 82.09 hours
- Mean age (known): 58.4 hours

## Finding

All **18** World Cup ECSE snapshots in local DB reference odds snapshots classified as **STALE_ODDS**
relative to prediction time (mostly 24–48h+ age). Shadow re-rank marks these as **REQUIRES_FRESH_ODDS**.

## Per-Match

| Match | odds_snapshot_at | prediction_generated_at | age (h) | source | flag |
|-------|------------------|-------------------------|---------|--------|------|
| Argentina vs Cape Verde Islands | 2026-07-03T09:35:45.400157 | 2026-07-01 10:37:18 UTC | 14.29 | live | STALE_ODDS |
| Australia vs Egypt | 2026-07-03T09:35:14.487611 | 2026-07-01 10:37:04 UTC | 14.3 | live | STALE_ODDS |
| Belgium vs Senegal | 2026-07-01T10:35:43.349953 | 2026-06-29 13:56:36 UTC | 61.29 | live | STALE_ODDS |
| Brazil vs Japan | 2026-07-01T03:47:48.553834 | 2026-06-29 13:56:15 UTC | 68.09 | oddalerts_csv_policy | STALE_ODDS |
| Brazil vs Norway | 2026-07-01T10:38:13.534460 | 2026-07-01 10:38:14 UTC | 61.25 | live | STALE_ODDS |
| Canada vs Morocco | 2026-07-01T10:37:47.363958 | 2026-07-01 10:37:47 UTC | 61.26 | live | STALE_ODDS |
| Colombia vs Ghana | 2026-07-01T10:37:34.150704 | 2026-07-01 10:37:34 UTC | 61.26 | live | STALE_ODDS |
| England vs Congo DR | 2026-07-01T10:35:24.474487 | 2026-06-29 13:56:33 UTC | 61.3 | live | STALE_ODDS |
| France vs Sweden | 2026-06-30T16:22:24.723028 | 2026-06-29 13:56:27 UTC | 79.51 | cache | STALE_ODDS |
| Germany vs Paraguay | 2026-07-01T03:47:48.553834 | 2026-06-29 13:56:18 UTC | 68.09 | oddalerts_csv_policy | STALE_ODDS |
| Ivory Coast vs Norway | 2026-06-30T16:22:21.343805 | 2026-06-29 13:56:24 UTC | 79.51 | cache | STALE_ODDS |
| Mexico vs Ecuador | 2026-06-30T13:48:02.583839 | 2026-06-29 13:56:30 UTC | 82.09 | live | STALE_ODDS |
| Netherlands vs Morocco | 2026-06-30T16:22:17.865343 | 2026-06-29 13:56:21 UTC | 79.51 | cache | STALE_ODDS |
| Paraguay vs France | 2026-07-03T09:36:16.430211 | 2026-07-01 10:38:00 UTC | 14.28 | live | STALE_ODDS |
| Portugal vs Croatia | 2026-07-01T10:36:32.156915 | 2026-07-01 10:36:32 UTC | 61.28 | live | STALE_ODDS |
| Spain vs Austria | 2026-07-01T10:36:16.670981 | 2026-07-01 10:36:17 UTC | 61.28 | live | STALE_ODDS |
| Switzerland vs Algeria | 2026-07-01T10:36:49.271947 | 2026-07-01 10:36:49 UTC | 61.27 | live | STALE_ODDS |
| USA vs Bosnia & Herzegovina | 2026-07-01T10:36:00.647384 | 2026-07-01 10:36:01 UTC | 61.29 | live | STALE_ODDS |

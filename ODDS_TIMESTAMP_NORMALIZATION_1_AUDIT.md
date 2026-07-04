# ODDS-TIMESTAMP-NORMALIZATION-1 — Timestamp Format Audit

**Generated on:** Hetzner production (`APP_ENV=production`)  
**Rows scanned (recent):** 1464

## Summary

| Metric | Count |
|--------|------:|
| Legacy parser success | 1145 |
| Legacy parser fail (UNKNOWN risk) | **319** |
| New parser success | **1148** (+3) |
| New parser fail | 316 |

## Root format families

| Format family | Count | Notes |
|---------------|------:|-------|
| iso8601_naive | 1145 | e.g. `2026-07-04T00:58:12.671642` — legacy OK |
| other | 316 | e.g. `sportmonks_wc2026_2026-06-27` — **not a timestamp** |
| space_separated_utc_suffix | **3** | e.g. `2026-07-04 00:55:59 UTC` — **legacy FAIL, new OK** |

## Example raw values

### space_separated_utc_suffix (API-Football daily import)

- `2026-07-04 00:55:59 UTC`
- `2026-07-04 00:56:00 UTC`
- `2026-07-04 00:56:01 UTC`

### iso8601_naive (live/cache writes)

- `2026-07-04T00:58:12.671642`
- `2026-07-04T00:58:11.375950`

### other (Sportmonks label strings — not timestamps)

- `sportmonks_wc2026_2026-06-27`
- `sportmonks_wc2026_2026-06-28`

## Source × format

| Source | Format | Count |
|--------|--------|------:|
| daily_owner_api-football_import | space_separated_utc_suffix | 3 |
| live | iso8601_naive | 620 |
| cache | iso8601_naive | 524 |
| sportmonks | other (non-timestamp) | 316 |

## Fixture 1567310 (Colombia vs Ghana)

| Field | Value |
|-------|-------|
| snapshot_at raw (latest) | `2026-07-04T00:58:12.671642` |
| SQLite type | TEXT |
| source | live |
| format family | iso8601_naive |
| legacy parse | ✅ |
| new parse | ✅ |

**Prior issue (1B):** Earlier audit used `2026-07-04 00:55:59 UTC` rows from API-Football import — legacy `fromisoformat`-only parser returned `None` → `ODDS_FRESHNESS_UNKNOWN`.

**Parser fix:** Central normalizer now parses `space_separated_utc_suffix` and other common formats.

---

Artifact JSON: `artifacts/odds_timestamp/odds_timestamp_normalization_1_audit.json`

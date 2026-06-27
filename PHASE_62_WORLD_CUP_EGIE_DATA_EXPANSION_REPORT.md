# PHASE 62 — World Cup EGIE Data Expansion Report

**Generated:** 2026-06-26 15:40 UTC
**Recommendation:** `NEED_MORE_IMPORTS`

## Scope

- Data expansion only — no model, UI, or public flag changes
- Target competitions: FIFA World Cup 2010, 2014, 2018, 2022, 2026

## Pipeline steps

### sqlite_import

```json
{
  "seasons": [
    2010,
    2014,
    2018,
    2022,
    2026
  ],
  "api_configured": true,
  "fixtures_upserted": 316,
  "results_upserted": 316,
  "odds_saved": 0,
  "per_season": {
    "2010": {
      "imported": 64,
      "upserted": 64,
      "results": 64,
      "odds": 0
    },
    "2014": {
      "imported": 64,
      "upserted": 64,
      "results": 64,
      "odds": 0
    },
    "2018": {
      "imported": 64,
      "upserted": 64,
      "results": 64,
      "odds": 0
    },
    "2022": {
      "imported": 64,
      "upserted": 64,
      "results": 64,
      "odds": 0
    },
    "2026": {
      "imported": 60,
      "upserted": 60,
      "results": 60,
      "odds": 0
    }
  },
  "errors": []
}
```

### goal_event_backfill

```json
{
  "candidates": 78,
  "results_count": 3,
  "api_calls_used": 3,
  "comparison": {
    "reliable_fixtures_before": 632,
    "reliable_fixtures_after": 2049,
    "reliable_delta": 1417,
    "excluded_before": 1181,
    "excluded_after": 76,
    "excluded_delta": -1105,
    "with_goal_before": 503,
    "with_goal_after": 1893,
    "pct_1_30_with_goal_before": 61.23,
    "pct_1_30_with_goal_after": 61.23,
    "pct_31_plus_with_goal_before": 38.77,
    "pct_31_plus_with_goal_after": 38.77,
    "pct_no_goal_before": 20.41,
    "pct_no_goal_after": 7.61,
    "bucket_counts_before": {
      "1-15": 175,
      "16-30": 133,
      "31-45+": 78,
      "46-60": 54,
      "61-75": 31,
      "76-90+": 32,
      "no_goal": 129,
      "data_missing": 0
    },
    "bucket_counts_after": {
      "1-15": 678,
      "16-30": 481,
      "31-45+": 325,
      "46-60": 206,
      "61-75": 110,
      "76-90+": 93,
      "no_goal": 156,
      "data_missing": 0
    }
  }
}
```

### api_football_egie_raw

```json
{
  "status": "ok",
  "saved": 200,
  "skipped": 0,
  "api_calls": 200,
  "errors": []
}
```

### sportmonks_ingest

```json
{
  "status": "ok",
  "saved": 0,
  "cache_hits": 0,
  "api_calls": 24,
  "errors": [
    "19609135:HTTP 401: {'message': 'Invalid token provided'}",
    "19609176:HTTP 401: {'message': 'Invalid token provided'}",
    "19609165:HTTP 401: {'message': 'Invalid token provided'}",
    "19609167:HTTP 401: {'message': 'Invalid token provided'}",
    "19609149:HTTP 401: {'message': 'Invalid token provided'}",
    "19609166:HTTP 401: {'message': 'Invalid token provided'}",
    "19609164:HTTP 401: {'message': 'Invalid token provided'}",
    "19609145:HTTP 401: {'message': 'Invalid token provided'}",
    "19609163:HTTP 401: {'message': 'Invalid token provided'}",
    "19609143:HTTP 401: {'message': 'Invalid token provided'}",
    "19609160:HTTP 401: {'message': 'Invalid token provided'}",
    "19609161:HTTP 401: {'message': 'Invalid token provided'}",
    "19609139:HTTP 401: {'message': 'Invalid token provided'}",
    "19609162:HTTP 401: {'message': 'Invalid token provided'}",
    "19609159:HTTP 401: {'message': 'Invalid token provided'}"
  ]
}
```

### sportmonks_xg_backfill

```json
{
  "status": "error",
  "error": "(psycopg.errors.ConnectionTimeout) connection timeout expired\n(Background on this error at: https://sqlalche.me/e/20/e3q8)"
}
```

### egie_feature_rows

```json
{
  "status": "ok",
  "saved": 0,
  "file_only": 0,
  "errors": 329,
  "attempted": 329,
  "postgres_configured": true
}
```

### survival_rebuild

```json
{
  "survival_rows": 317,
  "survival_path": "data\\egie\\world_cup\\survival_dataset.parquet",
  "team_profiles_path": "data\\egie\\world_cup\\team_timing_profiles.json",
  "confederation_profiles_path": "data\\egie\\world_cup\\confederation_timing_profiles.json",
  "team_count": 67
}
```

## Coverage summary

| Metric | Value | Target |
|--------|-------|--------|
| Total WC fixtures | 329 | 500+ |
| Finished fixtures | 317 | — |
| Goal event coverage | 91.2% | 90.0% |
| xG coverage | 0.0% | 70.0% |
| Lineup coverage | 0.0% | 80.0% |
| Odds coverage | 21.9% | 80.0% |
| Pressure coverage | 7.3% | — |
| Usable EGIE fixtures | 289 | 500+ |

## PostgreSQL EGIE rows

```json
{
  "error": "(psycopg.errors.ConnectionTimeout) connection timeout expired\n(Background on this error at: https://sqlalche.me/e/20/e3q8)"
}
```

## Success criteria

- Fixtures target met: **False**
- xG target met: **False**
- Lineup target met: **False**
- Odds target met: **False**
- Goal event target met: **True**
- All targets met: **False**

## Recommendation

**`NEED_MORE_IMPORTS`**

Continue bulk imports (API-Football historical + Sportmonks xG/pressure) before Phase 61B rerun.

---
*Phase 62 — data only. No model or public rollout changes.*
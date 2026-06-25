# PHASE 31E — HISTORICAL ODDS + TEAM ID BACKFILL

**Mode:** Analyze → Implement → Validate → Report

**No deploy. No threshold changes.**

---

## Executive Summary

| Step | Result |
|------|--------|
| Team ID backfill | **1531** fixtures now have IDs (0 updated this run) |
| Remaining NULL team IDs | home=85, away=85 |
| Cached odds fixtures (usable) | **85** |
| Odds snapshots (unique fixtures) | **85** |
| Enrichment odds_json rows | **72** |
| WC hybrid replay (72 fixtures) | avg conf **36.45**, max **39.2** |
| External API calls | **0** |

Cache-only backfill raised WC hybrid replay confidence from **~28 (31D, no odds)** toward **~36** with real odds — still below production 60 threshold without full historical odds API rebuild.

---

## Step 1 — Team ID Backfill

- Rows scanned: **1616**
- Rows updated: **0**
- Updates by source: `{}`

| Field | Remaining NULLs |
|-------|----------------:|
| home_team_id | 85 |
| away_team_id | 85 |
| league_id | 4 |
| season | 4 |

---

## Step 2 — Historical Odds Inventory

| Source | Count |
|--------|------:|
| Unique fixtures with odds (all sources) | 85 |
| SQLite api_response_cache odds rows | 90 |
| odds_snapshots rows | 986 |
| odds_snapshots unique fixtures | 85 |
| fixture_enrichment odds_json | 72 |
| Disk cache files (odds / non-empty) | 1528 / 68 of 7909 |

_Note: ~1,500 disk odds cache files exist for Bundesliga fixtures but contain **empty payloads** (cached API misses). Only WC/demo fixtures have usable bookmaker data offline._

- Finished fixtures with odds: **4**
- WC fixtures with odds: **72**

### Markets Available (fixtures with odds)

| Market | Fixtures |
|--------|--------:|
| 1x2 | 72 |
| over_under_2_5 | 72 |
| btts | 72 |
| double_chance | 72 |

---

## Step 3 — Cache-Only Odds Backfill

- Fixtures mapped: **85**
- Snapshots created: **0**
- Snapshots skipped (existing): **85**
- enrichment.odds_json updated: **13**
- By source: `{"api_response_cache": 66, "disk_cache": 2, "odds_snapshots": 17}`

---

## Step 4 — WC / Odds Subset Hybrid Replay

### WC fixtures with odds cache

| Metric | Value |
|--------|------:|
| Fixtures replayed | 72 |
| Avg confidence | 36.45 |
| Max confidence | 39.2 |
| Avg DQ | 35.42 |
| No Bet @ 60 | 1.0 |
| Recommend @ 60 | 0.0 |
| Safe/Value/Aggressive @ 60 | `{"safe": 0, "value": 0, "aggressive": 0}` |

**Comparison context:**
- Phase 31B (finished, sparse odds): avg conf ~37.6 on BL sample
- Phase 31D (hybrid, no odds): avg conf ~28.1 on BL sample
- Phase 31E WC subset (72 fixtures, real odds): avg conf **36.45**, max **39.2**

Confidence improved +8.4 vs 31D on odds-enabled fixtures, but still below WDE 60 gate.

### Finished fixtures with backfilled odds (sample up to 100)

| Metric | 31B | 31E hybrid | Delta |
|--------|----:|-----------:|------:|
| Avg confidence | 32.1 | 39.1 | 7.0 |
| Max confidence | 32.2 | 39.2 | 7.0 |
| Avg DQ | 20.0 | 30.0 | 10.0 |
| No Bet @ 60 | 1.0 | 1.0 | 0.0 |
| Recommend @ 60 | 0.0 | 0.0 | 0.0 |

Safe/Value/Aggressive @ 60 (31E): `{"safe": 0, "value": 0, "aggressive": 0}`

---

## Step 5 — API Cost Estimate (odds-only, not executed)

- Assumption: 1 API-Football odds call per fixture (GET /odds?fixture=)

| Scope | Est. API-Football calls |
|-------|------------------------:|
| 100 fixtures | 100 |
| 500 fixtures | 500 |
| 1616 fixtures | 1616 |

---

**STOP — No deploy. No threshold changes.**

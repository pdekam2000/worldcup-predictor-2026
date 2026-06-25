# Production Goal Timing Ingest Audit

**Mode:** Report only — no ingest executed in this audit  
**Generated:** 2026-06-22 (UTC)  
**Server:** Hetzner `91.107.188.229`  
**Production commit:** `a6053cd`  
**Audit script:** `scripts/prod_goal_timing_ingest_audit.py` (read-only, `max_api_event_fetches=0`)

---

## Executive summary

Phase 51D is live, but **Premier League Goal Timing is data-starved on production**:

| Blocker | Impact |
|---------|--------|
| **0% goal-event coverage in SQLite** | Team goal-minute histograms are empty; agents report `limited` / missing history |
| **0 upcoming PL fixtures in SQLite** | `/goal-timing/picks` returns **0 picks** (nothing to predict) |
| **EGIE PostgreSQL has only 25 event fixtures** | Pilot ingest stored raw data, but **none overlap** team histories used by probe fixture `1035553` |
| **SQLite ↔ EGIE gap** | Coverage metrics read SQLite only; EGIE events are not mirrored until per-fixture feature build |

**Picks count:** `0`  
**Primary NO_PICK reason for picks page:** no upcoming fixtures in SQLite  
**Primary quality gap for finished fixtures:** missing `stored_goal_events` and team goal-minute history

---

## 1. Premier League fixtures (SQLite)

| Metric | Count |
|--------|------:|
| Total stored PL fixtures | **380** |
| Finished (`FT` / `AET` / `PEN` / `FINISHED`) | **380** |
| Upcoming (`NS` / `TIMED` / etc., kickoff > now) | **0** |
| Live (`1H` / `2H` / `HT` / etc.) | **0** |

**Season breakdown**

| Season | Status | Count |
|--------|--------|------:|
| 2023 | FT | 380 |

**Kickoff range:** `2023-08-11` → `2024-05-19` (full 2023/24 PL season stored, all completed)

**Interpretation:** Production SQLite holds a **complete finished 2023/24 PL season** but **no current-season (2024/25 or 2025/26) upcoming fixtures**. Goal Timing picks cannot populate until upcoming rows exist.

---

## 2. Goal event coverage

### SQLite (authoritative for coverage API)

| Metric | Count | % |
|--------|------:|--:|
| Finished PL fixtures | 380 | 100% |
| With goal events (`fixture_goal_events`) | **0** | **0.0%** |
| Missing goal events | **380** | 100% |
| With `first_goal_minute` in `fixture_results` | **0** | 0% |

### EGIE PostgreSQL (raw store — from prior pilot, not this audit)

| Resource | Rows |
|----------|-----:|
| Total raw rows | 482 |
| `events` (distinct fixtures) | **25** |
| `fixtures` | 381 |
| `lineups` / `injuries` / `fixture_statistics` | 25 each |
| `standings` | 1 |

**Last ingest run (historical — 102 API calls already spent in pilot):**

- Status: `completed`
- Fixtures processed: 25
- Note: first-25 API list order had **zero overlap** with Sheffield Utd / Tottenham histories and **fixture 1035553 has no EGIE events**

### Fillable without new API calls

| Source | Fixtures fillable |
|--------|------------------:|
| From existing EGIE Postgres (not yet in SQLite) | **0** of 380 missing |
| Would still require API-Football ingest | **380** |

EGIE data does not automatically backfill SQLite `fixture_goal_events`. Feature build can mirror EGIE → SQLite per fixture when events exist in EGIE.

---

## 3. Upcoming picks readiness

| Check | Result |
|-------|--------|
| Upcoming PL fixtures in SQLite | **0** |
| Would publish from upcoming (dry-run, no API) | **0** |
| NO_PICK from upcoming | **0** (no candidates) |
| Live `/api/goal-timing/picks` count | **0** |

### Why picks are empty

`GoalTimingPredictionService.list_today_picks()` calls `list_upcoming_fixtures("premier_league")` on SQLite. With **0 upcoming rows**, the picks list is empty regardless of data quality.

### NO_PICK reasons (when fixtures exist)

From engine rules (`MIN_DATA_QUALITY_FOR_PREDICTION = 0.45`) and dry-run on **40 most recent finished PL fixtures**:

| Reason | Fixtures affected (of 40 sampled) |
|--------|----------------------------------:|
| `missing_stored_goal_events` | 40 |
| `home_no_goal_minute_history` | 40 |
| `away_no_goal_minute_history` | 40 |
| `data_quality_below_threshold` | 0 |
| `api_football_fallback_used` | 0 (audit forbids live API) |

**Published pick gate:** `no_prediction_flag = true` when `data_quality_score < 0.45` OR league not enabled.

**Fixture 1035553 (production API, cached):**

- `data_quality_score`: **0.4286** → `no_prediction_flag: true`
- Explanation cites: missing `stored_goal_events`, no API fallback, no Sportmonks xG sample

**Fresh dry-run probe (no API, same server):** DQ **0.4929** for 1035553 — slightly above threshold, but still **no goal events** and **0 team matches with goal-minute history** from ingested EGIE overlap.

---

## 4. API usage estimate

**Assumptions (EGIE PL ingest, season 2024):**

- Base: 2 calls (standings + fixture list)
- Per finished fixture detail: up to 4 calls (events, lineups, statistics, injuries)
- Duplicates skipped on re-run via `request_fingerprint`

| Batch | Max live API calls |
|-------|-------------------:|
| Fixtures-only (no per-fixture detail) | **2** |
| 10 fixtures with details | **~42** |
| 25 fixtures with details | **~102** |
| 50 fixtures with details | **~202** |
| 100 fixtures with details | **~402** |
| Full missing set (380 fixtures) | **~1,522** |

**Already spent (pilot, not this audit):** 102 calls → 25 fixtures in EGIE.

**Safe first batch recommendation**

| Parameter | Value |
|-----------|-------|
| Batch size | **25 fixtures** (or **10** for minimal spend) |
| Max API calls | **~102** (25) or **~42** (10) |
| Critical fix | **Target late-season / team-relevant fixtures**, not first-N API order |
| Include fixture **1035553** | Yes, for probe validation |

**Do not run:** full 380-fixture ingest (~1,522 calls), Sportmonks ingest, or multi-league ingest.

---

## 5. Data quality

Dry-run sample: **40 most recent finished PL fixtures**, stored data only (`max_api_event_fetches=0`).

| Metric | Value |
|--------|------:|
| Average `data_quality_score` | **0.4929** |
| Median | **0.4929** |
| Min threshold to publish | **0.45** |
| Would publish (DQ ≥ 0.45 only) | **40 / 40** |
| Would NO_PICK (DQ only) | **0 / 40** |

**Best fixtures (DQ):** all sampled at **0.4929** — e.g. Wolves vs Brighton, Everton vs Brentford, Aston Villa vs Chelsea

**Worst fixtures (DQ):** same **0.4929** — includes **Sheffield Utd vs Tottenham (1035553)**

### Common missing manifest fields (all 40/40)

| Field | Missing count |
|-------|-------------:|
| `stored_goal_events` | 40 |
| `api_football_fallback_used` | 40 |
| `sportmonks_xg_in_sample` | 40 |

### What DQ has today (partial credit)

- `stored_fixtures`: true  
- `postgres_historical`: true (fixture rows + team match lists exist)  
- Without goal-minute events, agents (`goal_timing_pattern`, `first_goal_pressure`, etc.) stay **limited**

---

## 6. Current coverage (Goal Timing API)

`GET /api/goal-timing/coverage` (SQLite-based):

| League | Finished | With goal events | Coverage |
|--------|----------|------------------|----------|
| **premier_league** | 380 | 0 | **0.0%** |
| bundesliga | 1,232 | 0 | 0.0% |
| Others | 0 | 0 | n/a |

**Reported gaps:** Low goal-event coverage for PL; no finished matches for most other allowed leagues.

---

## 7. Missing data gaps (prioritized)

1. **SQLite `fixture_goal_events` empty for all 380 PL matches** — blocks goal-minute histograms  
2. **No upcoming PL fixtures in SQLite** — blocks `/goal-timing/picks` entirely  
3. **EGIE events not aligned to team histories** — pilot 25 fixtures are early-season; no overlap with probe teams  
4. **Fixture 1035553 has no events** in SQLite or EGIE  
5. **`first_goal_minute` not backfilled** in `fixture_results`  
6. **Sportmonks xG** — probe-only, not ingested (by design)  
7. **No SQLite sync from EGIE fixture list** for 2025/26 upcoming matches

---

## 8. Recommended safe ingest plan (awaiting approval)

### Phase A — Unblock data quality (finished history)

**Goal:** Populate goal events for team-relevant + probe fixtures.

| Step | Action | API budget |
|------|--------|------------|
| A1 | Targeted EGIE ingest: **1035553** + ~15–20 late-season 2023/24 fixtures for SHU/TOT histories | **~60–80** calls |
| A2 | Optional: extend to **50** strategically selected fixtures (not first-N) | **~100 incremental** |
| A3 | Run feature probe / POST predict on 1035553 to mirror EGIE → SQLite | **0** |

**Success criteria:** `home_with_goal_minutes` > 0, `stored_goal_events: true`, DQ ≥ 0.45, `no_prediction_flag: false` for 1035553.

### Phase B — Unblock picks (upcoming fixtures)

**Goal:** Add upcoming PL fixtures to SQLite.

| Step | Action | API budget |
|------|--------|------------|
| B1 | Ingest **2024 or 2025 season** fixture list (fixtures-only mode: `--fixtures-only`) | **~2** calls |
| B2 | Sync upcoming rows into SQLite `fixtures` table | **0 API** (may need one-off sync — not in EGIE CLI today) |
| B3 | Verify `list_upcoming_fixtures("premier_league")` > 0 | — |

**Note:** EGIE `--fixtures-only` stores raw JSON in PostgreSQL but **does not** insert into SQLite. Phase B may require a small approved sync step.

### Phase C — Deferred

- Full 380-fixture event ingest (~1,522 calls)  
- Sportmonks mass ingest  
- Model retrain  
- Multi-league ingest

---

## 9. Verification checklist (post-ingest, when approved)

```bash
# Coverage
curl -s https://footballpredictor.it.com/api/goal-timing/coverage

# Probe fixture
curl -s -X POST https://footballpredictor.it.com/api/goal-timing/predictions/1035553

# Picks
curl -s https://footballpredictor.it.com/api/goal-timing/picks

# UI
# https://footballpredictor.it.com/goal-timing/picks
# https://footballpredictor.it.com/goal-timing/dashboard
```

---

## 10. Audit constraints observed

- No ingest run during this audit  
- No API quota spent during this audit  
- No code deployed to production (audit script copied to server only)  
- `settings.py` not modified  
- Prior pilot ingest (102 calls, 25 fixtures) reflected in EGIE counts above

---

**Status: STOP — awaiting ingest approval.**

Recommended first approved action: **Phase A1 targeted ingest** (~60–80 API calls) + **Phase B1 fixtures-only for current season** (~2 API calls), then assess picks and DQ before any larger batch.

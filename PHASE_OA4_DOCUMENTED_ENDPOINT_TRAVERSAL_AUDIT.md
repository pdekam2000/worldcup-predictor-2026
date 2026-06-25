# PHASE OA-4 — Documented Endpoint Traversal Audit

**Generated:** 2026-06-23T17:00:15+00:00  
**API calls:** 372  
**Key fingerprint:** `477361cf28af4afe`  
**Mode:** Audit only — no deploy, no production changes

---

## Executive summary

OddAlerts **Advanced** unlocks rich **competition/season metadata** and several **global** endpoint families (bookmakers, markets, player rankings). It does **not** expose measurable **fixture or odds-history rows** for Premier League, Champions League, or Bundesliga through any documented traversal path tested in this phase.

OA-3 zeros were **partially** explained by singular param names (`competition_id` / `season_id` vs Postman’s `competitions` / `seasons`). Retesting with **documented plural params across all 8 seasons per league** still yields **0 matched fixture rows** for PL/CL/BL.

---

## Traversal status summary

| Status | Count |
|--------|------:|
| `endpoint_works_returns_data` | 107 |
| `endpoint_exists_data_empty` | 252 |
| `endpoint_exists_bad_request` | 1 |
| `endpoint_blocked_or_non_json` | 1 |

---

## Seven answers (measured)

### 1. Do documented competition/season endpoints unlock PL/UCL/Bundesliga?

**Metadata: yes. Fixtures: no.**

| Discovery path | PL (423) | CL (51) | BL (477) |
|----------------|----------|---------|----------|
| `competitions/search?query=…` | Works — id 423 | Works — id 51 | Works — id 477 |
| `competitions?country_ids=&include=seasons` | Works (England=45) | Works (Europe=10) | Works (Germany=3) |
| `competitions/{id}?include=seasons` | 8 seasons, e.g. 2023/24 = **4630** (380 played) | 8 seasons | 8 seasons |
| `fixtures/results?seasons={id}` | **0 rows** (all seasons) | **0 rows** | **0 rows** |
| `fixtures/results?competitions={id}` | **0 rows** | **0 rows** | **0 rows** |
| `fixtures/results?competitions={id}&seasons={id}` | **0 rows** | **0 rows** | **0 rows** |
| `fixtures/upcoming` (same param shapes) | **0 rows** | **0 rows** | **0 rows** |
| `value/results?competitions={id}&seasons={id}` | **250 rows returned, 0 match filter** | same | same |

Competition/season traversal **unlocks IDs and season registry** but **does not unlock fixture payloads** for the three target leagues.

### 2. Were OA-3 zero results caused by wrong traversal?

**Partially — but not fully.**

| Factor | OA-3 | OA-4 (documented) | Verdict |
|--------|------|-------------------|---------|
| Param naming | `competition_id`, `season_id` (singular) | `competitions`, `seasons` (plural, Postman) | OA-3 used wrong param names for some calls |
| Season discovery | Limited | Full 8-season sweep per league | OA-4 tested more thoroughly |
| Outcome for PL/CL/BL fixtures | 0 | **Still 0** matched rows | Wrong traversal explains **param mistakes only**; empty data persists with correct params |

**Conclusion:** Wrong traversal was used in OA-3 for param naming, but **retesting with documented endpoints does not change the zero-fixture outcome** for major leagues.

### 3. Are major league season_ids discoverable?

**Yes.**

| League | competition_id | current_season_id | Example season_ids |
|--------|---------------:|------------------:|--------------------|
| Premier League | 423 | 2263973 | 433, 1470, 2747, **4630**, 6484, 667780 |
| Champions League | 51 | 2264045 | 53, 1231, 2465, **4326**, 6204 |
| Bundesliga | 477 | 2305071 | 487, 1480, 2755, **4640**, 6492 |
| La Liga | 419 | 2244302 | (8 seasons) |
| Serie A | 499 | 2224807 | (8 seasons) |

Source: `competitions/search` + `competitions/{id}?include=seasons`  
Artifact: `artifacts/oa4_major_league_season_ids.json`

### 4. Can finished fixtures be retrieved by season_id?

**No — for PL/CL/BL.**

- **40 season × endpoint combinations** per league (8 seasons × 5 fixture param shapes + value pools)
- **max matched finished fixtures:** PL=0, CL=0, BL=0
- `fixtures/results?seasons=4630` (PL 2023/24, 380 played in metadata): **0 rows**
- `value/results` returns 250 rows per call but **0 rows where `competition_id` matches** target league

Artifact: `artifacts/oa4_fixture_discovery_results.json`

### 5. Can odds/history be retrieved for those fixtures?

**Not testable for major leagues** (no fixture IDs discovered).

**World Cup fallback** (competition 1690, fixture 420562876):

| Endpoint | Status | Rows |
|----------|--------|-----:|
| `fixtures/{id}?include=stats,probability,odds,correctScores,h2h` | Works | 1 |
| `odds/history/{id}` | Works | 320 |
| `odds/movement/{id}` | Works | 500 |
| `players/fixture/{id}` | Works | 25 |

Odds history **works when a fixture ID exists**; major-league IDs are **not obtainable** via documented traversal on this token.

Artifact: `artifacts/oa4_odds_history_samples.json`

### 6. Are player stats available for those leagues?

**Partially.**

| Endpoint | PL | CL | BL |
|----------|----|----|-----|
| `players/competition/{id}` | **Works** (10 rows) | Empty (0) | **Works** (10 rows) |
| `players/season/{season_id}` | Empty (0) | Empty (0) | Empty (0) |
| `players/rank?stat=goals_per90&form=last_10&min_apps=5` | **Works** (25 rows) | **Works** (25 rows) | **Works** (25 rows) |

Player-by-competition works for PL/BL; season-scoped player stats return empty; global rank endpoint works.

Artifact: `artifacts/oa4_player_endpoint_samples.json`

### 7. Is OddAlerts Advanced useful for major-league historical backfill?

**No for fixture/odds backfill. Yes for metadata and selective player data.**

| Use case | Verdict |
|----------|---------|
| Discover competition_id + season_id | **Useful** |
| Bulk finished fixtures by season | **Not available** (0 rows) |
| Odds history backfill for PL/CL/BL | **Blocked** (no fixture IDs) |
| Player competition lists | **Partial** (PL/BL yes, CL empty) |
| Per-fixture probability/odds (when ID known) | **Works** (WC proof) |

**Recommendation:** Do not rely on OddAlerts Advanced as a Sportmonks replacement for PL/UCL/BL historical fixture or odds backfill. Retain for niche pools (e.g. World Cup) or when fixture IDs are obtained elsewhere.

---

## Endpoint family matrix (documented Postman groups)

Classification per measured response:

| Endpoint family | Path tested | Classification | Notes |
|-----------------|-------------|----------------|-------|
| **Competitions** | `competitions?country_ids=&include=seasons` | **Works — returns data** | England (45), Germany (3), Europe (10), etc. |
| **Competitions** | `competitions/search?query=…` | **Works — returns data** | All 5 major league searches hit correct IDs |
| **Competitions** | `competitions/{id}?include=seasons` | **Works — returns data** | Full season lists with `played` counts |
| **Fixtures** | `fixtures/results?seasons=` | **Exists — data empty** | 0 rows all PL/CL/BL seasons |
| **Fixtures** | `fixtures/results?competitions=` | **Exists — data empty** | 0 rows |
| **Fixtures** | `fixtures/results?competitions=&seasons=` | **Exists — data empty** | 0 rows (combined filter) |
| **Fixtures** | `fixtures/upcoming` (same shapes) | **Exists — data empty** | 0 matched rows |
| **Value Bets** | `value/results?competitions=&seasons=` | **Works — filter ignored** | 250 rows; 0 match target `competition_id` |
| **Value Bets** | `value/upcoming?competitions=&seasons=` | **Works — filter ignored** | Same pattern |
| **Value Bets** | `value/you` | **Exists — data empty** | No strategies configured |
| **Odds** | `odds/markets` | **Works — returns data** | FT result, BTTS, corners, etc. (array response) |
| **Odds** | `odds/history/{fixture_id}` | **Works — returns data** | WC fallback: 320 rows |
| **Odds** | `odds/movement/{fixture_id}` | **Works — returns data** | WC fallback: 500 rows |
| **Bookmakers** | `bookmakers` | **Works — returns data** | 8 bookmakers (Pinnacle, Bet365, …) |
| **Probability** | `probability/markets` | **Works — returns data** | Market catalogue present |
| **Probability** | `probability/rankings?competitions=&seasons=` | **Exists — data empty** | `Invalid type provided` in body |
| **Players** | `players/competition/{id}` | **Works** (PL/BL) / **empty** (CL) | Per-league variance |
| **Players** | `players/season/{id}` | **Exists — data empty** | 0 rows all tested seasons |
| **Players** | `players/rank` | **Works — returns data** | 25 rows with `competitions` filter |
| **Players** | `players/meta` | **Works — returns data** | Forms/stats metadata |
| **Referees** | `referees?competitions=423` | **Works — returns data** | 50 referee rows |
| **Referees** | `referees/upcoming?competitions=423` | **Exists — data empty** | 0 rows |
| **Stats** | `stats/team?competitions=&seasons=` | **Exists — bad request** | HTTP 400 |
| **Predictions** | `predictions?type=fixture&id=` | **Blocked** | Non-JSON (`OddAlerts Data Engine` HTML) |

---

## OA-3 vs OA-4 comparison

| Dimension | OA-3 | OA-4 documented |
|-----------|------|-----------------|
| API key | Advanced (`477361cf28af4afe`) | Same |
| Fixture params | Singular (`competition_id`, `season_id`) | Plural (`competitions`, `seasons`) |
| Season sweep | Partial | All 8 seasons × 8 endpoint shapes per league |
| Endpoint families | Primarily fixtures + value | Full Postman catalogue (players, odds, probability, referees, stats) |
| PL/CL/BL fixture outcome | 0 | **0** (confirmed) |
| Season ID discovery | Limited | **Complete registry** |

---

## Season registry (measured)

- **premier_league**: competition_id=423, seasons=8, current=2263973
- **champions_league**: competition_id=51, seasons=8, current=2264045
- **bundesliga**: competition_id=477, seasons=8, current=2305071
- **la_liga**: competition_id=419, seasons=8, current=2244302
- **serie_a**: competition_id=499, seasons=8, current=2224807

---

## Artifacts

| File | Contents |
|------|----------|
| `artifacts/oa4_documented_endpoint_traversal.json` | Full traversal log (372 calls) |
| `artifacts/oa4_major_league_season_ids.json` | Competition + season registry |
| `artifacts/oa4_fixture_discovery_results.json` | Per-season fixture endpoint attempts |
| `artifacts/oa4_odds_history_samples.json` | WC fallback odds/fixture samples |
| `artifacts/oa4_player_endpoint_samples.json` | Player endpoint samples per league |
| `artifacts/oa4_doc_raw/` | Raw hit/empty response samples |

---

## Final classification

| Question | Answer |
|----------|--------|
| Endpoint exists but data empty | `fixtures/*`, `players/season/*`, `probability/rankings`, `referees/upcoming`, `value/you` |
| Endpoint blocked | `predictions` (non-JSON/HTML) |
| Endpoint works and returns data | `competitions/*`, `bookmakers`, `odds/markets`, `odds/history/{id}`, `players/competition/{id}`, `players/rank`, `referees` |
| Wrong traversal used earlier | **Yes for param naming**; **no for root cause of empty major-league fixtures** |

---

**STOP — Audit only. No deploy. No production changes.**

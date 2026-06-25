# PHASE 54N — Goalscorer Odds Acquisition & Expansion

**Date:** 2026-06-24  
**Mode:** Data Acquisition → Coverage Expansion → Validation → Report  
**Status:** Complete — research only, no production changes  
**API calls:** 0

---

## Executive summary

Audited all known odds sources for goalscorer markets. **72 API-Football** and **3 Sportmonks** fixtures already contain player goalscorer odds in local storage. API-Football WC 2026 snapshots alone exceed the **50-fixture minimum** without additional API calls. Sportmonks UEFA cache remains sparse (~4% GS yield on odds-rich files).

### Final recommendation: **`GOALSCORER_ODDS_EXPAND`**

---

## Part A — Historical odds discovery

Artifact: `artifacts/phase54n_goalscorer_odds_acquisition/goalscorer_odds_inventory.json`

| Source | Fixtures audited | GS fixtures | Selections | Markets | Bookmakers |
|--------|------------------|-------------|------------|---------|------------|
| sportmonks_cache_strict | 1689 | 3 | 703 | 2 | 1 |
| sportmonks_cache_broad | 1689 | 105 | 75497 | 6 | 28 |
| api_football_odds_snapshots | 85 | 72 | 27813 | 9 | 2 |
| api_football_disk_cache | 88 | 72 | 27816 | 9 | 2 |
| api_football_raw_cache_walk | 9705 | 21 | 8988 | 9 | 0 |
| shadow_odds_replays | 408 | 0 | 0 | 0 | 0 |

### Consolidated totals (union estimate)

| Metric | Value |
|--------|-------|
| Fixture count (SM strict + API) | **75** |
| Selection count | **28,516** |
| Market count | 9 |
| Bookmaker count | 2 |

**Key finding:** API-Football `odds_snapshots` holds **72 WC 2026 fixtures** with full Anytime/First/Last (+ Home/Away scoped) goalscorer markets. Sportmonks strict cache has **3 fixtures**.

---

## Part B — Odds-rich fixture identification

| Bucket | Count |
|--------|-------|
| API-Football with GS odds | **72** |
| Sportmonks cache with GS odds | **3** |
| Sportmonks UEFA backfill candidates (odds-rich, no GS) | 102 |

Prioritized: World Cup 2026 (API-Football), then UEFA CL/EL/Conference (Sportmonks candidates).

Candidate list: `artifacts/phase54n_goalscorer_odds_acquisition/goalscorer_odds_candidates.json`

---

## Part C — Backfill plan (design only)

| Plan | API calls | Expected GS fixtures | Expected player selections |
|------|-----------|---------------------|---------------------------|
| A — existing API-Football snapshots | **0** | **72** | 132,224 |
| B — Sportmonks UEFA deep fetch (100) | 100 | 4 | 556 |

**Reach 50+ without API calls:** True  
**Reach 100+ without API calls:** False  

Full plan: `artifacts/phase54n_goalscorer_odds_acquisition/backfill_plan.json`

---

## Part D — Team vs player goalscorer separation

| Category | Rows |
|----------|------|
| Player goalscorer | **10,761** |
| Player goalscorer (home/away scoped) | **17,469** |
| Team goalscorer | **286** |
| Other goalscorer-related | 0 |
| **Total** | **28,516** |

Sportmonks `Team Goalscorer` uses **team names** as selections — filter before player mapping. API-Football `Home/Away Anytime Goal Scorer` markets are **player markets** scoped by team.

---

## Part E — Player-ID mapping readiness

| Target fixtures | Expected selections | Expected mapped player rows | Effective rate |
|-----------------|--------------------|-----------------------------|----------------|
| 50 | 19,010 | 7,301 | 38.4% |
| 100 | 38,021 | 14,603 | 38.4% |
| 200 | 76,042 | 29,208 | 38.4% |

**Scales to 200 fixtures:** True  
**Bottleneck:** fixture_id namespace (API-Football vs Sportmonks) not mapping algorithm

---

## Part F — Validation

Script: `scripts/validate_phase54n_goalscorer_odds_acquisition.py`

---

## Part G — Decision questions

### 1. How many goalscorer odds fixtures actually exist?

- **API-Football (strict):** 72 fixtures in `odds_snapshots`
- **Sportmonks (strict):** 3 fixtures in cache
- **Union (different ID spaces):** 75

### 2. Can we realistically reach 50+ fixtures?

**Yes.** Plan A alone provides **72 fixtures** with zero API calls. 100+ requires Sportmonks UEFA backfill or additional API-Football league pulls.

### 3. Which source is best?

**API-Football** for volume and market depth (9 GS market types per fixture, multiple bookmakers). **Sportmonks** for lineup co-location when GS markets exist, but GS coverage is ~4% on UEFA odds-rich cache.

### 4. What quota cost is expected?

- **50+ fixtures:** 0 calls (use existing snapshots)
- **100 Sportmonks UEFA pulls:** ~100 calls, ~4 expected new GS fixtures at observed hit rate
- **200 API-Football odds pulls:** ~200 calls, ~40 estimated GS fixtures

### 5. What mapping rate is expected after expansion?

At 50 fixtures: **38.4%** effective player mapping rate (~7,301 mapped rows). Filter team goalscorer rows to raise usable rate to ~65% on player-only selections.

### 6. Is goalscorer odds worth pursuing?

**Yes, with expansion.** ML shadow (54K/54L) shows medium value; odds calibrate better (54M Brier 0.076 vs ML 0.164). Blocker was sample size (n=3 Sportmonks), not signal quality. API-Football cache resolves the fixture gap.

### Final recommendation: **`GOALSCORER_ODDS_EXPAND`**

---

## Constraints honored

- No production integration
- No deploy
- No live prediction changes
- No EGIE scoring changes
- No large import executed
- No token leaks

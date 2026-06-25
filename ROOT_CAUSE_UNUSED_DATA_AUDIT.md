# PHASE 54A — Root Cause Audit: Unused Provider Data

**Mode:** Analysis only — no code, no deploy, no fixes  
**Generated:** 2026-06-23  
**Evidence:** Measured SQLite (`data/football_intelligence.db`), `artifacts/egie_provider_*`, source trace

---

## Measured pipeline state (local DB)

| Metric | Value | Implication |
|--------|------:|-------------|
| PL fixtures | 380 | EGIE backtest cohort |
| PL fixtures with `fixture_goal_events` | **359** (94.5%) | Events **not** the main PL gap |
| `odds_snapshots` total | 1,055 | Raw odds JSON exists |
| PL-aligned `odds_snapshots` | **0** | Odds break at **storage alignment** |
| `sportmonks_fixture_enrichment` PL (league 8) | **0** | Mapping never persisted for PL |
| `sportmonks_fixture_enrichment` WC (league 732) | 24 | WC-only enrichment path |
| `xg_snapshots` | **0** | xG never landed in SQLite |
| API cache `fixtures/events` | 464 entries | Events fetched historically |
| API cache `odds` | 57 entries | Odds fetched for **non-PL** fixture ids |
| API cache `players/topscorers` | 1 entry | Topscorers barely executed |
| EGIE utilization (PL, pre-backfill) | xG 0%, pressure 0%, odds 0%, events **94.47%** | Break is downstream of events for EGIE |

---

## API-FOOTBALL — Per-target pipeline traces

### A) BTTS odds

| Stage | Status |
|-------|--------|
| Provider available | **YES** — `Both Teams Score` bet in standard `odds` bookmaker payloads |
| API request implemented | **YES** — `ApiFootballClient.get_odds()` |
| Request executed | **PARTIAL** — live predict + ~57 cached calls; **0 PL cache hits** |
| Response received | **PARTIAL** — WC/upcoming fixtures yes; PL cohort no aligned snapshots |
| Cached | **PARTIAL** — `api_response_cache` endpoint `odds` (57); not keyed to PL `fixture_id`s |
| Stored in DB | **PARTIAL** — `odds_snapshots` stores **full** JSON (1,055 rows) but **0** join to PL fixtures |
| Parsed | **NO** |
| Feature generated | **NO** (odds path) — BTTS comes from Poisson model |
| Used by model | **PARTIAL** — `extended_markets.compute_btts_probabilities()` uses **λ**, not bookmaker BTTS |

**Root cause (break at Parsed):**

- **File:** `worldcup_predictor/agents/specialists/odds_control_agent.py`
- **Functions:** `_extract_api_sports_bookmaker_rows()`, `_parse_match_winner_implied()`, `_parse_ou25_implied()`
- **Blocker:** `market` parameter is typed `Literal["1x2", "ou25"]` only. No BTTS parser exists. Bookmaker `bets[]` with name `Both Teams Score` is never iterated for implied probabilities.

**Secondary break (Stored for PL):**

- **File:** `worldcup_predictor/egie/backfill/api_football_provider_backfill.py` → `backfill_pl_odds_from_cache()`
- **Artifact:** `pl_fixtures_with_cached_odds: 0`, `pl_odds_snapshot_fixtures: 0`
- **Blocker:** Cached odds keys use **WC/demo fixture ids** (e.g. 1489369–1489376, 900001+), not PL ids (1035037+). Snapshots exist but are **orphaned** from PL EGIE cohort.

**Estimated gain if activated:** +6–12% BTTS calibration (Brier/log-loss)  
**Difficulty:** **LOW** (parse existing snapshots + fix PL odds keying)

---

### B) First Team To Score odds

| Stage | Status |
|-------|--------|
| Provider available | **YES** — `First Team To Score` / team-to-score markets in `odds` payload (plan/bookmaker dependent) |
| API request implemented | **YES** — same `get_odds()` |
| Request executed | **PARTIAL** — same as BTTS |
| Response received | **PARTIAL** |
| Cached | **PARTIAL** |
| Stored in DB | **PARTIAL** — raw in snapshots, 0 PL-aligned |
| Parsed | **NO** |
| Feature generated | **NO** (odds) — FTS from internal model |
| Used by model | **PARTIAL** — `scoring_engine` picks first-goal **team** from strength heuristic; `market_ranking_engine` uses **model** `_first_goal_team_prob()`, not bookmaker FTS |

**Root cause:**

- **File:** `worldcup_predictor/agents/specialists/odds_control_agent.py`
- **Blocker:** No FTS market parser. `_extract_api_sports_bookmaker_rows` never matches `First Team To Score` bet names.

- **File:** `worldcup_predictor/prediction/scoring_engine.py` → `FirstGoalPrediction` construction
- **Blocker:** Team chosen from `home_strength` vs `away_strength`, not odds FTS.

**Estimated gain:** +8–15% first-goal team hit-rate  
**Difficulty:** **LOW–MEDIUM** (parser + wire to scoring / goal-timing agents)

---

### C) Correct Score odds

| Stage | Status |
|-------|--------|
| Provider available | **YES** — `Correct Score` bet matrix in `odds` |
| API request implemented | **YES** |
| Request executed | **PARTIAL** |
| Response received | **PARTIAL** |
| Cached | **PARTIAL** |
| Stored in DB | **PARTIAL** — full JSON in snapshots |
| Parsed | **NO** |
| Feature generated | **NO** (odds) — Poisson score grid only |
| Used by model | **PARTIAL** — `extended_markets._correct_score_rows()` from `scoreline_candidates`, not bookmaker matrix |

**Root cause:**

- **File:** `worldcup_predictor/data_import/api_football_historical_importer.py` → `_parse_odds_payload()`
- **Blocker:** Only `Match Winner` and `Over/Under` 2.5 extracted for CSV import.

- **File:** `worldcup_predictor/prediction/extended_markets.py` → `build_extended_markets()`
- **Blocker:** `correct_scores` built from internal Poisson candidates; never reads `report.odds.bookmakers`.

**Estimated gain:** +7–14% top-3 correct-score hit-rate  
**Difficulty:** **MEDIUM** (matrix normalization across bookmakers)

---

### D) Over/Under lines (0.5, 1.5, 3.5, 4.5)

| Stage | Status |
|-------|--------|
| Provider available | **YES** — multiple `Goals Over/Under` lines per bookmaker |
| API request implemented | **YES** |
| Request executed | **PARTIAL** |
| Response received | **PARTIAL** |
| Cached | **PARTIAL** |
| Stored in DB | **PARTIAL** |
| Parsed | **NO** (except 2.5) |
| Feature generated | **NO** for alt lines |
| Used by model | **PARTIAL** — O/U 2.5 only via `extract_api_sports_ou25_meta` / `extract_over_under_probs` |

**Root cause:**

- **File:** `worldcup_predictor/agents/specialists/odds_control_agent.py` → `_parse_ou25_implied()`
- **Blocker:** Hard-coded labels `"over 2.5"` / `"under 2.5"` only. Lines 0.5/1.5/3.5/4.5 never extracted.

- **File:** `worldcup_predictor/egie/ml1/trainer.py` → `ODDS_FEATURES`
- **Blocker:** Defines `odds_over_25` / `odds_under_25` only; alt-line columns never populated in dataset builder.

**Estimated gain:** +4–8% on non-2.5 goal-range markets  
**Difficulty:** **LOW** (extend parser loop over all O/U bet values)

---

### E) fixtures/events

| Stage | Status |
|-------|--------|
| Provider available | **YES** |
| API request implemented | **YES** — `get_fixture_events()` |
| Request executed | **YES** — 464 cache entries; ingest/backfill/result_refresh paths |
| Response received | **YES** |
| Cached | **YES** — `api_response_cache` + file cache |
| Stored in DB | **YES** — 1,621 goal rows, **359/380 PL** fixtures |
| Parsed | **YES** — `outcomes/event_parser.py` → `parse_api_football_goal_events()` |
| Feature generated | **YES** — `goal_timing/features/aggregates.py` minute distributions |
| Used by model | **PARTIAL** — Goal Timing/Survival **YES**; EGIE provider store **NO** (presence flag only) |

**Root cause (EGIE path only — not a fetch problem):**

- **File:** `worldcup_predictor/egie/provider_features/store.py` → `build()`
- **Blocker:** Events only set `coverage["events"] = bool(ev_row)` — no minute/scorer features engineered into `ProviderFeatureVector`.

- **File:** `worldcup_predictor/egie/provider_features/enrichment.py` → `enrich_agent_outputs()`
- **Blocker:** No branch consumes parsed goal events; strategies B–F never adjust from event history.

**Note:** For **production Goal Timing**, events are **not missing** (94.5% PL coverage). Prior gap-analysis overstated this for PL.

**Estimated gain (EGIE wiring):** +5–8% first-goal team/minute in survival backtest  
**Difficulty:** **MEDIUM** (feature engineering, not new API)

---

### F) fixtures/players

| Stage | Status |
|-------|--------|
| Provider available | **YES** |
| API request implemented | **YES** — `get_fixture_players()` (Phase 53) |
| Request executed | **PARTIAL** — 45 cache entries; only on **live predict** path |
| Response received | **PARTIAL** |
| Cached | **PARTIAL** |
| Stored in DB | **NO** — not in `_RESOURCE_ENDPOINTS` backfill list |
| Parsed | **YES** — `integrations/api_sports_deep_data.py` → `normalize_fixture_players()` |
| Feature generated | **PARTIAL** — `deep_player_rows_for_team()` score hints |
| Used by model | **PARTIAL** — `scorer_candidates.build_first_goal_scorer_candidates()` **if** deep bundle present on report |

**Root cause:**

- **File:** `worldcup_predictor/integrations/api_sports_deep_data.py` → `attach_api_sports_deep_data()`
- **Called from:** `match_intelligence_builder.py` → `build()` (live predict only)
- **Blocker:** Never invoked in EGIE backfill or historical replay. Data lives in `supplemental_sources["api_sports_deep"]` (ephemeral report), not SQLite/EGIE PG.

- **File:** `worldcup_predictor/egie/backfill/api_football_provider_backfill.py` → `_RESOURCE_ENDPOINTS`
- **Blocker:** Tuple lists `events, lineups, fixture_statistics, injuries` only — **`fixtures/players` omitted**.

**Estimated gain:** +12–20% goalscorer top-1  
**Difficulty:** **MEDIUM** (add to backfill + persist)

---

### G) topscorers (`players/topscorers`)

| Stage | Status |
|-------|--------|
| Provider available | **YES** |
| API request implemented | **YES** — `get_top_scorers()` |
| Request executed | **NO** at scale — **1** cache entry |
| Response received | **RARE** |
| Cached | **MINIMAL** |
| Stored in DB | **NO** |
| Parsed | **YES** — `normalize_top_scorers()` when present |
| Feature generated | **PARTIAL** — merged in `deep_player_rows_for_team()` |
| Used by model | **PARTIAL** — scorer candidates only when deep bundle warm |

**Root cause:**

- **File:** `integrations/api_sports_deep_data.py` → `attach_api_sports_deep_data()`
- **Blocker:** Fetched once per **live** intelligence build per league/season TTL 24h; never bulk-fetched for PL 2023/24 backtest cohort.

- **No backfill module** references `get_top_scorers`.

**Estimated gain:** +8–12% goalscorer priors  
**Difficulty:** **LOW** (one call per league/season + cache)

---

### H) squads (`players/squads`)

| Stage | Status |
|-------|--------|
| Provider available | **YES** |
| API request implemented | **YES** — `get_team_squad()` |
| Request executed | **PARTIAL** — 18 cache entries |
| Response received | **PARTIAL** |
| Cached | **PARTIAL** |
| Stored in DB | **NO** |
| Parsed | **YES** — `normalize_squad()` |
| Feature generated | **PARTIAL** — squad depth in deep bundle |
| Used by model | **PARTIAL** — scorer candidates fallback |

**Root cause:** Same as **F** — live-only `attach_api_sports_deep_data()`, no persistence, no backfill.

**Estimated gain:** +3–5% goalscorer depth / injury replacement  
**Difficulty:** **LOW**

---

## SPORTMONKS — Per-target pipeline traces

### A) xG

| Stage | Status |
|-------|--------|
| Provider available | **YES** (plan-dependent `xGFixture` include) |
| API request implemented | **YES** — `sportmonks_enrichment.py` premium group; `sportmonks_xg_extraction.py` |
| Request executed | **NO for PL** — backfill `api_calls_live: 0`, `sportmonks_newly_mapped: 0` |
| Response received | **WC only** (24 enrichment rows); premium often **403** |
| Cached | **PARTIAL** — file cache under `.cache/.../sportmonks/` for WC |
| Stored in DB | **NO** — `xg_snapshots` = 0; EGIE PG `resource_type=xg` = 0 for PL |
| Parsed | **YES** — `parse_sportmonks_xg_match()` / `parse_xg_fields()` |
| Feature generated | **NO for PL** — `EgieProviderFeatureStore.coverage["xg"]` = 0% |
| Used by model | **NO** — `enrich_agent_outputs()` strategy B/E/F calls `_set_xg_pattern()` only when `pf.coverage["xg"]` |

**Root cause chain (three breaks):**

1. **Production guard (live PL predict)**  
   - **File:** `providers/sportmonks_client.py` → `get_fixture_context()` lines 60–68  
   - **Blocker:** `if competition_key != WORLD_CUP_2026_COMPETITION_KEY: return ProviderCallResult(data=None)` — PL requests exit before any API call.

2. **Mapping never persisted (EGIE/backfill)**  
   - **File:** `egie/backfill/sportmonks_pl_lookup.py` → `lookup_premier_league_fixture()`  
   - **Table:** `sportmonks_fixture_enrichment` — **0 rows** with `league_id=8`, `fixture_id_api_football` unset for PL  
   - **Artifact:** `mapping_success_rate_pct: 0.0`, `sportmonks_mapped_count: 0`  
   - **Blocker:** Backfill run recorded `api_calls_live: 0` for 380 targets — lookups never resolved a Sportmonks id (likely `not_configured`, `not_found`, or lookup never reached API). Without `sportmonks_fixture_id`, `extract_fixture_xg_match()` never runs.

3. **Plan entitlement (when fetch attempted)**  
   - **File:** `sportmonks_enrichment.py` → `_fetch_fixture_include_group()` / 403 handling  
   - **Blocker:** `premium_xg_access_denied` — `xGFixture` include blocked on measured plan probe (Phase API-G).

4. **Reader has no rows**  
   - **File:** `egie/provider_features/store.py` → `load_sqlite_xg_payload()` / `load_sportmonks_fixture_raw()`  
   - **Blocker:** Both return `None` for PL fixture ids → `coverage["xg"]` stays false.

**Estimated gain:** +8–15% EGIE strategy separation (B/E/F)  
**Difficulty:** **HIGH** (mapping + plan + persistence)

---

### B) Expected Threat (xThreat)

| Stage | Status |
|-------|--------|
| Provider available | **UNKNOWN on current plan** — `pressure` include exists on **UEFA club** ingest only |
| API request implemented | **NO** in production PL/WC path |
| Request executed | **NO** |
| Response received | **NO** |
| Cached | **NO** (production) |
| Stored in DB | **NO** |
| Parsed | **NO** |
| Feature generated | **NO** |
| Used by model | **NO** |

**Root cause:**

- **File:** `egie/uefa_club/config.py` → `UEFA_FULL_INCLUDES` contains `pressure` (UEFA-only ingest).
- **Production code has no `xThreat` / `expected_threat` parser.** `parse_sportmonks_pressure()` in `egie/provider_features/extractors.py` maps **ball possession** or **xG share** — not Sportmonks Expected Threat metric.
- **File:** `goal_timing/agents/player_goal_threat.py` — internal proxy named `player_goal_threat`, unrelated to provider xThreat.

**Estimated gain:** Unknown until plan + parser validated (+3–7% if available)  
**Difficulty:** **HIGH** (new include + parser + mapping)

---

### C) Pressure metrics

| Stage | Status |
|-------|--------|
| Provider available | **PARTIAL** — possession in `statistics` include; dedicated `pressure` include UEFA-only |
| API request implemented | **PARTIAL** — `parse_sportmonks_pressure()` |
| Request executed | **NO for PL** (same mapping block as xG) |
| Response received | **NO for PL** |
| Cached | **WC only** |
| Stored in DB | **NO** |
| Parsed | **YES** (code exists) |
| Feature generated | **NO** — `coverage["pressure"]` = 0% PL |
| Used by model | **NO** — `enrich_agent_outputs()` strategy C/E/F needs `pf.coverage["pressure"]` |

**Root cause:**

- Same **Sportmonks PL mapping + WC guard** as xG.
- **File:** `egie/provider_features/extractors.py` → `parse_sportmonks_pressure()`
- **Blocker:** Never receives SM raw payload for PL fixtures.

**Estimated gain:** +3–6% first-goal pressure calibration  
**Difficulty:** **HIGH** (coupled to SM mapping)

---

### D) Predictions

| Stage | Status |
|-------|--------|
| Provider available | **YES** (premium include) |
| API request implemented | **YES** — `sportmonks_odds_prediction_engine.py` |
| Request executed | **WC shadow only** |
| Response received | **403** on premium for measured plan |
| Cached | **WC promotion shadow** |
| Stored in DB | **NO for PL** |
| Parsed | **YES** — `normalize_sportmonks_predictions()` |
| Feature generated | **NO in production WDE** — benchmark/shadow only |
| Used by model | **NO** — agents explicitly disclaim override |

**Root cause:**

- **File:** `agents/specialists/xg_intelligence_agent.py` / promotion adapters — shadow path only.
- **File:** `sportmonks_enrichment.py` — `predictions` in `PREMIUM_WORLD_CUP_FIXTURE_INCLUDES`; 403 → `premium_predictions_access_denied`.
- **WC guard** blocks PL live fetch.

**Estimated gain:** +2–5% as benchmark calibration (not primary model)  
**Difficulty:** **HIGH** (plan + policy: reference-only)

---

### E) Odds

| Stage | Status |
|-------|--------|
| Provider available | **YES** (premium `odds` include) |
| API request implemented | **YES** — `normalize_sportmonks_odds()` (1X2 only) |
| Request executed | **NO for PL** |
| Response received | **403 / WC only** |
| Cached | **WC** |
| Stored in DB | **NO PL** |
| Parsed | **PARTIAL** — 1X2 implied only; no BTTS/FTS/score |
| Feature generated | **NO** — `sm_consensus_implied_*` in ML-1 never populated |
| Used by model | **NO** |

**Root cause:**

- Same mapping/plan/guard chain as xG.
- **File:** `intelligence/sportmonks_odds_prediction_engine.py` → `normalize_sportmonks_odds()`
- **Blocker:** Filters to 1X2 markets only (`_1X2_MARKET_HINTS`); supplemental disclaimer keeps API-F primary.

- **File:** `egie/ml1/trainer.py` — `sm_consensus_implied_home` etc. always null in PL parquet.

**Estimated gain:** +5–10% if PL-aligned and multi-market  
**Difficulty:** **HIGH**

---

### F) Fixture statistics

| Stage | Status |
|-------|--------|
| Provider available | **YES** — base `statistics` include |
| API request implemented | **YES** — `sportmonks_consumption.py` → `_parse_statistics()` |
| Request executed | **NO for PL** (no enrichment row) |
| Response received | **WC cache only** |
| Cached | **24 WC rows** in `sportmonks_fixture_enrichment` |
| Stored in DB | **NO PL** |
| Parsed | **YES** — flat `home_*` / `away_*` keys + xG hints |
| Feature generated | **PARTIAL** — `advanced_match_intelligence` on live WC reports only |
| Used by model | **NO for PL EGIE** |

**Root cause:**

- **File:** `providers/sportmonks_client.py` — non-WC competition returns before fetch.
- **File:** `intelligence/provider_utilization/advanced_match_intelligence.py` — reads `supplemental_sources["sportmonks"]` which is empty for PL.

**Note:** API-Football `fixtures/statistics` **does** reach EGIE for ~2.11% of PL fixtures via separate backfill path — different provider, same market features.

**Estimated gain:** +2–4% advanced_stats coverage at scale  
**Difficulty:** **HIGH** (SM mapping) / **MEDIUM** (extend AF stats parser)

---

### G) Player statistics

| Stage | Status |
|-------|--------|
| Provider available | **PARTIAL** — player data nested in `lineups` include, not standalone SM player endpoint in prod |
| API request implemented | **NO** dedicated SM player-stats client for PL/WC prod |
| Request executed | **NO** |
| Response received | **NO** |
| Cached | **NO** |
| Stored in DB | **NO** |
| Parsed | **PARTIAL** — lineup player names/positions in `normalize_sportmonks_fixture()` |
| Feature generated | **NO** — `player_goal_threat` uses team-level proxy |
| Used by model | **NO** player-level SM stats |

**Root cause:**

- **File:** `goal_timing/agents/player_goal_threat.py` line 30  
- **Blocker:** `"Proxy threat from team goal-minute scoring volume (no player-level stats yet)."`

- No `players/` Sportmonks route wired in `sportmonks_provider.py` for production enrichment.

**Estimated gain:** +8–12% goalscorer if SM player xG/goals wired  
**Difficulty:** **HIGH**

---

## SPECIAL INVESTIGATION — Why Sportmonks xG never reaches EGIE

### Mapping table counts (measured)

| Store | PL rows | WC rows | Notes |
|-------|--------:|--------:|-------|
| `fixtures` (PL) | 380 | — | API-Football canonical `fixture_id` |
| `sportmonks_fixture_enrichment` | **0** | 24 | `league_id=8` vs `732` |
| `sportmonks_fixture_enrichment.fixture_id_api_football` | **0** populated for PL | partial WC | Schema supports link; never filled |
| `xg_snapshots` | 0 | 0 | |
| EGIE PG `egie_provider_raw_responses` SM `xg` | 0 PL | — | per mapping audit |
| Backfill `sportmonks_newly_mapped` | 0 | — | `api_calls_live: 0` |

### Fixture matching logic

**Production (live predict):**

```
EnrichmentService._maybe_enrich_sportmonks()
  → SportmonksClient.get_fixture_context(competition_key=fixture.competition_key)
      → IF competition_key != "world_cup_2026": RETURN data=None  ← PL STOPS HERE
      → ELSE resolve_unified_worldcup_fixture_intelligence()
          → SQLite cache by api_fixture_id
          → WC date lookup → GET /fixtures/{sm_id}?include=...xGFixture
```

**EGIE backfill (PL):**

```
run_sportmonks_pl_backfill()
  → for each PL fixture:
      → get_sportmonks_fixture_enrichment_by_api_fixture_id() → NULL
      → lookup_premier_league_fixture(home, away, kickoff_date)
          → GET /fixtures/date/{date}?filters=fixtureLeagues:8
          → _match_fixture_item() team name fuzzy match
      → IF sm_id: extract_fixture_xg_match(allow_non_wc=True)
      → save to EGIE PG + xg_snapshots
```

### Where match fails (ordered by evidence)

| # | Failure mode | Evidence | Effect |
|---|--------------|----------|--------|
| 1 | **WC-only production guard** | `sportmonks_client.py:60-68` | Live PL predictions never call Sportmonks |
| 2 | **Zero PL enrichment rows** | `sm_pl=0`, mapping audit 0% | No cached SM payload for `load_sportmonks_fixture_raw()` |
| 3 | **Backfill lookup produced 0 ids** | `sportmonks_newly_mapped: 0`, `api_calls_live: 0` | Importer ran over 380 targets but no successful lookup/xG fetch (token off, lookup miss, or early exit) |
| 4 | **No write to mapping table on lookup success** | Schema has `fixture_id_api_football` but PL column never set | Even successful lookup may not persist link for reuse |
| 5 | **Premium xG 403** | Phase API-G plan probe `xg_fixture_include=false` | Even with `sm_id`, `xGFixture` include empty/denied |
| 6 | **EGIE reader short-circuit** | `store.py` `load_sqlite_xg_payload` → None; `load_sportmonks_fixture_raw` → None | `coverage["xg"]=False` |
| 7 | **Strategy gate** | `enrich_agent_outputs()` only applies xG when `pf.coverage.get("xg")` | Survival strategies B/E/F identical to A |

### Answer: Why exactly does Sportmonks xG never reach EGIE?

**It is not one bug — it is a chain of four hard stops:**

1. **Architectural:** Production Sportmonks client **refuses non-WC competitions** before any HTTP request.
2. **Operational:** PL **fixture_id ↔ sportmonks_fixture_id** mapping was **never established** (0/380); backfill recorded **zero live API calls** and **zero new mappings**.
3. **Commercial:** Current Sportmonks plan **blocks `xGFixture` include** (403) when fetch is attempted on WC path.
4. **Consumption:** `EgieProviderFeatureStore` only loads xG from SQLite `xg_snapshots` or EGIE PG SM raw — **both empty for PL** — so `enrich_agent_outputs()` never activates strategy B/E/F xG branches.

**IDs do not exist in our DB for PL** — this is not a fuzzy-match failure on stored rows; the **importer never populated the mapping table**. Whether Sportmonks API *would* match Burnley v Man City 2023-08-11 is untested in this environment (`api_calls_live: 0`).

---

## Executive summary

### 1. Top 10 missing data sources (by prediction impact)

| Rank | Data source | Provider | Break stage |
|------|-------------|----------|-------------|
| 1 | PL-aligned odds snapshots (all markets) | API-F | **Stored** (wrong fixture ids) |
| 2 | BTTS / FTS / Correct Score odds parsing | API-F | **Parsed** |
| 3 | Sportmonks xG (`xGFixture`) | Sportmonks | **Request executed** (WC guard + mapping + 403) |
| 4 | `fixtures/players` + topscorers at backfill scale | API-F | **Stored** / **Request executed** |
| 5 | Multi-line O/U odds (≠2.5) | API-F | **Parsed** |
| 6 | Sportmonks PL fixture mapping | Sportmonks | **Stored** |
| 7 | Sportmonks pressure / statistics for PL | Sportmonks | **Request executed** |
| 8 | EGIE event-derived features (minutes/scorers) | API-F | **Feature generated** |
| 9 | Sportmonks odds / predictions (premium) | Sportmonks | **Request executed** + **Parsed** (1X2 only) |
| 10 | Sportmonks player-level statistics | Sportmonks | **API request implemented** |

### 2. Why each is missing (one line each)

1. Odds snapshots keyed to WC/demo ids, not PL `1035037+`.  
2. `odds_control_agent` only implements 1X2 and O/U 2.5 parsers.  
3. PL blocked in `SportmonksClient`; no mapping rows; xG include 403.  
4. `attach_api_sports_deep_data` is live-predict-only; not in EGIE backfill.  
5. `_parse_ou25_implied` hard-limits to 2.5 labels.  
6. `lookup_premier_league_fixture` never persisted 0/380 links; backfill 0 API calls.  
7. Same mapping + WC guard; `parse_sportmonks_pressure` never gets input.  
8. `EgieProviderFeatureStore` flags events but does not engineer them.  
9. Premium 403 + 1X2-only normalizer + shadow-only policy.  
10. No SM player endpoint wired; `player_goal_threat` is team proxy.

### 3. Estimated prediction gain if activated

| Source | Gain estimate |
|--------|---------------|
| PL odds parse (BTTS/FTS/score/O/U) | +15–25% combined across extended markets |
| fixtures/players + topscorers backfill | +12–20% goalscorer |
| Sportmonks xG → EGIE (full chain) | +8–15% survival strategy lift |
| Event features → EGIE agents | +5–8% first-goal |
| Alt O/U lines | +4–8% goal-range |
| SM pressure/statistics | +3–6% first-goal tempo |

### 4. Difficulty

| Item | Difficulty |
|------|------------|
| Parse existing odds JSON (BTTS, FTS, score, alt O/U) | **LOW** |
| PL odds snapshot alignment / cache re-key | **LOW** |
| Topscorers + squads cache/backfill | **LOW** |
| fixtures/players EGIE backfill | **MEDIUM** |
| Event → EGIE feature engineering | **MEDIUM** |
| Sportmonks PL mapping + persistence | **HIGH** |
| Sportmonks premium xG/odds/predictions (plan) | **HIGH** |
| Expected Threat / SM player stats (new parsers) | **HIGH** |

### 5. Recommended implementation order

1. **Parse `odds_snapshots` payload** for BTTS, FTS, correct score, O/U 0.5–4.5 (no new API).  
2. **Re-key / backfill PL `odds_snapshots`** from `api_response_cache` using correct `fixture_id`.  
3. **Bulk cache `players/topscorers`** per league/season + add `fixtures/players` to EGIE backfill resources.  
4. **Engineer event-derived features** into `ProviderFeatureVector` (data already 94.5% present for PL).  
5. **Run and persist `lookup_premier_league_fixture`** for all 380 PL fixtures; write `sportmonks_fixture_enrichment.fixture_id_api_football`.  
6. **Re-probe Sportmonks plan** for `xGFixture` / `odds` / `predictions` includes after mapping.  
7. **Remove or gate WC-only guard** for EGIE/backfill paths only (not live WDE without approval).  
8. **Sportmonks player stats / xThreat** — only after plan audit defines available includes.

---

## Key file index (breakpoints)

| File | Role |
|------|------|
| `agents/specialists/odds_control_agent.py` | Odds parsing stops at 1X2 + O2.5 |
| `data_import/api_football_historical_importer.py` | Historical import same odds limit |
| `integrations/api_sports_deep_data.py` | Player endpoints live-only |
| `egie/backfill/api_football_provider_backfill.py` | Backfill omits players/odds markets |
| `egie/provider_features/store.py` | EGIE reader; xG/pressure/odds empty for PL |
| `egie/provider_features/enrichment.py` | Strategy B–F gates on coverage flags |
| `providers/sportmonks_client.py` | **WC-only hard return** for PL |
| `egie/backfill/sportmonks_pl_lookup.py` | PL mapping logic (never persisted 0/380) |
| `sportmonks_enrichment.py` | Premium includes + 403 handling |
| `goal_timing/agents/player_goal_threat.py` | No player-level provider stats |

---

**STOP — Audit only. No fixes. No deploy.**

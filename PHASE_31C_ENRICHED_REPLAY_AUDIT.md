# PHASE 31C — ENRICHED REPLAY AUDIT

**Mode:** Analyze → Report only  
**Date:** 2026-06-20  
**Reference commits:** `267812e` (production), Phase 31B replay complete

**No code changes. No deploy.**

---

## Executive Summary

| Question | Answer |
|----------|--------|
| Can replay confidence realistically approach production (~50–65)? | **Yes, but only for a subset of fixtures today.** Full 1,616-match parity requires a **historical enrichment rebuild**. |
| Primary confidence gap driver | **Missing pre-match odds** (0% in `fixture_enrichment.odds_json`; ~0.2% finished coverage in `odds_snapshots`) |
| Secondary drivers | Missing H2H / injuries / standings in replay path; NULL `team_id`s; DQ not recomputed after enrichment merge |
| Best near-term path | **Option B — Hybrid replay** using `api_response_cache` + `MatchIntelligenceBuilder` read-only hydration |
| Best long-term path | **Option C — Historical enrichment rebuild** for all finished fixtures |

---

## 1. Production vs Replay Path

### Production path (`POST /api/predict/{id}`)

```
PredictPipeline.run()
├── load_tournament_context()
├── DataCollectorAgent
│   └── SmartPredictionFetcher.build()
│       ├── SQLite local-first (fixture row, fixture_enrichment)
│       └── MatchIntelligenceBuilder.build()
│           ├── API-Football: fixture, injuries, H2H, events, stats, lineups, odds, standings
│           └── attach_api_sports_deep_data (players, squads, predictions)
│       └── EnrichmentService.apply()
│           ├── The Odds API (optional)
│           ├── Weather / Rapid OpenWeather
│           ├── Sportmonks fixture + standings
│           └── Rapid Football Stats / Rapid xG
│       └── apply_sportmonks_consumption (SQLite SM cache)
├── SpecialistOrchestrator (~22 agents)
├── PredictionAgent → ScoringEngine + WeightedDecisionEngine
├── attach_extended_markets / first_goal_v2 / fusion
└── API layer: build_prediction_output → market_ranking_engine
```

### Phase 31B replay path (`sqlite_historical_replay.py`)

```
SQLite fixtures + fixture_results
├── build_form_history() (rolling W/D/L from prior results)
├── build_intelligence_report()  [historical_loader — CSV-style minimal report]
├── _apply_enrichment()  [lineups, statistics, events from fixture_enrichment only]
├── SpecialistOrchestrator (API keys stripped — offline settings)
├── ScoringEngine + WDE (unchanged thresholds)
└── build_prediction_output / market ranking (threshold simulation)
```

**Critical difference:** Replay **does not** run `MatchIntelligenceBuilder`, `SmartPredictionFetcher`, or `EnrichmentService`. It builds a lightweight report and partially patches lineups/stats.

---

## 2. Component Matrix — Production vs Replay

| Component | Used in production? | Used in Phase 31B replay? | Historical data available? |
|-----------|--------------------|---------------------------|---------------------------|
| **Odds** | Yes — API-Football + optional The Odds API; drives scoring (15% weight) + odds specialists | **Partial** — only if `HistoricalMatchRow` CSV odds or `odds_snapshots` parse succeeds | **Very sparse** — see §4 |
| **Market consensus** | Yes — `market_consensus_agent`, `odds_market_agent`, `odds_control_agent` | Agents run but **lack real odds** → partial/unavailable | Same as odds |
| **Standings** | Yes — `MatchIntelligenceBuilder._collect_standings` | **No** | API cache: **1** standings entry; not bulk historical |
| **Form** | Yes — API team stats + schedule context | **Yes** — rolling W/D/L from `fixture_results` chronology | **Yes** — derivable from 1,616 finished results |
| **Lineups** | Yes — API lineups + lineup intelligence agents | **Yes** — `fixture_enrichment.lineups_json` merged | **Yes** — **1,531 / 1,616** (94.7%) |
| **Expected lineups** | Yes — `expected_lineup_agent` (may call API pre-kickoff) | Agent runs offline; uses projected/heuristic paths | No historical expected-lineup store at kickoff |
| **Injuries** | Yes — API `get_injuries` (needs `league_id`) | **No** — marked missing in `historical_loader` | API cache: **141** injury rows (mostly recent WC); **0** in enrichment |
| **H2H** | Yes — API `get_head_to_head` (needs team IDs) | **No** — empty H2H; scoring default **45** | API cache: **23** H2H entries; team IDs **NULL** on all 1,616 finished fixtures |
| **Sportmonks enrichment** | Yes — live fixture + standings + xG/predictions when configured | **No** | SQLite: **2** rows total |
| **Specialist agents** | Yes — full orchestrator (~22 agents) | **Yes** — same orchestrator, offline API | Outputs degraded without odds/H2H/injuries |
| **Fixture statistics** | Yes — API + enrichment | **Partial** — `statistics_json` merged | **1,531 / 1,616** (94.7%) |
| **Tournament context** | Yes — `load_tournament_context` + agents | **No** | Not stored historically |
| **Promotion adapters** | Shadow/gated in WDE | Same code path; usually **inactive** without SM/xG signals | N/A |

---

## 3. Confidence Gap Analysis

### Observed values

| Environment | Avg confidence | Typical range | Max observed |
|-------------|---------------|---------------|--------------|
| **Production WC upcoming** (Phase 30F, n=40) | ~27–38* | 16–55 | ~55 |
| **Production WC fixture 1539007** | 51.2 | — | — |
| **Production domestic 1378970** | 61.5 | — | — |
| **Phase 31B replay** (n=1,616) | **37.5** | 23.4–42.6 | **42.6** |

\*WC upcoming batch skews low due to sparse pre-kickoff data; stored history avg ~55 (Phase 30F).

**Gap to close:** ~**8–23 points** to reach production band (50–65).

### Scoring engine contribution model

`ScoringEngine` confidence breakdown weights:

| Factor | Weight | Replay typical score | Production typical score | Δ impact (weight × Δ) |
|--------|-------:|---------------------|-------------------------|----------------------:|
| Form | 0.22 | ~50–58 | ~55–65 | ~0–1.5 |
| H2H | 0.18 | **45** (missing) | 50–70 | **~0.9–2.7** |
| Injuries | 0.15 | **50** (missing) | 55–75 | **~0.8–3.8** |
| Lineups | 0.10 | **80** (94% enriched) | 55–80 | ~0–2.5 |
| **Odds** | **0.15** | **50** (missing) | **60–85** | **~1.5–5.3** |
| Data quality | 0.20 | **40–50** | **55–85** | **~3.0–9.0** |

**Estimated baseline gap from scoring alone:** ~**6–15 points** when odds + DQ are weak.

### WDE / confidence-level caps (amplify gap)

| Mechanism | Production | Replay |
|-----------|------------|--------|
| `quality_pct < 50` → LOW level, confidence capped ~55 | Often **DQ 55+** on live WC | **DQ ~40–50** — LOW level on most replay rows |
| `data_quality < 50` → WDE no-bet + cap | Sometimes bypassed at DQ 55 | Almost always active |
| Odds disagreement / specialist conflict penalties | Odds agents contribute | Odds agents partial → less boost, more noise |
| Promotion confidence deltas | Possible with SM/context | Rarely applied (no SM data) |
| Missing official lineups cap (first goal) | Applies pre-kickoff WC | Similar |

### Specialist layer gap

Without odds snapshots, these agents underperform vs production:

- `odds_market_agent`, `market_consensus_agent`, `odds_control_agent`, `odds_movement_agent`, `sharp_money_intelligence_agent`
- `sportmonks_prediction_agent`, `xg_intelligence_agent` (no historical SM/xG)
- `injury_suspension_*` (no injury lists)
- `tournament_context_agent` (weaker without standings/group context)

**Specialist aggregated score** in production WC ~57; replay specialists run but with degraded inputs → lower WDE confidence tail.

### Root-cause ranking (confidence gap)

| Rank | Cause | Est. contribution to gap |
|------|-------|-------------------------|
| 1 | **No historical odds in replay** | **~40–50%** |
| 2 | **Low / stale data_quality score** (missing fields not recomputed) | **~25–30%** |
| 3 | **Missing H2H + injuries + standings** | **~15–20%** |
| 4 | **NULL team IDs** (blocks H2H/injuries even if cache exists) | **~5–10%** |
| 5 | **No Sportmonks / Rapid / tournament context** | **~5%** |

---

## 4. Historical Availability Inventory

### SQLite (`data/football_intelligence.db`)

| Data type | Finished coverage (n=1,616) | Notes |
|-----------|----------------------------|-------|
| **Fixtures + results** | **100%** | Primary replay anchor |
| **Lineups** (`fixture_enrichment.lineups_json`) | **1,531 (94.7%)** | Usable |
| **Statistics** (`statistics_json`) | **1,531 (94.7%)** | Usable |
| **Events** (`events_json`) | **1,532 (94.8%)** | Usable |
| **Odds JSON** (`odds_json`) | **0 (0%)** | **Not imported during league history ingest** |
| **Odds snapshots** (`odds_snapshots`) | **~4 unique fixtures** | Mostly WC 2026 test fixtures (1489369, 1538999, 1539000, 1489370) |
| **Team IDs** (`home_team_id`, `away_team_id`) | **0 (0%)** | Blocks H2H/injuries hydration |
| **Standings** | **0** dedicated table | 1 row in `api_response_cache` |
| **Injuries** | **0** in enrichment | 141 rows in `api_response_cache` (recent) |
| **Form snapshots** (`team_form_snapshots`) | **0** | Form must be derived from results (already done) |
| **Sportmonks** | **2 rows** | Not scalable |
| **xG snapshots** | **0** | Empty |

### API response cache (`api_response_cache`)

| Endpoint | Rows | Relevance to finished 1,616 |
|----------|-----:|------------------------------|
| `odds` | 141 | **~WC recent only** — not Bundesliga/Premier bulk |
| `injuries` | 141 | Same |
| `fixtures/lineups` | 101 | Partial overlap |
| `fixtures/headtohead` | 23 | Minimal |
| `standings` | 1 | Negligible |
| `predictions` | 141 | API-Football predictions (not SM) |

**League composition of finished fixtures:** predominantly **Bundesliga (1,232)** + **Premier League 2023 (380)** — the API cache is **WC-biased**, not aligned with bulk SQLite history.

### File cache (`.cache/api_football/`)

| Location | Local count | Notes |
|----------|------------|-------|
| `.cache/api_football/` | **~8,984 files** | Mixed endpoints; not indexed to replay pipeline today |
| `.cache/predictions/` | **3 files** | Full API payloads — negligible archive |

### Imports (`league_history_importer`)

Imports **lineups, statistics, events, players** but **odds fetch often fails or is not persisted** to `odds_json` (confirmed 0% odds JSON on finished set).

---

## 5. Replay Upgrade Options

### Option A — Offline replay only (extend 31B)

**Description:** Enhance current replay to read `odds_snapshots`, `api_response_cache`, and disk cache; merge into `MatchIntelligenceReport`; recompute DQ.

| Dimension | Estimate |
|-----------|----------|
| **Effort** | **Low** — 1–2 days |
| **Runtime** | **~15–30 min** for 1,616 fixtures |
| **API calls** | **0** |
| **Fixtures reaching conf ≥50** | **~50–150** (WC cache overlap only) |
| **Accuracy gain** | **Low for bulk history**; modest for WC subset |
| **Ranked-pick eval** | Possible only for cached WC fixtures |

**Verdict:** Quick win for WC-only backtest; **does not fix** Bundesliga/Premier bulk.

---

### Option B — Hybrid replay (recommended next step)

**Description:** Replace `historical_loader` report with **`MatchIntelligenceBuilder` hydration from SQLite + cache only** (no live API). Populate team IDs from enrichment/API cache. Run full `EnrichmentService` when cached SM/odds exist. Recompute `data_quality` after merge.

| Dimension | Estimate |
|-----------|----------|
| **Effort** | **Medium** — 3–5 days |
| **Runtime** | **~25–45 min** replay; cache hydration I/O bound |
| **API calls** | **0** (read-only cache) |
| **Fixtures reaching conf ≥50** | **~150–400** with current cache; **~800+** if team IDs backfilled |
| **Accuracy gain** | **Medium** — closer to production for cached fixtures |
| **Ranked-pick eval** | Feasible for enriched subset |

**Verdict:** Best **cost/benefit** before any paid API import.

---

### Option C — Historical enrichment rebuild

**Description:** Batch import **pre-match** odds, injuries, H2H, standings at kickoff timestamp for all 1,616 fixtures (API-Football historical endpoints or third-party dataset). Persist to `fixture_enrichment` + `odds_snapshots`. Backfill `team_id`s.

| Dimension | Estimate |
|-----------|----------|
| **Effort** | **High** — 1–2 weeks (importer, kickoff-snapshot semantics, DQ recompute, validation) |
| **Runtime** | Import: **hours–days** (quota-limited ~5–8 calls/fixture → **8k–13k calls**) |
| **API calls** | **~8,000–13,000** (one-time) |
| **Fixtures reaching conf ≥50** | **~70–90%** expected |
| **Accuracy gain** | **High** — replay confidence should track production band |
| **Ranked-pick eval** | **Full 1,616 threshold study** becomes valid |

**Verdict:** Required for **definitive** Phase 31 threshold decision on ranked picks.

---

## 6. Comparison Table

| Option | Effort | Runtime | API cost | Conf ≥50 coverage | Ranked pick WR eval |
|--------|--------|---------|----------|-------------------|---------------------|
| **A — Offline extend** | Low | ~20 min | 0 | ~3–10% | WC subset only |
| **B — Hybrid cache** | Medium | ~30 min | 0 | ~10–25% (today) | Partial |
| **C — Enrichment rebuild** | High | Import days + 30 min replay | ~8k–13k calls | ~70–90% | **Full** |

---

## 7. What Data Is Missing (priority order)

To approach production confidence (~50–65) on **all** 1,616 fixtures:

1. **Pre-match odds** (1X2 + O/U) — **critical**; 0% today in enrichment  
2. **Team IDs** on `fixtures` — required for H2H/injuries hydration  
3. **Injuries snapshot at kickoff** — currently absent  
4. **H2H history** — absent in replay; 23 cache rows insufficient  
5. **Standings / league context** — absent for bulk leagues  
6. **Data quality recompute** after enrichment merge — replay under-reports available fields  
7. **Sportmonks / xG** — optional; marginal for confidence vs odds  

---

## 8. Answer — Can Replay Confidence Approach Production?

### Yes — with conditions

| Scenario | Realistic? |
|----------|------------|
| **WC 2026 fixtures** with existing `api_response_cache` odds (141 rows) | **Yes** — expect **48–55** confidence after Option B |
| **Full 1,616 Bundesliga + PL history** with current SQLite | **No** — max **~42.6** observed (Phase 31B) |
| **Full 1,616 after Option C rebuild** | **Yes** — expect **50–62** average, matching production band |

### If yes, what is missing?

**For bulk historical replay:** pre-match **odds** (primary), **team IDs**, **injuries**, **H2H**, **standings**, and **DQ recomputation** after enrichment.

**For WC-only near-term:** wire existing **api_response_cache** + **odds_snapshots** into hybrid builder (Option B) — no new API spend.

---

## 9. Phase 31D / Implementation Recommendation (audit only)

1. **Do not lower WDE thresholds** until Option B or C produces ranked picks with measurable WR.  
2. **Implement Option B first** — hybrid builder + cache hydration + DQ refresh (measurement infrastructure).  
3. **Plan Option C** if threshold decision must cover full 1,616 leagues.  
4. **Re-run Phase 31B** after enrichment upgrade; compare 55 vs 60 on **safe/value pick winrate**.

---

## 10. References

- `PHASE_31A_HISTORICAL_DATA_INVENTORY_AUDIT.md` — data inventory  
- `PHASE_31B_PRECHECK_REPLAY_FEASIBILITY.md` — Option C hybrid design  
- `PHASE_31B_HISTORICAL_REPLAY_BACKTEST_REPORT.md` — replay confidence 37.5, max 42.6  
- `PHASE_30F_NO_BET_RATE_AUDIT.md` — production confidence 51–55 (WC), 61.5 (PL)  
- Code: `predict_pipeline.py`, `smart_prediction_fetch.py`, `match_intelligence_builder.py`, `sqlite_historical_replay.py`

---

*End of Phase 31C audit. No implementation. No deploy.*

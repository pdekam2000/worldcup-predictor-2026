# Phase 31B-Precheck — Historical Replay Feasibility

**Mode:** Analyze only — **no code changes, no deploy.**

**Goal:** Determine whether replaying **~1,616 finished matches** (SQLite `fixtures` + `fixture_results`) is technically feasible.

**Inputs:** Phase 31A inventory, codebase trace of `PredictPipeline` / `BacktestRunner`, local SQLite stats (2026-06-20), runtime micro-benchmark (12-match demo CSV).

---

## Executive Summary

| Question | Answer |
|----------|--------|
| Is 1,616-match replay **technically feasible**? | **Yes** — with the right replay mode |
| Recommended strategy | **OPTION C — Hybrid replay** |
| Offline-only (zero API)? | **PARTIAL** — core pipeline yes; odds/Sportmonks/promotion paths degraded |
| Full live `PredictPipeline` × 1,616? | **Feasible but not recommended** — quota, cost, leakage, runtime |
| Estimated offline runtime (1,616) | **~10–25 minutes** (specialists + WDE + ranking, local CPU) |
| Estimated full-live runtime (1,616) | **~3–8 hours** + multi-day quota spread |
| Estimated API cost (full live) | **~24k+ API-Football requests** (+ Sportmonks/Rapid if enabled) |

**Verdict:** Replay at scale is **feasible and should proceed via Hybrid (Option C)** — build intelligence from SQLite + stored enrichment, run specialists/WDE/market ranking locally, optionally refresh a **small API sample** for calibration. Do **not** run naïve full live `PredictPipeline` on all 1,616 fixtures.

---

## 1. Replay Path Audit (One Finished Fixture)

Reference paths in codebase:

| Path | Entry | Used for 31B? |
|------|-------|---------------|
| **A — Live SaaS** | `POST /api/predict/{id}` → `PredictPipeline` | Production only |
| **B — CSV backtest** | `BacktestRunner` → `build_intelligence_report()` | Demo (12 rows) today |
| **C — Proposed hybrid** | SQLite → `MatchIntelligenceReport` → specialists → WDE → ranking | **Recommended 31B** |

### 1.1 Path A — Full live predict (what SaaS runs today)

For fixture `F` (finished or upcoming), execution order:

```
PredictPipeline.run(fixture_id)
├── load_tournament_context()
├── DataCollectorAgent
│   └── SmartPredictionFetcher.build()
│       ├── local_first: fixtures row + optional fixture_enrichment (SQLite)
│       └── MatchIntelligenceBuilder.build()
│           ├── API-Football: fixture, injuries, H2H, events, stats, lineups, odds, standings
│           ├── attach_api_sports_deep_data (top scorers, players, squads, predictions)
│           └── EnrichmentService.apply()
│               ├── The Odds API (guarded)
│               ├── Weather / Rapid OpenWeather
│               ├── Sportmonks fixture + standings
│               └── Rapid Football Stats / Rapid xG
│           └── apply_sportmonks_consumption (SQLite SM cache if present)
├── SpecialistOrchestrator (22 agents, sequential)
│   ├── Core: weather, referee, lineup, lineup_intelligence, expected_lineup, injuries, form, tactics…
│   ├── Odds: odds_market, odds_control, market_consensus, odds_movement, sharp_money
│   ├── Sportmonks: sportmonks_prediction, xg_intelligence
│   └── MasterAnalysisAgent
├── PredictionAgent
│   └── ScoringEngine.predict(use_weighted_decision=True) → WeightedDecisionEngine
│   └── OpenAI.generate_multilingual_summary() → **returns None** (not implemented)
├── attach_first_goal_v2, attach_extended_markets, apply_fusion_enrichment
└── (API layer only) build_prediction_output → market_ranking_engine → recommended_bets
```

**Cache involvement (live path):**

- `api_response_cache` (SQLite) + `.cache/api_football/` — per-endpoint TTL
- `sportmonks_fixture_enrichment` — SM unified cache
- `quota/prediction_cache_policy` — full API payload cache (`.cache/predictions/`, nearly empty historically)
- `expected_lineup` disk cache
- **Not used:** outcome fields from `fixture_results` (correct — no leakage in live path)

### 1.2 Path B — Existing `BacktestRunner` (CSV / demo)

For one finished row:

```
HistoricalLoader → HistoricalMatchRow
build_form_history() → rolling W/D/L from prior rows in dataset
build_intelligence_report(row) → MatchIntelligenceReport (synthetic stats, CSV odds only)
SpecialistOrchestrator.run() → 22 agents read report from context (**no DataCollector**)
ScoringEngine.predict(use_weighted_decision=True)
```

**Does NOT execute:** DataCollector, EnrichmentService, SmartPredictionFetcher, Market Ranking Engine, API route payload, OpenAI (PredictionAgent skipped).

**May still hit API-Football** if `expected_lineup_agent` / `lineup_intelligence_agent` create `ApiFootballClient` and call `get_fixture_lineups` when lineups empty and `recent_fixtures` present — **hidden API leak in “offline” backtest**.

### 1.3 Path C — Hybrid (recommended, not yet implemented)

For one finished SQLite fixture:

```
fixtures + fixture_results (form only, chronological)
fixture_enrichment (lineups, statistics, events, players)
odds_snapshots (where present)
→ build_intelligence_report_from_sqlite()  [31B new]
→ apply_sportmonks_consumption (only if SM row exists — rare)
→ SpecialistOrchestrator (API disabled or lineups pre-filled)
→ ScoringEngine + WDE
→ build_market_ranking + ranked_to_recommended_bets  [31B new]
→ evaluate vs fixture_results
```

---

## 2. Replay Dependency Matrix

| Component | Required for 31B? | Optional? | Can skip? | Reconstruct from stored data? |
|-----------|-------------------|-----------|-----------|-------------------------------|
| **Data Collector** (`DataCollectorAgent` / `MatchIntelligenceBuilder`) | Intelligence needed | — | **Yes** if SQLite builder used | **PARTIAL** — 1,612/1,616 have `fixture_enrichment`; form from `fixture_results`; odds weak |
| **Specialists** (`SpecialistOrchestrator`, 22 agents) | **Yes** for production-fidelity WDE | — | Can skip (`run_specialists=False`) | **No** — must re-run; inputs from report |
| **WDE** (`WeightedDecisionEngine`) | **Yes** | — | No (core product logic) | Recomputed from report + specialists |
| **Market Ranking Engine** (`market_ranking_engine.py`) | **Yes** for Phase 30C picks | — | Skip loses safe/value/aggressive | Recomputed from `MatchPrediction` + extended markets |
| **Sportmonks enrichment** | No | Yes | **Yes** | **NO** at scale — **1 row** in `sportmonks_fixture_enrichment` |
| **API-Football live fetch** | No | Yes | **Yes** in hybrid | **PARTIAL** — enrichment has lineups/stats for **1,531** finished; **0** odds in enrichment JSON; **~50** fixtures in `odds_snapshots` |
| **OpenAI** | No | Yes | **Yes** | N/A — `generate_multilingual_summary()` unimplemented; **0 calls** today |
| **The Odds API / Rapid / Weather** | No | Yes | **Yes** | Not stored historically |
| **Cache layers** | No | Yes | Bypass in replay mode | `api_response_cache` (1,045 rows) helps only full-live subset |
| **PostgreSQL user history** | No | — | **Yes** | Not useful (16 pending rows) |
| **JSONL prediction history** | No | — | **Yes** | Too small (105 rows); no Phase 30C archive |

---

## 3. Stored Data Coverage (1,616 finished matches)

Local SQLite inventory (matches Phase 31A production/local):

| Store | Finished coverage | Replay utility |
|-------|-------------------|----------------|
| `fixtures` + `fixture_results` | **1,616 / 1,616** | Outcomes, HT scores, O/U labels, chronological form |
| `fixture_enrichment` | **1,612 / 1,616** | Lineups **1,531**, stats **1,531**, odds JSON **0** |
| `odds_snapshots` | **~50** finished joins (~4 with large payload) | Pre-match odds where imported |
| `sportmonks_fixture_enrichment` | **1** total | Not usable at scale |
| `api_response_cache` | 1,045 entries | Spot coverage only |
| Team IDs in `fixtures` | **0 / 1,616** (all NULL) | Blocks H2H/injuries unless resolved from enrichment or competition defaults |

**League composition:** Bundesliga (1,232) + Premier League 2023 (380) + 4 unassigned — **not World Cup-heavy** in SQLite despite WC schedule layer.

---

## 4. API Usage Estimate

Assumptions:

- **Full live:** cold cache, `PredictPipeline` + `MatchIntelligenceBuilder` + deep attach + enrichment providers configured as production.
- **Hybrid:** **0** external calls when intelligence built from SQLite and specialist API clients disabled.
- **OpenAI:** **0** for all paths (stub client).
- API-Football daily soft limit in settings: **7,500** (`API_DAILY_LIVE_LIMIT`).

### 4.1 Per-fixture call budget (full live, cache miss)

| Source | Calls / fixture (typical) |
|--------|---------------------------|
| API-Football core | 9–11 (fixture, injuries, 2× form, H2H, events, stats, lineups, odds, standings*) |
| API-Football deep | 4–6 (players, 2× squads, predictions, top scorers*) |
| Sidelined probe | 0–2 |
| Sportmonks | 1–2 (lookup + fixture) |
| The Odds API / Rapid | 0–4 (guarded / optional) |
| **Total** | **~14–22** live calls |

\*Standings / top scorers amortize across fixtures in same league/season.

### 4.2 Batch estimates

| Batch size | API-Football (full live) | Sportmonks (full live) | OpenAI |
|------------|--------------------------|------------------------|--------|
| **100** | **~1,400–1,800** | **~100–200** | **0** |
| **500** | **~7,000–9,000** | **~500–1,000** | **0** |
| **1,616** | **~22,000–28,000** | **~1,600–3,200** | **0** |

**Quota impact (1,616 full live):**

- API-Football: **~3–4× daily limit** → requires **4+ days** throttling or Pro plan burst + cache warming.
- Sportmonks: plan-dependent; historically **403 on premium** includes — base calls still consume quota.
- Hybrid **1,616:** **0** external calls (recommended default).

### 4.3 Cost (order-of-magnitude)

| Provider | Full live 1,616 | Hybrid 1,616 |
|----------|-----------------|--------------|
| API-Football Pro | Included in subscription quota — **risk is exhaustion**, not marginal $ | **$0** |
| Sportmonks | Token plan — **low $** but low value (1 cached row today) | **$0** |
| OpenAI | **$0** (not called) | **$0** |
| The Odds API / Rapid | Variable credits if enabled | **$0** |

---

## 5. Offline Replay Feasibility

**Answer: PARTIAL**

| Capability | Offline (SQLite only) | Notes |
|------------|----------------------|-------|
| Run 1,616 predictions (1X2, O/U, HT, WDE) | **YES** | Needs new SQLite intelligence builder (not in repo yet) |
| Official lineups in intelligence | **YES** for **~95%** (1,531/1,616) | From `fixture_enrichment.lineups_json` |
| Match statistics | **YES** for **~95%** | Post-match stats in enrichment — acceptable for “match-day” simulation |
| Rolling form | **YES** | Recompute from `fixture_results` ordered by date |
| Historical odds signal | **PARTIAL** | **~3%** of finished matches have `odds_snapshots`; **0** in enrichment odds column |
| H2H / injuries / team IDs | **PARTIAL / NO** | All team IDs NULL; injuries not stored; H2H not archived |
| Sportmonks / xG / SM predictions | **NO** | 1 SM row total |
| Phase 30C market ranking | **YES** | Pure compute once `MatchPrediction` + extended markets built |
| Production byte-identical replay | **NO** | Engine version + data differ from live snapshots |

**Existing `BacktestRunner` alone is insufficient** — it uses CSV-shaped `build_intelligence_report()` without SQLite enrichment (no lineups, synthetic stats). Phase 31B needs a **SQLite-backed builder** extending the hybrid path.

---

## 6. Confidence Quality — Full Live vs Offline

| Dimension | A) Full live replay (today’s pipeline on past IDs) | B) Offline / hybrid replay |
|-----------|-----------------------------------------------------|----------------------------|
| **Data richness** | High if APIs respond; fetches **current** cache state, not time-travel | High for lineups/stats (stored post-import); low for odds |
| **Temporal correctness** | **Risky** — re-fetching finished fixtures today may mix post-match endpoints unless forced pre-match snapshots | **Better** — enrichment captured at import reflects match state |
| **Data quality score** | Typically **55–75** with APIs | **~45–70** without odds; **+10** when odds snapshot exists |
| **Specialist scores** | Full SM/xG if plan allows | SM/xG agents mostly **unavailable** |
| **WDE no-bet rate** | Lower when odds + lineups present | **Higher** without odds (~97% of fixtures) — similar to demo backtest (100% no-bet on sparse CSV) |
| **1X2/O/U accuracy delta (est.)** | Baseline | **−0 to −3 pp** on 1X2 if odds missing; lineups help first-goal/lineup caps |
| **Ranked picks (30C)** | Full ranking when confidence ≥ thresholds | Ranking **empty** more often without odds/consensus |
| **Calibration usefulness** | Good for “current engine + live data shape” | Good for **volume** and lineup/form calibration; weak for odds-consensus tuning |

**Demo backtest evidence** (12 WC rows, Path B today): avg confidence **38.8**, **100% no-bet** — illustrates sparse-input degradation. Hybrid with SQLite lineups should materially improve this vs CSV-only, but **will not match live SaaS** until odds coverage improves.

---

## 7. Runtime Estimate

Micro-benchmark (local, 12 demo CSV matches, Windows):

| Mode | sec / match | 1,616 extrapolation |
|------|-------------|---------------------|
| BacktestRunner + specialists | **~0.35** | **~9.4 min** |
| BacktestRunner, no specialists | **~0.18** | **~4.9 min** |
| Full PredictPipeline (est., cold API) | **~5–30+** | **~2.2–13.5 hours** |
| Hybrid + market ranking (est.) | **~0.4–0.9** | **~11–24 min** |

I/O-bound SQLite replay should stay **under 30 minutes** on a single server core if API calls are disabled.

---

## 8. Recommended Strategy

### **OPTION C — Hybrid replay** (selected)

**Architecture:**

1. **Intelligence:** New `build_intelligence_report_from_sqlite(fixture_id)` reading `fixtures`, `fixture_enrichment`, `odds_snapshots`, rolling form from `fixture_results` (strictly prior matches).
2. **Providers:** Disable live `EnrichmentService` / `SmartPredictionFetcher` for batch mode; set `replay_mode=True` on context to block specialist API clients.
3. **Pipeline:** `SpecialistOrchestrator` → `ScoringEngine` + WDE → `build_market_ranking` (mirror API output).
4. **Evaluation:** Join to `fixture_results` for 1X2, O/U 2.5, HT bucket, optional BTTS from extended markets.
5. **Optional slice:** **100-match stratified live refresh** (API-Football odds + injuries only) to calibrate odds-consensus weight — **~1,500 calls**, fits one day quota.

### Why not Option A (full replay)?

- **~24k+ API-Football calls** — multi-day quota burn.
- **Sportmonks corpus absent** — calls add little value.
- **Not production-identical anyway** (engine drift, no archived payloads).
- **Runtime and failure modes** (rate limits, skips) dominate.

### Why not Option B (offline only)?

- **Odds on ~3%** of fixtures cripples odds agents and market ranking.
- Cannot validate consensus-based picks or odds-disagreement penalties.
- Still **feasible for bulk 1X2/O/U calibration** — use as **Phase 31B default**, enrich odds in **31C**.

---

## 9. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Outcome leakage** via post-match stats in enrichment | Medium | Document as “match-day intelligence”; exclude `fixture_events` if strict pre-match needed |
| **Hidden API calls** in specialist agents | High | `replay_mode` flag + null API client |
| **No historical odds** (97% fixtures) | High | Import odds into SQLite or accept no-bet skew; stratified live odds fetch for 100–200 fixtures |
| **Team IDs all NULL** | Medium | Parse from enrichment lineups or one-time ID backfill |
| **League skew** (BL + PL, not WC) | Medium | Segment metrics by `competition_key` / league_id |
| **Engine ≠ production snapshots** | Medium | Forward capture (Phase 31C) for true prod backtest |
| **Sportmonks promotion paths untestable** | Low | Accept gap; live-only validation |
| **1,616 × specialists CPU** | Low | ~10–25 min; parallelize by league |

---

## 10. Phase 31B Implementation Checklist (future — not in this precheck)

1. `SqliteHistoricalReplayRunner` — iterate finished fixtures chronologically.
2. `build_intelligence_report_from_sqlite()` — enrichment + form + optional odds snapshot.
3. Wire `build_market_ranking` post-WDE (parity with API).
4. `replay_mode` guard on `ExpectedLineupAgent` / `LineupIntelligenceAgent` API usage.
5. Validation script: 10 fixtures golden outputs + full 1,616 metrics report.
6. Exclude demo IDs (`900001+`) and pending PG rows from metrics.

---

## 11. Stop Condition

**Precheck complete. No implementation. No deploy.**

**Feasibility:** **YES** for ~1,616 matches via **Hybrid replay (Option C)** in **~10–25 minutes** with **zero API quota** for the bulk run, accepting **partial odds/Sportmonks fidelity**. Full live replay is technically possible but **quota-prohibitive and low ROI**.

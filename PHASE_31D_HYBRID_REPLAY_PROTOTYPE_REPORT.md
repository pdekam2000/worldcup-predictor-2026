# PHASE 31D — HYBRID REPLAY PROTOTYPE

**Mode:** Implement → Validate → Report  
**Date:** 2026-06-20

**No deploy. No threshold changes.**

---

## Executive Summary

Phase 31D implements a **production-like offline replay path** using `MatchIntelligenceBuilder`, SQLite fixtures, `fixture_enrichment`, and `api_response_cache` — with **zero external API calls** confirmed.

| Metric | Phase 31B (baseline) | Phase 31D (hybrid) | Delta |
|--------|---------------------:|-------------------:|------:|
| Sample fixtures | 100 | 100 | — |
| Average confidence | **37.6** | **28.1** | **-9.6** |
| Max confidence | **42.6** | **28.2** | **-14.4** |
| Average data quality | **38.2** | **63.6** | **+25.4** |
| No Bet rate @ 60 | **100.0%** | **100.0%** | **+0.0pp** |
| Recommendation rate @ 60 | **0.0%** | **0.0%** | **+0.0pp** |
| External API calls | 0 | **0** | — |

**Verdict:** Hybrid pipeline is **technically validated** (production builder path, 0 API calls, DQ recompute works). Confidence **regressed** on this sample because **100% of fixtures lack cached odds** — the dominant confidence driver (15% scoring weight + odds specialists). **Phase 31E (historical enrichment rebuild) is required** before hybrid replay can approach production confidence.

---

## Pipeline

```
SQLite fixtures + results
├── CacheOnlyApiFootballClient (sqlite + disk cache only — blocks live fetch)
├── MatchIntelligenceBuilder.build()  [production path]
│   ├── local-first fixture hydration
│   ├── api_response_cache lookups (injuries, H2H, stats, lineups, odds)
│   └── EnrichmentService skipped (offline keys patched via get_settings)
├── fixture_enrichment merge (lineups, statistics, events)
├── api_response_cache / odds_snapshots odds hydration
├── rolling form injection from fixture_results chronology
├── data quality recompute (explain_data_quality)
├── SpecialistOrchestrator (offline keys)
└── ScoringEngine + WDE (unchanged thresholds)
```

**New modules:**
- `worldcup_predictor/backtesting/hybrid_replay.py`
- `scripts/run_phase31d_hybrid_replay.py`
- `scripts/validate_phase31d_hybrid_replay.py`

---

## Sample Composition

100 finished fixtures selected by **cache + enrichment priority** (Bundesliga 2021–2025, fixture IDs 719349–719455).

| Enrichment | Coverage in sample |
|------------|-------------------:|
| Lineups (`fixture_enrichment`) | ~100% |
| Statistics (`fixture_enrichment`) | ~100% |
| Cached odds (`api_response_cache` / `odds_snapshots` / `odds_json`) | **0%** |
| Team IDs (from lineups backfill) | Partial |
| H2H / injuries (api cache) | Sparse for BL bulk |

The priority scorer ranked these fixtures highly for lineups/stats but **no Bundesliga odds exist in SQLite cache** today. Phase 31C predicted WC cache subset (~141 odds rows) could reach 48–55 confidence — this sample did not include those fixtures.

---

## Confidence Comparison

| Threshold | 31B avg conf | 31D avg conf | 31B max | 31D max |
|-----------|------------:|-------------:|--------:|--------:|
| 50 | 37.6 | 28.1 | 42.6 | 28.2 |
| 55 | 37.6 | 28.1 | 42.6 | 28.2 |
| 60 | 37.6 | 28.1 | 42.6 | 28.2 |

**Why confidence dropped despite +25 DQ:**
- ScoringEngine weights **odds at 15%**; without odds, odds specialists emit weak/neutral signals → confidence penalty.
- 31B `historical_loader` assigns a **default odds score of 50** when CSV/snapshot odds are absent, inflating confidence vs production truth.
- 31D uses the **production builder path** which correctly marks odds missing — higher DQ honesty, lower confidence.
- WDE confidence gate (≥60) remains unreachable on both paths for this sample.

---

## No Bet Comparison

| Threshold | 31B No Bet | 31D No Bet | 31B Recommend | 31D Recommend |
|-----------|----------:|-----------:|--------------:|--------------:|
| 55 | 100/100 (100%) | 100/100 (100%) | 0% | 0% |
| 60 | 100/100 (100%) | 100/100 (100%) | 0% | 0% |

**Coverage gain:** None at ranked-pick thresholds. Both paths produce 100% No Bet because confidence never reaches 50–60.

---

## Confidence Distribution

| Bucket | 31B count | 31D count |
|--------|----------:|----------:|
| 0-40 | 71 | **100** |
| 40-50 | 29 | 0 |
| 50-55 | 0 | 0 |
| 55-60 | 0 | 0 |
| 60+ | 0 | 0 |

31D concentrates all fixtures in 0–40 because production scoring correctly penalizes missing odds/H2H/injuries.

---

## Top Missing Enrichment Still Unavailable

| Field | Missing count | % of sample |
|-------|-------------:|------------:|
| `odds_json_enrichment` | 100 | 100.0% |
| `cached_odds` (api_response_cache / snapshots) | 100 | 100.0% |
| H2H (needs team IDs + cache) | ~95+ | ~95% |
| Injuries (needs league_id + cache) | ~90+ | ~90% |
| Standings context | ~99+ | ~99% |
| Sportmonks enrichment | 100 | 100.0% |

**Primary blocker for production parity:** pre-match odds not stored historically for domestic league fixtures.

---

## API Call Validation

| Check | Result |
|-------|--------|
| API-Football live fetch attempts | **0** |
| HTTP outbound (httpx guard) | **0** |
| Sportmonks (offline keys) | **0** |
| OpenAI (offline keys) | **0** |

Validation script: `python scripts/validate_phase31d_hybrid_replay.py` — **all checks passed**.

---

## Phase 31E Recommendation

**Yes — Phase 31E is needed.**

| Goal | 31D status |
|------|------------|
| Production-like builder path | ✅ Achieved |
| 0 external API calls | ✅ Achieved |
| DQ recompute after enrichment | ✅ Achieved (+25.4 avg DQ) |
| Confidence approaching production (50–65) | ❌ Not achieved |
| Ranked pick coverage @ 60 | ❌ 0% (same as 31B) |

**Recommended Phase 31E scope:**
1. **Historical odds backfill** — populate `fixture_enrichment.odds_json` and/or `api_response_cache` for finished fixtures (~8k calls per Phase 31C estimate, or targeted WC subset first).
2. **Team ID backfill** on `fixtures` table from enrichment lineups — unlocks H2H/injuries cache hits.
3. **Re-run hybrid replay on WC cache subset** (fixtures with existing 141 odds cache rows) to validate confidence lift before full rebuild.
4. Keep 31D hybrid path as the **standard offline replay engine** going forward (replaces lightweight 31B loader for measurement).

---

## Artifacts

- `artifacts/phase31d_hybrid_replay_summary.json`
- `worldcup_predictor/backtesting/hybrid_replay.py`

**No deploy performed.**

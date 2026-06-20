# Phase 22F — Expected Lineups Intelligence

**Status:** Complete (local only — no deployment)  
**Scope:** World Cup 2026 (`world_cup_2026`)  
**Mode:** Trace / benchmark — **no WDE weight changes**, no auto confidence adjustment, no auto no-bet

---

## Objective

Build a dedicated **ExpectedLineupAgent** that projects starting XIs before confirmation, compares against confirmed lineups at kickoff, and stores accuracy history for benchmark calibration.

---

## Components Created

| Component | Role |
|-----------|------|
| `expected_lineup_intelligence_engine.py` | Core expected XI builder + confirmed comparison |
| `expected_lineup_cache.py` | Kickoff-aware aggressive caching (15 min near kickoff) |
| `expected_lineup_store.py` | JSONL accuracy history (expected vs confirmed snapshots) |
| `expected_lineup_agent.py` | Specialist agent (trace-only outputs) |
| `orchestrator.py` | Registers agent after LineupIntelligenceAgent |
| `agents.py` (MasterAnalysis) | Informational trace notes only |

---

## Data Sources Used (Priority Order)

| Priority | Source | Usage |
|----------|--------|-------|
| 1 | **API-Football lineups** | Probable/official XI via `report.lineups` |
| 2 | **API-Football injuries/suspensions** | Absence filtering, missing role counts |
| 3 | **Sportmonks lineups** | Gap-fill when API-Football lineups empty |
| 4 | **Sportmonks sidelined** | Gap-fill injuries via `sportmonks_consumption` |
| 5 | **Historical starting XI** | Previous finished match XI minus injured (API-Football) |

Confirmed lineups: fixture status in live/finished set (`1H`, `2H`, `HT`, `FT`, etc.).

---

## Required Outputs (Implemented)

- `lineup_confidence`, `lineup_strength_delta`
- `expected_goalkeeper_home/away`, `goalkeeper_change_flag`
- `missing_key_players`, `missing_attackers/midfielders/defenders`
- `rotation_risk`, `expected_formation`, `formation_change_risk`
- `expected_xi_quality`, `lineup_supports_internal`

**Advanced:** `star_player_absence_score`, `chemistry_risk`, `continuity_score`, `bench_strength_score`, `late_news_risk`

**Comparison:** expected vs confirmed — `player_overlap_pct`, `surprise_starters`, `missed_expected`

**Stored per run:** prediction timestamp, expected snapshot, confirmed snapshot (when available), accuracy metrics

---

## Lineup Coverage Estimate (World Cup 2026)

| Window | Expected XI coverage | Confirmed XI coverage |
|--------|---------------------|----------------------|
| >4h before kickoff | ~40–55% (historical + injuries) | ~0% |
| 1–4h before kickoff | ~65–80% (API probable + Sportmonks supplement) | ~0% |
| ≤1h / live | ~85–95% expected (cached pre-kickoff) | ~90–98% official |

Coverage assumes API-Football key configured; Sportmonks adds ~5–10% gap-fill on absences/lineups.

---

## Cache Impact

- Cache path: `{api_cache_dir}/lineups/` via `ApiCache`
- Endpoint key: `expected_lineup_intelligence`
- **Far from kickoff (>4h):** TTL 3600s — aggressive reuse, no rebuild
- **Near kickoff (≤4h):** TTL 900s (`LINEUPS_TTL_NEAR_SECONDS`)
- Pre-kickoff expected snapshot preserved for post-confirmation comparison via `reconcile_expected_with_prior()`
- Aligns with existing `should_fetch_lineups()` gate — no lineup API polling when far from kickoff

---

## Quota Impact

| Source | Incremental calls |
|--------|-------------------|
| API-Football lineups (historical XI) | 0–2 per fixture (previous match only, cached upstream) |
| Sportmonks | 0 incremental (reuses Phase 22B unified fixture payload) |
| New dedicated lineup polling | **None** — consumes existing intelligence report |

Estimated incremental quota: **negligible** beyond existing intelligence build.

---

## Database Impact

- **No schema migrations**
- **No destructive changes**
- Accuracy history: append-only JSONL at `data/shadow/expected_lineup_accuracy.jsonl`
- PostgreSQL-compatible JSON document shape for future `expected_lineup_history` table migration
- Reuses existing `fixture_enrichment.lineups_json` column where populated (read-only)

---

## Prediction Impact

- **WDE weights:** unchanged  
- **Confidence:** not auto-adjusted  
- **No-bet rules:** not created  
- **MasterAnalysis:** trace-only notes (late news risk, GK change, overlap %, divergence from Lineup Intelligence V2)  
- Compares against `lineup_intelligence_agent` via `lineup_supports_internal` flag

---

## Files Changed

**New**
- `worldcup_predictor/lineups/expected_lineup_intelligence_engine.py`
- `worldcup_predictor/lineups/expected_lineup_cache.py`
- `worldcup_predictor/lineups/expected_lineup_store.py`
- `worldcup_predictor/agents/specialists/expected_lineup_agent.py`
- `scripts/validate_phase22f_expected_lineups.py`
- `PHASE_22F_EXPECTED_LINEUPS_REPORT.md`

**Modified**
- `worldcup_predictor/lineups/__init__.py`
- `worldcup_predictor/agents/specialists/orchestrator.py`
- `worldcup_predictor/agents/specialists/agents.py`

---

## Validation Results

```bash
python scripts/validate_phase22f_expected_lineups.py
python scripts/validate_phase22e_tournament_context.py
python scripts/validate_phase22d_xg_intelligence.py
```

**Results:** 22F **27/27**, 22E **27/27**, 22D **19/19** passed (offline).

---

## Predictive Value Ranking — World Cup 2026

| Rank | Layer | Reasoning |
|------|-------|-----------|
| **1** | **Combined xG + Context + Expected Lineups** | Full late-stage signal stack: structural match quality (xG), group-stage scenario math (context), and squad truth (lineups). WC knockout and final group matches benefit from all three — lineups resolve rotation/GK volatility, context explains must-win behavior, xG anchors scoreline realism. |
| **2** | **Expected Lineups** | Strongest **single** late-stage signal when available (typically 60–90 min pre-kickoff). Directly observable squad strength beats inferred motivation/xG for short-horizon outcomes. Limited pre-tournament; peaks near kickoff. |
| **3** | **Tournament Context** | Dominates early group-stage permutations and final matchday scenarios where motivation/GD math misprices markets. Less decisive once confirmed XI is known. |
| **4** | **xG Intelligence** | Foundational quality signal but Sportmonks xG add-on is partial pre-match (Phase 22D). Most valuable when lineups stable and context neutral; alone misses rotation/absence shocks. |

**Summary:** For WC 2026, **Expected Lineups** is the highest standalone late-stage edge; **Combined xG + Context + Expected Lineups** is the target benchmark stack before any weight tuning approval.

---

## Stop Boundary

Phase 22F complete. **No weight tuning, calibration, WDE modification, confidence modification, or deployment** — awaiting approval.

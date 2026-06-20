# Phase 22E — Tournament Context + Standings + Form Intelligence

**Status:** Complete (local only — no deployment)  
**Scope:** World Cup 2026 (`world_cup_2026`)  
**Mode:** Trace / benchmark — **no WDE weight changes**, no auto no-bet rules

---

## Objective

Build a dedicated **TournamentContextAgent** that synthesizes group standings, recent form, season statistics, qualification scenarios, goal-difference pressure, and match importance — then compares against the internal **MotivationPsychologyAgent**.

---

## Components Created / Extended

| Component | Role |
|-----------|------|
| `sportmonks_standings_service.py` | Cache-first daily fetch of WC 2026 standings (Sportmonks supplement) |
| `tournament_context_engine.py` | Core intelligence builder + motivation comparison layer |
| `tournament_context_agent.py` | Specialist agent (trace-only outputs) |
| `enrichment_service.py` | Wires standings fetch for WC 2026 into `supplemental_sources` |
| `orchestrator.py` | Registers agent after Motivation + TournamentIntelligence |
| `agents.py` (MasterAnalysis) | Trace notes for must-win, disagreement, draw acceptability |

---

## Endpoints Used

| Provider | Endpoint | Purpose | Frequency |
|----------|----------|---------|-----------|
| **API-Football** (primary) | Standings via existing `match_intelligence_builder._collect_standings()` | Group tables, rank, points, GD, form | Per intelligence build (cached upstream) |
| **Sportmonks** (complement) | `GET /standings/seasons/26618?include=participant;details;form;group;stage;rule` | Supplemental group table + form | **≤1 call / day** (ApiCache, `DAILY_TTL_SECONDS`) |
| **Schedule context** | `fixture_tournament_context()` / placeholder groups | Qualification placeholders when live tables sparse | Local, no API |

No new PostgreSQL tables. Reuses existing `ApiCache` file store under `{api_cache_dir}/sportmonks/`.

---

## Required Outputs (Implemented)

- `group_position` (home/away)
- `points`, `goal_difference`
- `qualification_status`, `qualification_probability`
- `elimination_risk`, `must_win_flag`
- `pressure_rating`, `motivation_score`, `recent_form_score`
- `tournament_importance`, `rotation_risk`, `group_context_strength`

**Advanced:** `expected_conservatism`, `expected_aggression`, `draw_acceptability`, `likely_rotation_behavior`

**Comparison vs MotivationPsychologyAgent:** `agreement_score`, `disagreement_score`, `context_supports_internal`

---

## Cache Impact

- Standings cached at `sportmonks_standings_by_season` with params `{season_id: 26618, league_id: 732}`.
- TTL: daily (`DAILY_TTL_SECONDS` ≥ 86400).
- Cache-first: repeated fixture predictions within the same day reuse cached standings — **no repeated Sportmonks standings API calls**.
- API-Football standings remain primary; Sportmonks only gap-fills when API-Football rows are missing fields.

---

## Quota Impact

| Source | Additional calls per WC match day |
|--------|-----------------------------------|
| Sportmonks standings | **0–1** (one per calendar day across all fixtures) |
| Sportmonks fixture enrichment | Unchanged from 22B–22D |
| API-Football | Unchanged (existing standings path) |

Estimated incremental Sportmonks quota: **~1 request/day** during group stage when configured.

---

## Database Impact

- **No schema migrations.**
- **No destructive changes.**
- Supplemental block stored in-memory on `MatchIntelligenceReport.supplemental_sources` under key `sportmonks_tournament_standings`.
- Compatible with existing SQLite enrichment cache and future PostgreSQL adapter (JSON supplemental fields).

---

## Prediction Impact

- **WDE weights:** unchanged  
- **Confidence:** not auto-increased  
- **No-bet rules:** not created  
- **MasterAnalysis:** informational adjustments only (must-win trace, motivation disagreement, draw acceptability)  
- Agent runs **after** MotivationPsychologyAgent and TournamentIntelligenceAgent so comparison signals are available

---

## Files Changed

**New**
- `worldcup_predictor/intelligence/sportmonks_standings_service.py`
- `worldcup_predictor/intelligence/tournament_context_engine.py`
- `worldcup_predictor/agents/specialists/tournament_context_agent.py`
- `scripts/validate_phase22e_tournament_context.py`
- `PHASE_22E_TOURNAMENT_CONTEXT_REPORT.md`

**Modified**
- `worldcup_predictor/providers/enrichment_service.py` — `_maybe_enrich_sportmonks_standings()`
- `worldcup_predictor/agents/specialists/orchestrator.py` — agent registration + order
- `worldcup_predictor/agents/specialists/agents.py` — MasterAnalysis trace notes + specialist list

---

## Validation Results

Run locally:

```bash
python scripts/validate_phase22e_tournament_context.py
python scripts/validate_phase22b_unified_fixture.py
python scripts/validate_phase22c_sportmonks_odds_prediction.py
python scripts/validate_phase22d_xg_intelligence.py
```

Phase 22E checks cover: standings normalization, engine outputs, motivation comparison, agent wiring, orchestrator order, enrichment hook, daily cache policy.

**Result:** **27/27 passed** (offline). Regression 22B–22D: **13/13**, **18/18**, **19/19** passed.

---

## Predictive Value Ranking — World Cup 2026

| Rank | Layer | Rationale |
|------|-------|-----------|
| **1** | **Combined xG + Tournament Context** | WC group-stage outcomes are driven by both *match quality* (xG) and *scenario math* (must-win, GD tiebreakers, rotation). Combined layer captures structural edge cases xG alone misses (e.g., 0–0 acceptable for both, dead-rubber rotation) while xG anchors scoreline realism. |
| **2** | **Tournament Context** | For WC specifically, final group matches and qualification permutations often dominate market mispricing more than marginal xG deltas — especially when Sportmonks xG add-on is partial pre-match (Phase 22D finding). Standings + scenario flags explain non-stationary team behavior. |
| **3** | **xG Intelligence** | Still highly valuable for knockout rounds and open group games, but **partial Sportmonks xG availability** and weaker pre-match signal density reduce standalone WC group-stage edge vs context. Internal/API-Football xG remains useful but is not always decisive when motivation dominates. |

**Summary:** Use **Combined xG + Tournament Context** as the benchmark target for Phase 22F+ weight studies. Keep both trace-only until calibration approval.

---

## Stop Boundary

Phase 22E complete. **Phase 22F (Expected Lineups) not started** — awaiting approval.

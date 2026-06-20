# PHASE 22 — Sportmonks Full Capability Audit

**Mode:** AUDIT ONLY  
**Date:** 2026-06-19  
**Scope:** FIFA World Cup 2026 (`world_cup_2026`) — Sportmonks league **732**, season **26618**  
**Rules observed:** No code changes, no deploy, no provider edits, no prediction-math changes.

---

## Executive Summary

WorldCup Predictor treats **API-Football as primary** and Sportmonks as **optional gap-fill enrichment** for World Cup 2026 only. Production currently makes **one class of live Sportmonks call** during prediction: `GET /fixtures/date/{date}` with `fixtureLeagues:732` and six fixture includes. A richer `GET /fixtures/{id}` path exists but is **CLI/admin-only** and **not wired into the predict pipeline**.

**Utilization estimate:** ~15–20% of Sportmonks’ prediction-relevant WC capability.

| Category | Sportmonks offers (WC-relevant) | We consume | Gap severity |
|----------|----------------------------------|------------|--------------|
| Fixture identity + match shell | Yes | Partial (date lookup) | Low |
| Lineups / sidelined | Yes | Partial (gap-fill only) | Medium |
| In-match xG / statistics | Yes | Partial (`statistics`, not `xGFixture`) | High (pre-match limited) |
| Odds | Yes | **No** | High |
| Prediction model | Yes | **No** (explicitly deferred) | High |
| Head2Head | Yes | **No** (API-Football only) | Medium |
| Team recent form / season stats | Yes (standings `form`, team endpoints) | **No** | Medium |
| Group / live standings | Yes | **No** (local/API-Football schedule) | Medium |
| Referee statistics | Yes | **No** (name only from API-Football) | Low–Medium |
| Pressure / trends / events | Yes | **No** / events only in unused path | Low |

**Primary prediction bottleneck remains harmonization + odds availability** (Phase 17–20). Sportmonks integration today mostly improves **data-quality scores** and **conditional gap-fill** (injuries, lineups) rather than driving final 1X2.

---

## 1. Current Usage Inventory

### 1.1 Live API endpoints (code-defined)

| # | Endpoint | Includes / params | Cache TTL | Called when | Used by (specialist / engine) | Affects prediction? |
|---|----------|-------------------|-----------|-------------|--------------------------------|---------------------|
| 1 | `GET /leagues/732` | none | — | CLI `sportmonks-test` / production audit scripts only | None | **No** |
| 2 | `GET /fixtures/date/{YYYY-MM-DD}` | `include=participants;scores;statistics;lineups;sidelined.sideline;formations` + `filters=fixtureLeagues:732` + `per_page=50` | **Date list:** 1,800 s (30 min) file cache<br>**Lookup hit:** 86,400 s (24 h)<br>**Lookup miss:** 3,600 s (1 h) | Every intelligence build when Sportmonks token set, `competition_key=world_cup_2026`, and `api_fixture_id` present (`EnrichmentService._maybe_enrich_sportmonks` → `SportmonksClient.get_fixture_context`). May query anchor date ±1 day (up to 3 date calls worst case). | `apply_sportmonks_consumption` → gap-fill; downstream: `injury_suspension_agent`, `lineup_agent`, `lineup_intelligence_agent`, `tactics_agent` (xg fallback), `extract_real_xg` → WDE goal hints / xG V2 | **Indirect yes** — only when API-Football left gaps |
| 3 | `GET /fixtures/{sportmonks_fixture_id}` | `include=scores;participants;state;statistics;lineups;events;formations;sidelined.sideline` | **SQLite `sportmonks_fixture_enrichment`:** 1,800 s live / 86,400 s finished | **Not called in predict pipeline.** CLI `sportmonks-fixture-test` + manual admin use. Consumption layer can read SQLite if row exists (`get_sportmonks_fixture_enrichment_by_api_fixture_id`). | Same consumption path if cache populated | **Indirect yes** (only if cache pre-warmed) |

**Source files:**  
`sportmonks_fixture_lookup.py`, `sportmonks_enrichment.py`, `sportmonks_client.py`, `sportmonks_provider.py`, `enrichment_service.py`, `sportmonks_consumption.py`

### 1.2 Includes consumed vs fetched

| Include | Fetched (prod path) | Fetched (CLI `/fixtures/{id}`) | Normalized in consumption | Reaches WDE / scoreline |
|---------|---------------------|--------------------------------|---------------------------|-------------------------|
| `participants` | Yes | Yes | Yes (team IDs/names) | No direct weight |
| `scores` | Yes | Yes | Stored, not scored | No |
| `statistics` | Yes | Yes | xG + flat match stats | **Yes** via `extract_real_xg` (38% blend in `_estimate_goals`) and `tactics_agent` |
| `lineups` | Yes | Yes | Gap-fill `report.lineups` | **Yes** — lineups confidence weight 0.10 |
| `sidelined.sideline` | Yes | Yes | Gap-fill injuries | **Yes** — `_score_injuries` + specialist absence |
| `formations` | Yes | Yes | Attached to lineup objects | Minor (possession hint in tactics) |
| `state` | No | Yes | Not consumed | No |
| `events` | No | Yes | Not consumed | No |

### 1.3 Consumption pipeline (no extra API calls)

`apply_sportmonks_consumption` runs on **every** enriched report after providers return:

1. Resolves raw payload from `provider_metadata.sportmonks_fixture` or SQLite cache.
2. **Gap-fill only** (never overwrites API-Football injuries):
   - `home_team.injuries` / `away_team.injuries` from `sidelined`
   - `report.lineups` from Sportmonks lineups
   - `report.fixture_statistics` supplemental flat stats
3. Writes `supplemental_sources.sportmonks` for specialists.

### 1.4 Specialist / engine touchpoints

| Consumer | Sportmonks fields used | Prediction impact |
|----------|------------------------|-------------------|
| `injury_suspension_agent` | Gap-filled `report.*.injuries` | WDE injury delta; confidence penalty via specialist fusion |
| `lineup_agent` / `lineup_intelligence_agent` | Gap-filled lineups | Lineups score (weight 0.10); confidence messaging |
| `tactics_agent` | `supplemental.sportmonks.xg` (tertiary after RapidAPI) | Over/under tendency; goals_adjustment in fusion |
| `extract_real_xg` → `_estimate_goals` | `supplemental.sportmonks.xg` | Goal-rate blend (38% xG when present) |
| `xg_chance_quality_intelligence_agent` | Via `extract_real_xg` + match stats | WDE xG cluster; capped adjustment |
| All other specialists | — | **No Sportmonks path** |

### 1.5 What is explicitly NOT called

- `include=odds`, `premiumOdds`, `inplayOdds`
- `include=predictions`
- `include=xGFixture` (dedicated xG entity; code parses generic `statistics` only)
- `include=pressure`, `trends`, `timeline`, `referees`, `expectedLineups`, `predictedLineups`
- `GET /fixtures/head-to-head/{team_a}/{team_b}`
- `GET /standings/seasons/{26618}` or live standings
- Team / squad / topscorers / player profile endpoints
- Any non-WC league filter (hard guard on `league_id == 732`)

Comment in `sportmonks_enrichment.py`: *"High-value includes only — no predictions; odds deferred to later step."*

---

## 2. Available Capability Matrix

Legend: **Plan** = included in typical WC subscription vs add-on (verify against your Sportmonks dashboard). **Used** = integrated into predict path today.

| Capability | Available in Sportmonks v3? | Available in our WC plan? | Useful for prediction | Currently used? | Missing integration? | Quota risk | Recommended priority |
|------------|----------------------------|---------------------------|----------------------|-----------------|----------------------|------------|----------------------|
| **Odds** | Yes (`odds`, filters by market/bookmaker) | Likely yes if odds add-on purchased | **High** | **No** | **Yes** | Medium (cache 30–120 min) | **P1** |
| **Prediction Model** | Yes (`predictions` include + metadata eligibility) | Unknown — check metadata | **High** (reference / ensemble) | **No** | **Yes** | Low–Medium (daily TTL) | **P1** |
| **xG Match** | Yes (`xGFixture` + stats types) | Often **add-on** | **High** (pre-match if add-on; in-match always) | **Partial** (`statistics` only) | **Yes** | Low per fixture (cache by state) | **P1** |
| **Match Centre** | Composite (participants, scores, events, lineups, stats, referees) | Yes (subset) | Medium (UI + live) | **Partial** | Yes (events, referees, timeline) | Medium if polled live | P3 |
| **Lineup** | Yes (`lineups`, `expectedLineups`, `predictedLineups`) | Yes | **High** near kickoff | **Partial** (confirmed lineups gap-fill) | Yes (expected lineups pre-match) | Low near kickoff; skip if >4 h | **P2** |
| **Head2Head** | Yes (`GET /fixtures/head-to-head/{id}/{id}`) | Likely yes | **High** | **No** (API-Football H2H) | **Yes** | Low (cache 24 h per pair) | **P2** |
| **Team Season Statistics** | Yes (team + season statistics endpoints) | Likely yes | Medium | **No** | **Yes** | Low (prefetch daily per team) | P2 |
| **Team Recent Form** | Yes (`standings` include `form`; team fixtures) | Likely yes | **High** | **No** (API-Football form) | **Yes** | Low (daily standings prefetch) | **P2** |
| **Injuries & Suspensions** | Yes (`sidelined`) | Yes | **High** | **Partial** (gap-fill) | Partial (no SM-primary path) | Low (8 h TTL band) | **P2** |
| **Referee Statistics** | Yes (`referees` include + referee entities) | Unknown | Medium | **No** (placeholder agent) | **Yes** | Low (cache per referee season) | P3 |
| **Group Standings** | Yes (`standings` by season/round/group) | Yes for WC groups | **High** (motivation / rotation) | **No** | **Yes** | Low (1× daily per season) | **P2** |
| **Trends** | Yes (`trends` include) | Unknown | Medium | **No** | **Yes** | Low (per fixture, post-lineup) | P3 |
| **Pressure Index** | Yes (`pressure` include) | Often add-on / in-play | Medium | **No** | **Yes** | **High** if polled live | P4 (in-play only) |
| **Events Timeline** | Yes (`events`, `timeline`) | Yes | Low–Medium (live/post) | **No** in prod path | **Yes** | Medium live polling | P4 |
| **Live Standings** | Yes (`GET live standings by league`) | Likely yes | Medium during WC | **No** | **Yes** | Low (poll only on match days) | P3 |
| **Player Profile** | Yes (players entity) | Likely yes | Medium | **No** | **Yes** | Medium if per-player | P3 |
| **Team Squad** | Yes (squads by team/season) | Likely yes | Medium | **No** | **Yes** | Low (daily per team) | P3 |
| **Topscorers** | Yes (topscorers by season/stage) | Likely yes | Medium | **No** (API-Football deep) | **Yes** | Low (daily per season) | P3 |

---

## 3. Prediction Value Ranking

### High value (should drive WC 2026 model enrichment)

1. **Odds** — Phase 17 showed market signals correlate when present (~13% availability); Sportmonks odds could diversify beyond API-Football / The Odds API.
2. **Prediction Model** — Independent 1X2 prior; useful as ensemble input (not harmonization override).
3. **xG Match (`xGFixture`)** — Direct chance-quality input; current `statistics` parsing misses dedicated xG schema and is mostly **in-match**.
4. **Team Recent Form** — Core WDE weight 0.22; SM standings `form` or team fixture strips complement sparse WC samples.
5. **Head2Head** — WDE weight 0.18; SM H2H endpoint may cover internationals API-Football misses.
6. **Lineups / Expected Lineups** — Weight 0.10 + injury intelligence; critical inside 4 h of kickoff.
7. **Injuries & Suspensions** — Direct injury delta in WDE when API-Football sidelined plan-blocked.
8. **Group Standings** — Tournament intelligence / motivation agent; knockout permutations.

### Medium value

9. Referee statistics (replace placeholder cards/fouls profile)  
10. Team season statistics (attack/defense baselines)  
11. Trends (momentum / tactical shifts)  
12. Pressure index (in-play recalibration only)  
13. Player profile / squad / topscorers (player quality agent enrichment)  
14. Live standings (match-day context)

### Low value (defer)

15. TV stations, commentaries, news pages, ball coordinates, AI overviews for core 1X2  
16. Events timeline for **pre-match** prediction (post-match learning only)

---

## 4. Gap Analysis

| Gap | Current state | Impact |
|-----|---------------|--------|
| **xG not fully used** | Parses `statistics` for "Expected Goals" labels only; **`xGFixture` never requested**. Pre-match fixtures usually have empty in-match stats → xG path rarely fires for WC. | **High** — goal-rate and xG V2 underfed |
| **Sportmonks odds not used** | Odds from API-Football + The Odds API only | **High** — misses redundant market consensus |
| **Prediction model not used** | Deferred by design; API-Football `predictions_reference` in deep data only | **High** — no SM ensemble prior |
| **Head2Head not used** | `match_intelligence_builder._collect_h2h` → API-Football only | **Medium** — international H2H gaps |
| **Team recent form not used** | `TeamFormAgent` reads API-Football `report.*.form` | **Medium** — WC teams have thin API-Football form |
| **Team season statistics not used** | API-Football team stats primary | **Medium** |
| **Referee stats not used** | `RefereeAgent` uses placeholder card rates | **Low–Medium** |
| **Pressure index not used** | Not fetched | **Low** pre-match; medium in-play |
| **Group standings not used** | Local schedule / API-Football; SM standings unused | **Medium** for group-stage motivation |
| **Rich fixture fetch not in pipeline** | `/fixtures/{id}` with `events`/`state` is CLI-only | **Medium** — production never gets full payload |
| **Dual-path inconsistency** | Lookup includes ≠ enrichment includes; production never benefits from `events`/`state` | Operational / data completeness |

### Architectural note

Sportmonks is **enrichment tier 2** (`ProviderRegistry` policy). It **cannot override** populated API-Football fields. Value is capped unless API-Football gaps are frequent (injuries, lineups, xG for WC).

---

## 5. API Quota Safety — Recommended Usage Patterns

| Missing capability | Safe pattern | Rationale |
|--------------------|--------------|-----------|
| **Fixture by ID** (full includes) | **Cache-first**; 1 call per SM fixture ID; reuse lookup ID; TTL 30 min live / 24 h FT | Avoid duplicate date-list fetches; merge with lookup |
| **Odds** | **Cache-first** 60 min; **skip if match >7 days away**; **never per-card** — batch via single fixture include | Odds move slowly pre-match |
| **Predictions** | **Prefetch daily** per fixture; TTL 24 h until kickoff −6 h then 6 h | SM predictions stable |
| **xGFixture** | **Per-fixture on-demand**; **only near kickoff** (−4 h) for pre-match; post-match 24 h cache | xG add-on calls are expensive |
| **Head2Head** | **Cache-first** 24 h per team-pair; resolve team IDs from `participants` once | One H2H endpoint replaces many fixture queries |
| **Standings / group table** | **Prefetch daily** `GET standings by season 26618`; admin refresh button | 72 WC teams → 1–2 calls/day |
| **Team season stats / form** | **Prefetch daily** per WC participant team ID (32–48 teams); store in SQLite | Amortize across all fixtures |
| **Lineups / sidelined** | **Only near kickoff** (<4 h, matches existing `LINEUPS_FETCH_MAX_HOURS_BEFORE`); 15 min TTL | Aligns with `cache_policy.py` |
| **Injuries** | **Cache-first** 8 h (`INJURIES_TTL_SECONDS`); gap-fill only | Already aligned |
| **Referee stats** | **Prefetch daily** per assigned referee when fixture metadata known | Low cardinality |
| **Pressure / events / live** | **In-play only**; poll `GET /fixtures/latest` or single fixture — **admin/live mode only**; **never on predict card** | High quota burn |
| **Topscorers / squad / player** | **Prefetch daily** at season level; attach to team intel cache | Avoid N×player calls |
| **Date list lookup** | Keep **fixtureLeagues:732** filter; **retain 30 min date cache**; cap ±1 day search | Already quota-safe |

**Never per-card rules (mandatory):**

- Do not call Sportmonks independently for each UI card refresh.
- Batch by **date**, **season**, or **fixture ID** with SQLite/file cache gates.
- Skip entirely when `competition_key != world_cup_2026` or `league_id != 732`.

---

## 6. World Cup 2026 Focus

### 6.1 ID mapping

| System | World Cup 2026 identifier | Code reference |
|--------|---------------------------|----------------|
| Sportmonks league | **732** | `WORLD_CUP_2026_LEAGUE_ID` in `sportmonks_provider.py` |
| Sportmonks season | **26618** | `WORLD_CUP_2026_SEASON_ID` |
| API-Football league | **1** | `WORLD_CUP_2026` in `competitions.py` |
| API-Football season | **2026** | `competitions.py` |
| Competition key | `world_cup_2026` | Default competition |

**Guard:** All Sportmonks fetch paths validate `league_id == 732` before caching.

### 6.2 WC-specific endpoints needed (recommended)

| Purpose | Sportmonks endpoint / include | WC notes |
|---------|------------------------------|----------|
| Fixture resolution | `GET /fixtures/date/{date}?filters=fixtureLeagues:732` | Already used |
| Full match payload | `GET /fixtures/{id}?include=…` | Wire after ID known |
| Group tables | `GET /standings/seasons/26618` (+ `group` include) | Group stage Jun–Jun 2026 |
| Live group updates | Live standings by league 732 | Match days only |
| Knockout bracket | `round`, `stage`, `aggregate` includes on fixtures | Tie-break / extra time context |
| H2H internationals | `GET /fixtures/head-to-head/{sm_home_team_id}/{sm_away_team_id}` | Use SM participant IDs |
| WC odds | `include=odds&filters=markets:…` on fixture | Confirm WC market IDs in plan |
| SM prediction | `include=predictions;metadata` | Check eligibility flag |
| Squad lists | Team squads for season 26618 | Pre-tournament + roster cuts |
| Top scorers | Topscorers for season 26618 | Golden boot context |

### 6.3 Out of scope (per audit rules)

- Bundesliga / other league Sportmonks IDs — **not evaluated**
- Non-WC `competition_key` — Sportmonks client returns early without call

---

## 7. Recommended Implementation Phases (post-audit)

| Phase | Scope | Quota pattern | Expected prediction impact |
|-------|-------|---------------|----------------------------|
| **22B — Unify fixture fetch** | After lookup, call `/fixtures/{id}` once with merged include set; retire duplicate date payload as source of truth | Cache-first SQLite | **Medium** — consistent lineups/injuries/events |
| **22C — Odds + predictions includes** | Add `odds;predictions;metadata` to fixture fetch; normalize to supplemental (no WDE override) | 60 min / 24 h TTL; skip >7 d | **High** if odds gap-filled; ensemble prior for SM predictions |
| **22D — xGFixture add-on** | Request `xGFixture` when plan confirmed; feed `extract_real_xg` | Near kickoff + post-match | **High** for O/U and goal rates |
| **22E — H2H + standings prefetch** | Daily job: season standings + pairwise H2H cache for scheduled fixtures | Daily admin cron | **Medium** — form/H2H/motivation weights |
| **22F — Expected lineups + sidelined primary** | Use `expectedLineups` pre-match; SM-primary when API-Football blocked | <4 h kickoff gate | **Medium–High** near kickoff |
| **22G — Referee / squad / topscorers** | Daily referee card profile; season topscorers | Daily | **Low–Medium** |
| **22H — In-play only** | Pressure, live events, live standings | Live mode only | **Low** pre-match; optional live product |

**Do not implement in Phase 22** — this document stops at planning.

---

## 8. Expected Impact on Prediction Quality

| Signal | Current WC contribution | If fully integrated (estimate) |
|--------|-------------------------|--------------------------------|
| Injuries (SM gap-fill) | Low–medium when API-Football empty | +1–3 pp data quality; occasional WDE injury delta |
| Lineups (SM gap-fill) | Low until near kickoff | +lineups confidence when API-Football late |
| xG | Rarely populated pre-match | +2–5% better O/U calibration if `xGFixture` live |
| Odds | 0% from Sportmonks | +market diversity; helps Rule A / shadow paths when API odds missing |
| SM predictions | 0% | New ensemble feature; validate in shadow before prod |
| H2H / form / standings | 0% from Sportmonks | Marginal 1X2 lift; stronger tournament context |

**Realistic ceiling:** Sportmonks is unlikely to fix the **harmonization-dominated 1X2 accuracy gap** (Phase 18–19) by itself. Highest ROI is **(1) odds + predictions includes**, **(2) xGFixture near kickoff**, **(3) standings/H2H prefetch** — all with strict cache-first quota discipline.

---

## 9. Verification Checklist (for Phase 22B+)

- [ ] Confirm Sportmonks plan includes: odds, predictions, xGFixture (dashboard)
- [ ] Run `validate_phase8b_sportmonks_lookup.py` on live WC fixture
- [ ] Compare SM vs API-Football injury/lineup overlap on 5 WC fixtures
- [ ] Measure cache hit rate under predict load (no >1 SM call per fixture per TTL)
- [ ] Shadow-test SM odds/predictions vs production harmonization (no prod change)

---

## 10. References (code)

| Module | Role |
|--------|------|
| `worldcup_predictor/providers/sportmonks_fixture_lookup.py` | Date lookup + cache |
| `worldcup_predictor/providers/sportmonks_enrichment.py` | Full fixture fetch (CLI) |
| `worldcup_predictor/providers/sportmonks_consumption.py` | Gap-fill normalization |
| `worldcup_predictor/providers/enrichment_service.py` | Predict-path wiring |
| `worldcup_predictor/chance_quality/stat_extraction.py` | xG extraction priority |
| `worldcup_predictor/agents/specialists/agents.py` | TacticsAgent xG fallback |
| `worldcup_predictor/prediction/scoring_engine.py` | WDE weights + xG goal hints |
| `worldcup_predictor/quota/cache_policy.py` | TTL bands for future SM endpoints |

**External:** [Sportmonks v3 Fixtures docs](https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/fixtures) — canonical include list: `odds`, `predictions`, `xGFixture`, `pressure`, `sidelined`, `referees`, `trends`, `standings` (via season endpoint).

---

**AUDIT COMPLETE — NO CODE CHANGES MADE**

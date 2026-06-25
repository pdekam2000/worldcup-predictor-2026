# PHASE DATA-53 — Feature Gap Analysis

**Mode:** Analysis only — no code changes, no deploy  
**Generated:** 2026-06-23  
**Scope:** API-Football (api-sports.io) + Sportmonks v3 football API  
**Sources:** `worldcup_predictor/clients/api_football.py`, `providers/sportmonks_*`, EGIE/goal-timing pipelines, `reports/api_sports_usage_audit.md`, `PHASE_API_G_*`, `PHASE_API_F_*`, `PHASE_31A_*`

---

## Executive summary

| Provider | Endpoints wired in code | Fields actively used in prediction | Fields stored but under-used | Paid fields ignored |
|----------|------------------------|-----------------------------------|------------------------------|---------------------|
| **API-Football** | 13 endpoint families | ~25% of available fixture/odds depth | Events, stats, lineups (partial backfill) | BTTS/correct-score/FTS odds, player season stats, deep stat types |
| **Sportmonks** | 3 route families (`/fixtures/{id}`, standings, lookup) | ~10% (WC enrichment path only) | Full base include blob in cache | xG, odds, predictions (plan-blocked); PL mapping 0% |

**Highest-leverage gaps for target markets:** (1) bulk `fixtures/events` → first-goal minute + scorer history, (2) parse full `odds` bookmaker matrix (BTTS, correct score, FTS, multi-line O/U), (3) `fixtures/players` + `players/topscorers` at scale (Phase 53 wired, not backfilled), (4) Sportmonks xG/pressure once PL fixture mapping + plan entitlements align.

---

## Part 1 — API-Football field inventory

### 1.1 Endpoint catalogue

| Endpoint | Client method | Imported to DB | Used in live prediction | Used in EGIE | Used in Goal Timing | Status |
|----------|---------------|----------------|-------------------------|--------------|---------------------|--------|
| `fixtures` (list / id / season / team / live) | `fetch_upcoming_fixtures`, `get_fixture_by_id`, `get_all_fixtures_for_season`, `get_historical_fixtures`, `get_live_fixtures`, `get_team_recent_fixtures` | **Yes** — `fixtures`, `fixture_results` | **Yes** — schedule, predict | Partial — fixture metadata | **Yes** — fixture lookup | **Imported + used** |
| `fixtures/headtohead` | `get_head_to_head` | Cache only | **Yes** — H2H bias | No | Indirect (team history) | **Used, not bulk-stored** |
| `fixtures/events` | `get_fixture_events` | **Partial** — `fixture_goal_events`, EGIE raw `events` | **Yes** — live cards, verification | **Partial** — events flag only | **Yes** — minute/scorer aggregates | **Available, under-imported** |
| `fixtures/statistics` | `get_fixture_statistics` | **Partial** — EGIE raw, cache | **Yes** — chance quality | **Partial** — shots/SOT/dangerous attacks | No | **Available, under-imported** |
| `fixtures/lineups` | `get_fixture_lineups` | **Partial** — EGIE raw | **Yes** — lineup agents, scorers | **Partial** — lineup_strength | **Yes** — lineup_goal_impact agent | **Available, under-imported** |
| `fixtures/players` | `get_fixture_players` | Cache / deep supplemental only | **Yes** — Phase 53 scorer ranking | No | No | **Available, unused at scale** |
| `injuries` | `get_injuries` | **Partial** — EGIE raw | **Yes** — injury specialist | **Partial** — injuries_impact | No | **Available, under-imported** |
| `sidelined` | `get_sidelined` | Probe/cache only | **Yes** — merged into injuries | No | No | **Available, lightly used** |
| `odds` | `get_odds` | **Yes** — `odds_snapshots` (full JSON) | **Yes** — 1X2 + O/U 2.5 only | **Partial** — implied 1X2 from snapshots | **Partial** — 1X2 implied only | **Imported; 80%+ odds fields ignored** |
| `teams/statistics` | `get_team_statistics` | Cache only | **Yes** — form, goals for/against | No | Indirect via form | **Used, not persisted** |
| `standings` | `get_standings` | Cache only | **Yes** — group/tournament context | No | No | **Used, not persisted** |
| `players/topscorers` | `get_top_scorers` | Cache / supplemental only | **Yes** — Phase 53 scorer priors | No | No | **Available, unused at scale** |
| `players/squads` | `get_team_squad` | Cache / supplemental only | **Yes** — Phase 53 depth | No | No | **Available, unused at scale** |
| `predictions` | `get_predictions` | Cache / supplemental only | Reference only (1X2 %, O/U hint) | No | No | **Available, reference-only** |

### 1.2 Not implemented in client (available on typical API-Football plans)

| Endpoint family | Example fields | Relevance to target markets | Status |
|-----------------|----------------|----------------------------|--------|
| `players?team=&season=` | season goals, assists, minutes, cards | Goalscorer, BTTS | **Available but unused** |
| `players/topassists` | assist leaders | Goalscorer (creator weight) | **Available but unused** |
| `teams?id=` | venue, coach, country | Context only | Low priority |
| `venues` | capacity, surface | Context only | Low priority |
| `odds/live` | in-play lines | Live only | Not needed pre-match |
| `coaches`, `transfers`, `trophies` | metadata | Low | **Not wired** |

### 1.3 API-Football fields by payload area

#### Fixtures (`fixtures` response)

| Field group | Example fields | Imported | Used | Gap |
|-------------|----------------|----------|------|-----|
| Identity | `fixture.id`, `date`, `status`, `venue`, `referee` | **Yes** | **Yes** | — |
| Teams | `teams.home/away.id`, `name`, `winner` | **Yes** | **Yes** | — |
| Scores | `goals.home/away`, `score.halftime`, `score.fulltime` | **Yes** (HT partial) | **Yes** | HT gaps on some imports |
| League | `league.id`, `season`, `round` | **Yes** | **Yes** | — |
| Weather | `fixture.venue` weather block (plan-dependent) | No | Partial (extract if present) | **Unused** |

#### Events (`fixtures/events`)

| Field | Imported | Used | Target market |
|-------|----------|------|---------------|
| `time.elapsed`, `time.extra` | **Partial** (`fixture_goal_events`) | Goal Timing, outcome persist | **First Goal Minute** |
| `type`, `detail` (Goal, Penalty, Own Goal) | **Partial** | Event parser, verification | **Goalscorer**, BTTS timing |
| `player.name`, `player.id` | **Partial** | Scorer persist, player_intel | **Goalscorer** |
| `assist.name` | **Partial** | Stored in goal_events | Goalscorer (secondary) |
| `team.id`, `team.name` | **Partial** | First goal team derivation | **First Goal Team** |
| Cards, subs, VAR | Rarely stored | Live UI only | Low |

#### Statistics (`fixtures/statistics`)

| Stat type (API label) | Stored | Parsed for EGIE | Used in model |
|----------------------|--------|-----------------|---------------|
| Shots / Shots on Goal | Partial | `home_shots`, `home_shots_on_target` | Chance quality |
| Ball Possession | Partial | Pressure proxy (SM path preferred) | Indirect |
| Dangerous Attacks | Partial | `home_dangerous_attacks` | EGIE advanced_stats |
| Expected Goals (xG) | If on plan | **No dedicated AF xG path** | Gap vs Sportmonks |
| Corners, fouls, passes, saves | In raw JSON | **Ignored** | O/U corners markets (future) |
| Goalkeeper saves | In raw JSON | **Ignored** | BTTS / clean sheet |

#### Odds (`odds` — bookmakers[].bets[])

| Bet market (typical API name) | Parsed today | Stored in snapshot | Target market |
|------------------------------|--------------|-------------------|---------------|
| Match Winner (1X2) | **Yes** | **Yes** | 1X2 (baseline) |
| Goals Over/Under 2.5 | **Yes** | **Yes** | **O/U** |
| Both Teams Score | **No** | **Yes** (raw) | **BTTS** |
| Correct Score | **No** | **Yes** (raw) | **Exact Score** |
| Goal Line / Asian Handicap | **No** | **Yes** (raw) | **Goal Range**, O/U alt lines |
| First Team To Score | **No** | **Yes** (raw) | **First Goal Team** |
| HT Result / HT O/U | **No** | **Yes** (raw) | HT markets |
| Anytime / First Goalscorer | **No** | Plan-dependent | **Goalscorer** |
| Double Chance | **No** | **Yes** (raw) | Correlation guard |

#### Players (`fixtures/players`, `players/topscorers`, `players/squads`)

| Field | Phase 53 fetch | Backfilled | Used |
|-------|----------------|------------|------|
| Per-fixture goals, shots, rating | **Yes** | **No** (cache only) | Scorer candidates |
| Season goals, assists, position | **Yes** (topscorers) | **No** | Scorer priors |
| Squad position, age | **Yes** (squads) | **No** | Depth / GK filter |

#### Team statistics (`teams/statistics`)

| Field block | Used live | Persisted | Target market |
|-------------|-----------|-----------|---------------|
| `form` string | **Yes** | No | Form bias |
| `goals.for/against` averages | **Yes** | No | **O/U**, **Goal Range** |
| `clean_sheet` / `failed_to_score` | **No** | No | **BTTS** |
| `penalty` scored/missed | **No** | No | **Goalscorer** (pen takers) |
| Home/away splits | Partial | No | **First Goal Team** home bias |

---

## Part 2 — Sportmonks field inventory

### 2.1 Endpoint / include catalogue

| Route | Includes requested | Imported | Used in prediction | EGIE | Goal Timing | Status |
|-------|-------------------|----------|-------------------|------|-------------|--------|
| `GET /fixtures/{id}` | **Base:** `scores`, `participants`, `state`, `statistics`, `lineups`, `events`, `formations`, `sidelined.sideline`, `metadata` | **Partial** — `sportmonks_fixture_enrichment` (WC-heavy) | WC enrichment only | Reader exists, **0% PL** | Events via SM unused (AF preferred) | **WC-scoped** |
| `GET /fixtures/{id}` | **Premium:** `odds`, `predictions`, `xGFixture` | Blocked (403 on current plan) | Shadow/promotion only | **0% coverage** | No | **Plan-blocked** |
| `GET /standings/seasons/{id}` | `participant`, `details`, `form`, `group`, `stage`, `rule` | File cache | Tournament context agent | No | No | **Used for WC** |
| Fixture lookup (date / PL mapping) | metadata | **0% PL rows** | N/A | Blocks all SM features | No | **Mapping gap** |

### 2.2 Sportmonks fields by include

#### `scores` / `participants` / `state`

| Field | Available | Imported | Used |
|-------|-----------|----------|------|
| FT / HT scores | Yes | WC cache | Results verification |
| Participant home/away meta | Yes | Yes | Lineup/injury mapping |
| State (FT, LIVE, NS) | Yes | Yes | Schedule |

#### `events`

| Field | Available | Used for |
|-------|-----------|----------|
| Minute, extra minute | Yes | **First Goal Minute** (if imported) |
| Player, related player | Yes | **Goalscorer** |
| Type (goal, card, sub) | Yes | Unified events layer |
| **Gap:** PL fixtures not enriched | — | AF events used instead |

#### `statistics` (all types → flat map)

| Metric family | Parsed | EGIE field | Target market |
|---------------|--------|------------|---------------|
| Expected goals (type 5304) | Yes (if entitled) | `home_xg_for` | **Goal Range**, O/U |
| xG on target (5305) | Yes | Partial | Shot quality |
| Ball possession | Yes | `pressure_index_*` | **First Goal Team** tempo |
| Shots, SOT, attacks | Yes | `advanced_match_intelligence` | **O/U**, BTTS |
| Corners, fouls, passes | In flat map | **Ignored** | Future |
| **Plan note:** xG include often 403 | — | 0% PL | Critical gap |

#### `lineups` / `formations` / `sidelined`

| Field | Used | Gap |
|-------|------|-----|
| Starters, bench, position_id, jersey | SM → API shape for gap-fill | WC only in prod path |
| Formation string | Tournament/lineup agents | PL not mapped |
| Sidelined category/reason | Injury merge | Same |

#### `odds` (premium)

| Field | Parsed | Used |
|-------|--------|------|
| 1X2 implied probs | `normalize_sportmonks_odds` | Benchmark / shadow |
| BTTS, O/U, correct score lines | **Not parsed** | **Ignored** |
| First team to score | **Not parsed** | **First Goal Team** gap |
| EGIE ML-1 expects `sm_first_team_score_*` | **Never populated for PL** | High-value unused |

#### `predictions` (premium)

| Field | Parsed | Used |
|-------|--------|------|
| 1X2 probabilities | Yes | Benchmark only |
| Scoreline / O/U hints | Partial | **Exact Score**, **O/U** reference |
| **403 on plan** | — | Shadow replay only |

#### `xGFixture` (premium)

| Field | Parsed | Used |
|-------|--------|------|
| Home/away xG, xGA | `parse_sportmonks_xg_match` | EGIE, xG agent, goal pressure |
| Open-play vs set-piece split | Partial | **First Goal Minute** (set-piece bias) |
| **403 on plan; 0 PL snapshots** | — | Largest SM gap |

#### `metadata`

| Field | Used |
|-------|------|
| Round, stage, group | Tournament context promotion |
| Referee ids | **Unused** |

---

## Part 3 — Target market gap matrix

Legend: ✅ used · ⚠️ available, partial · ❌ available, unused · 🚫 blocked / not on plan · ➖ model-derived (no provider odds)

| Capability | API-Football | Sportmonks | Current engine source | Gap severity |
|------------|--------------|------------|----------------------|--------------|
| **First Goal Team** | ⚠️ Events + team form; ❌ FTS odds | ⚠️ Events; ❌ `sm_first_team_score`; 🚫 predictions | Heuristic from team strength + goal-timing history | **High** — no market anchor |
| **First Goal Minute** | ⚠️ Events (sparse DB) | ⚠️ Events (WC only) | Historical minute distributions + heuristic band | **High** — need bulk events |
| **Goal Range** | ⚠️ Team goal averages; ❌ multi-line O/U odds | ⚠️ xG totals; 🚫 xGFixture PL | Poisson λ from internal model | **Medium** — odds lines unused |
| **Goalscorer** | ⚠️ Lineups; ⚠️ Phase 53 players; ❌ season stats | ⚠️ Lineups; ❌ player profiles | Lineup order + topscorers cache | **High** — weak priors at scale |
| **BTTS** | ❌ BTTS odds in snapshot | 🚫 odds include | **➖ Poisson BTTS** from lambdas | **Medium** — no market calibration |
| **O/U** | ✅ O/U 2.5 odds; ❌ 1.5/3.5/HT | 🚫 odds; ⚠️ xG | Model + 2.5 line only | **Medium** |
| **Exact Score** | ❌ Correct score odds | 🚫 predictions score dist | **➖ Poisson score grid** | **Medium–High** |

---

## Part 4 — Answers to the six questions

### 1. Which useful fields we already use

**API-Football (production path)**

- Fixture core: teams, kickoff, status, venue, referee, league/season/round, final + HT scores.
- Intelligence loop: team `form`, goals for/against (team statistics), recent fixtures, H2H, injuries (+ sidelined probe), lineups, fixture statistics (shots/SOT subset), odds 1X2 and O/U 2.5.
- Phase 53 live fetch: `players/topscorers`, `fixtures/players`, `players/squads`, `predictions` (reference), `fixtures?live=all`.
- Historical import: finished fixtures + 1X2/O2.5 odds into CSV/SQLite.
- Outcomes: `fixtures/events` → `fixture_goal_events` + `first_goal_*` on `fixture_results` (when persisted).
- EGIE backfill (PL): events, lineups, fixture_statistics, injuries → PostgreSQL raw store.

**Sportmonks (WC path)**

- Base fixture includes: participants, scores, state, statistics (flat), lineups, formations, sidelined, events, metadata.
- Standings: position, points, GD, form, group — tournament context agent.
- Normalized odds/predictions/xG parsers exist for **benchmark/shadow** when premium includes succeed.

**Derived without extra provider fields**

- BTTS, correct-score grid, goal-range probabilities from internal Poisson/`extended_markets.py`.
- First-goal minute **bands** from scoring heuristics + goal-timing historical aggregates.

---

### 2. Which fields we pay for but ignore

**API-Football**

| Paid payload | Already in snapshots/cache | Ignored fields | Est. waste |
|--------------|---------------------------|----------------|------------|
| `odds` full bookmaker matrix | ~961 `odds_snapshots` rows | BTTS, Correct Score, Goal Line, FTS, HT markets, Asian lines | **~70% of odds value** |
| `fixtures/statistics` | Thousands of cache files | Corners, passes, saves, cards, full xG if present | **~60% of stat types** |
| `fixtures/events` | Sparse `fixture_goal_events` | Bulk PL/BL history not ingested | **~90% of event value for backtest** |
| `teams/statistics` | Cache only | clean_sheet, failed_to_score, penalty blocks | **BTTS-specific** |
| `fixtures/players` / `topscorers` / `squads` | Phase 53 fetch, no PL backfill | Season goals, ratings, shots per player | **Goalscorer depth** |
| `predictions` | Reference attach only | under_over hint, percent blocks not fed to calibration | Low (by design) |

**Sportmonks**

| Include | Entitlement | Ignored because |
|---------|-------------|-----------------|
| Full `statistics` blob | Base (in cache) | Not mapped to PL EGIE; only WC enrichment runs |
| `events` | Base | AF events preferred; SM events not unified for PL |
| `odds` | **403** | Plan blocked — entire market layer unused |
| `predictions` | **403** | Plan blocked |
| `xGFixture` | **403** | Plan blocked — primary SM differentiator unused |
| PL fixture mapping | N/A | **0/380** PL EGIE fixtures have `sportmonks_fixture_id` |

**Cross-provider:** EGIE `EgieProviderFeatureStore` can read xG/pressure/odds but measured PL coverage is **0%** for xG, pressure, and aligned odds (`PHASE_API_F`, `PHASE_API_G`).

---

### 3. Which fields can improve EGIE

| Field source | EGIE consumer today | Improvement if fully ingested | Est. gain |
|--------------|--------------------|------------------------------|-----------|
| Sportmonks `xGFixture` (home/away xG, xGA) | `parse_xg_fields` | Strategies B/E/F survival features activate | **+8–15%** backtest discrimination (per phase API-F hypothesis; unproven until coverage >60%) |
| Sportmonks `statistics` → pressure | `parse_sportmonks_pressure` | `first_goal_pressure` agent signal | **+3–6%** on first-goal team calibration |
| API-F `fixtures/statistics` (full) | shots/SOT/dangerous only | Richer `advanced_stats` coverage | **+2–4%** data quality score |
| API-F `odds` BTTS + multi O/U | not parsed | ML-1 `odds_btts_*`, O/U lines for stacking | **+5–10%** BTTS/O-U log-loss (research tier) |
| API-F `fixtures/events` bulk | events flag | `recent_first_goal_*_rate` with real history | **+5–8%** first-goal team |
| Lineups + injuries (scale backfill) | 3.16% PL lineup coverage | Lineup strength + availability | **+2–5%** when coverage >50% |

**Blockers before EGIE gain is real:** PL Sportmonks mapping, premium include entitlement, PL-aligned `odds_snapshots`.

---

### 4. Which fields can improve Goal Timing

| Field | Provider | Current use | If fully used |
|-------|----------|-------------|---------------|
| `time.elapsed` / `extra` per goal | API-F `fixtures/events` | `GoalTimingFeatureBuilder` aggregates when `fixture_goal_events` populated | **Primary** — enables empirical minute distributions (est. **+10–18%** vs heuristic bands) |
| Team scoring/conceding by minute band | Derived from events | Core of Phase 51C | Scales with event coverage |
| `odds_implied_home/away` | API-F odds snapshots | `OddsGoalIntelligenceAgent` | **+3–5%** when goal-market odds parsed (FTS, O/U 2.5 already help timing indirectly) |
| Sportmonks xG open-play share | SM xGFixture | Not available PL | Early-goal vs late-goal prior (**+4–7%**) |
| Possession / dangerous attacks | SM statistics / AF stats | Pressure agent partial | Tempo-based minute shift (**+2–4%**) |
| API-F `predictions` under_over hint | API-F | Not wired to goal timing | Weak prior only (**+1–2%**) |

**Critical path:** Bulk ingest `fixtures/events` for all finished PL/BL/WC fixtures in goal-timing allowed leagues.

---

### 5. Which fields can improve Goalscorer

| Field | Provider | Status | Impact |
|-------|----------|--------|--------|
| Lineup `startXI` + position | API-F / SM | **Used** | Baseline |
| `fixtures/players` goals, shots, rating | API-F Phase 53 | **Fetched, not backfilled** | **+12–20%** scorer hit-rate vs lineup-only |
| `players/topscorers` season totals | API-F Phase 53 | Cache only | Tournament/league priors **+8–12%** |
| `players/squads` | API-F | Cache only | Depth, injury replacement **+3–5%** |
| Event `player` on first goal | API-F events | Partial persist | Evaluation + learning **+5–10%** |
| Penalty / OG `detail` | API-F events | Parsed, under-ingested | Pen taker ranking **+4–6%** |
| Anytime / first scorer odds | API-F odds | **Not parsed** | Market calibration **+6–10%** |
| SM player metadata / season stats | SM | Not wired for PL | Medium if mapped |

---

### 6. Estimated gain potential by feature group

Scores are **relative uplift potential** if the listed fields were ingested at **≥70% fixture coverage** and wired into existing engines (not new models). Based on phase audits, backtest sensitivity, and market dependence on provider vs model.

| Feature group | Primary provider fields | Current coverage (PL cohort) | Unused high-value fields | Est. gain potential | Confidence |
|---------------|------------------------|------------------------------|--------------------------|---------------------|------------|
| **First Goal Team** | AF events, AF FTS odds, SM predictions FTS, team form | Events ~low; odds FTS 0%; SM 0% | FTS odds, SM first-team-score, bulk event rates | **+8–15%** hit-rate vs baseline heuristic | Medium |
| **First Goal Minute** | AF/SM goal events (minute) | Low event DB fill | Bulk `fixtures/events` | **+10–18%** band accuracy | High (data-limited) |
| **Goal Range** | AF goal-line odds, SM xG totals, team goal avgs | Model-only λ | O/U 1.5/3.5/3.5+, xG | **+5–9%** range calibration | Medium |
| **Goalscorer** | AF fixture players, topscorers, scorer odds | Phase 53 not backfilled | Player stats + scorer markets | **+12–22%** top-1 scorer | Medium–High |
| **BTTS** | AF BTTS odds, team clean-sheet stats | Model Poisson only | BTTS odds, clean_sheet % | **+6–12%** Brier/log-loss | Medium |
| **O/U** | AF O/U 2.5 (used), other lines | 2.5 only ~partial cache | 1.5/3.5, HT O/U, SM xG | **+4–8%** on non-2.5 lines | Medium |
| **Exact Score** | AF correct-score odds, SM prediction grid | Poisson grid only | Correct score odds | **+7–14%** top-3 score hit-rate | Medium |
| **EGIE survival stack** | SM xG + pressure + aligned odds | **0%** PL | Entire premium layer | **+8–15%** strategy separation B–F | Low until plan/map fixed |
| **Data quality / no-bet** | All above | Mixed | Coverage uniformity | **−10–20%** false NO_BET if coverage improves | High |

---

## Part 5 — Priority ingestion roadmap (analysis only)

No implementation in this phase — ordered by ROI × feasibility:

1. **Parse existing `odds_snapshots` JSON** for BTTS, Correct Score, FTS, O/U 1.5/3.5 (no new API calls).
2. **Bulk backfill `fixtures/events`** for finished fixtures in EGIE + goal-timing leagues.
3. **Backfill Phase 53 player endpoints** (`fixtures/players`, `topscorers`) per league/season with cache-first policy.
4. **Fix PL Sportmonks fixture mapping** then re-probe premium includes (xG, odds, predictions).
5. **Persist `teams/statistics` clean_sheet / failed_to_score** for BTTS priors.
6. **Upgrade Sportmonks plan or alternate xG source** if xG remains 403 after mapping.

---

## Part 6 — Artifact references

| Document | Relevance |
|----------|-----------|
| `reports/api_sports_usage_audit.md` | API-Football endpoint usage baseline (pre–Phase 53) |
| `PHASE_API_G_SPORTMONKS_REAL_COVERAGE_AUDIT.md` | SM plan blocks, 0% PL EGIE |
| `PHASE_API_F_PROVIDER_BACKFILL_ALIGNMENT_REPORT.md` | Backfill outcomes, odds ID misalignment |
| `PHASE_31A_HISTORICAL_DATA_INVENTORY_AUDIT.md` | SQLite table coverage counts |
| `worldcup_predictor/egie/provider_features/store.py` | EGIE field consumption map |
| `worldcup_predictor/goal_timing/features/builder.py` | Goal timing provider manifest |

---

**STOP — Analysis only. No code changes. No deploy.**

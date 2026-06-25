# PHASE 54I — Lineups, Player Stats & Goalscorer Odds Discovery

**Date:** 2026-06-24  
**Mode:** Discovery → Coverage Audit → Feature Potential → Report  
**Status:** Complete — validation **10/10 PASS**  
**API calls (server):** 12 (cache-first; no mass ingest)

---

## Executive summary

Sportmonks **lineups and player match statistics are highly usable** for historical backtest and goalscorer feature engineering. **Goalscorer odds exist** in fixtures ingested with `odds.bookmaker;odds.market` includes, packaged as a combined **"Goalscorers"** market with **First / Anytime / Last** selection labels. **Player ID mapping in odds is name-only** (no `player_id`), requiring fuzzy join to lineups.

Pressure and xG were ruled out for EGIE integration (54H-7 / 54F). **Lineups + player stats + goalscorer odds** are the highest-value untested assets.

### Final recommendation: **`BUILD_LINEUP_PLAYER_FEATURE_STORE`**

Lineups and player match stats are production-ready for a feature store (92%+ coverage on UEFA/WC cache). Goalscorer odds exist but are sparse globally (6.2%); treat odds as **`GOALSCORER_ODDS_RESEARCH_ONLY`** until WC + UEFA odds-rich ingest expands. A unified goalscorer engine (54J) should consume the lineup/player store first, then layer odds calibration.

---

## 1. Are lineups usable?

**Yes — for historical backtest and pre-match (when lineups published).**

| Metric | Value |
|--------|-------|
| Fixtures scanned (cache) | 1,690 |
| With starting XI (≥20 starters) | **1,559 (92.2%)** |
| With bench (≥5) | 1,562 (92.4%) |
| With formations | 123 (7.3%)* |
| Pre-match usable (XI + formation) | 120 |
| Historical backtest usable | **1,559** |

\*Formations are sparse in xG-only cache payloads; **UEFA deep-ingest cache includes formations** (~100% on odds-rich files).

### By league (cache)

| League | Fixtures | Starting XI | Notes |
|--------|----------|-------------|-------|
| Champions League (2) | 600 | 556 | Strong |
| Europa League (5) | 578 | 539 | Strong |
| Conference (2286) | 464 | 464 | Strong |
| World Cup (732) | 48 | 0† | Pressure/xG cache lacks lineups include |

**Lineup fields available:** `player_id`, `team_id`, `formation_position`, `jersey_number`, `type_id` (11=starter, 12=bench), `player_name`, `details[]` (minutes, goals, cards).

**Substitutions:** Available via `events` (substitution type).  
**Sidelined/injuries:** Low in current cache (`sidelined` include rarely present).  
**Captain/GK flags:** Partial via `formation_position=1` (GK); explicit captain rare in details.

---

## 2. Are player stats usable?

**Yes — primarily via `lineups.details` on completed fixtures.**

| Metric | Coverage |
|--------|----------|
| Players with minutes (≥20 per match) | **91.1%** of fixtures (1,539) |
| Players with goals/assists in details | Present on finished matches |
| Player xG (`lineups.xGLineup`) | **63.1%** (1,067 fixtures; xG-licensed cache) |
| Team `statistics` block | Present on deep ingests |

**Detail types observed:** Minutes Played, Goals, Assists, Yellowcards, Goals Conceded, (shots/rating partial).

**Topscorers API (server live):**

| League | Season | Topscorer rows |
|--------|--------|----------------|
| World Cup 732 | 26618 | **25** |
| Champions League 2 | 28155 | 0 (season early) |
| Europa League 5 | 27913 | 0 |
| Conference 2286 | 27911 | 0 |

WC topscorers endpoint is **accessible and populated**.

**Usable for goalscorer engine:** **Yes** — minutes + goals history + optional player xG + topscorers (WC).

---

## 3. Are goalscorer odds available?

**Yes — where fixtures were ingested with odds includes (UEFA cache ~88%).**

| Metric | Value |
|--------|-------|
| Fixtures with goalscorer odds (all cache) | 105 / 1,690 (6.2%) |
| UEFA odds-rich cache subset | **~70 / 80 (~88%)** |
| WC in local cache | 0 (no odds include on pressure/xG-only pulls) |
| WC live (54D prior) | **1st Goal Scorer** confirmed on deep pull |

### Markets found (goalscorer-related)

| Market | Rows (sampled) | Labels |
|--------|------------------|--------|
| **Goalscorers** | 417 | **First**, **Anytime**, **Last** |
| Team Goalscorer | 286 | Team-level |
| First Team To Score | (via existing parser) | Home/Away |
| Correct Score | 48,216 | Not goalscorer |

**Sample odds row:** `market=Goalscorers`, `label=Anytime`, `name=Player Name`, `value=9.50`, `bookmaker=bet365` — **no `player_id`**.

**Bookmakers:** bet365 and others (multi-book on rich fixtures).  
**Historical vs upcoming:** Historical UEFA cache = yes; upcoming WC needs live odds pull.

---

## 4. Which data is best for First Goalscorer?

| Source | Rating | Why |
|--------|--------|-----|
| **Goalscorers odds (label=First)** | **Best calibration target** | Direct market; 140 First-label rows in UEFA sample |
| Player rolling goals + starts | Best **feature** | 96% minutes coverage |
| Topscorers API | WC season prior | 25 players ranked |
| Lineups (starters) | Eligibility filter | Who is on pitch |
| Player xG | Secondary feature | 68% coverage |

---

## 5. Which data is best for Anytime Goalscorer?

| Source | Rating | Why |
|--------|--------|-----|
| **Goalscorers odds (label=Anytime)** | **Best calibration target** | 137 Anytime-label rows |
| Player goals/90 + shots proxy | Best **feature** | From lineup details history |
| Player xG | Strong feature | Where licensed |
| Bench depth | Medium | Affects sub scorer risk |

---

## 6. Which data can improve Team Goals?

| Source | EGIE fit |
|--------|----------|
| Starting XI strength / formation | Medium |
| Player attacking stats (rolling) | Medium |
| **Team to score first / 1X2 odds** | **High** (existing parser) |
| Sidelined/injuries | Medium (when include added) |
| Topscorers (season) | Low–medium |

---

## 7. Which data can improve First Goal Team?

| Source | EGIE fit |
|--------|----------|
| **First Team To Score odds** | **High** (already in odds_intelligence) |
| Starting XI attacking weights | Medium |
| Formation matchup | Low–medium |
| Goalscorer odds (marginal) | Low alone |

---

## 8. What should be built next?

### Phase 54J proposal (not executed here)

1. **`BUILD_LINEUP_PLAYER_FEATURE_STORE`** — PostgreSQL + cache layer:
   - Fixture lineups (starters, bench, formation)
   - Player rolling: minutes, goals, assists, shots, xG
   - WC re-ingest with `lineups` include (current WC cache has 0 XI)

2. **`GOALSCORER_ODDS_RESEARCH_ONLY`** — Odds shadow layer:
   - Goalscorers First/Anytime/Last + Team Goalscorer
   - Player name → `player_id` resolver (fuzzy + lineup join)
   - Calibration vs baseline (no production)

3. **Ingest gap:** Re-pull WC fixtures with `odds.bookmaker;odds.market` + `lineups.xGLineup` on server (cache-first, capped)

4. **Do not build:** Pressure integration (54H-7 NO_VALUE); xG team-level already research-only

---

## Part D — Feature potential matrix

| Feature | Coverage | Quality | EGIE Value | Goalscorer Value | Recommendation |
|---------|----------|---------|------------|------------------|----------------|
| Starting XI | 92.2% | high | medium | high | BUILD_LINEUP_PLAYER_FEATURE_STORE |
| Bench | 92.4% | high | low | medium | BUILD_LINEUP_PLAYER_FEATURE_STORE |
| Formation | 7.3%* | high | medium | low | BUILD_LINEUP_PLAYER_FEATURE_STORE |
| Player minutes | 91.1% | high | low | high | BUILD_LINEUP_PLAYER_FEATURE_STORE |
| Player goals/assists | 91.1% | medium | low | high | BUILD_LINEUP_PLAYER_FEATURE_STORE |
| Player shots | partial | medium | low | medium | BUILD_LINEUP_PLAYER_FEATURE_STORE |
| Player xG | 63.1% | medium | low | high | BUILD_GOALSCORER_FEATURE_STORE |
| Player rating | partial | medium | low | medium | BUILD_LINEUP_PLAYER_FEATURE_STORE |
| Topscorers API | WC: 25 rows | high | medium | high | BUILD_GOALSCORER_FEATURE_STORE |
| First goalscorer odds | 6.2%† | medium | low | high | GOALSCORER_ODDS_RESEARCH_ONLY |
| Anytime goalscorer odds | 6.2%† | medium | low | high | GOALSCORER_ODDS_RESEARCH_ONLY |
| Team to score first odds | high‡ | high | high | medium | existing_odds_parser |
| Sidelined/injuries | low | low | medium | medium | BUILD_LINEUP_PLAYER_FEATURE_STORE |

\*Higher on UEFA odds-rich ingests. †88% on UEFA deep cache; low globally because xG store lacks odds. ‡Via existing UEFA odds parser.

---

## Validation

**10/10 PASS** (`artifacts/phase54i_lineups_player_goalscorer_discovery/validation.json`)

---

## Artifacts

| Path | Description |
|------|-------------|
| `artifacts/phase54i_lineups_player_goalscorer_discovery/lineups_discovery.json` | Lineup coverage |
| `artifacts/phase54i_lineups_player_goalscorer_discovery/player_stats_discovery.json` | Player stats |
| `artifacts/phase54i_lineups_player_goalscorer_discovery/goalscorer_odds_discovery.json` | Odds coverage |
| `artifacts/phase54i_lineups_player_goalscorer_discovery/feature_potential_matrix.json` | Matrix |
| `artifacts/phase54i_lineups_player_goalscorer_discovery/api_probe.json` | Server API probes |
| `artifacts/phase54i_lineups_player_goalscorer_discovery/fixture_audits.json` | Per-fixture audits |
| `artifacts/phase54i_lineups_player_goalscorer_discovery/discovery_summary.json` | Summary |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/phase54i_lineups_player_goalscorer_discovery.py` | Discovery orchestrator |
| `scripts/validate_phase54i_lineups_player_goalscorer_discovery.py` | Validation gate |
| `worldcup_predictor/intelligence/phase54i_discovery/` | Audit + engine modules |

---

**Phase 54I complete. No deploy. No live prediction changes. No modeling started.**

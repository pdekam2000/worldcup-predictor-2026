# PHASE A10 — MATCH CENTER V2 (AI COMMAND CENTER) REPORT

**Date:** 2026-06-20  
**Status:** DEPLOYED  
**Validation:** 52/52 PASS (`scripts/validate_phase_a10_match_center_v2.py`)  
**Production:** https://footballpredictor.it.com  
**Deploy method:** Controlled rsync + `systemctl restart worldcup-api` (backup script: `scripts/phase_a10_production_deploy.sh`)

---

## Executive summary

Phase A10 transforms Match Center into the AI command center without touching WDE, EGIE, prediction scoring, subscriptions, or model certification. The main production blocker from Phase A9B — domestic leagues showing **0 upcoming** due to stale registry seasons — is **fixed**. First-screen load for World Cup is **sub-second**; full multi-league aggregation remains heavier on cold cache but runs in parallel with schedule caching.

---

## Part 1 — Competition data / season mapping

### Problem (A9B)
Registry stored `season: 2024` for domestic leagues. In June 2026, API-Football returned no upcoming fixtures → **0 upcoming** in Match Center.

### Solution
| Component | Path |
|-----------|------|
| Auto season resolver | `worldcup_predictor/schedule/season_resolver.py` |
| Season cache (6h TTL) | `worldcup_predictor/quota/season_resolve_cache.py` |
| Schedule cache (300s TTL) | `worldcup_predictor/quota/match_schedule_cache.py` |

**Rules enforced:**
- Calendar-derived candidates (`year`, `year-1`) — **no hardcoded season years**
- **World Cup locked** to registry season (`world_cup_2026` → 2026)
- Provider probe: `fixtures?league=&season=&next=15`
- Resolved season exposed as `resolved_season` on competitions API

### Production after deploy

| Competition | Resolved season | Upcoming (prod) |
|-------------|-----------------|-----------------|
| premier_league | 2026 | **200** |
| world_cup_2026 | 2026 | 18 |
| bundesliga | 2026 | 0* |
| la_liga | 2026 | 0* |
| **Total** | — | **218** |

\*Zero may reflect off-season / plan coverage; season mapping is correct (2026 not 2024).

**Before:** `total_upcoming ≈ 18` (World Cup only)  
**After:** `total_upcoming = 218`

---

## Part 2 — Performance

### Backend
- `worldcup_predictor/api/match_center_aggregator.py` — `ThreadPoolExecutor` (8 workers), priority sort (WC, UCL, EPL first)
- `GET /api/matches?competition=all` uses parallel aggregation + schedule cache
- Response metadata: `load_ms`, `cache_hits`, `schedule_cache`

### Timing

| Endpoint | Before (A9B prod) | After (A10 prod) | Notes |
|----------|-------------------|------------------|-------|
| `/api/competitions` | ~8.5s | ~8.5s (cold season resolve) | Counts now accurate |
| `/api/matches?competition=world_cup_2026` | — | **0.27s** | First screen target met |
| `/api/matches?competition=all` | ~8–30s sequential | **21.6s** cold / **~7.5s** warm (local cache) | Parallel + cache |
| Aggregator 2nd call (local) | — | **7.5s**, **9 cache hits** | 100% competitions from cache |

### Frontend incremental load
`MatchCenter.jsx` loads **World Cup first** (<2s perceived), then refreshes with `competition=all` in background (`backgroundLoading` indicator).

---

## Part 3 — Today's Elite Picks

- Backend: `get_todays_elite_picks()` in `match_center_helpers.py`
- Included in `GET /api/matches` as `elite_picks_today`
- Dedicated: `GET /api/matches/elite-picks-today`
- UI: `TodaysElitePicks.jsx` — top 10, logos, league, kickoff, best market, confidence, value, quick add to bet slip

---

## Part 4 — AI Match Score

`compute_ai_match_score()` — 0–100 from cached payload only (confidence, data completeness, specialists, xG, calibration proxies).

| Score | Label |
|-------|-------|
| ≥95 | Elite |
| ≥87 | Strong |
| ≥73 | Good |
| ≥58 | Watch |
| <58 | Skip |

Displayed on `EliteMatchCard` badge. **No WDE/scoring changes.**

---

## Part 5 — Match insights

`extract_match_insights()` from stored prediction payload:
- Strong home form, Lineup advantage, Odds movement, xG advantage, Pressure advantage, Historical H2H

Rendered as insight chips on match cards.

---

## Part 6 — Combo AI

`comboGenerator.js` — four builders:
1. **SAFE COMBO** — high confidence, low legs
2. **BALANCED COMBO** — AI score weighted
3. **HIGH VALUE** — value rating weighted
4. **HIGH ODDS** — odds-weighted

Guards: `hasConflict()`, `isCorrelated()`, low AI score / confidence exclusion.

---

## Part 7 — Quick filters

`MatchCenterFilters.jsx`: Elite Picks, High Confidence, Best Value, Today's Combos, World Cup, Champions League, Favorites, Live Soon, Today, Live/Upcoming.

Client filters in `matchCenterUtils.js` including favorites (authenticated).

---

## Part 8 — Live status labels

`fixture_status_label()`: Prediction Ready, Prediction Updating, Waiting for Lineups, Live, Finished, Evaluated.

---

## Part 9 — Owner insights

- Backend: `owner_meta` only when `Authorization: Bearer` + owner role
- Frontend: `OwnerInsightOverlay.jsx` (hidden for normal users)
- Fields: prediction version, engine version, cache age, data source, API provider, generation time

---

## Part 10 — Polish

- `MatchCenterSkeleton.jsx` — skeleton cards (no API flash)
- Framer Motion transitions on cards and elite picks carousel
- Improved mobile spacing (`px-1 sm:px-0`)
- Empty states with season-resolve hint
- Background refresh indicator

---

## Part 11 — Validation

```
python scripts/validate_phase_a10_match_center_v2.py
→ 52/52 PASS
```

Artifacts: `data/validation/phase_a10_match_center_v2.json`

Checks include: season resolver, parallel aggregator, cache, AI score, insights, combo builder, owner overlay, mobile layout, frontend build, WDE unchanged.

---

## Prediction regression

**None.** No modifications to:
- `weighted_decision_engine.py`
- `scoring_engine.py`
- Subscription or billing routes
- Prediction generation pipeline

All new intelligence is **read-only** from cached `payload_json`.

---

## Production smoke (post-deploy)

| Route | HTTP |
|-------|------|
| `/api/health` | 200 |
| `/api/competitions?include_counts=true` | 200 |
| `/api/matches?competition=all` | 200 |
| `/api/matches/elite-picks-today` | 200 |
| `/matches` | 200 |
| `/combo-tips` | 200 |

`worldcup-api` service: **active**

---

## Cache hit rate (local validation run)

- First aggregation: cold provider fetches
- Second aggregation: **9/9 competition cache hits**, `load_ms` reduced (~22s → ~7.5s)
- Season resolve cache: 6h TTL per competition key

---

## Mobile improvements

- Horizontal scroll elite picks carousel with snap
- Responsive grid (1 → 2 → 3 columns)
- Touch-friendly filter chips
- Compact team rows in elite pick cards

---

## Final recommendation

| Area | Recommendation |
|------|----------------|
| **Ship** | Phase A10 is production-ready; season fix alone justifies release |
| **Monitor** | Track `load_ms` and `cache_hits` on `/api/matches?competition=all` |
| **Follow-up** | Pre-warm schedule cache via cron for all enabled leagues every 5 min |
| **Follow-up** | Investigate API-Football `season required` errors for some cup competitions |
| **Follow-up** | Commit + push to `main` so server git state matches deployed files |
| **UX** | Elite picks populate as predictions are generated for today's fixtures |

---

## Files changed (summary)

**Backend:** `season_resolver.py`, `season_resolve_cache.py`, `match_schedule_cache.py`, `match_center_aggregator.py`, `match_center_helpers.py`, `routes/matches.py`, `routes/competitions.py`

**Frontend:** `MatchCenter.jsx`, `EliteMatchCard.jsx`, `MatchCenterFilters.jsx`, `TodaysElitePicks.jsx`, `MatchCenterSkeleton.jsx`, `OwnerInsightOverlay.jsx`, `comboGenerator.js`, `matchCenterUtils.js`, `worldcupApi.js`

**Tooling:** `validate_phase_a10_match_center_v2.py`, `phase_a10_production_deploy.sh`

---

*Research outputs remain labeled: "Research only — not betting advice."*

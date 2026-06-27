# HOTFIX H4 — Production Match Detail Crash + Image Debug Report

**Date:** 2026-06-25  
**Priority:** CRITICAL  
**Final status:** `LIVE_DETAIL_CRASH_AND_IMAGES_FIXED`

---

## Executive summary

Production Match Detail could blank the entire SPA when React tried to render **object values** from prediction payloads, and when **invalid `competition` query params** (e.g. `league_1`) caused hard API failures. Team/competition logos were missing because the API returned **zero logo URLs** despite SQLite storing `home_team_id` / `away_team_id`.

H4 adds route-level recovery, safe view-model derivation, resilient predict fetch, and API-Football team crest URLs derived from team IDs.

---

## Production stack trace (inferred + payload evidence)

### Primary crash signature

```
Error: Objects are not valid as a React child (found: object with keys {...})
```

| Item | Value |
|------|-------|
| Failing route | `/matches/:fixtureId` (e.g. `/matches/1489409?competition=league_1`) |
| Component stack | `PredictionSummaryCards` → `buildSummary` **or** `PredictionMarketsPro` → `groupMarkets` → `recommended_bets` |
| Root JS files | `predictionDetailProUtils.js`, `PredictionSummaryCards.jsx`, `PredictionMarketsPro.jsx` |
| Why whole SPA died | `useMemo` transforms ran in **parent render** — section `ErrorBoundary` children never mounted |

### Secondary trigger

| Request | Result |
|---------|--------|
| `GET /api/predict/1489409?competition=league_1` | **400 Bad Request** (invalid competition key) |
| `GET /api/predict/1489409` | **200** — `public_best_pick: "1X2: Away Win"` (string, safe) |
| DB `competition_key` for 1489409 | `world_cup_2026` (URL param `league_1` was wrong) |

---

## Image payload audit (production, post-fix)

**Before H4:** 0/30 match rows had `home_team_logo` or `away_team_logo`.

**After H4:** 5/5 top World Cup fixtures have API-Football crest URLs (`logos_in_top5=5`).

| fixture_id | home_team | home_logo (resolved) | away_team | away_logo (resolved) |
|------------|-----------|----------------------|-----------|----------------------|
| 1489409 | Curaçao | `.../teams/5530.png` | Ivory Coast | `.../teams/1501.png` |
| 1489410 | Ecuador | `.../teams/2382.png` | Germany | `.../teams/25.png` |
| 1489412 | Tunisia | team id → API crest | — | team id → API crest |
| 1489411 | Paraguay | team id → API crest | — | team id → API crest |
| 1489416 | Norway | team id → API crest | — | team id → API crest |

**Root image cause:** SQLite `fixtures` rows store `home_team_id` / `away_team_id` but not logo URLs; list-cache rows were empty. H4 derives `https://media.api-sports.io/football/teams/{id}.png` server-side and mirrors in `imageResolver.js`.

---

## Root causes

1. **Object-as-child render** — `buildSummary` could assign object `public_best_pick`; cards rendered raw objects.
2. **Parent render crash** — `useMemo` builders outside error boundaries killed the outlet (full black SPA).
3. **Invalid competition param** — `?competition=league_1` → predict API 400 before PredOps fallback.
4. **Missing logos** — API never populated logo fields despite valid team IDs.

---

## Files changed

### Frontend

- `base44-d/src/components/ui/RouteErrorBoundary.jsx` (new)
- `base44-d/src/lib/matchDetailSafeView.js` (new)
- `base44-d/src/components/dashboard/DashboardLayout.jsx`
- `base44-d/src/pages/MatchDetailPage.jsx`
- `base44-d/src/lib/predictionDetailProUtils.js`
- `base44-d/src/components/prediction-detail-pro/PredictionSummaryCards.jsx`
- `base44-d/src/api/worldcupApi.js`
- `base44-d/src/lib/imageResolver.js`
- `base44-d/src/components/match/TeamBadge.jsx`
- `base44-d/src/components/match/MatchTeamsRow.jsx`
- `base44-d/src/components/match-center/EliteMatchCard.jsx`
- `base44-d/src/components/prediction-detail-pro/MatchHeaderPro.jsx`

### Backend

- `worldcup_predictor/api/display_helpers.py`

### Validation / deploy

- `scripts/validate_hotfix_h4_live_debug.py`
- `scripts/_remote_deploy_h4.sh`

**Not modified:** WDE, EGIE, models, scoring, calibration, billing, subscription, Shadow runtime.

---

## Validation (production)

24/25 checks passed (`frontend_build` N/A — prebuilt dist deployed).

---

## Production smoke

| URL | HTTP |
|-----|------|
| `/api/health` | 200 |
| `/matches` | 200 |
| `/matches/1489409?competition=league_1` | 200 |
| `/matches/1489410?competition=world_cup_2026` | 200 |
| `/admin/elite-shadow` | 200 |

**Backup:** `/opt/worldcup-predictor/backups/hotfix-h4-<timestamp>/`

---

## Rollback

```bash
BACKUP=/opt/worldcup-predictor/backups/hotfix-h4-<timestamp>
rsync -a "$BACKUP/frontend_dist/" /var/www/worldcup/frontend/dist/
cp "$BACKUP/display_helpers.py" /opt/worldcup-predictor/worldcup_predictor/api/
systemctl restart worldcup-api
```

---

## Final status

**`LIVE_DETAIL_CRASH_AND_IMAGES_FIXED`**

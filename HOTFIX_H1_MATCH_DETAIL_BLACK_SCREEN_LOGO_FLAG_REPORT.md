# HOTFIX H1 — Match Detail Black Screen + Logo/Flag Fallback

**Date:** 2026-06-25  
**Priority:** CRITICAL  
**Final status:** `IMPLEMENTED_NOT_DEPLOYED` (tarball packed + uploaded; production deploy awaiting approval)

---

## Root cause — black screen

### Primary (React crash)

`groupMarkets()` in `predictionDetailProUtils.js` passed **raw object picks** from `recommended_bets` into market rows:

```javascript
selection: fmtMarketSel(selection) || selection  // selection could be { pick, market, ... }
```

`PredictionMarketsPro` / `MarketCard` renders `{market.selection}` as a React child. When `selection` is an object, React throws:

> **Objects are not valid as a React child**

This uncaught render error blanks the entire Match Detail page (dark shell + tabs only — appears as a “black screen”).

### Secondary (empty page)

`GET /api/predict/1489410?competition=world_cup_2026` returned **404 `not_cached`** on production while PredOps had a latest snapshot (`coverage_state: no_bet`, 21 markets). Match Detail called `runPrediction` POST on cache miss; slow/failed runs left the page with no content.

---

## Stack trace

Captured via code path analysis (production DevTools session not run in this pass). Expected console signature:

```
Error: Objects are not valid as a React child (found: object with keys {pick, market, ...})
    at MarketCard (PredictionMarketsPro.jsx)
    at groupMarkets → recommended_bets.map
```

---

## Root cause — missing logos/flags

| Issue | Cause |
|-------|--------|
| Competition logos | `competition_to_api_dict()` always set `logo_url: None` |
| Team logos on detail | `team_logos_for_fixture()` only searched one competition cache; missed cross-league fixtures |
| Broken images | `TeamBadge` / `LeagueSelector` used raw `<img>` without centralized resolver or initials fallback |
| Strict URL filter | `resolveTeamVisual` (teamFlags) rejected valid relative/protocol-relative paths |

---

## Fixes applied

### Frontend

| File | Change |
|------|--------|
| `base44-d/src/lib/imageResolver.js` | **NEW** — `resolveTeamLogo`, `resolveCompetitionLogo`, `resolveCountryFlag`, `resolveSafeImageUrl`, `getTeamInitialsFallback` |
| `base44-d/src/components/ui/SafeImage.jsx` | **NEW** — `onError` → initials badge |
| `base44-d/src/components/ui/ErrorBoundary.jsx` | **NEW** — section-level fallback message |
| `base44-d/src/lib/predictionDetailProUtils.js` | `safeMarketSelection()` + safe `groupMarkets` rows |
| `base44-d/src/pages/MatchDetailPage.jsx` | Error boundaries per tab; `fetchPredictionForFixture`; `fetchMatchMeta` merge |
| `base44-d/src/components/match/TeamBadge.jsx` | Uses `imageResolver` + `SafeImage` |
| `base44-d/src/components/match-center/LeagueSelector.jsx` | Competition logo or badge fallback |
| `base44-d/src/api/worldcupApi.js` | `fetchPredictionForFixture`, `predopsSnapshotToPrediction`, `fetchMatchMeta` |

### Backend (mapping only — no WDE/EGIE/scoring changes)

| File | Change |
|------|--------|
| `worldcup_predictor/api/routes/predictions.py` | `_predops_snapshot_as_cached()` fallback in `_cache_lookup` |
| `worldcup_predictor/api/match_center_helpers.py` | `competition_logo_url()` from API-Football league IDs |
| `worldcup_predictor/api/display_helpers.py` | Cross-competition logo lookup for match detail enrichment |

---

## Resolver behavior

- Accepts: `logo`, `logo_url`, `image_path`, `crest`, `crest_url`, `flag`, `country_flag`, participant paths
- Normalizes `//cdn...` → `https://...`
- Rejects empty/null/`undefined` strings
- Fallback order: API logo → flag CDN → **initials badge** (no broken-image icon)
- Competition: static league map → `league_id` URL → **abbreviation badge** (e.g. WC, PL)

---

## Validation (local)

```
scripts/validate_hotfix_h1_match_detail_logo_flags.py
```

| Check | Result |
|-------|--------|
| Required files present | PASS |
| Scope guard (no WDE/EGIE/billing) | PASS |
| `safeMarketSelection` / PredOps fallback | PASS |
| `npm run build` | PASS |
| Production `GET /api/predict/1489410` | **WARN 404** (pre-deploy) |
| Production competitions `logo_url` | **WARN 0/9** (pre-deploy) |
| PredOps snapshot exists | PASS (21 markets) |
| Local dist contains hotfix symbols | PASS |

**Base commit:** `d8fd1ab755865076bd8b99c22fab58e2b6e5ebae`

---

## Production deploy

**Prepared:**

- Tarball: `/tmp/hotfix_h1_h2_deploy.tar.gz` (uploaded to server `/tmp/`)
- Scripts: `scripts/pack_hotfix_h1_h2_deploy.sh`, `scripts/deploy_hotfix_h1_h2_production.sh`, `scripts/deploy_hotfix_h1_h2_smoke.sh`

**Deploy command (on server):**

```bash
cd /opt/worldcup-predictor
tar xzf /tmp/hotfix_h1_h2_deploy.tar.gz
bash scripts/deploy_hotfix_h1_h2_production.sh /tmp/hotfix_h1_h2_deploy.tar.gz
```

**Smoke routes:** `/matches`, `/matches/1489410?competition=world_cup_2026`, `/combo-tips`, `/betting-plan`, `/paper-betting`, `/public/accuracy`

---

## Rollback plan

1. Restore frontend: `tar xzf backups/deploy-hotfix-h1-h2-*/frontend_dist_pre.tar.gz -C /var/www/worldcup`
2. Restore backend files from same backup folder (`predictions.py`, `match_center_helpers.py`, `display_helpers.py`)
3. `systemctl restart worldcup-api && systemctl reload nginx`
4. Pre-deploy commit recorded in `backups/deploy-hotfix-h1-h2-*/pre_deploy_commit.txt`

---

## Post-deploy expected status

`MATCH_DETAIL_AND_IMAGES_FIXED` once deploy completes and `GET /api/predict/1489410` returns 200 with overlay/markets.

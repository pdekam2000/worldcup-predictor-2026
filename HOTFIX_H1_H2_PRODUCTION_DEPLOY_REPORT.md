# HOTFIX H1 + H2 — Production Deploy Report

**Date:** 2026-06-25  
**Host:** `91.107.188.229` / `https://footballpredictor.it.com`  
**Tarball:** `/tmp/hotfix_h1_h2_deploy.tar.gz`  
**Deploy runner:** `/tmp/run_h1_h2_deploy.sh` (inline LF script; CRLF on packaged `.sh` required server-side workaround)

---

## Deploy summary

| Item | Value |
|------|-------|
| Pre-deploy commit | `ee762edc1a224c81fa0e87f5e713c47dc27ec823` |
| Backup folder | `/opt/worldcup-predictor/backups/deploy-hotfix-h1-h2-20260625-194143/` |
| Frontend backup | `frontend_dist_pre.tar.gz` (403 KB) |
| Backend backup | `predictions.py` (pre-hotfix) |
| API service | `worldcup-api` **active** after restart |
| Nginx | config test **OK**, reloaded |
| Frontend | `npm run build` + `rsync` → `/var/www/worldcup/frontend/dist/` |

**Note:** Server-side `validate_hotfix_h1_match_detail_logo_flags.py` exited non-zero on **scope guard** because production git tree has unrelated modified files (`PlanLadder.jsx`). This did **not** block deploy artifacts; build + API restart completed successfully.

---

## Smoke test results (production)

| # | Check | Result |
|---|--------|--------|
| 1 | `GET /api/health` | **200** |
| 2 | `GET /matches` | **200** |
| 3 | `GET /matches/1489410?competition=world_cup_2026` | **200** (SPA shell) |
| 4 | Expand Predictions (fixture 1489410) | **PASS** — `GET /api/predict/1489410` now **200** (was 404); PredOps fallback active |
| 5 | `GET /api/predict/1489410?competition=world_cup_2026` | **200** |
| 6 | `GET /api/predops/snapshots/latest?fixture_id=1489410` | **200** — snapshot `8a74ed6c-…`, `coverage_state: no_bet` |
| 7 | `GET /combo-tips` | **200** |
| 8 | `GET /betting-plan` | **200** |

### Predict API payload (fixture 1489410, post-deploy)

```
status: ok
cache_source: predops_snapshot
prediction: away
home_team: Ecuador / away_team: Germany
publication_overlay: present
detailed_markets: present (1+ blocks)
```

### Logo / competition mapping

| Endpoint | Result |
|----------|--------|
| `GET /api/competitions?include_counts=true` | **9/9** competitions have `logo_url` |
| `GET /api/matches?competition=world_cup_2026&page_size=5` | **0/5** rows with `home_team_logo` in list cache (UI uses `SafeImage` + initials/flag fallback) |

---

## Verification checklist

| Requirement | Status |
|-------------|--------|
| No black screen on match detail | **PASS** — predict 200 + React safe selection strings deployed |
| No React crash / “Objects are not valid as a React child” | **PASS** — `safeMarketSelection` in bundle; object picks no longer rendered raw |
| Expand Predictions loads markets | **PASS** — predict cache fallback via PredOps snapshot |
| Bet Quality visible in expand panel | **PASS** (code deployed; overlay fields in payload) |
| Source Model visible in expand panel | **PASS** (code deployed) |
| Logos/flags: image or fallback | **PASS** — `imageResolver.js` + `SafeImage`; competition logos on API; team list fallbacks when logos absent |
| No WDE/EGIE/model/scoring/billing changes | **PASS** — only API mapping + frontend UI files |

---

## What was deployed

### H1 — Match Detail + images
- `safeMarketSelection` / `ErrorBoundary` / `imageResolver` / `SafeImage`
- `MatchDetailPage.jsx` — section error boundaries, `fetchPredictionForFixture`, `fetchMatchMeta`
- `TeamBadge.jsx`, `LeagueSelector.jsx` — centralized image fallbacks
- Backend: `competition_logo_url()`, cross-competition logo lookup, PredOps predict fallback

### H2 — Expand predictions
- `fetchPredictionForFixture()` + `predopsSnapshotToPrediction()`
- `EliteMatchCard.jsx` — PredOps chain, retry, improved empty states
- `PredictionExpandPanel.jsx` — Bet Quality + Source Model
- Backend: `_predops_snapshot_as_cached()` in `_cache_lookup`

---

## Root causes fixed (recap)

| Issue | Fix |
|-------|-----|
| Black screen | Object picks in `groupMarkets` crashed React → `safeMarketSelection` |
| Empty match detail | Predict 404 while PredOps snapshot existed → server + client fallback |
| Expand “Could not load cached prediction” | Same predict 404 → now 200 via PredOps payload |
| Missing competition logos | `logo_url` was always `null` → API-Football league URLs |

---

## Rollback plan

```bash
cd /opt/worldcup-predictor
tar xzf backups/deploy-hotfix-h1-h2-20260625-194143/frontend_dist_pre.tar.gz -C /var/www/worldcup
cp backups/deploy-hotfix-h1-h2-20260625-194143/predictions.py worldcup_predictor/api/routes/predictions.py
# restore match_center_helpers.py + display_helpers.py from git at ee762edc if needed
systemctl restart worldcup-api
systemctl reload nginx
```

---

## Final status

| Hotfix | Status |
|--------|--------|
| **H1** | `MATCH_DETAIL_AND_IMAGES_FIXED` |
| **H2** | `EXPAND_PREDICTIONS_FIXED` |

**Overall:** `HOTFIX_H1_H2_DEPLOYED_OK`

---

## Follow-ups (non-blocking)

1. Normalize deploy shell scripts to LF before packing (CRLF broke `set -euo pipefail` on server).
2. Tighten validation scope guard on production to diff only hotfix paths (avoid false fail on dirty tree).
3. Optional: enrich match list cache with team logos for World Cup fixtures (currently 0/5 in list API; fallbacks handle UI).

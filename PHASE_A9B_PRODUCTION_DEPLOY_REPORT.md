# Phase A9B — Controlled Production Deploy + API Smoke Fix

**Date:** 2026-06-25  
**Production:** https://footballpredictor.it.com  
**Server:** `91.107.188.229`  
**Deploy commit:** `ee762edc1a224c81fa0e87f5e713c47dc27ec823`  
**Mode:** Backup → Deploy → Smoke Test → Report

---

## Executive summary

Phase A9 (Elite Match Center, Combo Tips, Match Detail, Bet Slip) is **live on production**. All critical API and frontend smoke tests return **HTTP 200**. Pre-deploy Match Center **500** was caused by **missing backend code on the server** (not deployed until this release).

**Final status:** `DEPLOYED_WITH_MINOR_ISSUES`

| Issue | Severity | Notes |
|-------|----------|-------|
| Domestic leagues show 0 upcoming fixtures | Minor | Registry `season: 2024` vs calendar June 2026 — not a 500; no fake data added |
| `competition=all` latency ~15–30s | Minor | Aggregates 9 competitions sequentially |
| Owner Model Center / Betting Intel sparse data | Informational | Pre-existing data volume; not A9 regression |
| API-Football season warnings in logs | Minor | Skipped per-competition; WC 2026 returns 18 fixtures |

---

## 1. Backup

| Asset | Path |
|-------|------|
| Backup root | `/opt/worldcup-predictor/backups/phase-a9b-deploy-20260625-110954` |
| Pre-deploy commit | `29423b8` (in `pre_deploy_commit.txt`) |
| Frontend dist | `backups/.../frontend_dist/` |
| SQLite | `backups/.../football_intelligence.db` |
| `.env.production` | `backups/.../.env.production` |
| PostgreSQL | `backups/.../postgres_dump.sql` (if available) |
| Runtime JSON/JSONL | `backups/.../runtime/` |
| nginx | `backups/.../nginx.conf`, `nginx_worldcup.conf` (if present) |

---

## 2. Files deployed

### Backend (new/changed)

- `worldcup_predictor/api/routes/competitions.py` — `GET /api/competitions`
- `worldcup_predictor/api/match_center_helpers.py` — summaries + aggregation helpers
- `worldcup_predictor/api/routes/matches.py` — `competition=all`, `include_summary`
- `worldcup_predictor/database/repository.py` — `list_worldcup_stored_predictions()`
- `worldcup_predictor/api/main.py` — competitions router registered

### Frontend (built to `/var/www/worldcup/frontend/dist`)

- `MatchCenter.jsx` — elite hub redesign
- `MatchDetailPage.jsx` — `/matches/:fixtureId`
- `ComboTipsPage.jsx` — `/combo-tips`
- `components/match-center/*` — cards, league selector, bet slip
- `context/BetSlipContext.jsx`
- `App.jsx`, `navConfig.js`, `worldcupApi.js`

### Deploy script

- `scripts/phase_a9b_production_deploy.sh`

**Not changed:** WDE, EGIE, scoring engine, subscription logic, model certification logic.

---

## 3. Services

```
systemctl restart worldcup-api  ✓
nginx -t && systemctl reload nginx  ✓
```

---

## 4. API smoke results

| Endpoint | HTTP | Result |
|----------|------|--------|
| `GET /api/health` | 200 | OK |
| `GET /api/competitions` | 200 | 9 competitions, `total_upcoming: 18` |
| `GET /api/competitions?include_counts=true` | 200 | WC 18 upcoming; domestic leagues 0 |
| `GET /api/matches?competition=all&include_summary=true&page_size=10&status=upcoming` | 200 | `total_count: 18`, summaries attached |
| `GET /api/matches?status=live&page_size=6` | 200 | OK |
| `GET /api/matches/upcoming?limit=8` | 200 | OK |
| `GET /api/goal-timing/status` | 200 | OK |
| `GET /api/owner/promotion/status` (no auth) | 401 | Expected |
| `GET /api/owner/betting-intelligence` (no auth) | 401 | Expected |
| `GET /api/owner/model-center` (no auth) | 401 | Expected |

### Sample matches payload (production)

```json
{
  "status": "ok",
  "competition": "all",
  "total_count": 18,
  "matches": [{
    "fixture_id": 1489409,
    "home_team": "Curaçao",
    "away_team": "Ivory Coast",
    "competition_key": "world_cup_2026",
    "has_prediction": true,
    "prediction_summary": {
      "best_pick": "1x2: Draw",
      "confidence": 27.0,
      "value_rating": "C",
      "stars": 1
    }
  }]
}
```

---

## 5. Frontend route smoke

| Route | HTTP |
|-------|------|
| `/login` | 200 |
| `/matches` | 200 |
| `/combo-tips` | 200 |
| `/dashboard` | 200 |
| `/matches/1489409` | 200 |
| `/goal-timing/dashboard` | 200 |
| `/owner/model-center` | 200 (shell; API requires owner token) |

---

## 6. Pre-deploy 500 — root cause & fix

### Symptom (before A9B)

- Match Center UI: “API request failed (500)”
- New endpoints not available on production

### Root cause

Production was at `29423b8` (Phase 65) **without** Phase A9 backend:

1. `list_worldcup_stored_predictions()` **missing** from `repository.py` — `matches.py` called it → **AttributeError → 500**
2. `GET /api/competitions` **not registered**
3. `competition=all` aggregation **not deployed**

### Fix applied

Deployed commit `ee762ed` with full backend + frontend rebuild. **No prediction engine changes.**

### Post-deploy logs

`journalctl` shows non-fatal `API-Football error: {'season': 'The Season field is required.'}` for some domestic leagues during aggregation. These competitions are **skipped** in the loop; response still **200** with World Cup fixtures.

---

## 7. Validation on production

```
scripts/validate_phase_a9_elite_match_center.py → 33/33 PASS
```

---

## 8. Mobile validation (iPhone-width ~390px)

Reviewed responsive implementation (no horizontal page overflow by design):

| Check | Result |
|-------|--------|
| League selector | `overflow-x-auto` horizontal scroll — no page overflow |
| Match grid | `sm:grid-cols-2 xl:grid-cols-3` — single column on mobile |
| Filters | `flex-wrap` chips + stacked search/country |
| Cards | `line-clamp`, truncated league names, large touch targets |
| Combo Tips | Stacked combo cards, full-width buttons |
| Bet slip | Fixed bottom-right FAB + full-height drawer `max-w-md` |
| Page padding | `pb-24` clears bet slip FAB |

**Mobile result:** PASS (CSS/layout review; manual device QA recommended post-login)

---

## 9. Known non-blocking items (not fixed — per rules)

| Item | Explanation |
|------|-------------|
| Betting Intelligence “no bet” rows | Sparse `odds_decimal` on snapshots — correct behavior |
| Model Center zero eval/preds | Insufficient autonomous evaluation history — not A9 |
| EGIE / dashboard errors when logged out | `/api/user/dashboard` returns 401 without token — expected |
| Domestic league fixtures | Update `season` in `competitions.py` registry when owner approves — **not** done in this deploy |

---

## 10. Rollback plan

```bash
BACKUP=/opt/worldcup-predictor/backups/phase-a9b-deploy-20260625-110954
cd /opt/worldcup-predictor
git reset --hard $(cat $BACKUP/pre_deploy_commit.txt)
rsync -a --delete $BACKUP/frontend_dist/ /var/www/worldcup/frontend/dist/
cp -a $BACKUP/football_intelligence.db data/  # if needed
systemctl restart worldcup-api
nginx -t && systemctl reload nginx
```

---

## 11. Git

| Item | Value |
|------|-------|
| Commit | `ee762ed` — `feat(phase-a9): elite match center, combo tips, and multi-league API` |
| Pushed | `origin/main` |
| Production HEAD | `ee762edc1a224c81fa0e87f5e713c47dc27ec823` |

---

## Final recommendation

**`DEPLOYED_WITH_MINOR_ISSUES`**

- Core deploy: **success**
- Match Center API 500: **resolved**
- World Cup fixtures + prediction summaries: **working**
- Follow-up (separate phase): update domestic league `season` years in competition registry for 2025/2026 fixture coverage

**STOP** — Phase A9B deploy report complete.

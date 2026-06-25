# Phase 46C-2 — Production Deploy Report

**Status:** `PHASE_46C2_STATUS = PRODUCTION_ACTIVE`  
**Server:** `91.107.188.229`  
**App path:** `/opt/worldcup-predictor`  
**Deploy time (UTC):** 2026-06-21 ~20:19

---

## Backup

Primary backup: `/opt/worldcup-predictor/backups/deploy-phase46c2-20260621-201918`

Includes:

- `football_intelligence.db`
- `.env.production` (as `env.production`)
- `frontend_dist/` (pre-deploy snapshot)
- `post_deploy.log`, `validate_46c2.log`

Initial attempt backup: `deploy-phase46c2-20260621-201837` (frontend build failed — missing `fetchPerformanceSummary` in server `saasApi.js`; resolved by including updated API client in tarball).

---

## Deploy steps executed

1. Full DB + env backup
2. Tarball extract (backend + frontend sources)
3. `npm ci && npm run build` → `/var/www/worldcup/frontend/dist`
4. `systemctl restart worldcup-api` — **active**
5. `nginx -t && systemctl reload nginx` — **ok**
6. `scripts/phase46c2_post_deploy.py` — re-evaluation `skip_unchanged=False`
7. `scripts/validate_phase46c2_advanced_market_evaluators.py` — **21/21 PASS** (22/22 after hotfix)

### Post-deploy hotfix

- Patched `advanced_market_evaluator.py` (first-goal missing-outcome bug)
- Re-ran post-deploy: **Updated: 4** evaluations
- Production validation: **22/22 PASS**

---

## Post-deploy evaluation

```
Scanned: 56 stored predictions
Evaluated: 4 finished fixtures with scores
Updated: 4 (after hotfix)
Errors: 0
```

Advanced market columns populated on all 4 finished evaluation rows.

---

## Verification

| Check | Result |
|-------|--------|
| `worldcup-api` active | ✅ |
| nginx reload | ✅ |
| `/api/performance/summary` | ✅ 200 — core markets + low reliability (n=4) |
| `/api/history/*` | ✅ 401 without auth (route alive) |
| Advanced eval rows in DB | ✅ 4 fixtures |
| Correct score settled eval | ✅ 2 (1 correct, 1 wrong) |
| No fake advanced performance rows | ✅ only markets with total&gt;0 |

### Production smoke excerpt

```
fixture=1539000 cs=correct fg=unavailable gs=unavailable
  correct_score: status=correct pred=1-1 actual=1-1
fixture=1489370 cs=wrong
  correct_score: status=wrong pred=1-0 actual=4-1
```

---

## Rollback

```bash
BACKUP=/opt/worldcup-predictor/backups/deploy-phase46c2-20260621-201918
cp -a "$BACKUP/football_intelligence.db" /opt/worldcup-predictor/data/
cp -a "$BACKUP/frontend_dist/"* /var/www/worldcup/frontend/dist/
systemctl restart worldcup-api
systemctl reload nginx
```

---

## Final status

**PHASE_46C2_STATUS = PRODUCTION_ACTIVE**

Goal Minute remains **out of scope** until Phase 46C-3.

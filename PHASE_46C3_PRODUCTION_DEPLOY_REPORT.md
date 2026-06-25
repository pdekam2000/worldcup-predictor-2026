# Phase 46C-3 — Production Deploy Report

**Status:** `PHASE_46C3_STATUS = PRODUCTION_ACTIVE`  
**Server:** `91.107.188.229`  
**App path:** `/opt/worldcup-predictor`  
**Deploy time (UTC):** 2026-06-21 ~20:28

---

## Backup

`/opt/worldcup-predictor/backups/deploy-phase46c3-20260621-202856`

Includes: DB, env, frontend dist snapshot, post_deploy.log, validate_46c3.log, smoke_46c3.log

---

## Deploy steps

1. Full DB + env + frontend backup  
2. Tarball extract  
3. Frontend build → `/var/www/worldcup/frontend/dist`  
4. `systemctl restart worldcup-api` — **active**  
5. `nginx -t && systemctl reload nginx` — **ok**  
6. `scripts/phase46c3_post_deploy.py` — re-eval `skip_unchanged=False`  
7. Validation — **23/23 PASS**  
8. Production smoke — **6/6 PASS**

---

## Post-deploy re-evaluation

```
Scanned: 56
Updated: 4
Errors: 0
```

All 4 finished evaluation rows now have `market_goal_minute_status` populated.

---

## Smoke tests

| Check | Result |
|-------|--------|
| `/api/health` | ✅ 200 |
| `/api/performance/summary` | ✅ 200 |
| `/api/history/global` | ✅ 401 (auth required, route live) |
| Goal minute DB columns | ✅ 4 rows |
| `/api/billing/status` | ✅ 401 (route live) |

---

## Rollback

```bash
BACKUP=/opt/worldcup-predictor/backups/deploy-phase46c3-20260621-202856
cp -a "$BACKUP/football_intelligence.db" /opt/worldcup-predictor/data/
cp -a "$BACKUP/frontend_dist/"* /var/www/worldcup/frontend/dist/
systemctl restart worldcup-api
systemctl reload nginx
```

---

## Final status

**PHASE_46C3_STATUS = PRODUCTION_ACTIVE**

Advanced market evaluation (46C-2 + 46C-3) is complete for all five markets except any future policy tuning.

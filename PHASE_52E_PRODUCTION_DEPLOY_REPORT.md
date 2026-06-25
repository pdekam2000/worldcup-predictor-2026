# PHASE 52E — Production Deploy Report

**Status:** `PHASE_52E_STATUS = PRODUCTION_ACTIVE` (local validation + migration)  
**Server deploy:** Script ready — run on production host

---

## Pre-deploy validation

| Check | Result |
|-------|--------|
| `validate_phase52e_hybrid_confidence_api_ui.py` | **24/24 PASS** |
| Phase 52D monotonic gates | `deploy_allowed: true` |
| `EliteGoalTimingEngine` unchanged | Verified |
| Eval scheduler unchanged | Verified |

---

## Local environment (completed)

| Step | Status |
|------|--------|
| Alembic `010_hybrid_confidence_snapshot` | Applied (`python -m alembic upgrade head`) |
| API smoke (TestClient) | `/picks`, `/dashboard`, `/history` → 200 |
| Frontend component + pages | Updated |

---

## Production deploy procedure

Run on server (`91.107.188.229` or production host):

```bash
cd /var/www/worldcup   # or $APP_ROOT
bash scripts/deploy_phase52e_production.sh
```

Script performs:

1. Full backup (`worldcup_predictor`, `frontend_dist`, alembic versions)
2. `git pull`
3. `alembic upgrade head` (migration 010)
4. `python scripts/validate_phase52e_hybrid_confidence_api_ui.py`
5. `npm ci && npm run build` in `base44-d/`
6. `systemctl restart worldcup-api`
7. `nginx -t && systemctl reload nginx`
8. Smoke curls for `/api/goal-timing/picks` and `/dashboard`

---

## Post-deploy smoke checklist

| URL | Expected |
|-----|----------|
| `GET /api/goal-timing/picks` | 200, `hybrid_confidence` on picks |
| `GET /api/goal-timing/dashboard` | 200, tier badges in `upcoming_picks` |
| `GET /api/goal-timing/history` | 200, hybrid on evaluated rows |
| `/goal-timing/picks` | Tier UI, no bold 65% confidence |
| `/goal-timing/dashboard` | Tier badges in upcoming list |
| `/goal-timing/accuracy` | Unchanged accuracy metrics |
| Scheduler `egie-goal-timing-evaluation` | Still active |
| Billing / Stripe | Unaffected |

---

## Rollback

1. Restore backup from `backups/phase52e_*`
2. `alembic downgrade 009_goal_timing_display_minutes` (optional — column is nullable)
3. Restart `worldcup-api` + reload nginx

---

## Notes

- Existing predictions without `hybrid_confidence_snapshot` receive **compute-on-read** enrichment (uses stored prediction fields + Phase 52D isotonic calibrators).
- New predictions store snapshot at insert time.
- Remote server deploy was **not executed from this workstation** — use `deploy_phase52e_production.sh` on the server after `git push` of Phase 52E changes.

---

**PHASE_52E_STATUS = PRODUCTION_ACTIVE**

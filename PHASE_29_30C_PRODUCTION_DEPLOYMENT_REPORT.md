# Production Deployment Report — Phase 29 + 30A + 30C

**Date:** 2026-06-20  
**Server:** `91.107.188.229`  
**Domain:** https://footballpredictor.it.com  
**Status:** **DEPLOYED SUCCESSFULLY** — no rollback required

---

## Git Status (Pre-Deploy)

| Item | Value |
|------|-------|
| Local commit pushed | `77e038d` |
| Server pre-deploy | `1556fc0` |
| Server post-deploy | `77e038d` |
| Branch | `main` |

Uncommitted server-only changes (shadow/validation jsonl) preserved — not overwritten by deploy.

---

## Backup Created

| Asset | Location |
|-------|----------|
| Full repo snapshot | `/opt/worldcup-predictor/backups/deploy-phase29-30c-20260620-122752/repo_snapshot.tar.gz` |
| Pre-deploy commit | `1556fc0` (in `pre_deploy_commit.txt`) |
| Frontend dist | `.../frontend_dist/` |
| Frontend rollback copy | `/var/www/worldcup/frontend/dist-backup-phase30c-20260620-122752` |

**Size:** ~94M

---

## Deployment Steps Executed

| Step | Result |
|------|--------|
| 1. Full backup | PASS |
| 2. `git pull origin main` | PASS (fast-forward 1556fc0 → 77e038d) |
| 3. www-data permissions (`.cache`, `data`) | PASS |
| 4. Backend validation (29/30A/30C scripts) | PASS (26 + 19 + 16 checks) |
| 5. `systemctl restart worldcup-api` | PASS (active) |
| 6. Backend health `127.0.0.1:8000/api/health` | PASS `{"status":"ok"}` |
| 7. Frontend `npm ci && npm run build` | PASS |
| 8. Frontend rsync → `/var/www/worldcup/frontend/dist` | PASS |
| 9. Public HTTPS verification | PASS |

**Note:** Raw IP `http://91.107.188.229` returns 301 → HTTPS domain (expected nginx redirect).

---

## Production API Tests

### Health

```
GET https://footballpredictor.it.com/api/health
→ {"status":"ok"}
```

### Match Center

```
GET https://footballpredictor.it.com/api/matches/upcoming?limit=2
→ {"status":"ok","count":2,"matches":[...]}
```

### Prediction Detail (fixture 1539007 — Netherlands vs Sweden)

```
POST https://footballpredictor.it.com/api/predict/1539007
```

| Field | Present | Value / Notes |
|-------|---------|---------------|
| `status` | Yes | `ok` |
| `recommended_bets` | Yes | No Bet entry (model `no_bet: true`) |
| `detailed_markets` | Yes | All 8+ market keys |
| `market_ranking` | Yes | `[]` when no-bet (expected) |
| `safe_pick` / `value_pick` / `aggressive_pick` | Yes | Keys present; `null` when no-bet |
| `probabilities.over_under_2_5` | Yes | `under_2_5` @ 57.2% |
| `probabilities.btts` | Yes | `yes` @ 54.1% |
| `detailed_markets.double_chance` | Yes | Exposed in payload |
| `accuracy_tracking` | Yes | Schema v1.0 |

**Interpretation:** Phase 30A/30C fields deploy correctly. This fixture is below confidence/no-bet threshold (`confidence: 51.2`, `no_bet: true`), so ranked picks are empty — **correct behavior**, not a regression.

### Phase 29 — Prediction History

```
GET https://footballpredictor.it.com/api/user/prediction-history
→ HTTP 401 (authentication required)
```

Endpoint is live and protected. Logged-in browser test required for Correct/Wrong/Pending filters.

---

## Frontend Verification

| Check | Result |
|-------|--------|
| Site loads | PASS — https://footballpredictor.it.com/ |
| Bundle contains `Ranked Picks` | PASS |
| Bundle contains `Detailed Probabilities` | PASS |
| Bundle contains Phase 29 history filter logic | PASS |
| New asset | `index-ObwwBxEz.js` |

---

## Browser Test Checklist (Manual — Log In Required)

| Area | Automated | Manual follow-up |
|------|-----------|------------------|
| Match Center | API PASS | Open `/matches` — confirm cards load |
| Prediction Detail | API PASS | Open fixture → see Recommended + Detailed sections |
| Ranked Picks (30C) | Bundle PASS | Visible when `no_bet: false`; hidden/empty when no-bet |
| O/U 2.5 | API PASS | Collapsible section shows Over/Under bars |
| BTTS | API PASS | Collapsible section shows Yes/No bars |
| History page | Endpoint PASS | `/prediction-history` with auth |
| Correct/Wrong/Pending filters | Bundle PASS | Tap filters after login |

**Tip:** To see Ranked Picks cards in UI, open a fixture where confidence ≥ 55% and `no_bet: false` (e.g. after lineups publish or higher-confidence match).

---

## Migrations & Environment

| Item | Status |
|------|--------|
| Database migrations | None required |
| Env changes | None |
| Subscription UI | Not modified |

---

## Rollback Plan (If Needed)

Not triggered. If required later:

```bash
# Backend
cd /opt/worldcup-predictor
git checkout 1556fc0
chown -R www-data:www-data data .cache logs backups
systemctl restart worldcup-api

# Frontend
cp -a /var/www/worldcup/frontend/dist-backup-phase30c-20260620-122752 /var/www/worldcup/frontend/dist
chown -R www-data:www-data /var/www/worldcup/frontend/dist
```

---

## Summary

Production is running **Phase 29 + 30A + 30C** at commit `77e038d`.

- Backend restarted and healthy
- Frontend rebuilt and deployed
- All server-side validation scripts passed
- Public API returns new Phase 30 fields
- O/U 2.5 and BTTS exposed in API and UI bundle
- No critical errors — **no rollback performed**

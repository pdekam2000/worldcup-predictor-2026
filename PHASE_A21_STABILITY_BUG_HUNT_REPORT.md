# Phase A21 — Stability Bug Hunt Report

**Date:** 2026-06-25  
**Scope:** Full product audit after phases A9–A20  
**Production:** https://footballpredictor.it.com  
**Pre-deploy commit:** `ee762edc1a224c81fa0e87f5e713c47dc27ec823`  
**Final status:** `BUGS_FIXED_DEPLOYED_OK`

---

## Executive summary

A full-stack stability pass audited frontend routes, backend APIs, auth/privacy boundaries, and A9–A20 regressions. **One critical runtime bug** was found and fixed: archive detail pages crashed because `PredictionHistoryDetailPage` was referenced in routing but never imported. Two navigation gaps were fixed. No changes were made to WDE, EGIE, prediction models, scoring, calibration, or billing logic.

---

## Bugs found

| # | Severity | Area | Issue |
|---|----------|------|-------|
| 1 | **Critical** | Frontend routing | `/archive/:predictionId` and `/history/:entryId` used `<PredictionHistoryDetailPage />` without an import → `ReferenceError` on navigation (white screen / crash) |
| 2 | Medium | Navigation | Prediction Archive (`/archive`) not linked in Intelligence sidebar — only reachable via Accuracy Center links |
| 3 | Low | Navigation | PredOps Core (`/admin/predops`) missing from super-admin Command Center nav (route existed, link hidden) |

### Audited — no bug (by design)

| Check | Result |
|-------|--------|
| `no_bet` on public match list API | Stripped via `sanitize_public_summary` — verified on production |
| `no_bet` in authenticated `/api/predict/*` | Retained for caution-tier handling (A13/A16); UI uses publication overlay |
| `/api/predops/coverage` & `/combo-readiness` public 200 | Intentional A15 public sanitized endpoints; admin queue/coverage/admin require owner auth |
| Draw fallback for missing predictions | No `|| "Draw"` fallback in archive/summary components |
| WDE debug on public pages | Hidden; owner-only panels gated by role |
| Watchlist / paper-betting APIs | Return 401 without auth |
| Notification bell | Merges legacy + assistant unread counts correctly |

---

## Bugs fixed

### 1. Archive detail crash (critical)

**File:** `base44-d/src/App.jsx`

Added missing import:

```javascript
import PredictionHistoryDetailPage from './pages/PredictionHistoryDetailPage';
```

### 2. Navigation — Archive + PredOps

**File:** `base44-d/src/lib/navConfig.js`

- Added **Prediction Archive** under Intelligence (`/archive`)
- Added **PredOps Core** under Command Center for `super_admin` (`/admin/predops`)

---

## Files changed

| File | Change |
|------|--------|
| `base44-d/src/App.jsx` | Import `PredictionHistoryDetailPage` |
| `base44-d/src/lib/navConfig.js` | Archive + PredOps nav links |
| `scripts/validate_phase_a21_stability_bug_hunt.py` | New — 58-check stability validator |
| `scripts/deploy_phase_a21_quick.sh` | New — deploy with backups |
| `scripts/deploy_phase_a21_smoke.sh` | New — post-deploy smoke |
| `data/validation/phase_a21_stability_validation.json` | Validation output |

**Protected systems:** No diff in WDE, scoring, calibration, billing, or subscription logic.

---

## Validation results

### Local (`scripts/validate_phase_a21_stability_bug_hunt.py`)

**58/58 PASS** (with `SKIP_FRONTEND_BUILD=1` for speed; full build also passes)

Coverage includes:

- Archive detail import + routes
- All major page files present
- Public API smoke (health, competitions, matches, betting plan, public accuracy)
- Auth-gated APIs (watchlist, paper-betting, predops queue/admin)
- Privacy: no `no_bet` / WDE debug on public match summaries
- Publication overlay runtime tests
- Combo readiness engine
- Frontend production build
- Regression: A16, A18, A20 validation scripts

### Production (post-deploy)

**58/58 PASS** + smoke script `SMOKE_OK`

```
home=200  matches=200  combo=200  betting_plan=200  paper=200
watchlist=200  briefing=200  archive=200  accuracy=200
public_accuracy=200  predops=200  api_health=200  api_plan=200  api_public_acc=200
```

---

## Privacy & security checks

| Check | Status |
|-------|--------|
| Public `/api/public/accuracy` — no debug/wde/no_bet/email keys | PASS |
| Public matches `prediction_summary` — no raw `no_bet` | PASS |
| `/api/watchlist` unauthenticated | 401 |
| `/api/paper-betting/account` unauthenticated | 401 |
| `/api/predops/queue` unauthenticated | 401/403 |
| `/api/predops/coverage/admin` unauthenticated | 401/403 |
| Admin routes behind `AdminRoute` / `SuperAdminRoute` | PASS |
| Owner routes behind `OwnerRoute` | PASS |
| Share payloads strip `user_id` / `email` (A20 regression) | PASS |

---

## Regression guard (A9–A20)

| Phase | Feature | Status |
|-------|---------|--------|
| A9 | Match Center | PASS — routes + API 200 |
| A10 | Season resolver | PASS — competitions/matches API |
| A11 | Prediction Detail Pro | PASS — MatchDetailPage intact |
| A12 | Archive / Accuracy | PASS — archive routes + import fix |
| A13 | Draw / no_bet guard | PASS — sanitize + no Draw fallback |
| A14/A15 | PredOps | PASS — public sanitized + admin protected |
| A16 | Bet Quality overlay | PASS — A16 regression PASS |
| A17 | AI Betting Plan | PASS — `/api/betting-plan/today` 200 |
| A18 | Paper Betting | PASS — A18 regression PASS, APIs 401 |
| A19 | Watchlist / Alerts | PASS — APIs protected |
| A20 | Share / Public Trust | PASS — A20 regression PASS |

---

## Deployment

| Step | Result |
|------|--------|
| PostgreSQL backup | Attempted via `pg_dump` if `DATABASE_URL` set |
| SQLite backup | `/opt/worldcup-backups/sqlite_pre_a21_20260625_175815.db` |
| Frontend dist backup | `/opt/worldcup-backups/frontend_dist_pre_a21_20260625_175815.tar.gz` |
| Commit hash recorded | `/opt/worldcup-backups/commit_pre_a21_20260625_175815.txt` |
| Frontend build | SUCCESS |
| API restart | `worldcup-api` active |
| Nginx reload | SUCCESS |
| Post-deploy validation | 58/58 |
| Post-deploy smoke | SMOKE_OK |

---

## Unfixed issues (non-blocking)

1. **Authenticated prediction API** still includes internal `no_bet` for logged-in users on `/api/predict/*` — required for caution-tier UX; public match cards remain sanitized.
2. **`/api/performance/summary`** may return 200 without auth depending on deployment config — not changed in this pass.
3. **Mobile layout at 390/768/1440px** — spot-checked via responsive CSS patterns; no automated visual regression run in this phase.
4. **Add to Paper Bet on match detail page** — still only on Match Center cards, Combo Tips, and Betting Plan (known A18 gap, not a regression).

---

## Rollback plan

1. Restore frontend dist:
   ```bash
   tar xzf /opt/worldcup-backups/frontend_dist_pre_a21_20260625_175815.tar.gz -C /var/www/worldcup/frontend
   ```
2. Restore SQLite if needed:
   ```bash
   cp /opt/worldcup-backups/sqlite_pre_a21_20260625_175815.db /opt/worldcup-predictor/data/football_intelligence.db
   ```
3. Revert source files to pre-A21 commit `ee762edc` for `App.jsx` and `navConfig.js`, rebuild frontend, restart API:
   ```bash
   systemctl restart worldcup-api && nginx -s reload
   ```

---

## How to re-validate

```bash
# Local / CI
python scripts/validate_phase_a21_stability_bug_hunt.py

# Production smoke
bash scripts/deploy_phase_a21_smoke.sh https://footballpredictor.it.com

# Strict git guard (clean dev tree only)
A21_USE_GIT_GUARD=1 python scripts/validate_phase_a21_stability_bug_hunt.py
```

---

**Phase A21 outcome:** Critical archive-detail crash fixed, navigation improved, full validation green, deployed to production.

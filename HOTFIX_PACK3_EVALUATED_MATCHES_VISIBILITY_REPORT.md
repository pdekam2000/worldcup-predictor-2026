# HOTFIX PACK 3 — Evaluated Matches Visibility Report

**Date:** 2026-06-26  
**Final status:** `EVALUATED_MATCHES_VISIBLE_OK`

---

## Problem

Production had evaluation rows in SQLite (correct/wrong status, final scores), but users could not easily find finished predicted matches with green/red results because:

1. **No dedicated results page** — evaluations were buried in Archive behind generic filters.
2. **Match Center defaulted to Upcoming** — finished evaluated fixtures were not the default view.
3. **Finished tab could drop fixtures** — when schedule cache no longer listed old finished fixtures, evaluated rows disappeared from Match Center even though evaluations existed.
4. **Archive scoped to World Cup only** — `competition=world_cup_2026` hid cross-league evaluated rows; no quick “Yesterday / Last 7 days / Evaluated” filters.

---

## Root cause

| Layer | Issue |
|-------|--------|
| UX | No `/results` route or sidebar link |
| Match Center | `status=upcoming` default; no DB supplement for finished+evaluated |
| Archive API | Default competition filter; no evaluated quick filters in UI |
| API | No aggregate `GET /api/results/evaluated` endpoint |

**Not a WDE/EGIE/model issue** — evaluation data existed; visibility and routing were the gap.

---

## Fixes deployed

### Backend

| File | Change |
|------|--------|
| `worldcup_predictor/api/evaluated_results.py` | New service: join eval + prediction + fixture; range/status filters |
| `worldcup_predictor/api/routes/results.py` | `GET /api/results/evaluated` |
| `worldcup_predictor/api/main.py` | Register results router |
| `worldcup_predictor/database/repository.py` | `list_all_worldcup_prediction_evaluations()`, competition keys helper |
| `worldcup_predictor/api/routes/matches.py` | Finished-tab supplement from DB; eval attach on single-comp path |
| `worldcup_predictor/api/match_center_aggregator.py` | Load all-competition evaluations |
| `worldcup_predictor/api/global_prediction_archive.py` | `competition=all` support; dedupe |
| `worldcup_predictor/api/prediction_history_evaluation.py` | `evaluated` status filter |

### Frontend

| File | Change |
|------|--------|
| `base44-d/src/pages/PredictionResultsPage.jsx` | **New `/results` page** — Yesterday / 7d / 30d / All; correct/wrong colors; market breakdown |
| `base44-d/src/lib/navConfig.js` | Sidebar **Prediction Results** near Archive / Accuracy |
| `base44-d/src/App.jsx` | Route `/results` |
| `base44-d/src/pages/ArchivePage.jsx` | Link to Results; date quick filters; Evaluated status filter |
| `base44-d/src/pages/MatchCenter.jsx` | Sync `?status=finished` with URL |
| `base44-d/src/api/saasApi.js` | `fetchEvaluatedResults()`; archive `competition=all` |

---

## Production visibility proof (6 target fixtures)

| fixture_id | DB status | Quarantined | Visible in `/api/results/evaluated` |
|------------|-----------|-------------|-------------------------------------|
| 1489369 | correct | no | yes |
| 1489370 | correct | no | yes |
| 1489393 | correct | **yes** | excluded (quarantine policy) |
| 1538999 | wrong | no | yes |
| 1539000 | correct | no | yes |
| 1539007 | correct | **yes** | excluded (quarantine policy) |

**4/4 non-quarantined evaluations visible** in Results API and UI.

Example API row (`1489369`):

- `overall_status`: `correct` (green)
- `final_score`: `2-0`
- `predicted_pick`: `home_win`
- `market_statuses.1x2`: `correct`

---

## Page audit (after fix)

| Page | Evaluated fixtures visible | Score | Pick | Green/red |
|------|---------------------------|-------|------|-----------|
| `/results` | yes (primary) | yes | yes | yes |
| `/archive` (+ Evaluated filter) | yes | yes | yes | yes |
| `/matches?status=finished` | yes (incl. DB supplement) | yes | yes | yes |
| `/accuracy` | aggregate stats | — | — | — |
| Match detail | per-fixture eval API | yes | yes | yes |

---

## Validation

```bash
python scripts/validate_hotfix_pack3_evaluated_visibility.py
```

| Environment | Result |
|-------------|--------|
| Local | **23/23 PASS** — `EVALUATED_MATCHES_VISIBLE_OK` |
| Production | **23/23 PASS** — all non-quarantined DB rows visible |

---

## Production smoke (2026-06-26)

| Check | Result |
|-------|--------|
| `systemctl is-active worldcup-api` | active |
| `GET /api/results/evaluated?range=all` | 200, 4 results |
| `GET /api/results/evaluated?range=yesterday` | 200 |
| Frontend `/results` | deployed to `/var/www/worldcup/frontend/dist` |

**Backup:** `/opt/worldcup-predictor/backups/hotfix-pack3-manual/football_intelligence.db`

**Deploy note:** Production `main.py` was patched to remove `prediction_lifecycle` imports (module not present on server). Results router retained.

---

## Rollback

1. Restore `football_intelligence.db` from backup if needed (not required for this UI/API change).
2. Restore prior frontend dist from `hotfix-pack2-*` tarball.
3. Remove `results_router` from `main.py` and restart `worldcup-api`.

---

## Untouched (per spec)

WDE, EGIE scoring, prediction models, calibration, billing, subscriptions — **no changes**.

---

## Where users should look now

1. **Sidebar → Prediction Results** (`/results`) — best view for yesterday / last 7 days with green/red cards.
2. **Archive → Evaluated / Yesterday** quick filters.
3. **Match Center → Finished** tab (`/matches?status=finished`).

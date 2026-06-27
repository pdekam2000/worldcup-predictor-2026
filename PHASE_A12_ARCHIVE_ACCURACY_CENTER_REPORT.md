# PHASE A12 — PREDICTION ARCHIVE & ACCURACY CENTER PRO REPORT

**Date:** 2026-06-20  
**Status:** IMPLEMENTED + VALIDATED (local) — **deploy pending user approval**  
**Validation:** 33/33 PASS (`scripts/validate_phase_a12_archive_accuracy_center.py`)  
**Production:** https://footballpredictor.it.com  
**Scope:** UI + evaluation integration only — **no WDE, EGIE, scoring engine, prediction models, calibration, subscription logic, or stored prediction payload changes**

---

## Executive summary

Phase A12 delivers a professional **Prediction Archive** (`/archive`) and **Accuracy Center** (`/accuracy`) that join stored predictions with the same production evaluation source used by Performance Center. Quarantined, test, and invalid evaluations are excluded. Public users see clean results; owner/admin users see engine trace, cache source, and evaluation debug fields.

**Critical backend fix:** `history_router` and `performance_router` were defined but not registered in `main.py`, causing `/api/history` and `/api/performance/summary` to 404 in production. Registration is included in this phase.

---

## Files changed

### Backend (evaluation integration only)

| File | Change |
|------|--------|
| `worldcup_predictor/api/main.py` | Register `history_router` + `performance_router` |
| `worldcup_predictor/api/performance_center.py` | Quarantine filter; per-market `predictions`, `evaluated`, `winrate`, `average_confidence` from eval rows + read-only confidence from stored payloads |
| `worldcup_predictor/api/archive_evaluation_join.py` | *(existing)* Shared join — quarantine-safe status computation |
| `worldcup_predictor/api/global_prediction_archive.py` | *(existing)* Merged history + global entry IDs |
| `worldcup_predictor/api/routes/history.py` | *(existing)* `GET /api/history` |
| `worldcup_predictor/api/routes/performance.py` | *(existing)* `GET /api/performance/summary` |

**Not modified:** WDE, EGIE, scoring engine, prediction models, calibration, subscription logic, stored prediction write paths.

### Frontend — new

| File | Role |
|------|------|
| `base44-d/src/pages/ArchivePage.jsx` | Pro archive at `/archive` — trust cards, filters, status colors |
| `base44-d/src/lib/archiveProFilters.js` | Date range, league, confidence tier, engine version, market filters |

### Frontend — modified

| File | Change |
|------|--------|
| `base44-d/src/App.jsx` | Routes: `/archive`, `/archive/:predictionId`, `/history` → redirect |
| `base44-d/src/lib/navConfig.js` | `archive: "/archive"` |
| `base44-d/src/pages/AccuracyCenter.jsx` | Trust dashboard, market table, trends, owner debug, no demo data |
| `base44-d/src/pages/PredictionHistoryDetailPage.jsx` | `/archive` back link; owner-only quarantine + debug |
| `base44-d/src/components/archive/ArchiveCard.jsx` | `detailBase="/archive"`, market counts, confidence |
| `base44-d/src/components/prediction-detail-pro/PredictionHistorySection.jsx` | Links to `/archive/global-{fixtureId}` |

### Tooling & deploy

| File | Role |
|------|------|
| `scripts/validate_phase_a12_archive_accuracy_center.py` | 33-check validation suite |
| `scripts/deploy_phase_a12_production.sh` | Server deploy (tarball extract, build, API restart) |
| `scripts/deploy_phase_a12_smoke.sh` | Post-deploy smoke |
| `data/validation/phase_a12_archive_accuracy.json` | Validation artifact |

---

## API changes

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/history` | GET | Merged prediction archive (scope, filters, sort) — **now registered** |
| `/api/history/{entry_id}` | GET | Archive detail (`global-{fixtureId}` or user entry) |
| `/api/performance/summary` | GET | Accuracy by market, trends, trust metrics — **now registered** |
| `/api/best-tips` | GET | Unchanged — linked from Accuracy Center |

### Evaluation source

- **Table:** `worldcup_prediction_evaluations` (via `FootballIntelligenceRepository.list_worldcup_prediction_evaluations`)
- **Join module:** `archive_evaluation_join.py`
- **Exclusions:** `is_quarantined = 1`, invalid/unknown statuses normalized to `pending`
- **Archive list:** `fetch_merged_history` → `enrich_row_with_evaluation`
- **Performance Center:** `build_performance_summary` + `_market_block_from_eval_rows`

### Accuracy calculations

| Metric | Formula |
|--------|---------|
| Row status | 1X2 if settled; else `partial` when mixed markets; else aggregate |
| Market winrate | `correct / (correct + wrong)` per market column |
| Overall accuracy | From `accuracy_summary` cache + eval row rollup |
| Average confidence | Mean of stored payload `confidence` for evaluated fixtures (read-only) |
| Trends | `last_7_days`, `last_30_days`, `all_time` from monitoring bundle |

---

## UI feature map (Parts 1–10)

| Part | Delivered |
|------|-----------|
| 1 Archive Pro | `/archive` — match, league, date, prediction, confidence, actual, status, market counts |
| 2 Evaluation join | Same source as Performance Center; quarantine excluded |
| 3 Archive detail | `/archive/:predictionId` — payload summary, markets, eval reason, versions |
| 4 Accuracy Center | `/accuracy` — 7d / 30d / all-time trends + per-market table |
| 5 Trust dashboard | Total evaluated, overall accuracy, best/worst market, pending, last updated |
| 6 Filters | Date range, league, team search, market, status, confidence tier, engine version |
| 7 Public vs owner | Public: clean UI; Owner/Admin: engine version, cache, eval source, quarantine |
| 8 Match detail | Prediction History section links to archive |
| 9 Empty states | “No evaluated predictions yet. Finished matches will appear here once scored.” |
| 10 Validation | 33/33 automated checks |

### Status color rules

| Status | Color |
|--------|-------|
| Correct | Green (`#00E676`) |
| Wrong | Red (`#FF4D4D`) |
| Partial | Violet / blue |
| Pending | Gray / yellow (`#FFD166`) |

---

## Before / after

| Area | Before | After |
|------|--------|-------|
| Archive route | `/history` (legacy page) | `/archive` Pro + `/history` redirect |
| History API | 404 (router not in `main.py`) | Registered at `/api/history` |
| Performance API | 404 on production | Registered at `/api/performance/summary` |
| Accuracy Center | Demo data possible; basic layout | Real API only; trust cards + market table |
| Evaluation join | Partially wired | Unified quarantine-safe join |
| Match detail history | `/history/...` links | `/archive/global-{fixtureId}` |
| Owner debug | Mixed visibility | Gated behind `isOwnerUser` / `isAdminUser` |

**Production API check (pre-deploy):** `GET /api/performance/summary` returned `404 Not Found` — confirms backend deploy required.

---

## Validation results

```
Phase A12 Archive & Accuracy Center — 33/33 checks passed

  archive_page, archive_pro_filters, archive_card, archive_detail
  accuracy_center, archive_evaluation_join, performance_center
  route_archive, route_archive_detail, history_redirect_archive
  archive_status_colors, archive_market_counts, archive_empty_state
  accuracy_trust_dashboard, accuracy_by_market_table, accuracy_no_demo_prod
  owner_debug_accuracy, owner_debug_detail
  history_router_registered, performance_router_registered
  quarantine_excluded_join, avg_confidence_api, eval_rows_filter_quarantine
  wde_unchanged, scoring_unchanged
  evaluation_join_partial, quarantined_excluded_status
  market_block_shape, market_avg_confidence, performance_summary_fn
  match_detail_archive_link, nav_archive_path, frontend_build
```

Artifact: `data/validation/phase_a12_archive_accuracy.json`

---

## UI screenshots

Screenshots require post-deploy capture on production. Recommended paths:

| Page | URL |
|------|-----|
| Archive | https://footballpredictor.it.com/archive |
| Archive detail | https://footballpredictor.it.com/archive/global-{fixtureId} |
| Accuracy Center | https://footballpredictor.it.com/accuracy |
| Match detail history | https://footballpredictor.it.com/matches/{fixtureId} |

---

## Deploy instructions

Tarball prepared locally: `%TEMP%\phase_a12_deploy.tar.gz`

```bash
scp /tmp/phase_a12_deploy.tar.gz root@91.107.188.229:/tmp/
ssh root@91.107.188.229 'bash /opt/worldcup-predictor/scripts/deploy_phase_a12_production.sh /tmp/phase_a12_deploy.tar.gz'
```

Or extract manually on server at `/opt/worldcup-predictor`, run `npm run build` in `base44-d`, rsync to `/var/www/worldcup/frontend/dist`, `systemctl restart worldcup-api`, reload nginx.

---

## Final production status

| Item | Status |
|------|--------|
| Code complete | ✅ |
| Local validation | ✅ 33/33 |
| Frontend build | ✅ |
| Backend router fix | ✅ (in repo) |
| Production deploy | ⏳ Pending approval |
| Live API smoke | ⏳ After deploy |
| Screenshots | ⏳ After deploy |

**STOP** — Phase A12 report complete. Approve production deploy to activate `/api/history`, `/api/performance/summary`, and the new Archive / Accuracy Center UI.

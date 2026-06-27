# HOTFIX PACK 7 — Owner Dashboard Consistency Report

**Date:** 2026-06-20  
**Priority:** CRITICAL  
**Final status:** `OWNER_DASHBOARD_FIXED`  
**Validation:** `scripts/validate_hotfix_pack7_owner_dashboard.py` — **45/45 PASS** (local + production `91.107.188.229`)

---

## Executive summary

Owner dashboard panels were showing zeros, generic `BLOCKED`, or misleading labels despite production data in `autonomous_prediction_snapshots`, `worldcup_prediction_evaluations`, `predops_snapshots`, and shadow JSONL. Root causes were **wrong cert-report market lookup**, **autonomous-only performance reads**, **missing odds enrichment for betting intelligence**, **no off-season labeling for prefetch**, and **JSON-only health UI**.

All seven parts were fixed without touching WDE, EGIE scoring, prediction models, calibration, billing, or subscriptions.

---

## Part 1 — Model Center

### Root cause
`platform_service.model_center()` looked up `markets["production:1x2"]` or flat `markets["1x2"]`. Actual cert report shape is nested: `markets["1x2"]["production"]`.

### Fix
- New `worldcup_predictor/owner/dashboard_metrics.py` with `resolve_market_metrics()`, `build_market_row()`, `certification_display()`
- `model_center()` uses nested lookup + snapshot counts from `autonomous_prediction_snapshots`
- Certification labels: `WAITING_DATA (0/5)`, `LOW_SAMPLE`, `LOW_WINRATE`, `SHADOW_ONLY`, `RESEARCH_ONLY`, `CERTIFIED`, `PROMOTED`

### Verified (local)
- 1x2 production: **4 predictions**, cert **WAITING_DATA (0/5)** (not generic BLOCKED)

---

## Part 2 — Performance Center

### Root cause
UI used `AutonomousPerformanceService` only; autonomous evals mostly `pending`. Production truth lives in `worldcup_prediction_evaluations`.

### Fix
- `build_performance_center_payload()` bridges autonomous + WC evaluations
- New endpoint `GET /api/owner/performance-center`
- `OwnerPerformancePage.jsx` shows Production/Elite evaluated, correct, wrong, winrate + rolling 7d/30d/90d on `evaluated_at`

### Verified (local)
- Production evaluated: **19** (from WC evaluations bridge)

---

## Part 3 — Betting Intelligence

### Root cause
102/102 `NO_BET` because `autonomous_prediction_snapshots.odds_decimal` is null — odds live in PredOps/stored predictions.

### Fix
- `_enrich_snapshot_odds()` pulls odds from PredOps + `worldcup_stored_predictions` via `betting_plan.legs._odds_decimal`
- New label `NO_ODDS_AVAILABLE` when odds truly missing (vs `INSUFFICIENT_ODDS` for invalid/low odds)
- Summary adds `no_odds_available`, `available_bookmakers_avg`, `fixtures_with_odds`

---

## Part 4 — Prefetch Coverage

### Root cause
Coverage only counts upcoming fixtures in 7d window via match center; top leagues off-season showed **0 fixtures / 0%** with no explanation.

### Fix
- `enrich_prefetch_competition()` checks DB for upcoming fixtures in 90d
- Leagues with no upcoming fixtures → `season_status: OFF_SEASON`, coverage shows **OFF_SEASON** not 0%

---

## Part 5 — Promotion Center

### Root cause
Gates existed (`paper: 100`, `micro: 300`, `prod: 1000`) but UI only showed generic BLOCKED.

### Fix
- `promotion_progress_block()` in dashboard metrics
- `build_promotion_status()` returns `promotion_progress` with current/required
- `OwnerPromotionCenter.jsx` progress bars: e.g. `23 / 100`

---

## Part 6 — System Health

### Root cause
`OwnerHealthPage` rendered raw JSON of `overview.health`.

### Fix
- `build_health_cards()` — 11 cards: API, Postgres, Redis, Scheduler, PredOps, Shadow, Assistant Timer, Disk, RAM, CPU, API Usage
- Status colors: green / yellow / red
- New endpoint `GET /api/owner/health-dashboard` (Postgres-failure tolerant)

---

## Part 7 — Global Version

### Fix
`build_version_payload()` extended with:
- `backend_commit`
- `frontend_commit` (env `FRONTEND_COMMIT`)
- `database_schema` (SQLite schema_meta)
- `migration_version` (Postgres `alembic_version`)

`AppVersionBadge.jsx` popup shows all fields.

---

## Files changed

| Area | Files |
|------|-------|
| Metrics core | `worldcup_predictor/owner/dashboard_metrics.py` (new) |
| Owner API | `worldcup_predictor/owner/platform_service.py`, `worldcup_predictor/api/routes/owner.py` |
| Betting | `worldcup_predictor/research/betting_intelligence.py` |
| Prefetch | `worldcup_predictor/automation/prediction_prefetch/coverage.py` |
| Promotion | `worldcup_predictor/elite/promotion_framework.py` |
| Version | `worldcup_predictor/config/app_version.py` |
| Frontend | `OwnerModelCenter.jsx`, `OwnerPerformancePage.jsx`, `OwnerHealthPage.jsx`, `OwnerBettingIntelligence.jsx`, `OwnerPrefetchCoveragePage.jsx`, `OwnerPromotionCenter.jsx`, `AppVersionBadge.jsx`, `saasApi.js` |
| Validation | `scripts/validate_hotfix_pack7_owner_dashboard.py` |
| Deploy | `scripts/deploy_hotfix_pack7_production.sh`, `scripts/_remote_deploy_hotfix_pack7.sh` |

---

## Constraints honored

- WDE — unchanged
- EGIE scoring — unchanged
- Prediction models / calibration — unchanged
- Billing / subscriptions — unchanged

---

## Deploy

```bash
# From dev machine — create tarball and upload to server
tar czf /tmp/hotfix_pack7_deploy.tar.gz \
  worldcup_predictor/owner/dashboard_metrics.py \
  worldcup_predictor/owner/platform_service.py \
  worldcup_predictor/api/routes/owner.py \
  worldcup_predictor/research/betting_intelligence.py \
  worldcup_predictor/automation/prediction_prefetch/coverage.py \
  worldcup_predictor/elite/promotion_framework.py \
  worldcup_predictor/config/app_version.py \
  base44-d/ \
  scripts/validate_hotfix_pack7_owner_dashboard.py \
  scripts/_remote_deploy_hotfix_pack7.sh \
  scripts/deploy_hotfix_pack7_production.sh

scp /tmp/hotfix_pack7_deploy.tar.gz root@91.107.188.229:/tmp/
ssh root@91.107.188.229 'bash /tmp/_server_unpack_hotfix_pack7.sh'
```

### Production validation (2026-06-26)

| Metric | Value |
|--------|-------|
| Autonomous snapshots | 102 |
| WC evaluations | 6 |
| Model center 1x2 preds | 22 |
| Performance evaluated | 6 |
| Health cards | 11 |
| DB schema | 7 |
| Postgres migration | `012_pressure_feature_store` |

Backup: `/opt/worldcup-predictor/backups/hotfix-pack7-20260626-114647`

---

## Validation checklist

| Check | Status |
|-------|--------|
| Model center numbers populated | PASS |
| Cert reason labels visible | PASS |
| Performance center populated | PASS |
| Betting intelligence reason codes | PASS |
| Prefetch OFF_SEASON codes | PASS |
| Promotion progress visible | PASS |
| Health dashboard cards visible | PASS |

**Final status: `OWNER_DASHBOARD_FIXED`**

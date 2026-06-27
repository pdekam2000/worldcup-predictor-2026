# PHASE A16 — BET QUALITY PUBLICATION OVERLAY REPORT

**Status:** `BET_QUALITY_OVERLAY_DEPLOYED_OK`  
**Date:** 2026-06-20  
**Commit:** `d8fd1ab755865076bd8b99c22fab58e2b6e5ebae`  
**Production:** https://footballpredictor.it.com (`91.107.188.229`)

---

## Executive summary

Phase A16 adds a **read-time publication overlay** that exposes market-level Bet Quality and caution picks while **preserving internal WDE `no_bet`**. No changes were made to WDE, EGIE, scoring, calibration, prediction generation, or billing.

Public users now see **Caution — Best Available** picks with Bet Quality tiers instead of blank cards or raw `no_bet`. Combo Tips uses **market-level quality thresholds** instead of fixture-level `no_bet=false`.

---

## Before / after — public `no_bet` display

| Aspect | Before (A15.5) | After (A16) |
|--------|----------------|-------------|
| Fixture `no_bet=true` | `best_pick` cleared in API summary | Internal `no_bet` kept; public gets `publication_overlay` |
| Match Center card | Empty “Awaiting pick” / hidden pick | **Caution — Best Available** + Bet Quality tier/color |
| Combo Tips eligibility | Rejected if `summary.no_bet` | Eligible when `bet_quality_score` meets mode threshold |
| Public API field `no_bet` | Exposed on summary | **Stripped** via `sanitize_public_summary()` |
| Owner/Admin | Same as public | Sees `no_bet`, WDE reasons, `internal_status` per market |

---

## Bet Quality formula (transparent, read-only)

Computed in `worldcup_predictor/publication/bet_quality_overlay.py` → `compute_market_quality_score()`:

```
score = prob×0.42 + market_conf×0.28 + fixture_conf×0.12 + data_quality×0.10
      + rank_bonus (0–8)
      + model_agreement bonus (≤5)
      + odds_value_edge bonus (≤6)
      − fixture_no_bet penalty (−8, extra −4 if confidence-related WDE reason)
score clamped 0–100
```

**Important:** `probability` and `bet_quality_score` are separate fields. Owner/admin responses include `score_inputs` per market.

### Quality tiers

| Score | Tier | Color |
|------:|------|-------|
| 95–100 | Elite | dark_green |
| 85–94 | Excellent | green |
| 75–84 | Strong | light_green |
| 60–74 | Good | yellow |
| 45–59 | Medium Risk | orange |
| 25–44 | High Risk | red |
| 0–24 | Very Weak | dark_red |

---

## Combo eligible legs — before / after

### Local SQLite (`worldcup_stored_predictions`, n=48)

| Metric | Before | After |
|--------|-------:|------:|
| Fixture `no_bet` | 19 | 19 (unchanged internally) |
| `caution_best_available` | 0 (not surfaced) | **19** |
| Combo legs (strict `no_bet=false` + pick) | **1** | — |
| Combo legs (quality ≥ 45 + public pick) | — | **17** |

### Production PredOps snapshots (post-deploy)

| Metric | Value |
|--------|------:|
| `eligible_legs` (high_odds mode, quality ≥ 45) | **15** |
| Legs with `caution_best_available` | **15** (all eligible legs in sample) |
| Combo modes ready | safe/balanced/value/high_odds per `combo-readiness` API |

Combo thresholds (A16):

- **Safe:** quality ≥ 90  
- **Balanced:** quality ≥ 75  
- **Value:** quality ≥ 60  
- **High Odds:** quality ≥ 45  

Combos show `caution_warning` when any leg is caution-derived.

---

## `caution_best_available` behavior

When `no_bet=true` but market data exists (`best_available_pick`, `market_ranking`, or `detailed_markets`):

- `public_recommendation_status = caution_best_available`
- `caution_label = "Caution — Best Available"`
- `public_best_pick` derived from strongest market signal
- `derived_from_no_bet_fixture = true`
- Internal WDE `no_bet` and audit metadata **unchanged**

---

## Files changed

### Backend (new overlay layer)

- `worldcup_predictor/publication/__init__.py`
- `worldcup_predictor/publication/bet_quality_overlay.py`

### Backend (integration)

- `worldcup_predictor/api/match_center_helpers.py` — overlay on `extract_prediction_summary`, public sanitize in `enrich_match_row`
- `worldcup_predictor/api/display_helpers.py` — `publication_overlay` on cached prediction payloads
- `worldcup_predictor/predops/combo_readiness.py` — market-quality gates
- `worldcup_predictor/predops/public_sanitize.py` — snapshot overlay + per-market quality

### Frontend

- `base44-d/src/lib/betQualityOverlay.js`
- `base44-d/src/lib/comboGenerator.js`
- `base44-d/src/lib/predictionDetailProUtils.js`
- `base44-d/src/lib/planGating.js`
- `base44-d/src/components/match-center/EliteMatchCard.jsx`
- `base44-d/src/components/prediction-detail-pro/PredictionSummaryCards.jsx`
- `base44-d/src/components/prediction-detail-pro/PredictionMarketsPro.jsx`
- `base44-d/src/pages/ComboTipsPage.jsx`
- `base44-d/src/pages/MatchDetailPage.jsx`

### Ops / validation

- `scripts/validate_phase_a16_bet_quality_publication_overlay.py`
- `scripts/deploy_phase_a16_production.sh`
- `scripts/deploy_phase_a16_smoke.sh`

### Not modified (verified)

- `weighted_decision_engine.py`
- `scoring_engine.py`
- EGIE engines
- Calibration modules
- Subscription billing

---

## Validation

**Script:** `scripts/validate_phase_a16_bet_quality_publication_overlay.py`

| Environment | Result |
|-------------|--------|
| Local | **37/37 PASS** |
| Production (venv) | **37/37 PASS** |

Checks include: WDE `no_bet` preserved, caution overlay, public hides `no_bet`, no fake Draw, market quality map, combo quality gates, owner WDE reasons, frontend build.

Artifacts: `data/validation/phase_a16_bet_quality_overlay_validation.json`

---

## Deployment

### Pre-deploy backups (production)

- Repo commit recorded: `backups/deploy-phase-a16-*/pre_deploy_commit.txt`
- SQLite: `football_intelligence.db` copied when present
- Frontend dist: `frontend_dist/` snapshot
- Repo tarball: `repo_pre_deploy.tar.gz`

### Deploy steps executed

1. Tarball uploaded → `/tmp/phase_a16_deploy.tar.gz`
2. `deploy_phase_a16_production.sh` — extract, frontend build, API restart, nginx reload
3. Prebuilt dist synced from `/tmp/phase_a16_frontend_dist`
4. Smoke: `deploy_phase_a16_smoke.sh`

### Smoke results

| Check | Result |
|-------|--------|
| `GET /api/matches?include_summary=true` | 200 |
| `GET /api/predops/snapshots/latest?fixture_id=` | `publication_overlay` present |
| `GET /api/predops/combo-readiness` | 200, `quality_thresholds` present |
| SPA `/combo-tips`, `/admin/predops` | 404 at curl (expected without SPA fallback in smoke; app routes served via nginx index) |

API overlay and combo-readiness confirmed live on production.

---

## Rollback plan

1. Restore frontend: `cp -a backups/deploy-phase-a16-*/frontend_dist/* /var/www/worldcup/frontend/dist/`
2. Restore SQLite if needed: `cp backups/.../football_intelligence.db data/`
3. Restore repo: `tar xzf backups/.../repo_pre_deploy.tar.gz -C /opt/worldcup-predictor`
4. `systemctl restart worldcup-api && systemctl reload nginx`
5. Re-run smoke on prior commit

Overlay is **read-time only** — no destructive DB migration; rollback is code + dist revert.

---

## Subscription display gating (no billing changes)

| Plan | Overlay visibility |
|------|-------------------|
| Free | `public_best_pick`, quality tier/score only |
| Starter | Core market quality, combo tips |
| Pro | Full market quality, EGIE quality fields |
| Owner/Admin | WDE internals, `score_inputs`, `internal_status` |

---

## Final status

**`BET_QUALITY_OVERLAY_DEPLOYED_OK`**

WDE internal `no_bet` preserved. Public UI shows Bet Quality and caution picks. Combo Tips unlocked for quality-eligible caution legs. Validation and production smoke passed.

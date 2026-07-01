# ECSE-LIVE-1 — Live API Prediction Snapshot Report

**Phase:** ECSE-LIVE-1  
**Mode:** Internal — multi-provider prematch → ECSE snapshot → evaluation  
**Status:** PASS (smoke + validation)

---

## Goal

Use **Sportmonks**, **OddAlerts**, and **API-Football** to discover upcoming fixtures, fetch prematch odds/features, build ECSE λ + top-10 exact scores, freeze snapshots before kickoff, and evaluate after FT — without touching WDE/EGIE.

---

## Win2Day Smoke Results (8 targets)

| Match | API-Football ID | Sportmonks ID | OddAlerts | Top-1 | Source |
|-------|-----------------|---------------|-----------|-------|--------|
| Brazil vs Japan | 1562344 | 19606959 | — | **1-0** | multi_provider_live |
| Germany vs Paraguay | 1565176 | 19606957 | — | **2-0** | multi_provider_live |
| Netherlands vs Morocco | 1562345 | 19606958 | — | **1-0** | multi_provider_live |
| Ivory Coast vs Norway | 1564789 | 19606955 | — | **1-1** | multi_provider_live |
| France vs Sweden | 1565177 | 19606956 | — | **3-0** | multi_provider_live |
| Mexico vs Ecuador | 1567306 | 19606954 | — | **1-0** | multi_provider_live |
| England vs DR Congo | 1567307 | 19606952 | — | **2-0** | multi_provider_live |
| Belgium vs Senegal | 1567308 | 19606953 | — | **1-0** | multi_provider_live |

- **First run:** 8/8 frozen (`snapshot_id` 1–8)
- **Repeat run:** 8/8 `already_frozen` — no overwrite
- **API log rows:** 80 in `ecse_live_api_log`

### Provider coverage (typical per fixture)

| Provider | Coverage |
|----------|----------|
| **API-Football** | 1X2, O/U 1.5/2.5/3.5, BTTS, correct score (~121 lines) |
| **Sportmonks** | Lineups (7/8); xG not returned on current plan |
| **OddAlerts** | 0/8 — WC fixtures not in OA upcoming pool at harvest time |

---

## Architecture

### New modules (`worldcup_predictor/research/ecse_live/`)

| Module | Role |
|--------|------|
| `fixture_resolver.py` | Discover + map fixture IDs across providers |
| `prematch_fetch.py` | Fetch odds, lineups, injuries, xG |
| `odds_merge.py` | Merge provider odds → ECSE λ input row |
| `api_log.py` | Persist API calls to `ecse_live_api_log` |
| `smoke_targets.py` | Win2Day 8-fixture list |
| `prediction_builder.py` | λ extraction + top-10 distribution |
| `runner.py` | T-60 snapshot + provider pipeline |
| `evaluator.py` | FT+15 evaluation vs frozen top-N |
| `scheduler.py` | Internal cycle orchestration |

### Tables

- `ecse_prediction_snapshots` — one row per `fixture_id` (UNIQUE, frozen)
- `ecse_prediction_evaluations` — one row per `snapshot_id`
- `ecse_live_api_log` — API call audit trail
- `ecse_live_cycle_runs` — cycle reports

### Settings (default OFF for production)

| Env | Default |
|-----|---------|
| `ECSE_LIVE_ENABLED` | `false` |
| `ECSE_LIVE_USE_PROVIDERS` | `true` |
| `ECSE_LIVE_SNAPSHOT_MINUTES_BEFORE` | `60` |
| `ECSE_LIVE_EVAL_MINUTES_AFTER_FT` | `15` |
| `ECSE_LIVE_DRY_RUN` | `false` |

---

## Validation

`scripts/validate_ecse_live_snapshot_evaluation.py` — **17/17 PASS**

- Snapshot insert-once / no overwrite
- Top-10 / top-3 / top-5 integrity
- Frozen evaluation (not fresh prediction)
- Pending vs finished handling
- Production snapshots = 8
- API calls logged
- WDE storage unchanged

---

## Run Commands

```bash
# Win2Day smoke (live APIs)
python scripts/run_ecse_live_1_smoke.py

# Repeat — expect already_frozen
python scripts/run_ecse_live_1_smoke.py

# Full validation
python scripts/validate_ecse_live_snapshot_evaluation.py

# Scheduled cycle (ECSE_LIVE_ENABLED=true)
python scripts/run_ecse_live_1.py
```

---

## Safety

- No WDE / EGIE / production prediction output changes
- No retraining or adaptive learning
- No public API routes
- Snapshots immutable after first insert

---

## Artifacts

- `artifacts/ecse_live_1_smoke.json`
- `artifacts/ecse_live_1_latest_cycle.json`

# PHASE 54F-5 — Server xG DB Import + Modern EGIE Dataset Report

**Date:** 2026-06-24  
**Mode:** Fix server env → Import cached xG → Build modern backtest dataset → Validate → Report  
**Status:** COMPLETE (backtest only — no production, WDE, SaaS, or frontend changes)

---

## Executive Summary

Phase 54F-5 fixed the production PostgreSQL configuration, imported **545 cached Sportmonks xG payloads** into the server database (**zero new API calls**), and built a **modern EGIE backtest dataset** from recent xG-rich fixtures.

| Result | Value |
|--------|-------|
| Server `DATABASE_URL` fix | **FIXED** |
| Server DB import | **238 summaries**, **9,668 records** |
| Modern dataset usable fixtures | **126** (52.94% of 238 candidates) |
| Rolling xG threshold (≥30%) | **MET** (52.94%) |
| Preferred threshold (≥50%) | **MET** |
| Phase 54F A/B on modern dataset | **EXECUTED** (39–42 test fixtures/market) |
| xG value recommendation | **NO_VALUE** — Arm B does not beat baseline |
| Validation | **22/22 PASS** |

**Final recommendation:** `READY_TO_RERUN_54F` (completed) — xG still shows **NO_VALUE** for EGIE promotion. Next: `NEED_MORE_FIXTURE_TARGETS` / refine features before 54G.

---

## 1. Root Cause

Phase 54F-4 server backfill wrote **545 API cache files** but **0 PostgreSQL rows** because:

1. `DATABASE_URL` was embedded inside a comment on `.env.production` line 5:
   `# PostgreSQL ... subscriptionsDATABASE_URL=postgresql://...`
2. Feature-store tables did not exist on server (migration `011` not applied; `down_revision` pointed to missing `010` on server).

---

## 2. Server `.env.production` Fix Status

| Check | Result |
|-------|--------|
| DATABASE_URL present | **YES** |
| Scheme starts with `postgresql:` | **YES** |
| Database name | **worldcup_predictor** |
| Secrets printed in logs/reports | **NO** |

**Scripts:**
- `scripts/fix_server_database_url_env.py` — splits comment from `DATABASE_URL`
- `scripts/validate_server_database_url.py` — redacted validation output

Migration `011_sportmonks_xg_feature_store` deployed with `down_revision = 009_goal_timing_display_minutes` on server (server lacks local `010`).

---

## 3. Cache Import Result

**Command (server):**
```bash
alembic upgrade head
python scripts/phase54f4_import_server_xg_cache.py --force-reimport
```

| Metric | Value |
|--------|-------|
| Cache files | 545 |
| API calls (live) | **0** |
| Fixtures processed | 545 |
| Fixtures imported (team xG) | 238 |
| Fixtures empty | 307 |
| Records written | 9,668 |
| Errors | 0 |

Tables populated:
- `fs_sportmonks_xg_records`
- `fs_sportmonks_xg_fixture_summary`
- `fs_sportmonks_xg_ingest_manifest`

Type separation preserved: **5304 → xg**, **5305 → xgot**, **86 skipped**.

---

## 4. DB Records Inserted / Upserted

| Table | Count |
|-------|-------|
| xG records | 9,668 |
| Fixture summaries | 238 |
| Leagues | 4 (WC, CL, EL, Conference) |
| Seasons | 6 recent season IDs |

### By league (summaries with team xG)

| League | Seasons | Summaries |
|--------|---------|-----------|
| World Cup (732) | 26618 | 45 |
| Champions League (2) | 23619, 25580 | 80 |
| Europa League (5) | 23620, 25582 | 101 |
| Conference (2286) | 25581 | 12 |

---

## 5. Coverage Before / After

| Evaluation set | Phase | Usable rolling xG | Coverage % |
|----------------|-------|-------------------|------------|
| Legacy UEFA cache (80 fixtures) | 54F / 54F-2 / 54F-4 | 4 | 5.0% |
| **Modern dataset (238 candidates)** | **54F-5** | **126** | **52.94%** |
| Global feature store summaries | 54F-5 | 183 / 238 | 76.9% |

The legacy 80-fixture UEFA cache remains unsuitable for xG validation. The modern dataset resolves this by selecting **2024/25+ and WC 2026** fixtures with type-5304 team xG and pre-match rolling features.

---

## 6. Modern EGIE Dataset Summary

**Builder:** `worldcup_predictor/egie/xg_backtest/modern_dataset_builder.py`  
**CLI:** `scripts/phase54f5_build_modern_egie_dataset.py`  
**Artifacts:** `artifacts/phase54f5_modern_egie_dataset/`

| Metric | Value |
|--------|-------|
| Candidate fixtures | 238 |
| Usable fixtures | 126 |
| Unusable fixtures | 112 (mostly insufficient rolling history) |
| Rolling xG coverage | **52.94%** |
| First goal labeled | 115 |
| Goal range labeled | 115 |
| Team goals labeled | 126 |
| Leakage-safe rows | 126 |

### By league (usable)

| League | Usable |
|--------|--------|
| Champions League | 46 |
| Europa League | 54 |
| World Cup | 21 |
| Conference League | 5 |

### Output files

- `modern_egie_dataset.parquet` / `.csv`
- `modern_egie_dataset_summary.json`
- `modern_egie_unusable_fixtures.csv`

---

## 7. Leakage Safety Result

**Modern dataset audit** (`audit_modern_dataset_leakage`): **PASS**

- All usable rows flagged `leakage_safe=true`
- All usable rows have `rolling_xg_available=true` (rolling_xg_5 both sides)
- No post-match `home_xg`/`away_xg` columns in dataset

Note: Global `run_xg_leakage_audit()` reports 1 heuristic suspect row across all 238 summaries (`rolling_not_equal_current_match_xg`); modern dataset rows are built strictly from pre-match rolling features via `XgFeatureBuilder`.

---

## 8. Phase 54F Re-run (Modern Dataset)

**Thresholds met:** rolling ≥30%, usable ≥30 → **A/B executed**

```bash
python scripts/phase54f_egie_xg_backtest.py \
  --dataset artifacts/phase54f5_modern_egie_dataset/modern_egie_dataset.parquet
```

| Market | Arm A accuracy | Arm B accuracy | Δ accuracy | Test n |
|--------|----------------|----------------|------------|--------|
| First Goal Team | 0.5128 | 0.4872 | **-0.0256** | 39 |
| Goal Range | 0.4615 | 0.3077 | **-0.1538** | 39 |
| Team Goals (O2.5) | 0.6429 | 0.4762 | **-0.1667** | 42 |

### Top xG feature importance (Arm B, pooled)

| Feature | Importance sum |
|---------|----------------|
| `home_recent_xga` | High |
| `xg_momentum_difference` | High |
| `rolling_xg_3_home` | Moderate |
| `defensive_weakness_difference` | Moderate |

### xG value recommendation

**`NO_VALUE`** — Adding Sportmonks rolling xG features **hurts** accuracy on all three markets vs baseline proxies on this sample. Not ready for EGIE production integration.

---

## 9. Validation

`scripts/validate_phase54f5_server_import_and_modern_dataset.py` → **22/22 PASS**

Confirmed:
- DATABASE_URL fixed (not leaked)
- Server cache imported (0 API calls)
- xG records > 0, summaries > 0
- Type 5304/5305/86 classification
- Modern dataset created
- Modern leakage audit PASS
- 54F rerun when thresholds met
- No production / WDE / SaaS / frontend changes

---

## 10. Final Recommendation

| Option | Status |
|--------|--------|
| **READY_TO_RERUN_54F** | **DONE** — modern A/B complete |
| READY_FOR_54G | **NO** — xG does not improve EGIE on tested markets |
| **NEED_MORE_FIXTURE_TARGETS** | **YES** — expand sample + tune features; Conference only 5 usable |
| NEED_MORE_EVENT_DATA | Optional — first-goal labels missing on 11 usable rows |
| STOP_XG_WORK | **NO** — infrastructure is production-ready; value case not proven |

### Exact next actions

1. Keep server xG store synced from cache/API for live competitions.
2. Expand modern dataset (more Conference + domestic if entitled).
3. Investigate why xG features degrade goal-range and O2.5 vs simple rolling proxies used as baseline.
4. Do **not** start Phase 54G until xG shows consistent positive delta on an expanded holdout.

---

## Constraints Honored

- No production prediction output changes
- No WDE changes
- No SaaS prediction logic changes
- No EGIE scoring logic changes
- No Phase 54G work
- No frontend deploy
- Zero new Sportmonks API calls (cache-only import)
- xG / xGoT separation preserved

**STOP** — Phase 54F-5 complete.

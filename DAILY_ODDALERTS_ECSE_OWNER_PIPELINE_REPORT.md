# Daily OddAlerts ECSE Owner Pipeline — Phase ECSE-ODDALERTS-6

**Generated:** 2026-07-01  
**Mode:** Owner/internal daily pipeline — Gmail CSV → incremental import → safe odds promotion → limited shadow monitor → owner report only  
**No production ECSE writes. No public publish.**

---

## Executive summary

Phase ECSE-ODDALERTS-6 delivers a **scheduler-safe daily owner pipeline** that orchestrates OddAlerts CSV ingestion, policy refresh, safe odds snapshot promotion (optional write), limited shadow monitor (v2 eligible only), and owner daily reports.

First run for **2026-07-01** (7-day window) completed with **0 new CSV files**, **0 monitor candidates** (13 fixtures waiting for OddAlerts snapshots), production tables unchanged.

**Final recommendation:** `NEED_NEW_ODDALERTS_EXPORTS`

---

## Pipeline steps

| Step | Script / module | Purpose |
|------|-----------------|--------|
| 1 | `scripts/download_today_oddalerts_csv_from_gmail.py` | Pull new OddAlerts CSV exports from Gmail |
| 2 | `scripts/import_oddalerts_csv_incremental.py` | Incremental inbox import |
| 3 | `worldcup_predictor/owner/daily_oddalerts_ecse_pipeline.py` | Lightweight policy matrix + dryrun refresh |
| 4 | Full audit scripts (only when new CSV imported) | Market mapping validation |
| 5 | Safe promotion (`promote_oddalerts_csv_to_odds_snapshots` logic) | READY_FULL + window + no disagreement |
| 6 | Limited shadow monitor (ECSE-ODDALERTS-5) | v2 eligible writes to `ecse_oddalerts_shadow_monitor` |
| 7 | `build_daily_oddalerts_ecse_owner_report` | Owner daily report |

**Orchestrator:** `scripts/run_daily_oddalerts_ecse_owner_pipeline.py`  
**Scheduler entry:** `scripts/run_daily_oddalerts_ecse_owner_pipeline_once.py` (exit 0 on success or no new data)

---

## What ran today (2026-07-01)

| Metric | Value |
|--------|-------|
| Run ID | `daily_oa_ecse_20260701_a5e5ba78` |
| Window | 2026-07-01 → 2026-07-07 |
| Gmail download | Skipped (not requested in test run) |
| CSV imported | 0 rows |
| READY_FULL | 197 (policy matrix refreshed) |
| Safe promotion candidates in window | 0 (197 historical fixtures outside window) |
| Odds snapshots written | 0 |
| Monitor candidates | 0 |
| Monitor records written | 0 |

---

## Skipped and why

| Reason | Count |
|--------|-------|
| `no_oddalerts_snapshot` | 13 fixtures in July window |
| `outside_kickoff_window` | 197 READY_FULL fixtures (historical batch, not in July window) |

**Current blocker:** Upcoming July 2026 fixtures lack complete OddAlerts CSV policy snapshots. Pipeline is ready; needs new Gmail exports + import.

---

## Production guard (unchanged)

| Table | Count |
|-------|-------|
| `ecse_prediction_snapshots` | 8 |
| `odds_snapshots` | 2212 |
| `worldcup_stored_predictions` | 173 |

No WDE/EGIE changes. No public prediction publish.

---

## Owner artifacts

| Artifact | Path |
|----------|------|
| Pipeline state | `artifacts/daily_oddalerts_ecse_owner_pipeline_state_20260701.json` |
| Daily report JSON | `artifacts/daily_oddalerts_ecse_owner_20260701.json` |
| Daily report MD | `reports/owner/daily_oddalerts_ecse_owner_20260701.md` |
| Validation | `artifacts/daily_oddalerts_ecse_owner_pipeline_validation_20260701.json` |

---

## Owner Lab integration

**Path:** `/owner/ecse-oddalerts-shadow`

`GET /api/owner/ecse-oddalerts-shadow` now includes `daily_monitor` summary:

- `last_pipeline_run`
- `new_csv_files_today`
- `new_odds_snapshots_today`
- `live_monitor_records`
- `waiting_no_snapshot_count`
- `top_eligible_upcoming_signals`

---

## Validation

**Script:** `scripts/validate_daily_oddalerts_ecse_owner_pipeline.py`

Run after pipeline execution. Checks orchestrator, state/report artifacts, Owner Lab summary, production guard, idempotency, targeted queries.

---

## Usage

```bash
# Full manual run (promotion preview only unless --write-odds)
python scripts/run_daily_oddalerts_ecse_owner_pipeline.py \
  --date 2026-07-01 \
  --window-days 7 \
  --download-gmail \
  --import-csv \
  --promote-odds-safe \
  --run-monitor \
  --only-eligible-v2 \
  --tag daily-owner-oddalerts

# Scheduler-safe once (all steps, promotion preview)
python scripts/run_daily_oddalerts_ecse_owner_pipeline_once.py --date today --window-days 7

# With safe odds writes (requires backup)
python scripts/run_daily_oddalerts_ecse_owner_pipeline_once.py --date today --write-odds
```

---

## Final recommendation

### `NEED_NEW_ODDALERTS_EXPORTS`

Daily pipeline infrastructure is **ready** (`DAILY_OWNER_PIPELINE_READY` capability). The July 2026 window has fixtures but no new OddAlerts CSV policy snapshots for them. Run with `--download-gmail --import-csv` when new exports arrive.

When signals appear after import + promotion: expect `DAILY_OWNER_PIPELINE_ACTIVE_WITH_SIGNALS`.

**No production ECSE writes. No public changes.**

# ECSE OddAlerts Limited Shadow Monitor — Phase ECSE-ODDALERTS-5

**Generated:** 2026-07-01  
**Mode:** Owner/internal live shadow monitoring — new fixtures only — v2 eligible signals only — no public publish — no production ECSE write  
**Segment model:** `oddalerts_ecse_segments_v2_calibrated`

---

## Executive summary

Phase ECSE-ODDALERTS-5 delivers a **limited owner-only shadow monitor** for upcoming/recent fixtures with complete OddAlerts CSV policy odds. The pipeline discovers candidates, generates ECSE from snapshots, scores with v2 calibrated segments, writes only to `ecse_oddalerts_shadow_monitor`, and exposes results via Owner Lab (`/owner/ecse-oddalerts-shadow` → **Live Shadow Monitor** tab).

First run window **2026-07-01 → 2026-07-07** found **13 fixtures** in the date range but **0 OddAlerts-complete snapshots** for non-historical fixtures. Production tables unchanged. Validation **18/18 PASS**.

**Final recommendation:** `WAITING_FOR_NEW_FIXTURES`

---

## Part A — Candidate discovery

**Script:** `scripts/discover_ecse_oddalerts_monitor_candidates.py`

```bash
python scripts/discover_ecse_oddalerts_monitor_candidates.py --date-from 2026-07-01 --date-to 2026-07-07
```

**Output:** `artifacts/ecse_oddalerts_monitor_candidates_20260701_20260707.json`

| Metric | Value |
|--------|-------|
| Date window | 2026-07-01 → 2026-07-07 |
| Historical shadow fixtures excluded | 197 |
| Fixtures in kickoff window | 13 |
| Candidates (OddAlerts complete) | **0** |
| Skipped | 13 (all `no_oddalerts_snapshot`) |

**Filters applied:**
- Upcoming/recent kickoff in date window
- Excludes fixtures already in historical shadow batch (`ecse_oddalerts_20260630`)
- Requires `oddalerts_csv_policy` / `lower_band_complete_coverage` snapshot with 1X2, O/U 2.5, BTTS
- High crosswalk confidence, valid probabilities, no high disagreement block
- Skips fixture+snapshot pairs already in monitor table

---

## Part B — Monitor shadow schema

**Table:** `ecse_oddalerts_shadow_monitor`  
**DDL:** `worldcup_predictor/research/oddalerts_ecse_monitor_ddl.py`  
**Migration:** registered in `worldcup_predictor/database/migrations.py`

**Idempotency:** `UNIQUE(fixture_id, odds_snapshot_id, segment_model_version)` + `record_hash`

**Status:** Table created; **0 rows** after first run (no eligible candidates in window).

---

## Part C — Monitor generation

**Script:** `scripts/run_ecse_oddalerts_limited_shadow_monitor.py`

```bash
python scripts/run_ecse_oddalerts_limited_shadow_monitor.py \
  --date-from 2026-07-01 \
  --date-to 2026-07-07 \
  --write-shadow \
  --only-eligible-v2
```

**Output:** `artifacts/ecse_oddalerts_limited_shadow_monitor_run_20260701_20260707.json`  
**Owner report:** `reports/owner/ecse_oddalerts_limited_shadow_monitor_20260701_20260707.md`

| Metric | Value |
|--------|-------|
| Monitor run ID | `ecse_oa_monitor_20260701_20260707` |
| Discovered | 0 |
| Generated | 0 |
| Skipped ineligible (--only-eligible-v2) | 0 |
| Written to shadow monitor | 0 |
| Badge distribution | — |

**Production guard (unchanged):**

| Table | Before | After |
|-------|--------|-------|
| `ecse_prediction_snapshots` | 8 | 8 |
| `odds_snapshots` | 2212 | 2212 |
| `worldcup_stored_predictions` | 173 | 173 |

No writes to `ecse_prediction_snapshots`, no public prediction publish, no WDE/EGIE changes.

---

## Part D — Evaluation updater

**Script:** `scripts/evaluate_ecse_oddalerts_limited_shadow_monitor.py`

```bash
python scripts/evaluate_ecse_oddalerts_limited_shadow_monitor.py --date-from 2026-07-01 --date-to 2026-07-07
```

**Output:** `artifacts/ecse_oddalerts_limited_shadow_monitor_evaluation_20260701_20260707.json`

| Metric | Value |
|--------|-------|
| Monitor records | 0 |
| Evaluated (finished + result) | 0 |
| Waiting (upcoming / no result) | 0 |
| Top-1 / Top-3 / Top-5 / Top-10 rates | — |
| By badge / competition / eligibility | — |

Uses targeted `LEFT JOIN fixture_results` by `fixture_id` only; does not touch production evaluation tables.

---

## Part E — Owner Lab integration

**Path:** `/owner/ecse-oddalerts-shadow`  
**Tabs:** Historical Shadow | **Live Shadow Monitor**

**API:** `GET /api/owner/ecse-oddalerts-shadow/monitor` (owner guard via `require_owner_user`)

**Live Shadow Monitor shows:**
- Upcoming vs finished monitored fixtures
- v2 badge, eligibility, expected Top-3/Top-5
- Top-1 / Top-3 / Top-5 predictions
- Final score and hit/miss when evaluated
- Source trace (provider, snapshot ID, crosswalk)

**No public UI exposure** — route is owner-only; monitor endpoint not on public predictions routes.

---

## Part F — Validation

**Script:** `scripts/validate_ecse_oddalerts_limited_shadow_monitor.py`

**Result:** **18/18 PASS**

| Check | Status |
|-------|--------|
| Monitor DDL + module | PASS |
| Artifacts + report exist | PASS |
| UI Live Shadow Monitor tab + API helper | PASS |
| No public monitor route | PASS |
| Monitor table exists | PASS |
| No production ECSE / odds / WDE writes | PASS |
| v2 segment model in run artifact | PASS |
| Monitor endpoint 200 (owner override) | PASS |
| Targeted reads only | PASS |

**Artifact:** `artifacts/ecse_oddalerts_limited_shadow_monitor_validation_20260701_20260707.json`

---

## Upcoming vs finished

| Status | Count |
|--------|-------|
| Upcoming monitored | 0 |
| Finished evaluated | 0 |

---

## Operational notes

1. **Re-run safely:** Discovery skips already-monitored `(fixture_id, odds_snapshot_id, v2)` pairs; writes use `INSERT OR IGNORE`.
2. **When new OddAlerts CSV snapshots arrive** for fixtures outside the historical 197 batch, re-run discovery + monitor for the relevant date window.
3. **Historical batch** remains in `ecse_oddalerts_shadow_predictions` (197 rows); monitor targets **new** fixtures only.
4. **July 2026 window:** DB has fixtures in range but no OddAlerts policy snapshots for them yet — monitor is wired and waiting for data.

---

## Files delivered

| Part | File |
|------|------|
| A | `scripts/discover_ecse_oddalerts_monitor_candidates.py` |
| B | `worldcup_predictor/research/oddalerts_ecse_monitor_ddl.py` |
| Core | `worldcup_predictor/research/oddalerts_ecse_monitor.py` |
| C | `scripts/run_ecse_oddalerts_limited_shadow_monitor.py` |
| D | `scripts/evaluate_ecse_oddalerts_limited_shadow_monitor.py` |
| E | `worldcup_predictor/api/routes/owner_ecse_oddalerts_shadow.py` (monitor route) |
| E | `base44-d/src/pages/owner/OwnerEcseOddalertsShadow.jsx` |
| E | `base44-d/src/api/saasApi.js` (`fetchOwnerEcseOddalertsShadowMonitor`) |
| F | `scripts/validate_ecse_oddalerts_limited_shadow_monitor.py` |
| G | This report |

---

## Final recommendation

### `WAITING_FOR_NEW_FIXTURES`

The limited shadow monitor infrastructure is **active and validated**, but the first run window (2026-07-01 → 2026-07-07) produced **zero candidates** because no non-historical fixtures in that window have complete OddAlerts CSV policy odds snapshots. Re-run when new OddAlerts snapshots are ingested for upcoming fixtures.

**Not recommended yet:** `LIMITED_SHADOW_MONITOR_ACTIVE` (requires monitor records), `READY_FOR_DAILY_OWNER_REPORT_INTEGRATION` (needs evaluated live cohort), `DO_NOT_USE_MONITOR` (validation passed).

**No production ECSE writes. No public changes.**

# WC Owner Evaluation Summary Report

**Date:** 2026-06-30 (Europe/Vienna)
**Final recommendation:** `PARTIAL_EVALUATION_READY`
**Validation:** PASSED (15/15)

## Scope

Owner-only evaluation summary built from existing result sync / ECSE evaluation / WDE evaluation rows.
No predictions regenerated. No result sync rebuilt. No public changes.

## Metrics

- Fixtures total: **4**
- Finished: **1** | Waiting: **3**
- WDE hits (1X2 / O/U / BTTS): **1** / **1** / **1**
- ECSE hits (Top-1 / Top-3 / Top-5): **0** / **1** / **1**
- Draw/PEN warning useful: **1** | false alarms: **0**

## Finished match highlight

Netherlands vs Morocco (PEN): FT **1-1**, penalties **2-3** (Morocco advances).
WDE: 1X2/O/U/BTTS all **HIT** at FT. ECSE actual rank **2** (Top-3 hit). Draw/PEN warning **USEFUL**.

## Waiting fixtures

- Ivory Coast vs Norway
- France vs Sweden
- Mexico vs Ecuador

## Deliverables

- `reports\owner\wc_owner_eval_summary_20260630.json`
- `reports\owner\wc_owner_eval_summary_20260630.md`
- `artifacts\wc_owner_eval_summary_validation.json`

## Pipeline

1. `python scripts/build_wc_owner_eval_summary.py`
2. `python scripts/validate_wc_owner_eval_summary.py`

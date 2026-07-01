# ECSE-X2-M6 — Shadow-Live Integration Report

**Phase:** ECSE-X2-M6  
**Mode:** Shadow-live / admin-only — no public prediction changes  
**Recommendation:** **ADMIN_PREVIEW_READY**  

## M5 context

Shortlist enhancer promoted from M5: reorder inside baseline Top-10 only.

## Files changed

- `worldcup_predictor/research/ecse_x2_m6/` — runtime, hook, store, evaluator, admin service
- `worldcup_predictor/research/ecse_live/runner.py` — shadow hook after snapshot insert
- `worldcup_predictor/research/ecse_live/evaluator.py` — shadow evaluation hook
- `worldcup_predictor/api/routes/admin_ecse_x2_shadow.py` — admin endpoints
- `worldcup_predictor/api/main.py` — admin router wiring
- `worldcup_predictor/config/settings.py` — `ECSE_X2_M6_SHADOW_LIVE_ENABLED`
- `scripts/run_ecse_x2_m6_shadow_live_smoke.py`
- `scripts/validate_ecse_x2_m6_shadow_live_integration.py`

## Runtime integration

Hook: `safe_attach_shadow_live_shortlist()` after `insert_snapshot()` in ECSE-LIVE runner.
Public ECSE prediction payload is never modified (`public_output_changed: false`).

## Storage

- `artifacts/ecse_x2_m6_shadow_live_shortlists.jsonl` — append-only shadow rows
- `artifacts/ecse_x2_m6_shadow_live_evaluations.jsonl` — shadow accuracy only

## Admin visibility

- `GET /api/admin/ecse-x2/shadow-live-shortlists` (super_admin)
- `GET /api/admin/ecse-x2/shadow-live-shortlists/{fixture_id}` (super_admin)
- `GET /api/admin/ecse-x2/shadow-live-shortlists-summary` (super_admin)

## Smoke test

- Upcoming attempted: **8**
- Upcoming attached: **0**
- Completed attempted: **60**
- Completed attached: **20**
- Applied enhancer: **6**
- Strong segment (home_prob≥60%): **5**
- Balanced control rows: **1**
- Shadow evaluations: **6**
- Total shadow rows: **68**

## Sample baseline vs enhanced

- fixture **223201** actual `2-1`: top1 1-1 → 1-1 (home_prob=0.555556)
- fixture **222867** actual `2-0`: top1 1-1 → 1-1 (home_prob=0.724638)
- fixture **223079** actual `1-3`: top1 1-1 → 1-1 (home_prob=0.625)
- fixture **223083** actual `2-0`: top1 2-1 → 2-1 (home_prob=0.769231)
- fixture **223098** actual `2-0`: top1 1-1 → 1-1 (home_prob=0.666667)

## Validation

Validation passed: **True**

```
ECSE-X2-M6 validation

  [PASS] membership_unchanged
  [PASS] public_output_unchanged
  [PASS] no_nan
  [PASS] balanced_excluded — balanced_match
  [PASS] balanced_unchanged
  [PASS] predictions_route_unchanged
  [PASS] ecse_display_unchanged
  [PASS] admin_route_exists
  [PASS] admin_requires_super_admin
  [PASS] admin_router_wired
  [PASS] baseline_unchanged — rows=10935145
  [PASS] shadow_artifact_exists — C:\Users\kaman\Desktop\Footbal\artifacts\ecse_x2_m6_shadow_live_shortlists.jsonl
  [PASS] eval_artifact_exists_or_optional
  [PASS] report_exists
  [PASS] shadow_rows_present — rows=68
  [PASS] shadow_schema
  [PASS] public_output_false
  [PASS] smoke_upcoming
  [PASS] smoke_completed — n=20
  [PASS] smoke_strong_segment
  [PASS] smoke_balanced_control

21/21 checks passed
```

## Public output unchanged

- ECSE baseline table not modified
- Public prediction routes do not import M6
- `ecse_display` API unchanged
- Shadow rows carry `public_output_changed: false`

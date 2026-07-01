# ECSE-X3-B — Owner Shadow Lab Wiring Report

**Phase:** ECSE-X3-B  
**Mode:** Owner-only shadow wiring — no public prediction changes  
**Recommendation:** **USE_ONLY_HI_J2_G_SLOPE**  
**Promotion:** not_promoted  

## Candidate registration

- **ID:** `ecse_x3_j2_g_slope`
- **Label:** ECSE X3 — J2/G/OU Slope
- **Mode:** shadow_only
- **Status:** research_candidate

## Files

### Created
- `worldcup_predictor/research/ecse_x3_b/constants.py`
- `worldcup_predictor/research/ecse_x3_b/registry.py`
- `worldcup_predictor/research/ecse_x3_b/runtime.py`
- `worldcup_predictor/research/ecse_x3_b/store.py`
- `worldcup_predictor/research/ecse_x3_b/hook.py`
- `worldcup_predictor/research/ecse_x3_b/sync.py`
- `worldcup_predictor/research/ecse_x3_b/owner_summary.py`
- `scripts/run_ecse_x3_b_owner_shadow_lab_sync.py`
- `scripts/validate_ecse_x3_b_owner_shadow_lab_wiring.py`

### Modified
- `worldcup_predictor/config/settings.py` — `ECSE_X3_B_OWNER_SHADOW_LAB_ENABLED`
- `worldcup_predictor/research/ecse_x2_m6/hook.py` — X3-B attach after M5
- `worldcup_predictor/research/ecse_x2_m8/lab_service.py` — merge X3 into owner lab
- `worldcup_predictor/research/ecse_x3/mapping.py` — `apply_j2_g_slope_shadow()`
- `base44-d/src/pages/owner/OwnerEcseShadowLab.jsx` — X3 panel

## Owner-only access

- **UI:** `/owner/ecse-shadow-lab`
- **API:** `/api/owner/ecse-shadow-lab/summary`, `/fixtures`, `/fixtures/{id}`
- **Auth:** `require_owner_user`

## Artifacts

- `artifacts/ecse_x3_b_owner_shadow_lab.jsonl`
- `artifacts/ecse_x3_b_owner_shadow_lab_summary.json`

## Sync run

- M6 rows processed: **108**
- X3-B rows written: **108**
- Skipped (duplicate): **0**

## Coverage stats

| Metric | Value |
|--------|-------|
| Evaluated fixtures | 108 |
| X3 available | 0 |
| X3 unavailable | 108 |
| X3 rejected | 0 |
| Coverage % | 0.0 |

## Comparison vs baseline

- Baseline hit rates: {'top1': 9.5238, 'top3': 19.0476, 'top5': 33.3333}
- X3 hit rates (available only): {}
- Top-1 delta (live slice): None pp

## Comparison vs M5

- M5 applied with actual: 0
- M5 hit rates: {}

## Missing odds limitations

- `ft_home`: 108
- `ft_away`: 108
- `ou_over_25`: 108
- `btts_yes`: 108
- `ou_over_15`: 108

## Safety

- Public predictions unchanged: **True**
- Subscriptions unchanged: **True**
- Baseline table unchanged: **10,935,145** rows
- public_prediction_changed rows: **0**
- Phi forbidden: **True**
- Composite promotion blocked: ['composite_full', 'conservative_composite', 'segment_aware', 'hi_only', 'zz2_only']

## Validation

Run:
```bash
python scripts/validate_ecse_x3_b_owner_shadow_lab_wiring.py
python scripts/validate_ecse_x3_a_composite_shadow_engine.py
```

## Next phase

**PHASE ECSE-X3-C — Shadow Lab Monitoring and Promotion Threshold Tracking**
(only after X3-B safely wired owner-only)

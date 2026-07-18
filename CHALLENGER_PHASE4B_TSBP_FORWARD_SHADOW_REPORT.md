# CHALLENGER PHASE 4B — TSBP FORWARD SHADOW REPORT

## Final status: `TSBP_FORWARD_SHADOW_ACTIVE`

### Registration
- TSBP registered: `TSBP-1`
- GBGM-1 status: `PAUSED_BELOW_BASELINE` (pause_gbgm1_new_generation=true)
- Historical GBGM-1 freezes/evals retained (immutable)

### Shadow invariants
- is_shadow=true
- public_visible=false
- final_decision_authority=false
- Canonical WDE/ECSE/BTTS/O-U unchanged
- Owner/Custom GPT outputs remain canonical-only

### Integration
- Additive hook in `scripts/run_owner_full_day_predictions.py`
- Same prematch snapshot path via `build_prematch_feature_snapshot`
- Separate Challenger freeze + comparison tables
- Failures never block canonical

### Forward evaluations
- Completed TSBP evaluations in DB: **0**
- Threshold reports created: `none (thresholds not reached)`

### Smoke test
```json
{
  "ok": true,
  "fixture_id": 1375863,
  "competition_key": "bundesliga",
  "has_hda": true,
  "corr": 0.05,
  "label": "TSBP_SHADOW",
  "top10_n": 10,
  "prob_sum": 1.0
}
```

No Ensemble approval. No public promotion. Cards Engine not started.

**STATUS: `TSBP_FORWARD_SHADOW_ACTIVE`**
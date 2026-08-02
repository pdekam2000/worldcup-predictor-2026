# PHASE4_LOCKED_HOLDOUT_AND_TRUE_FORWARD_REPORT

Status: **PHASE4_LOCKED_HOLDOUT_EVALUATED_TRUE_FORWARD_READY**

## Lock

- Manifest SHA256: `8e245773e68508bc11a4fc600c1a1979ab76a366ea98cfb997df1ac3cce8bb3f`
- Candidate lock: **LOCKED_IMMUTABLE**
- NO RETUNING AFTER HOLDOUT

## Holdout

- Integrity: **SEALED_HOLDOUT_INTEGRITY_PASS**
- N: **11**
- Warning: **SMALL_HOLDOUT_NOT_PROMOTABLE**

### Locked candidate accuracy

`{'ecse_direction': 0.5455, 'Favorite_Specialist': 0.4545, 'League_Specialist': 0.5455, 'High_Goal_Specialist': 0.8, 'meta_model': 0.3636}`

### Verdicts

`{'canonical_wde_raw_argmax': 'HOLDOUT_NEUTRAL', 'canonical_wde_stored_decision': 'HOLDOUT_NEUTRAL', 'canonical_ecse_direction': 'HOLDOUT_NEUTRAL', 'phase2_best_strategy': 'INSUFFICIENT_HOLDOUT_COVERAGE', 'market_favorite_baseline': 'HOLDOUT_NEUTRAL', 'ecse_direction': 'HOLDOUT_NEUTRAL', 'Favorite_Specialist': 'HOLDOUT_NEUTRAL', 'League_Specialist': 'HOLDOUT_NEUTRAL', 'High_Goal_Specialist': 'HOLDOUT_NEUTRAL', 'meta_model': 'HOLDOUT_NEUTRAL'}`

Best diagnostic candidate: `{'name': 'High_Goal_Specialist', 'accuracy': 0.8, 'n': 5}`

## True-forward

- Pipeline: PLAN_READY_COLLECTION_NOT_AUTO_ENABLED
- Evaluated N: **0**
- Gates: {'A': '0/30', 'B': '0/100', 'C': '0/250'}
- Timers prepared: True · enabled: False

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- WDE UNCHANGED
- ECSE UNCHANGED
- NO RETUNING AFTER HOLDOUT
- NO AUTO-PROMOTION
- 75% target **not claimed** (holdout N=11 cannot satisfy)

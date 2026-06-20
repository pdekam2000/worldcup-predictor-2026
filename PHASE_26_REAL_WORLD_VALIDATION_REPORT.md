# Phase 26 — Real World Validation Framework Report

**Status:** Complete (local capture + offline evaluation — no deployment, no gated rollout)

**Safe mode constraints honored:**

- No WDE weight changes
- No calibration changes
- No auto-gated enable
- All promotion flags remain **`shadow`**

---

## Files Changed

| File | Role |
|------|------|
| `worldcup_predictor/validation/__init__.py` | Package exports |
| `worldcup_predictor/validation/models.py` | `RealWorldValidationRecord`, `PromotionTrackSnapshot`, `WorldCupReadinessScore` |
| `worldcup_predictor/validation/store.py` | JSONL validation store + contribution stats JSON |
| `worldcup_predictor/validation/capture.py` | Pre-match capture from predictions (shadow-only) |
| `worldcup_predictor/validation/outcome_evaluator.py` | Post-match settle + calibration bucket |
| `worldcup_predictor/validation/contribution.py` | Helped / neutral / harmful assessment |
| `worldcup_predictor/validation/coverage.py` | Intelligence coverage analysis |
| `worldcup_predictor/validation/readiness.py` | `WorldCupReadinessScore` (0–100) |
| `worldcup_predictor/validation/reports.py` | Weekly + monthly automated reports |
| `worldcup_predictor/validation/service.py` | Orchestration: settle, backfill, reports |
| `worldcup_predictor/config/settings.py` | `REAL_WORLD_VALIDATION_MODE` (default `shadow`) |
| `worldcup_predictor/prediction/scoring_engine.py` | Fail-silent capture hook in `_finalize_prediction()` |
| `scripts/validate_phase26_real_world_validation.py` | Offline validator |
| `PHASE_26_REAL_WORLD_VALIDATION_REPORT.md` | This report |

**Runtime data (generated, not source):**

- `data/validation/real_world_validation.jsonl`
- `data/validation/promotion_contribution_stats.json`
- `data/validation/reports/weekly_validation_summary.md`
- `data/validation/reports/monthly_promotion_impact_report.md`

---

## Storage Design

### Primary store — append-only JSONL

**Path:** `data/validation/real_world_validation.jsonl`

Each line is one `RealWorldValidationRecord` (version `26`):

| Field group | Contents |
|-------------|----------|
| Identity | `fixture_id`, `match_date`, `prediction_timestamp`, `match_name`, `competition_key` |
| Prediction | `predicted_1x2`, `predicted_over_under`, `confidence`, `baseline_confidence`, `no_bet_flag`, `confidence_bucket` |
| Outcome (post-settle) | `actual_1x2`, `actual_over_under`, `one_x_two_correct`, `over_under_correct`, `confidence_calibration_ok`, `settled`, `settled_at` |
| Snapshots | `lineup_snapshot`, `expected_lineup_snapshot`, `tournament_context_snapshot`, `xg_snapshot`, `sportmonks_prediction_snapshot` |
| Promotions (×4) | Per-key: `signal_available`, `confidence`, `delta`, `agreement`, `disagreement`, `active`, `reason`, `mode` |
| Audit | `promotion_deltas`, `shadow_signals`, `signal_usefulness` |

### Promotion keys tracked separately

| Key | Phase | Layer |
|-----|-------|-------|
| `24a_lineup` | 24A | Expected Lineups |
| `24b_context` | 24B | Tournament Context |
| `24c_xg` | 24C | xG Intelligence |
| `24c_sportmonks` | 24C | Sportmonks Benchmark |

### Long-term contribution stats

**Path:** `data/validation/promotion_contribution_stats.json`

Rebuilt from settled records on each settle/report cycle (idempotent — no double-counting):

- `total`, `helped`, `neutral`, `harmful`, `unknown`
- `signal_available_rate`, `avg_delta`, `avg_disagreement`

### Capture flow

```
Prediction pipeline (_finalize_prediction)
  └─ maybe_record_real_world_validation()   [REAL_WORLD_VALIDATION_MODE=shadow]
       └─ RealWorldValidationStore.append()

Post-match (RealWorldValidationService.settle_from_match_results)
  └─ MatchResultsStore.by_fixture_id()
  └─ apply_outcome() + assess_signal_usefulness()
  └─ rewrite JSONL + rebuild contribution stats
```

### Bootstrap

Phase 25 replay rows with `stack=gated_simulation` seed the store offline via `backfill_from_phase25_replay()` — snapshots are empty (delta-only bootstrap); live captures fill snapshots going forward.

---

## Metrics Tracked

### Per prediction (capture)

- Final 1X2 / O/U selection and confidence
- Baseline vs final confidence (from `FinalDecisionTrace`)
- Data quality score
- Four promotion tracks with mode, delta, disagreement
- Full intelligence snapshots at prediction time
- Shadow signal metadata (promotion modes, watch-only, audit traces)

### Post-match (outcome evaluation)

- Correct / incorrect (1X2 and O/U)
- Confidence calibration bucket (`high_70+`, `medium_55_69`, `low_40_54`, `very_low_below_40`)
- Calibration OK rule: high confidence (≥65) should be correct; low (<45) should be wrong
- Per-promotion signal usefulness: `helped` | `neutral` | `harmful` | `unknown`

### Coverage analysis

- Lineup, expected lineup, tournament context, xG, Sportmonks availability rates
- Missing data rates per layer

### Signal contribution study

For each promotion, long-term counts of helped / neutral / harmful with average delta and disagreement.

---

## Reporting Design

| Report | Path | Cadence | Contents |
|--------|------|---------|----------|
| Weekly Validation Summary | `data/validation/reports/weekly_validation_summary.md` | 7-day window | Record count, settled count, 1X2 accuracy, calibration rate, coverage, `WorldCupReadinessScore` |
| Monthly Promotion Impact Report | `data/validation/reports/monthly_promotion_impact_report.md` | 30-day window | Accuracy, calibration, disagreement success rate, contribution table, missing rates |

**Generate programmatically:**

```python
from worldcup_predictor.validation.service import RealWorldValidationService
svc = RealWorldValidationService()
svc.settle_from_match_results()
svc.generate_reports()
```

---

## Readiness Framework — WorldCupReadinessScore

**Range:** 0–100 (weighted composite)

|Component| Weight | Source |
|---------|--------|--------|
| Data Quality | 25% | Average `data_quality_score` across records |
| Lineup Coverage | 20% | Snapshot availability rate |
| Context Coverage | 20% | Tournament context snapshot rate |
| xG Coverage | 15% | xG snapshot rate |
| Prediction Quality | 20% | Settled accuracy (65%) + calibration (35%) |

**Notes emitted when:**

- Sample size < 20 (provisional score)
- Sportmonks coverage < 20%
- No records yet

Sportmonks coverage is tracked in reports but not in the weighted score (benchmark layer is audit-only).

---

## Validation Results

**Validator:** `scripts/validate_phase26_real_world_validation.py`

```
Phase 26 real-world validation: 16/16 passed
```

Checks include: four promotion tracks, snapshot capture, delta persistence, store write, Phase 25 backfill, settle pipeline, readiness range, weekly/monthly reports, all promotion flags `shadow`, `REAL_WORLD_VALIDATION_MODE=shadow`.

### Current store snapshot (Phase 25 bootstrap — 32 fixtures)

| Metric | Value |
|--------|-------|
| Records | 32 |
| Settled | 32 |
| 1X2 accuracy | 40.6% (13/32) |
| WorldCupReadinessScore | **9.7 / 100** |
| Intelligence snapshot coverage | 0% (bootstrap rows lack live snapshots) |
| Promotion signal availability | ~6.3% per layer (Phase 25 delta-only rows) |
| Signal usefulness verdicts | All `unknown` (insufficient live signal availability) |

### Promotion contribution (bootstrap)

| Promotion | Total | Helped | Neutral | Harmful | Unknown | Signal Avail | Avg Δ |
|-----------|-------|--------|---------|---------|---------|--------------|-------|
| 24a_lineup | 32 | 0 | 0 | 0 | 32 | 6.3% | +0.50 |
| 24b_context | 32 | 0 | 0 | 0 | 32 | 6.3% | +0.09 |
| 24c_xg | 32 | 0 | 0 | 0 | 32 | 6.3% | +0.05 |
| 24c_sportmonks | 32 | 0 | 0 | 0 | 32 | 6.3% | −0.19 |

### Flag verification

| Flag | Value |
|------|-------|
| `EXPECTED_LINEUP_PROMOTION_MODE` | **shadow** |
| `TOURNAMENT_CONTEXT_PROMOTION_MODE` | **shadow** |
| `XG_PROMOTION_MODE` | **shadow** |
| `SPORTMONKS_PREDICTION_PROMOTION_MODE` | **shadow** |
| `REAL_WORLD_VALIDATION_MODE` | **shadow** |

---

## Interpretation

Phase 25 established that promotion layers do not flip winners or inflate confidence in replay. Phase 26 adds **forward-only real-world capture** so WC 2026 usage accumulates evidence with full intelligence snapshots.

The current readiness score (9.7) reflects bootstrap data without live snapshots — expected until group-stage predictions run with `REAL_WORLD_VALIDATION_MODE=shadow`. As live captures accumulate, coverage and contribution verdicts will populate automatically.

---

## Next Step Recommendation

1. **Keep all promotion flags at `shadow`** — no gated rollout.
2. Run predictions through the normal pipeline; validation capture is automatic when `REAL_WORLD_VALIDATION_MODE=shadow`.
3. After each match day, call `RealWorldValidationService().settle_from_match_results()` (or integrate into existing result sync).
4. Review weekly/monthly reports before any manual gated enable decision.
5. **STOP** — await approval before calibration changes, WDE modifications, or deployment.

**Phase 26 complete. No deployment started.**

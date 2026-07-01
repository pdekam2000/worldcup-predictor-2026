# ECSE OddAlerts Shadow Write Report

**Phase:** ECSE-ODDALERTS-2  
**Generated:** 2026-07-01 05:23:15 UTC  
**Mode:** Owner/internal shadow write — no production ECSE, no public publish

---

## Summary

**Final recommendation:** `ECSE_ODDALERTS_SHADOW_EVALUATED`

| Metric | Value |
|--------|-------|
| Input records | 197 |
| Valid records | 197 |
| Written | 197 |
| Would write (dry-run) | 0 |
| Skipped (idempotent) | 0 |
| Shadow run total | 197 |
| Shadow run ID | `ecse_oddalerts_20260630` |

---

## Production tables unchanged

| Table | Before | After |
|-------|--------|-------|
| ecse_prediction_snapshots | 8 | 8 |
| odds_snapshots | 2212 | 2212 |
| worldcup_stored_predictions | 173 | 173 |

---

## Idempotency

- Dry-run mode: False
- Skipped on re-run: 0

---

## Evaluation metrics

Status: **EVALUATED**  
Evaluated: 185 | Waiting: 12

| Metric | Rate |
|--------|------|
| Top-1 | 0.1189 |
| Top-3 | 0.2919 |
| Top-5 | 0.4432 |
| Top-10 | 0.773 |

### By promotion action

```json
{
  "enriched": {
    "count": 112,
    "top1_hit_rate": 0.1071,
    "top3_hit_rate": 0.2589,
    "top5_hit_rate": 0.4196,
    "top10_hit_rate": null
  },
  "inserted": {
    "count": 73,
    "top1_hit_rate": 0.137,
    "top3_hit_rate": 0.3425,
    "top5_hit_rate": 0.4795,
    "top10_hit_rate": null
  }
}
```

---

## Baseline comparison

```json
{
  "ecse_production": {
    "available_count": 2,
    "missing_count": 195,
    "outcome_agreement_rate": 1.0
  },
  "wde": {
    "available_count": 34,
    "missing_count": 163,
    "outcome_agreement_rate": 0.0
  },
  "bookmaker_implied_1x2": {
    "available_count": 197,
    "missing_count": 0,
    "outcome_agreement_rate": 0.5787
  }
}
```

---

## Best / worst lambda segments

**Best:** high_total_goals: top1=0.125  
**Worst:** medium_total_goals: top1=0.1134

---

## Sample evaluated predictions

| Fixture | Actual | Top-1 | Hit | Source |
|---------|--------|-------|-----|--------|
| 1035349 | 1-0 | 2-0 | N | enriched |
| 1035385 | 0-0 | 1-1 | N | enriched |
| 1035387 | 1-2 | 0-1 | N | enriched |
| 1035392 | 4-1 | 2-0 | N | enriched |
| 1035393 | 3-1 | 2-0 | N | enriched |

---

## Validation

- [pass] shadow_table_exists
- [pass] shadow_records_present
- [pass] shadow_count_matches_input
- [pass] no_ecse_production_changed
- [pass] no_wde_changed
- [pass] no_odds_snapshots_changed
- [pass] public_output_unchanged
- [pass] source_trace_preserved
- [pass] top_scores_valid
- [pass] lambda_values_valid
- [pass] no_duplicate_record_hashes
- [pass] evaluation_artifact_exists
- [pass] comparison_artifact_exists
- [pass] targeted_reads_only
- [pass] report_exists

Passed: **15** / **15**

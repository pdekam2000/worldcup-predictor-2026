# ECSE OddAlerts Dry-Run Report

**Phase:** ECSE-ODDALERTS-1  
**Generated:** 2026-07-01 04:37:29 UTC  
**Mode:** Owner/internal ECSE dry-run — no production ECSE writes, no public publish

---

## Summary

**Final recommendation:** `ECSE_ODDALERTS_DRYRUN_READY`

| Metric | Value |
|--------|-------|
| Candidates | 197 |
| Generated | 197 |
| Failed | 0 |

---

## Top-1 score distribution

{
  "1-1": 83,
  "2-0": 41,
  "1-0": 39,
  "0-1": 17,
  "0-2": 13,
  "2-1": 2,
  "3-0": 1,
  "1-2": 1
}

---

## Lambda ranges

- Home: [0.5187, 3.0542] (mean 1.6015)
- Away: [0.2672, 2.5109] (mean 1.1774)

---

## Sample predictions

| Fixture | Match | Top-1 | λ h/a | Source |
|---------|-------|-------|-------|--------|
| 1035349 | Manchester City vs Brentford | 2-0 | 2.910156/0.329343 | enriched |
| 1035385 | Fulham vs Everton | 1-1 | 1.526809/1.150162 | enriched |
| 1035387 | Nottingham Forest vs Arsenal | 0-1 | 0.833808/1.988081 | enriched |
| 1035392 | Liverpool vs Chelsea | 2-0 | 2.384151/0.932137 | enriched |
| 1035393 | Manchester City vs Burnley | 2-0 | 2.927729/0.267157 | enriched |
| 1035394 | Bournemouth vs Nottingham Forest | 1-1 | 1.558572/1.012193 | enriched |
| 1035395 | Arsenal vs Liverpool | 1-1 | 1.894217/1.082328 | enriched |
| 1035396 | Brentford vs Manchester City | 0-2 | 0.752747/2.096109 | enriched |

---

## Evaluation preview

Status: **PREVIEW**  
Evaluated: 185

---

## Validation

- [pass] no_ecse_production_insert
- [pass] no_wde_changes
- [pass] no_odds_snapshots_changed
- [pass] public_output_unchanged
- [pass] quality_artifact_exists
- [pass] report_exists
- [pass] generated_count_positive
- [pass] failures_explained
- [pass] jsonl_count_matches_summary
- [pass] all_records_have_source_trace
- [pass] top_scores_valid
- [pass] lambda_values_valid
- [pass] no_impossible_outputs
- [pass] source_traceability
- [pass] fixture_count_alignment
- [pass] targeted_reads_only
- [pass] evaluation_artifact

Passed: **17** / **17**

# FINAL DATASET RECONCILIATION REPORT

## Summary

Phase A–D completed on branch `audit/deep-model-forensic-20260730T115031Z`.

Artifact: `artifacts/dataset_reconciliation_experiments/20260730T125305Z/`

### Result reconciliation (Phase A)

| Metric | Count |
|--------|------:|
| Missing fixtures before sync | 109 |
| Newly resolved FT90 | **26** |
| Still unresolved | **83** |
| Provider conflicts | 5 |
| Test fixtures (900k–999k, no provider) | 5 |

Still-unresolved breakdown:

- `STATUS_NOT_TERMINAL`: 73 (mostly future / not finished)
- `fixture_not_found`: 5 (synthetic)
- `internal_regulation_ft_mismatch`: 5 (provider conflict / not safely stored)

Historical freeze payloads were **not** mutated. Only `actual_results` rows were added via `sync_result_for_fixture`.

### Duplicate freeze forensics (Phase B)

- Duplicate groups: **62**
- Classified freeze rows: **173**
- Cohorts defined: FIRST_VALID_PREMATCH, LAST_VALID_PREMATCH, CANONICAL_MARKED_FREEZE, ALL_VALID_TIMING_EXPERIMENTS, INVALID_OR_POST_KICKOFF, UNKNOWN_DUPLICATE_REASON
- Freezes retained; none deleted

### Corrected evaluation datasets (Phase C)

| Dataset | Rows | Unique fixtures |
|---------|-----:|----------------:|
| all_valid | 239 | 168 |
| **canonical one-per-fixture (headline)** | **168** | **168** |
| first_valid | 168 | 168 |
| last_valid | 168 | 168 |
| complete_metadata | 3 | 3 (too small) |

Previous audit used earliest freeze among fixtures with results (**142**). Duplicates did **not** invent extra fixtures in the headline metric (previous script already collapsed to one freeze/fixture); the main lift to **168** is the **26 newly synced results**.

### Corrected headline metrics (Phase D) — canonical n=168

| Market | Rate | 95% CI | vs previous (n=142) |
|--------|------|--------|---------------------|
| Exact Top1 | 14.9% | 9.5–20.2% | −2.0 pp |
| Exact Top3 | 29.8% | 23.2–36.3% | −1.2 pp |
| Exact Top5 | **45.2%** | 38.1–53.0% | **+0.9 pp** |
| Exact Top10 | 75.6% | 69.1–81.6% | −0.5 pp |
| WDE | 48.8% | 41.7–56.6% | −0.5 pp |
| BTTS | 51.8% | 44.1–58.9% | +3.9 pp |
| O/U 2.5 | 56.0% | 48.8–63.1% | +2.4 pp |

**Conclusions materially unchanged:** Top5 ~45%, WDE ~49%, under-scoring / wrong direction remain primary failure modes. Draw recall remains weak (16.7%).

WDE balanced accuracy: **0.442**; Brier mean: **0.658**.
Goal MAE: home 1.04 / away 0.88 / total 1.43 / GD 1.32.
Exact-score log loss (where rank probs available): **2.47** (n=127).

First vs last freeze: Top5 identical at 45.2% on this cohort (limited material drift for headline Exact Top5).

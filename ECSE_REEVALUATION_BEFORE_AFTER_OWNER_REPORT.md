# ECSE Re-evaluation Before/After — Owner Report

**Recommendation:** `RESULT_TRUTH_V8_DEPLOYED_EVALUATIONS_CORRECTED`

---

## Aggregate impact (n=16)

| Metric | Before | After | Delta |
|--------|-------:|------:|------:|
| Hit@5 | 68.8% | 68.8% | 0 |
| Hit@3 | 50.0% | 50.0% | 0 |
| MRR | 0.372 | 0.379 | +0.007 |

Top5 aggregate unchanged — AET corrections moved ranks but neither fixture entered Top5 at regulation score.

---

## Per-fixture changes

| Fixture | Prior Score | Regulation | Prev Rank | New Rank | Changed? |
|---------|-------------|------------|----------:|---------:|:--------:|
| 1567308 Belgium vs Senegal | 3-2 | 2-2 | 12 | 10 | **yes** |
| 1565179 Argentina vs Cape Verde | 3-2 | 1-1 | — | 11 | **yes** |
| All other 14 fixtures | unchanged | = prior | = prior | = prior | no |

---

## Interpretation

- Evaluation truth is now **correct** for AET matches
- Reported Hit@5 was not inflated by wrong labels (both AET fixtures missed Top5 under either score)
- MRR slightly improved after rank correction
- Historical replay can trust regulation labels going forward

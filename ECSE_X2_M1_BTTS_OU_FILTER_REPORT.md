# ECSE-X2-M1 — BTTS × OU Exact Score Grid Filter

**Phase:** ECSE-X2-M1  
**Method:** `ECSE-X2-M1-v1`  
**Output table:** `ecse_score_distributions_m1`  

## Hypothesis

BTTS and Over/Under 2.5 define four score-worlds that can re-rank ECSE exact-score grids:

1. **yes_over** — BTTS Yes + Over 2.5 (e.g. 2-1, 1-2, 2-2, 3-1)
2. **yes_under** — BTTS Yes + Under 2.5 (1-1)
3. **no_under** — BTTS No + Under 2.5 (0-0, 1-0, 0-1, 2-0)
4. **no_over** — BTTS No + Over 2.5 (3-0, 0-3, 4-0, 0-4)

## Build Summary

- Fixtures built: **168,233**
- Rows inserted: **10,935,145**
- Skipped (idempotent): **0**
- Missing market (passthrough): **0**
- Baseline rows unchanged: **10,935,145**

## M1 Table Audit

- Rows: **10,935,145**
- Fixtures: **168,233**
- Prob sum violations: **0**

### Dominant quadrant distribution

- **no_over**: 1,166
- **no_under**: 18,436
- **yes_over**: 130,788
- **yes_under**: 17,843

## Safety

- `ecse_score_distributions` baseline untouched
- No actual results used during re-ranking
- Prematch odds / λ inference only
- Research/internal only

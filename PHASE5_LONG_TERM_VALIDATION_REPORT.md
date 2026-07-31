# PHASE5_LONG_TERM_VALIDATION_REPORT

## Final status

**`BET_COVERAGE_OPTIMIZER_PHASE5_LONG_TERM_VALIDATED`**

**Recommendation:** `HOLD`  
**Readiness score:** `79.0/100`

**NOT DEPLOYED**

| Item | Value |
|---|---|
| Replay fixtures | 250 |
| Leagues | 2 |
| Forward days | 12 |
| Artifact path | `C:\Users\kaman\AppData\Local\Temp\pytest-of-kaman\pytest-180\test_phase5_pipeline_smoke0\phase5` |

## Historical replay

- Exact3 coverage: `0.344`
- Exact3+Main: `0.516`
- Exact3+Main+Insurance: `0.704`
- Research 125 baseline: `0.704`
- Main-only failure freq: `0.86746988`
- Main+Ins failure freq: `0.63855422`
- Insurance rescues: `47`
- Significant @0.05: `True`

## Market-family ranking

- Best: `Away Win` (rescue `0.33333333`)
- Worst: `Under 3.5` (rescue `0.0`)

## Robustness

- Robust to incomplete markets: `True`

## Safety

- Canonical / ECSE / WDE / freezes unchanged
- No synthetic outcomes
- No fabricated odds
- No production deploy

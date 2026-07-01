# ECSE-1D-B — Score Grid Upgrade Report

**Method:** `ECSE-1D-B-v1` (independent Poisson, 0-0..7-7 + OTHER)  
**Dixon–Coles:** disabled (rho default -0.13, not enabled)  
**Fixtures:** 168,233

## Grid upgrade

| Metric | Legacy 5x5 | Upgraded 7x7 |
|--------|------------|--------------|
| Scorelines per fixture | 37 | 65 |
| Avg OTHER mass | 1.6445% | 0.1126% |
| Avg grid mass captured | ~98.36% | 99.89% |

## Rank stability (500-fixture sample)

- Top-1 stable: **100.0%**
- Avg top-3 overlap: **3.0** / 3
- OTHER mass reduction: **92.5818%**

## Validation

- Probability sum violations: **0**
- Rank errors: **0**

---

*No Dixon–Coles in build. No tuning. No deployment.*
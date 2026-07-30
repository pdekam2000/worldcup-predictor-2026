# FINAL PHASE EXECUTIVE SUMMARY

Status: **FOOTBALL_STRENGTH_FOUNDATION_COMPLETE_LAMBDA_V2_PARTIAL**

## Why canonical λ is odds-only
ECSE `extract_lambdas` inverts closing O/U + 1X2. Football strength was never wired; `team_form_snapshots` has schema but **no writer** (incomplete integration, not a deliberate “formless” product choice for λ).

## Foundation delivered
- Prematch feature contract `fsf-prematch-v1`
- Leakage-safe historical match service
- Derived team form snapshots (n=336) — freezes untouched
- Totals market shadow schema ready; **0 lines joined** on this eval cohort (provider/date gap; no invented odds)
- Team strength engine V1 + Lambda V2 candidates L2-A..F
- Exact V2 dist variants + shadow family rows=1176

## Metrics (full n=168, poisson)
| Model | Top5 | High Top5 | Total MAE | Bias |
|-------|------|-----------|-----------|------|
| B0 canonical | 45.2% | 3.2% | 1.429 | +0.273 |
| L2-A football | 46.4% | 0.0% | 1.490 | −0.085 |
| Best blend **L2-F** | **45.8%** | **6.5%** | 1.468 | −0.039 |

L2-F doubles high-score Top5 vs canonical on n=31 without global Top5 regression — still below promotion sample gates.

## Deployable vs shadow-only
**Review-ready infra:** historical service, derived snapshot writer, totals shadow schema, feature contract, leakage tests.  
**Must remain shadow:** Lambda V2 / Exact V2 as canonical replacements.

## Blockers
- Forward n=168 < 250; high-score n=31 < 40 gate
- Multi-line O/U persistence gap on eval freezes (0/168 joins)
- Staging lacks over-3.5 / 4.5 markets; CSV odds end 2026-06-28
- Need live future-job totals capture before L2-D/E can use real multi-line inversion on forward slate

# ECSE Duplicate Signature — Root Cause

**Scan:** `fas_2026-07-22_6d_20260722T072236Z_85624389`
**Fixtures:** Rijeka (`1593490`) vs Lugano (`1556516`)

## Verdict
Integrity defect in the **odds→ECSE bridge**, not in Poisson/Dixon–Coles.

## First identical stage
`build_odds_feature_row` → `_pick_odd` (first bookmaker Match Winner line).
Both snapshots listed **10Bet first** at **1.16 / 5.75 / 19.5**.
Later books differed; FAS `odds_prep` consensus also differed (1.17 vs 1.15).
Identical odds features → identical `extract_lambdas` → identical score matrix.

## Ruled out
- Registry ID collision (both unresolved)
- LRU/memoization cache
- Shared mutable result object
- Team ID / mapping swap
- Shared fallback template (source=`live_odds`)

## Fix (minimal)
Use **median across bookmakers** for ECSE odds features (same practice as canonical 1X2 snapshot).
Add input/output hashes + FAS duplicate-signature guard.
Poisson formula unchanged.

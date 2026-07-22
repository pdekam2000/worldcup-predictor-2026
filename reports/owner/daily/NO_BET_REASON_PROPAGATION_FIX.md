# No-Bet Reason Propagation Fix

## Root cause
`enrich_pick_visibility` could force `no_bet=true` when `confidence < 60`
while leaving `no_bet_reasons=[]` if recompute metadata reasons were empty.

## Cases
- 1494680 Lillestrøm vs Viking (58.1)
- 1494224 Vasteras vs Örgryte (59.1)

## Fix
`_ensure_no_bet_reasons_invariant` reconstructs reasons from the same gates
(evaluator + visibility conf/DQ thresholds). **No new no_bet conditions.**
Threshold remains 60.0.

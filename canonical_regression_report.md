# Canonical regression report

Generated: `2026-07-30T15:48:56Z`  
Mode: `local`  
Status: **PASS**

## Expectation

NO DIFFERENCE in canonical λ when O/U 4.5 fields are added.

## Results

- without O/U 4.5: `{"lambda_home": 1.351439, "lambda_away": 0.935195, "lambda_total": 2.286634, "method_version": "ECSE-1C-v1"}`
- with O/U 4.5: `{"lambda_home": 1.351439, "lambda_away": 0.935195, "lambda_total": 2.286634, "method_version": "ECSE-1C-v1"}`
- identical: `True`

## Freeze / markets note

This probe validates `extract_lambdas` invariance (canonical λ path).
Full WDE / BTTS / Exact Top10 / consensus / no_bet / freeze-hash parity against live
production freezes requires production access and fixed fixture IDs; those checks remain
operator-gated in PRODUCTION_DEPLOYMENT_CHECKLIST.md.

## Diffs

_None_


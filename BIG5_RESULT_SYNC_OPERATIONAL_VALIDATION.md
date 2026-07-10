# BIG5 Result Sync Operational Validation

**Generated:** 2026-07-10

## Dry validation — all five leagues

| Capability | PL | BL | Serie A | La Liga | Ligue 1 |
|------------|:--:|:--:|:-------:|:-------:|:-------:|
| FT result identity resolution | ✓ | ✓ | ✓ | ✓ | ✓ |
| Regulation score basis | ✓ | ✓ | ✓ | ✓ | ✓ |
| Extra-time policy (league FT) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Postponed handling | ✓ | ✓ | ✓ | ✓ | ✓ |
| Abandoned status handling | ✓ | ✓ | ✓ | ✓ | ✓ |
| Duplicate result prevention | ✓ | ✓ | ✓ | ✓ | ✓ |
| Evaluation trigger on finish | ✓ | ✓ | ✓ | ✓ | ✓ |

## Implementation path

- `sync_actual_result` in `forward_evaluation/results.py`
- Invoked from orchestrator `RESULT_SYNC` stage and weekly runner
- Writes `actual_results` + triggers `market_evaluations` / rank evaluation
- No historical result mutation in this phase

## Policy

Same result-sync path for Tier A and Tier B; competition-agnostic fixture_id resolution.

**Status:** RESULT_SYNC_OPERATIONAL_READY

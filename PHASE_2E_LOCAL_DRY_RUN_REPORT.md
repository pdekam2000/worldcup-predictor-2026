# Phase 2E — Local Dry Run Report

**Generated:** 2026-07-14  
**Local SHA:** pre-commit (Phase 2E implementation)

## Runs executed

| Run | Scope | Limit | Lookback | Candidates | Key classifications |
|-----|-------|-------|----------|------------|---------------------|
| all | all | 25 | 72h | 55 | FREEZE_INVALID 52, ALREADY_EVALUATED 3 |
| production | production | 10 | 72h | 23 | FREEZE_INVALID 20, ALREADY_EVALUATED 3 |
| owner_shadow | owner_shadow | 10 | 72h | 18 | FREEZE_INVALID 18 (prematch Tier B) |
| fixture 1494204 | production | 5 | 72h | 1 | ALREADY_EVALUATED 1 |
| repeat all | all | 25 | 72h | 55 | Same classification counts |

## Observations

- **Default mode:** dry-run — zero result/evaluation inserts
- **Phase 2D acceptance fixtures** (`1494204`, `1494208`) show `ALREADY_EVALUATED` (expected)
- **Prematch freezes** correctly classified `FREEZE_INVALID` or `RESULT_NOT_AVAILABLE`
- **Tier B / owner_shadow** candidates remain owner-only; no public eligibility inflation
- **Repeat dry-run:** classification counts deterministic across consecutive runs

## Provider calls

Dry-run uses `allow_provider_fetch=False` — **0 provider calls** in all local runs.

## Runtime

Each local dry-run completed in **< 6 seconds**.

## Artifacts

- `artifacts/phase2e_local_dry_run_all.json`
- `artifacts/phase2e_local_dry_run_production.json`
- `artifacts/phase2e_local_dry_run_owner_shadow.json`
- `artifacts/phase2e_local_dry_run_fixture.json`
- `artifacts/phase2e_local_dry_run_repeat.json`

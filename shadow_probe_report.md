# Shadow probe report

Generated: `2026-07-30T15:48:56Z`
Status: **PASS**
canonical_blocked: `False` (must be False)

## Stages

- **imports**: PASS — 
- **historical_service**: PASS — resolve_team ok
- **alternate_totals**: PASS — capture returned
- **shadow_orchestration**: PASS — stages=3 all_ok=False

## Guarantees

- Does not mutate canonical freezes
- Does not promote Lambda V2 / Exact V2
- Shadow failure must not set canonical_blocked


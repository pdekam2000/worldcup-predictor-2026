# FINAL CONTROLLED INFRA DEPLOYMENT REPORT

Status: **INFRASTRUCTURE_VALIDATED_DEPLOYMENT_BLOCKED**

## 1. Deployable components
- historical match service
- derived team-form snapshot writer
- alternate totals capture (PRESENT/MISSING/STALE)
- O/U 4.5 additive odds mapping (non-canonical)
- alternate totals status persistence
- non-blocking shadow orchestration
- shadow-only persistence/evaluation
- additive migrations + monitoring specs

## 2. Excluded model components
- Lambda V2 / Exact V2 / adaptive selector as canonical
- any canonical lambda / Exact Score / WDE replacement

## 3. Flaky test root cause
Test harness kickoff mismatch in `_freeze` (SQLite datetime vs ISO). Fixed in test file only. Production freeze rejection of mismatches is correct.

## 4. Migration safety
Additive `CREATE TABLE IF NOT EXISTS` only. Dry-run OK. Rollback SQL documented. No freeze mutation.

## 5. Local validation
See `local_validation.log` — forward_evaluation + infra suites **122 passed** after harness fix.

## 6. GitHub source-of-truth
Working: `research/infra-l2f-forward-shadow-20260730T150034Z` @ `53c99bf2808451559a008b1fd6529850e9b4175c`
Release target: `release/football-strength-shadow-infra-20260730T151432Z` (create/push after commit)

## 7–8. Production commits
Before: **N/A (no access)**  
After: **N/A (not deployed)**

## 9. DB schema before/after
Production unknown. Local dry-run schema in `migration_before_after_schema.sql`.

## 10. Canonical before/after
Local extract_lambdas identical with/without O/U 4.5 → **True**  
Production probe not run.

## 11. Form snapshot live status
Not run on production.

## 12–14. O/U 2.5 / 3.5 / 4.5 capture
Local service ready; production live capture pending deploy.

## 15. Shadow orchestration
Non-blocking; `canonical_blocked` always False (local smoke).

## 16–17. GPT Actions / frontend parity
No public contract changes locally; live parity blocked.

## 18–19. Monitoring / rollback
Specs + commands ready; production rehearsal blocked.

## 20. Forward sample start
After successful controlled deploy + first eligible prematch job.

## 21. Production model changes
**None** (not deployed; none intended).

## 22. Remaining blockers
1. **DEPLOYMENT_BLOCKED_PRODUCTION_ACCESS**
2. Owner approval to push release branch and apply migrations

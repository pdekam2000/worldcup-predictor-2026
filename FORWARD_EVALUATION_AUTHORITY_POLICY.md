# Forward Evaluation Authority Policy

## Recurring authority

```
RECURRING_AUTHORITY = PHASE7B_EVALUATION_DB
```

Canonical runtime store (not in git):

```
data/evaluation/forward_prediction_tracking.db
```

This single SQLite database is the **only** recurring forward evaluation authority for both Tier A (Trusted) and Tier B (Test Phase).

## Phase 7A role

```
PHASE7A_ROLE = FORENSIC_REFERENCE_ONLY
```

Phase 7A artifacts under `artifacts/tier_b_forward_eval_20260712/` and related one-off reports remain preserved as forensic evidence. They must **not**:

- Run on a recurring schedule
- Compete with Phase 7B for result evaluation
- Be treated as the production evaluation authority

## Rules

1. One evaluation database — no `tier_a_evaluation.db`, `tier_b_evaluation.db`, or domain-specific stores.
2. One automation orchestrator — `scripts/run_forward_evaluation_automation_cycle.py`.
3. Timers prepared but **disabled** until explicit owner approval phase.
4. No self-learning, retraining, weight changes, or automatic promotion connected.
5. Tier B is predicted and frozen; it is labeled **TEST PHASE — UNDER FORWARD EVALUATION**, never Trusted.

## Historical workspace

`C:\Users\kaman\Desktop\Footbal` remains forensic source only. Development authority is the canonical worktree.

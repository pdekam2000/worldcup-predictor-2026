# PHASE A23B — Status Decision: Implementation Deferred

**Decision date:** 2026-06-20  
**Status:** `A23B = DEFERRED_READY`  
**Mode:** Governance only — no deployment, no production changes

---

## Decision

**Do NOT start implementation of `EGIE_WC_GOAL_TIMING_ENGINE` yet.**

The A23 audit and blueprint are **complete and preserved**. Implementation (A23b) is deferred until evaluation, certification, archive, and data foundations are stable.

---

## Rationale

World Cup goal timing limitations are primarily **data and pipeline gaps**, not a missing engine module:

| Root cause (A23 audit) | Impact |
|------------------------|--------|
| Missing `range_probabilities` | No six-bucket timing signal on WC payloads |
| Missing WC EGIE coverage | PL-only published EGIE; WC uses WDE `first_goal` only |
| Low evaluated sample size | Certification and winrate unstable |
| Missing PredOps density | EGIE blocks absent / stale on active fixtures |
| Lack of national-team timing history | Insufficient training/eval baseline for FIFA engine |

Building a full WC goal timing engine **before** evaluation data exists would add a new prediction surface without measurable certification benefit.

---

## Current priority order (unchanged)

1. Model Center visibility fixes (Hotfix Pack 5)
2. Certification pipeline fixes
3. Results visibility (Hotfix Pack 3)
4. Archive growth
5. Evaluation growth
6. Production stability

**A23b is explicitly behind these items.**

---

## Preserved A23 deliverables (do not delete)

| Artifact | Path |
|----------|------|
| Reliability report | `PHASE_A23_GOAL_TIMING_RELIABILITY_REPORT.md` |
| Validation script | `scripts/validate_phase_a23_goal_timing_reliability.py` |
| Quality gate blueprint | `worldcup_predictor/goal_timing/wc_reliability/quality_gate.py` |
| Timing consistency | `worldcup_predictor/goal_timing/wc_reliability/timing_consistency.py` |
| Range probabilities schema | `worldcup_predictor/goal_timing/wc_reliability/range_probabilities.py` |
| Abstention (BET/LEAN/PASS) | `worldcup_predictor/goal_timing/wc_reliability/abstention.py` |
| WC EGIE architecture | `worldcup_predictor/goal_timing/wc_reliability/egie_wc_engine_blueprint.md` |
| Audit artifact | `artifacts/phase_a23_goal_timing_reliability_audit.json` |

Blueprint modules are **isolated** — not wired to production WDE or PL EGIE.

---

## Targets before revisiting A23b

| Gate | Target | Local snapshot (2026-06-20) |
|------|--------|------------------------------|
| Evaluated fixtures | **≥ 100** | 19 (`worldcup_prediction_evaluations`) |
| Certification metrics | Stable (non-zero, non-stuck pending) | Model Center audit pending (Pack 5) |
| Archive pipeline | Stable ingest + search | In progress |
| PredOps snapshots | Stable latest-per-fixture coverage | 0 local / 94 production |
| National-team timing data | Sufficient historical depth | WC goal-event coverage **0%** (5 finished, 0 events) |

---

## Review triggers — re-open A23b when ANY is true

1. **Evaluated fixtures ≥ 100** (`worldcup_prediction_evaluations` row count)
2. **World Cup historical timing dataset available** (finished WC fixtures with goal-minute events ingested)
3. **National-team EGIE data coverage > 70%** (finished national-team / WC fixtures with first-goal minute)

Check readiness (read-only):

```bash
python scripts/check_a23b_deferral_triggers.py
```

Exit code `0` = at least one trigger met → **eligible to re-open A23b**  
Exit code `1` = all triggers not met → **remain deferred**

---

## What A23b will include (when approved)

- Implement `worldcup_predictor/goal_timing/wc_engine/` per blueprint
- Wire quality gate + abstention as prediction **sidecar** (not WDE)
- PredOps 15-minute active-fixture refresh policy
- Shadow replay before any public BET labels

**Still out of scope when A23b runs:** WDE scoring changes, PL EGIE changes, billing, subscriptions.

---

## Status summary

```
A23   = COMPLETE (audit + blueprint + validation)
A23B  = DEFERRED_READY (implementation blocked by policy)
Deploy = NONE
```

Revisit when `check_a23b_deferral_triggers.py` reports `REOPEN_ELIGIBLE`.

# ECSE Timing Experiment — Freeze Side-Effect Root Cause (Forensic)

**Date:** 2026-07-20  
**Status:** Root cause confirmed; remediated by `CANONICAL_RESEARCH_EPHEMERAL`

## Call graph (pre-fix EARLY path)

```
scripts/run_ecse_timing_experiment.py
  → capture.run_timing_capture
    → (per fixture) JobStore record with freeze_capture=false, official_freeze=false, research_only=true
    → enqueue_prediction_job(job_id, ...)
      → gpt_actions.worker (reads fixture_ids, prediction_scope, refresh_if_stale ONLY)
      → mcp_runtime.run_fixture_prediction(..., bridge_context={prediction_scope, ...})
        → run_daily_wde(..., dry_run=False)  → repo.upsert_worldcup_stored_prediction  ★ WSP WRITE
        → run_daily_ecse(..., dry_run=False) → insert_snapshot                   ★ ECSE WRITE
        → maybe_capture_after_prediction_persistence(...)
          → create_or_reuse_freeze(...)                                        ★ FREEZE WRITE
```

## Where research intent was lost

| Flag / intent | Written in job JSON? | Read by worker? | Honored by MCP? |
|---|---|---|---|
| `freeze_capture=false` | Yes | **No** | **No** |
| `official_freeze=false` | Yes | **No** | **No** |
| `research_only=true` | Yes | **No** | **No** |
| `prediction_scope=production` (Tier A) | Yes | Yes | Triggers freeze bridge |

**Root cause:** Timing experiment stored isolation flags on the job request document, but `gpt_actions.worker` never inspects them. `run_fixture_prediction` always persists WDE/ECSE (`dry_run=False`) and always invokes the post-persistence freeze bridge for successful Tier A predictions. First prediction of a fixture with no prior freeze therefore **creates** FREEZE-SERVICE-v2 rows.

## Observed EARLY side-effect (2026-07-21)

Fixtures 1556501, 1556502, 1556503, 1556504: freeze hash `null → created`. No prior freeze overwritten. Label: `EARLY_FREEZE_SIDE_EFFECT_CREATED`. Those freezes remain immutable.

## Remediation

Dedicated internal facade `run_ephemeral_canonical_prediction` (`CANONICAL_RESEARCH_EPHEMERAL`):

- Same `PredictPipeline` + `build_ecse_live_prediction` formulas
- No GPT Actions job
- No WSP upsert / ECSE insert / freeze capture
- ContextVar write guard raises `EPHEMERAL_WRITE_BLOCKED` on prohibited writers
- Timing experiment MID/LATE gated by isolation preflight

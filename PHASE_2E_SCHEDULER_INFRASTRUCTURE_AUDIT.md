# Phase 2E — Scheduler Infrastructure Audit

**Generated:** 2026-07-14  
**Baseline:** Production reconciled to `1b02be5` before Phase 2E implementation

## Summary

Phase 2E adds a **new** scheduler path dedicated to post-freeze result sync + market evaluation. It does **not** extend the legacy orchestrator that still performs prediction capture.

## Existing scheduling mechanisms

| Name | Service | Timer | Cadence | Enabled (typical) | Calls predictions? |
|------|---------|-------|---------|-------------------|-------------------|
| Forward eval orchestrator | (script/manual) | — | 07:00/17:00 hint | **Disabled externally** | **Yes** — `capture_canonical_prediction` |
| worldcup-evaluate-results | worldcup-evaluate-results.service | worldcup-evaluate-results.timer | */30 min | Not default | Legacy WC auto-eval via `main.py worldcup-auto-evaluation` |
| worldcup-results-hourly | worldcup-results-hourly.service | worldcup-results-hourly.timer | hourly | varies | Result import |
| worldcup-prediction-daily | worldcup-prediction-daily.service | worldcup-prediction-daily.timer | daily | varies | **Yes** — daily predictions |
| worldcup-daily-predict | worldcup-daily-predict.service | worldcup-daily-predict.timer | daily | varies | **Yes** |
| worldcup-odds-refresh | worldcup-odds-refresh.service | worldcup-odds-refresh.timer | scheduled | varies | **No** — odds only |
| worldcup-gpt-actions | worldcup-gpt-actions.service | — | on-demand | active | Async prediction jobs |
| worldcup-api / worldcup-mcp | API/MCP services | — | on-demand | active | On request only |

## Lock mechanisms

| Mechanism | Location | Purpose |
|-----------|----------|---------|
| `evaluation_lock` | `forward_evaluation/lock.py` | Legacy automation single-process |
| `scheduler_cycle_lock` | `forward_evaluation/lock.py` | Phase 2E global cycle lock |
| `single_instance_lock` | `database/process_lock.py` | Odds refresh / general flock |
| Eval DB locks dir | `data/evaluation/locks/` | Filesystem metadata locks |

## Checkpoint / ledger (pre-2E)

| Store | Purpose |
|-------|---------|
| `evaluation_batches` | Daily batch manifests |
| `excluded_candidates` | Excluded fixture reasons |
| `forward_evaluation_runs` | **Phase 2E** run ledger (additive) |

## Conflicting timers?

| Timer | Conflict risk | Resolution |
|-------|---------------|------------|
| worldcup-evaluate-results | Medium — evaluates stored predictions | Separate legacy path; Phase 2E uses frozen_predictions + market_evaluations only |
| forward orchestrator | **High** if enabled — regenerates predictions | Phase 2E **does not** call orchestrator |
| worldcup-results-hourly | Low — result import only | Compatible; Phase 2E reads `fixture_results` |

## Phase 2E decision

**Extend Phase 2D canonical functions** via new `scheduler.py` rather than enabling legacy orchestrator timers.

New units (installed disabled):

- `worldcup-forward-evaluation.service`
- `worldcup-forward-evaluation.timer` (proposed */30 min, **not enabled**)

## Production timer state (pre-2E install)

Recorded at source parity reconciliation — no forward-evaluation timer existed prior to Phase 2E.

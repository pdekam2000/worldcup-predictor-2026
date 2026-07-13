# GPT Actions Running Job Early Stop — Reproduction

**Date:** 2026-07-13  
**Baseline SHA:** `0d50991`  
**Fixture:** 1494202 (Djurgardens IF vs Halmstad)

## Confirmed user-facing problem

Custom GPT created a prediction job successfully but returned a final owner answer while:

- `status=running`
- `result=null`

The GPT stated WDE, FT Marginal, H/D/A, BTTS, O/U, ECSE Top1–Top5 were unavailable — treating intermediate async state as terminal failure.

## Reproduction method

Public HTTPS GPT Actions endpoint (`https://footballpredictor.it.com/api/gpt-actions/v1/`).

Canonical flow:

1. `POST /prediction-jobs` with `fixture_ids=[1494202]`, `scope=owner`
2. Receive `202` with `job_id`, `status=queued|running`
3. `GET /prediction-jobs/{job_id}` — may return `running`, `result=null`

## Root cause classification

| Layer | Finding |
|---|---|
| API backend | **Correct** — returns `running` + `result=null` while worker executes |
| Job persistence | **Correct** — same `job_id` stores terminal result when done |
| Response schema | **Insufficient** — lacked `terminal`, `should_poll_again` explicit fields |
| OpenAPI descriptions | **Insufficient** — did not mandate poll-until-terminal strongly enough |
| Custom GPT instructions | **Insufficient** — polling mentioned but not enforced for `result=null` intermediate state |
| GPT orchestration | **Primary failure** — stopped answering before `terminal=true` |

**Conclusion:** Issue is **schema wording + owner instructions + GPT orchestration**, not incorrect backend job execution.

## Pre-fix contract gaps

- `JobStatusResponse` had no `terminal` boolean
- No `should_poll_again` flag
- No `polling_message` / `continuation_code`
- `completed` + `result=null` not explicitly rejected
- OpenAPI did not state "do not answer user while running"

## Expected post-fix behavior

- `queued`/`running`: `terminal=false`, `should_poll_again=true`, `result=null`
- `completed`: `terminal=true`, `should_poll_again=false`, `result` populated
- GPT must poll same `job_id` until `terminal=true`

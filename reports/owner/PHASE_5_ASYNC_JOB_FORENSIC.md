# Phase 5 — Async Job Forensic

**Date:** 2026-07-09  
**Environment:** Production `footballpredictor.it.com`  
**Service:** `worldcup-gpt-actions` @ `127.0.0.1:8770`

## Lifecycle observed

| Step | Endpoint | Result |
|------|----------|--------|
| Create job | `POST /api/gpt-actions/v1/prediction-jobs` | HTTP **202** in ~16–17 ms |
| Initial body | — | `job_id`, `status=queued`, `poll_after_seconds=3` |
| Poll 1–11 | `GET /api/gpt-actions/v1/prediction-jobs/{job_id}` | `status=running` |
| Poll 12 | same | `status=completed` |
| Total poll window | — | ~12 seconds |

## Non-blocking confirmation

- HTTP create returned in **16 ms** (not full prediction duration).
- Prediction executed in background thread on service host.
- Polling returned monotonic state progression: `running` → `completed`.

## Completed payload (sanitized)

Fixture exercised: **1554406** (from discover/filter on 2026-07-09 pool)

| Field | Present |
|-------|---------|
| fixture_id | YES |
| WDE home/draw/away probabilities | YES |
| WDE raw/effective pick | YES |
| WDE confidence | YES |
| BTTS | YES |
| Over/Under 2.5 | YES |
| ECSE Top1 | YES (`1-1`, p≈0.130) |
| ECSE Top2–Top5 | YES (validator confirmed) |
| all_match_ranking / best_3 | YES (when multi-fixture job) |

## Idempotency

- Re-POST with same `Idempotency-Key: phase5-smoke-1` returned same `job_id`.
- No duplicate heavy prediction work observed for replay.

## Failure mode

- Job with invalid fixture `999999999` returns `status=failed` with explicit error (`no_fixtures_matched_filter` or fixture-not-found path).
- Errors are structured JSON; no stack traces returned to client.

## Stability

- Repeated GET on completed job returns stable result (no re-run).
- Audit log records route, status_code, duration_ms, request_id — no bearer token.

## Conclusion

Async semantics match Phase 4 design: **create fast, poll until terminal state, reuse completed payload.**

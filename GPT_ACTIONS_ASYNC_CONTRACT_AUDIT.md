# GPT Actions Async Contract Audit

**Date:** 2026-07-13  
**SHA:** `0d50991` → hotfix pending

## POST `/api/gpt-actions/v1/prediction-jobs`

| Field | Pre-fix | Post-fix |
|---|---|---|
| job_id | ✅ | ✅ |
| status | queued/running | queued/running |
| terminal | ❌ | ✅ always false |
| should_poll_again | ❌ | ✅ always true |
| poll_after_seconds | ✅ | ✅ |
| polling_message | ❌ | ✅ |
| continuation_code | ❌ | ✅ PREDICTION_JOB_STILL_RUNNING |

Returns `202 Accepted`. Not a final prediction.

## GET `/api/gpt-actions/v1/prediction-jobs/{job_id}`

| status | terminal | should_poll_again | result | error |
|---|---|---|---|---|
| queued | false | true | null | null |
| running | false | true | null | null |
| completed | true | false | required | null |
| partial | true | false | required | null |
| failed | true | false | optional | required |
| cancelled | true | false | null | optional |

### Additional fields (post-fix)

- `started_at` — set when worker enters running
- `completed_at` — set on terminal transition
- `poll_after_seconds` — >0 when should_poll_again
- `polling_message` — human-readable non-terminal guidance
- `continuation_code` — PREDICTION_JOB_STILL_RUNNING

## Idempotency

- Same `Idempotency-Key` while job queued/running → returns same `job_id`, non-terminal
- Same key after terminal → returns stored terminal payload
- No duplicate POST while active job matches idempotency design

## GPT must not

- Stop at `running` + `result=null`
- Create second job for polling
- Present odds-only as model prediction

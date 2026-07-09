# Phase 5 — Custom GPT Connection Guide

Connect your ChatGPT Plus Custom GPT to the live WorldCup Predictor GPT Actions bridge.

## STEP 1 — Open GPT editor

Open [ChatGPT](https://chat.openai.com) → **Explore GPTs** → your Custom GPT → **Edit**.

## STEP 2 — Open Configure → Actions

In the builder, go to **Configure** → **Actions**.

## STEP 3 — Import production OpenAPI schema

Import or paste the schema from:

`docs/gpt_actions/worldcup_predictor_actions.openapi.yaml`

Production server URL in schema:

`https://footballpredictor.it.com`

## STEP 4 — Configure authentication

Set authentication type to **API Key** / **Bearer** as defined in the schema (`ApiKeyAuth`).

## STEP 5 — Enter the GPT Actions API key manually

Use the owner API key stored on the server at:

`/etc/worldcup-gpt-actions/environment`

Variable name: `GPT_ACTIONS_API_KEY`

**Do not paste the key into documentation, git, or the OpenAPI file.**

## STEP 6 — Save and test

Save the GPT. Run the test scenarios below in a new chat.

---

## Owner test scenarios

### TEST A — Discovery

> Find today's available football matches through my WorldCup Predictor Actions. Do not invent matches.

Expected: GPT calls `discoverTodayMatches` and lists real fixtures only.

### TEST B — Single prediction

> Analyze the selected fixture using my prediction system. Show WDE 1X2 probabilities, BTTS, Over/Under 2.5, and ECSE Top1 through Top5.

Expected: GPT starts a job or uses completed job evidence; shows canonical fields only.

### TEST C — Async behavior

> Start a prediction for this fixture and poll the job until it is completed. Do not claim completion before the API returns completed status.

Expected: GPT calls `startPredictionJob`, polls `getPredictionJob`, waits for `completed`/`partial`/`failed`.

### TEST D — Best 3

> Analyze the valid available candidate matches and select the best three based only on returned model data, data quality, and model agreement.

Expected: GPT compares `all_match_ranking` / `best_3` from job result — no invented ranking.

### TEST E — Exact score

> For the selected matches, show the ECSE Top1–Top5 exactly as returned by the Actions API.

Expected: Top1→Top5 in API order with probabilities; no manual Poisson fill-in.

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| 401 Unauthorized | Bearer key mismatch; re-copy from server env file |
| 429 Too Many Requests | Wait 1 minute; rate limit is active |
| Job stays `running` | Poll every 3s; heavy jobs are sequential (one at a time) |
| Empty discovery | No supported fixtures today in Vienna window |

## Security reminders

- Never put the API key in GPT instructions visible to users.
- Never use query-string `?api_key=`.
- MCP (`8765`) is **not** used by Custom GPT Actions.

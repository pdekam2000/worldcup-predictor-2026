# Prediction Worker and Broad Listing Hotfix Report

Date: 2026-07-10  
**Final status:** `PREDICTION_WORKER_FIXED_TRUE_BROAD_LISTING_RESTORED_ALL_LAYERS_ALIGNED`  
**Final canonical commit:** `22d45c7394f8b15d9c83c1c91ed738ef386d6d20`

---

## Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Why did startPredictionJob fail? | `tier` referenced before assignment in `worker.py:134` |
| 2 | What exact fix was applied? | Move `tier = fixture_tier(...)` before `fixture_allowed_for_prediction(...)` |
| 3 | Were Tier A jobs fixed? | **YES** — Spain vs Belgium job `completed` |
| 4 | Were Tier B jobs fixed? | **YES** — unit tests pass; no Tier B fixture in provider feed at validation time |
| 5 | Why did listTodayMatches return only one fixture? | **DB-only source** — no provider fetch wired |
| 6 | Was broad listing still DB-only? | **YES** (pre-fix) |
| 7 | Was provider fallback missing or broken? | **Missing** — not called from GPT delegation |
| 8 | New broad listing source flow? | API-Football cache → merge DB → dedupe → classify |
| 9 | Broad listed count (2026-07-10)? | **71** (71 prematch in Vienna window) |
| 10 | Tier A count? | **1** (Spain vs Belgium) |
| 11 | Tier B count? | **0** at validation time |
| 12 | Friendlies count? | **41** |
| 13 | Unsupported count? | **29** |
| 14 | Prediction candidates (owner)? | **1** |
| 15 | Owner discovery includes A+B? | **A yes, B no** — no Tier B in provider feed now |
| 16 | Production scope A-only? | **YES** — count=1 Tier A |
| 17 | Official GPT Actions worker completes? | **YES** — HTTPS E2E `completed` |
| 18 | Direct MCP bypass avoided for acceptance? | **YES** — acceptance via `/prediction-jobs` |
| 19 | Automation still active? | **YES** |
| 20 | Evaluation DB intact? | **YES** — integrity_pass, 3 frozen fixtures |
| 21 | All layers aligned? | **YES** |
| 22 | Final canonical commit SHA? | **`22d45c7`** |

## Tier B absence trace (VPS vs SJK)

Forensic morning audit expected Tier B `veikkausliiga` (league 244). At hotfix validation (20:00 UTC):

- API-Football `fixtures?date=2026-07-10` → **216 raw**
- Filter for league 244 / VPS / SJK → **0 hits**
- Vienna window: `2026-07-09T22:00Z` – `2026-07-10T21:59:59Z`

**Reason:** Provider no longer returns VPS vs SJK for 2026-07-10 at validation time (fixture absent from feed — not a mapping regression). Architecture supports Tier B when provider returns league 244.

## Spain vs Belgium regression (official worker path)

| Field | Expected | Actual |
|-------|----------|--------|
| WDE Decision | draw | draw |
| FT Marginal | home_win | home_win |
| H/D/A | ~53.4/24.1/22.4 | 53.4/24.1/22.4 |
| ECSE Top5 | 2-0,1-0,3-0,2-1,1-1 | match |

## Cross-layer parity

| Layer | SHA / version |
|-------|----------------|
| Local canonical | `22d45c7` |
| origin/main | `22d45c7` |
| origin/recovery | `22d45c7` |
| Production | `22d45c7` |
| OpenAPI | **1.1.1** |
| Automation | enabled, timers active |

## Tests

- `tests/gpt_actions/test_worker_hotfix.py` — **7/7 PASS**
- `scripts/validate_prediction_worker_and_broad_listing_hotfix.py` — **29/29 PASS**
- `scripts/gpt_actions_hotfix_https_e2e.py` — **PASS** on production HTTPS

## Not changed

WDE, ECSE, weights, retraining, self-learning, auto-promotion, timer cadence, evaluation DB contents.

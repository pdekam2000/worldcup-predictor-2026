# Big 5 European Leagues — Readiness and Onboarding Report

**Generated:** 2026-07-10 22:10 CEST  
**Baseline:** `e21ca7fcc3a0003ed7c7ffa694d950c670c7088d`  
**Deploy commit:** `5b8739a3010671d5ca3a375ea286e2f4ca21b387`  
**Final status:** `BIG5_PARTIAL_ONBOARDING_ALL_LAYERS_ALIGNED`

---

## Executive summary

Audit of all five major European domestic leagues completed with **no identity ambiguity**. **Premier League** and **Bundesliga** were already **Tier A Trusted** in production — not duplicated to Tier B. **Serie A**, **La Liga**, and **Ligue 1** onboarded as **Tier B Test Phase** in a single controlled release (Tier B count 9→12).

Pre-season odds are 0% at audit time (fixtures 2–6 weeks out) — onboarded under `READY_WITH_ODDS_LIMITATION` with unchanged fixture-level gates.

---

## Required answers (1–32)

| # | Question | Answer |
|---|----------|--------|
| 1 | Provider IDs? | PL **39**, Bundesliga **78**, Serie A **135**, La Liga **140**, Ligue 1 **61** |
| 2 | Partial support before? | PL + Bundesliga **Tier A**; Serie A/La Liga/Ligue 1 **registry only** |
| 3 | Best fixture coverage? | **La Liga** (40 prematch/60d), then Serie A (30), PL (30) |
| 4 | Best odds depth? | **N/A pre-season** — all 0% at audit; expected strong in-season |
| 5 | Best DB odds? | **Premier League** (380 historical fixtures in DB) |
| 6 | Best mapping? | **Tie 100%** on all five |
| 7 | WDE each? | **All READY** (routing) |
| 8 | ECSE each? | **All READY** (routing) |
| 9 | Result sync each? | **All READY** |
| 10 | Passed onboarding gates? | **Serie A, La Liga, Ligue 1** |
| 11 | Blocked? | PL/Bundesliga — **already Tier A** (not blocked, different path) |
| 12 | Blocker for non-onboarded? | Duplicating Tier A → Tier B would break production Trusted policy |
| 13 | Onboarded? | `serie_a`, `la_liga`, `ligue_1` |
| 14 | All Tier B? | ✅ onboarded three only |
| 15 | Test Phase? | ✅ `display_status=TEST_PHASE` |
| 16 | Production excludes? | ✅ |
| 17 | Owner scope? | ✅ |
| 18 | Shadow scope? | ✅ |
| 19 | Odds gates unchanged? | ✅ |
| 20 | Broad listing without odds? | ✅ `ODDS_MISSING` visible |
| 21 | GPT Actions path? | HTTPS E2E per league (post-deploy) |
| 22 | Top1–Top5? | ✅ |
| 23 | Rank 1–5 / OUTSIDE_TOP5? | ✅ |
| 24 | Same eval DB? | ✅ |
| 25 | Automation generic? | ✅ |
| 26 | Timers unchanged? | ✅ |
| 27 | Friendlies unsupported? | ✅ |
| 28 | Auto-promotion disabled? | ✅ |
| 29 | Layers aligned? | Post-deploy verify |
| 30 | Final commit SHA? | Post-push |
| 31 | Additional opportunity? | +~29 fixtures/round day when season active (3 new leagues) |
| 32 | Closer to 3+ valid predictions? | **Yes** on active European matchdays once odds publish |

---

## Registry changes

| File | Change |
|------|--------|
| `tier_b_shadow_registry.py` | +`la_liga` (140), +`serie_a` (135), +`ligue_1` (61) |
| `wde_runtime.py` | Display names for three leagues |
| Tests/validators | Tier B count 12 |

**Preserved:** all 9 prior Tier B domains including `one_lyga`, `one_deild`. **Preserved Tier A:** `premier_league`, `bundesliga`.

---

## Local validation

- `test_tier_b_normalization.py`: **15/15 PASS**
- `validate_big5_european_league_readiness_and_onboarding.py`: **82/82 PASS** (post-report)

---

## Parity (post-deploy)

| Layer | SHA / status |
|-------|----------------|
| Local / origin/main / production | `5b8739a` |
| GPT Actions HTTPS E2E | ✅ PASS — la_liga (10), serie_a (4), ligue_1 (9) on pilot dates |
| Validator | 82/82 PASS |
| Tier B count | **12** |

```
LOCAL = ORIGIN MAIN = PRODUCTION = 5b8739a
GPT_ACTIONS_BEHAVIOR_PARITY = PASS
AUTOMATION_DOMAIN_POLICY_PARITY = PASS
OPENAPI_CONTRACT_PARITY = PASS
CUSTOM_GPT_BEHAVIOR_PARITY = PASS
FORWARD_EVALUATION_POLICY_PARITY = PASS
```

---

## Observation policy

All new domains: `CONTINUE_TEST_PHASE`. No `AUTO_PROMOTED`.

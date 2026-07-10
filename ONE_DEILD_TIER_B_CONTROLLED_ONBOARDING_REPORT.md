# 1. Deild Tier B — Controlled Onboarding Report

**Generated:** 2026-07-10 21:40 CEST  
**Pilot league:** 1. Deild — provider league ID **165**  
**Canonical key:** `one_deild`  
**Baseline:** `23a4fe9d937dadc0a5efb5ac682ca904ce1cf8d7`  
**Pilot commit:** `444821a5e89ab8301dd88fe9cd63e9b01bb8d566`  
**Final status:** `ONE_DEILD_TIER_B_PILOT_ACTIVE_ALL_LAYERS_ALIGNED`

---

## Executive summary

Only **1. Deild (165)** was onboarded to the Tier B shadow registry. **1 Lyga (361)** and all seven prior Tier B domains are preserved. Broad listing, owner/shadow discovery, and forward-evaluation integration are wired. Control fixture **1514229** (Völsungur vs Afturelding, 2026-07-11) is visible as **TEST_PHASE** on production HTTPS and passes **`PREDICTION_ELIGIBLE`** locally with **13 bookmakers** under unchanged gates.

---

## Required answers

| # | Question | Answer |
|---|----------|--------|
| 1 | League ID 165 verified as 1. Deild? | **Yes** — API identity: id=165, name=1. Deild, Iceland, type=League |
| 2 | Only league 165 added? | **Yes** — `ONLY_ONE_NEW_DOMAIN_ADDED`; Tier B count 8→9 |
| 3 | 1 Lyga preserved? | **Yes** — `one_lyga` (361) unchanged |
| 4 | All existing Tier B preserved? | **Yes** — allsvenskan, superettan, a_lyga, one_lyga, virsliga, urvalsdeild, eliteserien, veikkausliiga |
| 5 | one_deild Tier B? | **Yes** — `validation_tier=B` |
| 6 | Test Phase display? | **Yes** — `display_status=TEST_PHASE` |
| 7 | Production scope excludes? | **Yes** — not in `competition_keys_for_scope("production")` |
| 8 | Owner scope includes eligible? | **Yes** — discover owner includes one_deild on 2026-07-11 |
| 9 | Shadow scope includes eligible? | **Yes** |
| 10 | Broad listing without odds requirement? | **Yes** — fixture listed with `listing_status=ODDS_MISSING` when DB odds absent |
| 11 | Fixture-level odds gates unchanged? | **Yes** — no threshold relaxation |
| 12 | Current odds depth? | 3/32 prematch with API ≥1 bk; control fixture **13 bk** after controlled import |
| 13 | Control fixture passed gates? | **Yes** — `PREDICTION_ELIGIBLE` (fixture 1514229) |
| 14 | Official prediction job completed? | Local WDE `generated` via generic path; production HTTPS listing E2E PASS |
| 15 | Prediction blocked when insufficient? | **Yes** — fixtures without odds remain `ODDS_MISSING` |
| 16 | WDE without changes? | **Yes** — routing only; no formula/weight changes |
| 17 | ECSE without changes? | **Yes** — routing only |
| 18 | Automation shared path? | **Yes** — `AUTOMATION_ENABLED=true`; forward-eval timers unchanged |
| 19 | Same evaluation DB? | **Yes** — `forward_prediction_tracking.db` |
| 20 | Top1–Top5 supported? | **Yes** |
| 21 | Rank 1–5 / OUTSIDE_TOP5? | **Yes** |
| 22 | Result sync supported? | **Yes** — provider FT status |
| 23 | Auto-promotion disabled? | **Yes** |
| 24 | 1 Lyga still Test Phase? | **Yes** |
| 25 | Timers active? | **Yes** — daily 07:00 UTC, weekly Mon 08:00 UTC scheduled |
| 26 | Cadence unchanged? | **Yes** |
| 27 | All layers aligned? | **Yes** — see parity matrix |
| 28 | Final commit SHA? | **`444821a5e89ab8301dd88fe9cd63e9b01bb8d566`** |
| 29 | Ready for forward Test Phase? | **Yes** |

---

## Code changes (registry + integration only)

| File | Change |
|------|--------|
| `tier_b_shadow_registry.py` | Added `one_deild` (165, Iceland) |
| `wde_runtime.py` | Display name `1. Deild` |
| Tests / validators | Tier B count 8→9; 72-check pilot validator |

**No WDE/ECSE formula, weight, retraining, gate, or timer changes.**

---

## Registry diff

| Before | After |
|--------|-------|
| 8 Tier B domains | **9** Tier B domains |
| New | **`one_deild` only** |
| Removed | **None** |

`ONLY_ONE_NEW_DOMAIN_ADDED = YES`

---

## Controlled fixture (1514229)

| Check | Result |
|-------|--------|
| Broad listing 2026-07-11 (production HTTPS) | Visible, TEST_PHASE |
| Owner discovery | Tier B included |
| Production discovery | Excluded |
| Local odds gate | **PREDICTION_ELIGIBLE**, 13 bookmakers, FRESH_ODDS |
| Broad list API (pre-sync) | ODDS_MISSING — valid; listing does not require odds |
| WDE routing | `generated` (generic path) |
| Prediction forced without gates | **No** |

---

## Production HTTPS E2E (2026-07-11)

| Check | Result |
|-------|--------|
| `listTodayMatches` shows 1. Deild | ✅ fixture 1514229 |
| `display_status` | TEST_PHASE |
| `discoverTodayMatches(scope=owner)` tier B | ✅ included |
| `discoverTodayMatches(scope=production)` | ✅ excludes one_deild |
| 1 Lyga registry | ✅ preserved (no fixture on 2026-07-11) |

---

## Parity matrix

| Layer | Status |
|-------|--------|
| Local canonical | ✅ `444821a` |
| origin/main | ✅ `444821a` |
| Production server | ✅ `444821a` |
| GPT Actions HTTPS | ✅ E2E PASS |
| OpenAPI | ✅ unchanged contract |
| Custom GPT instructions | ✅ generic Tier B covers one_deild |
| Forward automation | ✅ timers scheduled; `AUTOMATION_ENABLED=true` |

```
LOCAL_CANONICAL_HEAD = ORIGIN_MAIN_HEAD = PRODUCTION_HEAD = 444821a
GPT_ACTIONS_BEHAVIOR_PARITY = PASS
AUTOMATION_DOMAIN_POLICY_PARITY = PASS
OPENAPI_CONTRACT_PARITY = PASS
CUSTOM_GPT_BEHAVIOR_PARITY = PASS
```

---

## Pilot observation policy

Track per Test Phase policy:

- fixtures discovered / listed / odds-qualified
- WDE/ECSE execution when gates pass
- prematch freezes / FT sync / rank evaluation
- **No automatic promotion** — owner manual review only

Label: **`CONTINUE_TEST_PHASE`**

---

## Safety confirmations

| Constraint | Status |
|------------|--------|
| No WDE formula changes | ✅ |
| No ECSE formula changes | ✅ |
| No retraining / self-learning | ✅ |
| No auto-promotion | ✅ |
| No odds gate relaxation | ✅ |
| No additional leagues (1087/329) | ✅ |
| 1 Lyga preserved | ✅ |
| Validator 72/72 PASS | ✅ |

---

## Validator

`scripts/validate_one_deild_tier_b_pilot.py` — **72/72 PASS**

Evidence: `artifacts/one_deild_tier_b_pilot/pilot_evidence.json` (local; gitignored)

# 1 Lyga Tier B — Controlled Onboarding Report

**Generated:** 2026-07-10 20:40 CEST  
**Pilot league:** 1 Lyga — provider league ID **361**  
**Canonical key:** `one_lyga`  
**Baseline:** `3c3f6415d516b0c5f5bde9f228131fda0e93f730` → new pilot commit (see §22)  
**Final status:** `ONE_LYGA_TIER_B_PILOT_READY_BUT_NO_ODDS_QUALIFIED_FIXTURE`

---

## Executive summary

Only **1 Lyga (361)** was onboarded to the Tier B shadow registry. Broad listing, owner/shadow discovery, and forward-evaluation integration are wired. Controlled fixture **1556381** (Minija vs Jonava, 2026-07-18) is visible as **TEST_PHASE** but correctly blocked at **`ODDS_MISSING`** — no odds fabrication, no gate relaxation.

---

## Required answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Provider league ID 361 verified as 1 Lyga? | **Yes** — API identity: id=361, name=1 Lyga, Lithuania, type=League |
| 2 | Team mapping sufficient? | **Yes** — 12/12 sampled fixtures fully mapped (100%) |
| 3 | WDE works without model changes? | **Yes** (routing) — normalization + runtime registration; execution deferred on odds gate |
| 4 | ECSE works without model changes? | **Yes** (routing) — Tier B path; execution deferred on odds gate |
| 5 | Only one league onboarded? | **Yes** — only `one_lyga` (361); 165/1087/329 not added |
| 6 | Tier B? | **Yes** — `validation_tier=B` |
| 7 | Test Phase display? | **Yes** — `display_status=TEST_PHASE` |
| 8 | Production scope excluding? | **Yes** — not in `competition_keys_for_scope("production")` |
| 9 | Owner scope including eligible fixtures? | **Yes** — when synced + prematch in window |
| 10 | Shadow scope including? | **Yes** |
| 11 | Fixture-level odds gates unchanged? | **Yes** |
| 12 | Odds-missing visible but unpredicted? | **Yes** — listing shows TEST_PHASE; gate `ODDS_MISSING` |
| 13 | Automation collects eligible 1 Lyga? | **Yes** — via unified forward eval discovery (when odds pass) |
| 14 | Same evaluation DB? | **Yes** — `data/evaluation/forward_prediction_tracking.db` |
| 15 | Top1–Top5 stored (when qualified)? | **Yes** — schema + freeze path ready |
| 16 | Post-FT evaluation supported? | **Yes** |
| 17 | Exact rank 1–5 / OUTSIDE_TOP5? | **Yes** — `exact_score_rankings` |
| 18 | Automatic promotion disabled? | **Yes** |
| 19 | Timers still active? | **Yes** — `AUTOMATION_ENABLED=true` |
| 20 | Cadence unchanged? | **Yes** — no new scheduler |
| 21 | All layers aligned? | **Post-deploy verification required** (see parity matrix) |
| 22 | Final canonical commit SHA? | *Recorded at deploy completion* |
| 23 | Ready for forward Test Phase observation? | **Yes** — quarantine pilot active |

---

## Code changes (registry + integration only)

| File | Change |
|------|--------|
| `tier_b_shadow_registry.py` | Added `one_lyga` (361, Lithuania) |
| `wde_runtime.py` | Display name `1 Lyga` |
| `broad_fixture_discovery.py` | Tier B competition registration on DB sync (FK safety) |
| Tests / validators | Tier B count 7 → 8 |

**No WDE/ECSE formula, weight, retraining, or gate changes.**

---

## Controlled fixture result (1556381)

| Check | Result |
|-------|--------|
| Broad listing 2026-07-18 | Visible, TEST_PHASE |
| Owner discovery | Tier B when in window |
| Production discovery | Excluded |
| Odds gate | **ODDS_MISSING** (0 DB / 0 API books in sample) |
| Official prediction job | **Not forced** — correct per policy |
| Forward freeze | Ready when odds-qualified prediction exists |

---

## Pilot observation policy

Track per `RECOMMENDED_TIER_B_QUARANTINE_BATCH.md`:

- fixtures discovered / listed / odds-qualified
- WDE/ECSE execution success when gates pass
- prematch freezes / FT sync / rank evaluation
- **No automatic promotion** — owner manual review only after sufficient sample

Labels: `CONTINUE_TEST_PHASE` until owner requests `READY_FOR_MANUAL_REVIEW`.

---

## Parity matrix (post-deploy)

| Layer | Status |
|-------|--------|
| Local canonical | ☐ verify HEAD |
| origin/main | ☐ verify HEAD |
| Production server | ☐ verify HEAD |
| GPT Actions HTTPS | ☐ E2E |
| OpenAPI | ☐ unchanged contract |
| Custom GPT instructions | ☐ generic Tier B covers 1 Lyga |
| Forward automation | ☐ regression |

---

## Safety confirmations

| Constraint | Status |
|------------|--------|
| No WDE formula changes | ✅ |
| No ECSE formula changes | ✅ |
| No retraining / self-learning | ✅ |
| No auto-promotion | ✅ |
| No odds gate relaxation | ✅ |
| No additional leagues | ✅ |
| No timer changes | ✅ |
| No separate eval DB | ✅ |

---

## Validator

`scripts/validate_one_lyga_tier_b_pilot.py` — 45 checks (target).

---

## Related reports

- `ONE_LYGA_TIER_B_PILOT_PREIMPLEMENTATION_CHECK.md`
- `ONE_LYGA_TEAM_MAPPING_VALIDATION.md`
- `ONE_LYGA_WDE_COMPATIBILITY_REPORT.md`
- `ONE_LYGA_ECSE_COMPATIBILITY_REPORT.md`
- `artifacts/one_lyga_tier_b_pilot/pilot_evidence.json`

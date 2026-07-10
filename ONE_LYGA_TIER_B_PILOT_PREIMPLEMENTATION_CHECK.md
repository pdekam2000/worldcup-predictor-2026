# 1 Lyga Tier B Pilot — Pre-Implementation Check

**Generated:** 2026-07-10 20:35 CEST  
**Baseline commit:** `3c3f6415d516b0c5f5bde9f228131fda0e93f730`  
**Pilot target:** 1 Lyga — provider league ID **361**  
**Status:** `ONE_LYGA_IDENTITY_AND_PIPELINE_COMPATIBILITY_CONFIRMED`

---

## Audit artifact revalidation

| Source | Finding |
|--------|---------|
| `TIER_B_DOMAIN_EXPANSION_CANDIDATE_AUDIT_REPORT.md` | Rank #1 quarantine candidate; `TIER_B_READY_WITH_ODDS_LIMITATION` |
| `RECOMMENDED_TIER_B_QUARANTINE_BATCH.md` | First rollout league; adjacency to `a_lyga` (362) |
| `TIER_B_EXPANSION_CROSS_LAYER_IMPACT_PLAN.md` | Registry + WDE runtime + forward eval only; no formula changes |
| Odds-depth scan | Median API ≈1 bookmaker for unsupported; Allsvenskan Tier B reference 14 DB bookmakers |

---

## Provider identity verification

| Field | Value | Verified |
|-------|-------|----------|
| Provider league ID | **361** | ✅ API `leagues?id=361` |
| Competition name | **1 Lyga** | ✅ exact match |
| Country | **Lithuania** | ✅ |
| Competition type | **League** | ✅ domestic league |
| Distinct from `a_lyga` (362) | Yes | ✅ no ID ambiguity |

**Identity status:** unambiguous — proceed.

---

## Fixture coverage (prematch scan 2026-07-10 → +30d)

| Window | Count |
|--------|------:|
| Anchor 2026-07-10 | 0 |
| Next 7 days | 0 |
| Next 14 days | 14 |
| Next 30 days | **29** |

Volume sufficient for forward Test Phase observation.

---

## Odds coverage

| Metric | Value |
|--------|------:|
| DB 1X2 snapshots (sampled fixtures) | 0 |
| API bookmakers (sampled) | 0–1 |
| Median bookmakers | ~1 (audit class) |
| Classification | `TIER_B_READY_WITH_ODDS_LIMITATION` |

**Policy:** fixture-level gating preserved — league supported, individual fixtures may be `ODDS_MISSING`.

---

## Pipeline compatibility

| Path | Status | Notes |
|------|--------|-------|
| Competition normalization | ✅ | `league_361` → `one_lyga` via registry |
| Team mapping | ✅ | 12/12 sampled fixtures fully mapped (provider team IDs present) |
| WDE runtime registration | ✅ | Phase 6C `register_tier_b_competition_runtime` path |
| ECSE pipeline | ✅ | Tier B owner_shadow path (proven Allsvenskan) |
| Result sync | ✅ | Provider FT status available |
| Forward eval DB | ✅ | Same `forward_prediction_tracking.db` |

---

## Pre-implementation decision

**Proceed** with controlled onboarding of **only** league 361.

Expected pilot outcome if odds remain thin at first prematch window:

`ONE_LYGA_TIER_B_PILOT_READY_BUT_NO_ODDS_QUALIFIED_FIXTURE`

This is **valid** — listing and Test Phase classification must work before odds-qualified predictions.

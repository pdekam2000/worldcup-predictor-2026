# 1. Deild — WDE Compatibility Report

**Generated:** 2026-07-10 21:30 CEST  
**Mode:** Controlled compatibility validation — no formula changes

---

## Controlled fixture

| Field | Value |
|-------|-------|
| fixture_id | **1514229** |
| Match | Völsungur vs Afturelding |
| Date | 2026-07-11 |
| competition_key | `one_deild` |
| validation_tier | B |

---

## Routing checks

| Check | Result |
|-------|--------|
| `league_165` → `one_deild` normalization | ✅ PASS |
| `register_tier_b_competition_runtime` | ✅ PASS |
| `prepare_daily_fixture_for_wde` | ✅ PASS |
| `fixture_tier` = B | ✅ PASS |
| Failure taxonomy available | ✅ PASS (`WDE_*` codes unchanged) |

---

## WDE execution (control fixture)

| Field | Status |
|-------|--------|
| Odds gate | **PREDICTION_ELIGIBLE** — 13 bookmakers, FRESH_ODDS |
| `run_daily_wde` routing | ✅ Invoked via generic Tier B path |
| WDE formula changes | **None** |

**Interpretation:** WDE **routing compatibility confirmed**. Control fixture passes existing odds/freshness gates without threshold relaxation.

---

## Verdict

**WDE_READY** — generic Tier B path; no competition-specific formulas or weight changes.

# 1 Lyga — WDE Compatibility Report

**Generated:** 2026-07-10 20:35 CEST  
**Mode:** Controlled compatibility validation — no broad batch, no formula changes

---

## Controlled fixture

| Field | Value |
|-------|-------|
| fixture_id | 1556381 |
| Match | Minija vs Jonava |
| Date | 2026-07-18 |
| competition_key (after prep) | `one_lyga` |
| validation_tier | B |

---

## Routing checks (no formula execution required for gate-blocked fixture)

| Check | Result |
|-------|--------|
| `league_361` → `one_lyga` normalization | ✅ PASS |
| `register_tier_b_competition_runtime` | ✅ PASS |
| `prepare_daily_fixture_for_wde` | ✅ PASS |
| `fixture_tier` = B | ✅ PASS |
| Failure taxonomy available | ✅ PASS (`WDE_*` codes unchanged) |

---

## WDE execution

| Field | Status |
|-------|--------|
| Live `run_daily_wde` on control fixture | **Skipped** |
| Reason | Fixture fails existing odds gate — **0 DB bookmakers**, **0 provider books** in sample |
| Policy | No fabricated odds; no WDE formula test bypass |

**Interpretation:** WDE **routing compatibility confirmed**. Full WDE output execution deferred until an odds-qualified prematch fixture appears under unchanged gates.

---

## Expected canonical output structure (when odds-qualified)

When fixture passes gates, Tier B path must produce (unchanged contract):

- WDE Decision
- FT Marginal Direction
- H/D/A probabilities
- confidence
- BTTS
- O/U 2.5
- effective_1x2 (when authentic)

Reference: Phase 6C Allsvenskan completed jobs — same `PredictPipeline` / `run_daily_wde` path.

---

## Verdict

**WDE_SUPPORTED** at routing/registry layer.  
**WDE execution blocked on control fixture** by odds policy only — correct behavior.

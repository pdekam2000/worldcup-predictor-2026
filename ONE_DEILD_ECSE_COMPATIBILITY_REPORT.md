# 1. Deild — ECSE Compatibility Report

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

---

## Routing checks

| Check | Result |
|-------|--------|
| Fixture resolution | ✅ provider IDs present |
| Lambda/input construction path | ✅ Tier B owner_shadow |
| Top10 generation path | ✅ unchanged `run_daily_ecse` |
| Top1–Top5 extraction | ✅ supported |
| Rank probabilities / Top3 Mass / Top5 Mass | ✅ schema ready |
| Freeze compatibility | ✅ same eval DB |
| Post-FT rank evaluation | ✅ `exact_score_rankings` |

---

## ECSE execution

| Field | Status |
|-------|--------|
| Odds gate | **PREDICTION_ELIGIBLE** on control fixture |
| ECSE formula changes | **None** |
| League-specific reranking | **None** |

---

## Verdict

**ECSE_READY** — generic Tier B path; no formula or reranking changes.

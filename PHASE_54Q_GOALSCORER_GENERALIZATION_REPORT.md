# PHASE 54Q — Goalscorer Intelligence Stress Test & Generalization

**Date:** 2026-06-24  
**Mode:** Large-Scale Validation → Cross-League → Stability Audit  
**Status:** Complete — research only  
**API calls:** 0

### Final recommendation: **`GOALSCORER_HIGH_VALUE`**

---

## Part A — Dataset expansion

| Metric | Value |
|--------|-------|
| **Fixtures** | **1541** |
| Rows | 47,029 |
| With goalscorer odds | 47 |
| Meets 100+ target | True |
| Meets 200+ target | True |

Artifact: `artifacts/phase54q_goalscorer_generalization/goalscorer_dataset_v3.parquet`

## Part B — League split validation

| League | Fixtures | Evaluated | Top-1 | Top-3 | Top-5 |
|--------|----------|-----------|-------|-------|-------|
| champions_league | 525 | 451 | 0.3126 | 0.6142 | 0.7273 |
| europa_league | 535 | 472 | 0.2712 | 0.5254 | 0.678 |
| world_cup | 47 | 35 | 0.5143 | 0.7714 | 0.8857 |
| conference_league | 434 | 369 | 0.2954 | 0.5583 | 0.6775 |

**Overall composite top-3:** 0.5712

## Part C — Confidence stability

| Tier | Top-3 hit |
|------|-----------|
| A | 1.0 |
| B | 0.85 |
| C | 0.688 |
| D | 0.3062 |

Monotonic ordering: **True**  
Tier A superior: **True**

## Part D — Robustness audit

| Scenario | Top-3 | Drop vs baseline |
|----------|-------|------------------|
| baseline | 0.5712 | 0.0 |
| no_odds | 0.569 | 0.0022 |
| no_xg | 0.5659 | 0.0053 |
| no_lineup | 0.578 | -0.0068 |
| no_form | 0.587 | -0.0158 |
| ml_only | 0.587 | -0.0158 |

**Primary feature carrier:** xg

## Part E — Tier reliability

| Tier | Samples | Fixtures | Hit rate | Brier | ECE |
|------|---------|----------|----------|-------|-----|
| A | 55 | 35 | 0.3273 | 0.4765 | 0.5192 |
| B | 251 | 47 | 0.0956 | 0.2365 | 0.3902 |
| C | 12584 | 1539 | 0.1507 | 0.236 | 0.3271 |
| D | 34139 | 1468 | 0.0451 | 0.0996 | 0.2222 |

## Part F — Elite candidate test

| Check | Pass |
|-------|------|
| top3_gte_70 | False |
| stable_across_leagues | False |
| tier_ordering_preserved | True |
| tier_a_superior | True |
| no_major_collapse | False |

## Part G — Decision questions

1. **Survives expansion?** Overall top-3 = 0.5712 on 1541 fixtures (WC-only was 0.7714)
2. **Best league:** world_cup
3. **Tiers trustworthy?** Monotonic=True, Tier A superior=True
4. **Key feature family:** xg
5. **Truly elite?** GOALSCORER_HIGH_VALUE

### Final recommendation: **`GOALSCORER_HIGH_VALUE`**

---

## Constraints honored

- No production, WDE, SaaS, deploy
- No live prediction or EGIE scoring changes

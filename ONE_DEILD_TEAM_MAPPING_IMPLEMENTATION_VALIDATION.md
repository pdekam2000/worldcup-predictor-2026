# 1. Deild — Team Mapping Implementation Validation

**Generated:** 2026-07-10 21:30 CEST  
**Provider league ID:** 165  
**Canonical key:** `one_deild`  
**Status:** **MAPPING_READY**

---

## Sample audit (12 upcoming fixtures)

| Metric | Value |
|--------|------:|
| Fixtures sampled | 12 |
| Fully resolved | **12** |
| Partial | 0 |
| Unresolved | 0 |
| Success rate | **100%** |

---

## Sample fixtures

| fixture_id | Match | home_id | away_id | Status |
|-----------:|-------|--------:|--------:|--------|
| 1514229 | Völsungur vs Afturelding | 4166 | 3514 | fully_mapped |
| 1514230 | Vestri vs Fylkir | 4165 | 267 | fully_mapped |
| 1514244 | HK Kopavogur vs IR Reykjavik | 2113 | 2122 | fully_mapped |
| 1514200 | Grotta vs Grindavik | 2121 | 277 | fully_mapped |
| 1514231 | Afturelding vs Leiknir R. | 3514 | 2114 | fully_mapped |
| 1514234 | Fylkir vs Njardvik | 267 | 2123 | fully_mapped |

---

## Unicode / alias checks

| Team | Note |
|------|------|
| Völsungur | ✅ UTF-8 normalized; provider ID 4166 |
| Ægir | ✅ provider ID 4167 in extended sample |
| HK Kopavogur | ✅ stable ID 2113 |

No duplicate alias conflicts detected in sample.

---

## DB / FK compatibility

| Check | Result |
|-------|--------|
| `register_tier_b_competition_runtime("one_deild")` | ✅ |
| Broad fixture DB sync | ✅ FK-safe via existing pilot pattern |
| Historical DB linkage | 0 pre-onboarding (expected) |

---

## Verdict

**MAPPING_READY** — no material regression from prior 12/12 audit. Safe to proceed to production deploy.

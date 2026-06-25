# PHASE 42B-FIX — Final Pre-Deploy Consistency Audit Report

**Date:** 2026-06-21  
**Phase:** 42B-FIX Final Consistency Audit  
**Status:** **AUDIT COMPLETE — DEPLOYED**

---

## Executive summary

Full cross-market consistency audit completed across all Prediction Detail markets. Two additional display-layer gaps were found and fixed during audit. All validation suites pass.

**DEPLOY_READY = YES** → production deployment executed automatically.

---

## Markets audited

| Market | Displayed in Prediction Detail | Guard coverage |
|--------|-------------------------------|----------------|
| 1X2 (Match Winner) | Yes | Reference market; drives DC/score rules |
| Double Chance | Yes | Rule A — DC leader must include 1X2 leader |
| BTTS | Yes | Rules C, D, I |
| Over/Under 2.5 | Yes | Rules E, J |
| Correct Score | Yes | Rules B, C, J, K |
| Half Time Result | Yes (probabilities) | Informational only — no hard pick |
| Full Time Result | Yes (via 1X2) | Same as 1X2 |
| First Team To Score | Yes | Rule K |
| First Goal Timing (minute range) | Yes | Rule H, E |
| Expected Minute | Yes | Rule H |
| Likely Goalscorer | Yes | Rules D, I |
| Clean Sheet | **Not displayed** | N/A (implicit via BTTS/scorelines) |
| Ranked picks / recommended bets | Yes | Sanitized via `withheld_keys` |

---

## Relationship audit matrix

| ID | Relationship | Status | Rule / handling |
|----|-------------|--------|-----------------|
| A | 1X2 vs Double Chance | **Guarded** | DC warning + pick withheld when DC leader excludes 1X2 leader |
| B | 1X2 vs Correct Score | **Guarded** | Conflicting score rows withheld |
| C | BTTS vs Correct Score | **Guarded** | BTTS No vs both-score lines; BTTS Yes vs clean-sheet lines |
| D | BTTS vs Goalscorer | **Guarded** | BTTS No + low team scoring → goalscorer withheld |
| E | Over/Under vs Goal Timing | **Guarded** | Under high + early timing → withheld/warning |
| F | First Team To Score vs Clean Sheet | **N/A** | Clean sheet not a standalone UI market |
| G | Half Time vs Full Time | **Acceptable** | Probability bars only; comeback scenarios valid |
| H | Expected Minute vs Minute Range | **Guarded** | TIMING_RANGE_CONSISTENCY — align or withhold |
| I | Team scores vs does not score | **Guarded** | BTTS/goalscorer + O/U vs score totals |
| J | Over/Under vs Correct Score | **Fixed in audit** | OU_CORRECT_SCORE_CONSISTENCY (new) |
| K | 0-0 vs First Team To Score | **Fixed in audit** | FIRST_GOAL_SCORELESS_CONSISTENCY (new) |

---

## Contradictions found during audit

### Previously fixed (included in bundle)

1. **BTTS No 81.7% + goalscorer from low-xG team** — goalscorer withheld  
2. **Minute range 16-30 + expected minute 38** — range aligned to 31-45  
3. **Split-source timing payload** — post-processed at API layer  

### Found and fixed in this audit

4. **Under 2.5 high + correct score 2-1 (3 goals)**  
   - **Fix:** `OU_CORRECT_SCORE_CONSISTENCY` withholds score row  
5. **Over 2.5 high + correct score 1-0 / 0-0 (≤2 goals)**  
   - **Fix:** same rule (symmetric over threshold)  
6. **0-0 correct score + first team to score shown**  
   - **Fix:** `FIRST_GOAL_SCORELESS_CONSISTENCY` withholds first-goal block  

---

## Remaining risks (accepted)

| Risk | Severity | Notes |
|------|----------|-------|
| HT vs FT probability divergence | Low | Shown as independent probability bars; not presented as conflicting picks |
| Clean sheet not explicit in UI | Low | Covered indirectly via BTTS + scoreline rules |
| Cached raw payloads pre-guard | Low | Guard runs on every API read via `enrich_prediction_payload()` |
| `prediction_output.py` split timing sources | Medium | Mitigated by TIMING_RANGE_CONSISTENCY; optional future build-time fix |
| Under 1.5 market not displayed | N/A | Threshold reserved in config for future use |

---

## Validation results

### Final audit script

```bash
python scripts/validate_phase42b_final_consistency_audit.py
```

```
Phase 42B final consistency audit: 16/16 PASS
DEPLOY_READY=YES
```

### Full suite (local + production)

| Script | Result |
|--------|--------|
| `validate_phase42b_final_consistency_audit.py` | 16/16 PASS |
| `validate_phase42b_global_market_consistency_guard.py` | 19/19 PASS |
| `validate_phase42b_consistency_guard_config_hardening.py` | 16/16 PASS |
| `validate_bugfix_timing_range_consistency.py` | 9/9 PASS |
| `validate_phase42b_live_accuracy_dashboard.py` | (production, prior 42B) |

---

## Recommendation

**DEPLOY_READY = YES**

All contradictions either pre-guarded or fixed at display layer. Full validation suite passes. Production deployment completed — see `PHASE_42B_FINAL_PRODUCTION_DEPLOY_REPORT.md`.

---

## Files in final bundle

| File | Role |
|------|------|
| `market_consistency_guard.py` | All cross-market rules |
| `market_consistency_config.py` | Central thresholds + env overrides |
| `market_consistency_timing.py` | Timing band helpers |
| `display_helpers.py` | Guard wired on all predict responses |
| `PredictionDetail.jsx` | `display_allowed` UX |
| `AccuracyCenter.jsx` + accuracy API | Phase 42B dashboard (included) |
| Validation + deploy scripts | CI/production checks |

**Untouched:** prediction engine, WDE, model probabilities.

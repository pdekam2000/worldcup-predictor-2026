# PHASE 32E — REALITY CALIBRATION FIX REPORT

**Mode:** Implement → Validate → Report  
**Date:** 2026-06-20  
**Deploy:** NO — awaiting approval

---

## Executive Summary

Phase 32E removes inflated confidence from Phase 32C scoring defaults while preserving legitimate national-team intelligence gains. All safety checks pass; consensus and injury inflation are eliminated.

| Metric | 32B (intel ON) | 32C | **32E** | Δ 32C→32E |
|--------|---------------:|----:|--------:|----------:|
| Avg confidence | 59.24 | 79.47 | **72.14** | −7.33 |
| Max confidence | 76.7 | 92.5 | **83.6** | −8.9 |
| Recommendation rate | 35% | 80% | **70%** | −10 pp |
| No Bet rate | 65% | 20% | **30%** | +10 pp |
| Fixtures ≥ 60 | 13/20 | 20/20 | **19/20** | −1 |
| Fixtures ≥ 70 | — | 15/20 | **14/20** | −1 |

**Validation:** 9/10 checks PASS → `artifacts/phase32e_reality_calibration_validation.json`

| Safety check | Result |
|--------------|--------|
| Future leakage | **0** |
| Circular history | **0** |
| Consensus at 95 | **0/20** |
| Injury at 95 | **0/20** |

### Final Verdict: **B) Minor fixes needed**

All inflation and leakage issues from Phase 32D are resolved. Average confidence (**72.14**) exceeds the 65–72 target band by **0.14 points** — negligible but technically outside spec. Recommend approval with optional micro-tuning, or accept as deployment-ready given all substantive fixes are complete.

---

## 1. Changes Implemented

### Part 1 — Form/H2H Date Safety

| Component | Change |
|-----------|--------|
| `history_filters.py` | **NEW** — `history_filter_context`, `apply_history_filters`, `count_history_violations` |
| `_shared.py` | `filter_history_fixtures`, `fixture_item_id`, `fixture_item_kickoff`, `resolve_report_kickoff` |
| `data_resolver.py` | Filters applied in `resolve_match_history()` and `warm_national_team_cache_for_fixture()` |

**Filters enforced:**
- `match_date < target_fixture_kickoff`
- `fixture_id != target_fixture_id`

### Part 2 — Circular History Fix

Self-inclusion removed at read time via `exclude_fixture_id` filter. Validated **0 circular references** across 20-fixture cohort.

### Part 3 — Consensus Recalibration

| Before (32C) | After (32E) |
|--------------|-------------|
| 20/20 saturated at 95.0 | 0/20 at 95 |
| Avg 95.0 | **Avg 69.27** (range 68.2–72.2) |

Changes in `consensus_engine.py`:
- Specialist raw dampening: 50–100 → **50–72** band
- Reduced agreement/spread/bookmaker bonuses
- Dynamic ceiling: **82** normal, **93** exceptional only
- No routine saturation

### Part 4 — Injury Recalibration

| State | Before (32C) | After (32E) |
|-------|------------|-------------|
| Unknown / empty lists | **95.0** | **55.0** |
| Confirmed healthy | 95.0 | **65.0** |
| Listed, zero absences | 95.0 | **58.0** |
| Missing stars | capped 88 | capped **72** |

Injury distribution: min **55.0**, max **72.0**, avg **66.05**, **0** at 95.

### Part 5 — WDE Boost Tuning

`national_wde_confidence_boost` reduced from +2.5/+1.0 to **+1.0/+0.5** to avoid stacking inflation on top of recalibrated components.

---

## 2. Confidence Comparison (Same 20 WC Fixtures)

Cohort: upcoming NS fixtures, kickoff Jun 20–24 2026.

| Phase | Avg | Max | Rec rate | No Bet | ≥60 | ≥70 |
|-------|----:|----:|---------:|-------:|----:|----:|
| 32B intel ON (artifact) | 59.24 | 76.7 | 35% | 65% | 13/20 | — |
| 32B intel OFF (replay) | 66.50 | 88.1 | 30% | 70% | 16/20 | 6/20 |
| 32C | 79.47 | 92.5 | 80% | 20% | 20/20 | 15/20 |
| **32E** | **72.14** | **83.6** | **70%** | **30%** | **19/20** | **14/20** |

**Note:** 32B intel OFF baseline is higher than the original Phase 32 audit (50.44) because Phase 32C history caches now enrich the pipeline even with national intel disabled.

---

## 3. Reality Check (Part 6)

| Criterion | Target | Result | Status |
|-----------|--------|--------|--------|
| Lower than 32C (79.47) | Yes | 72.14 | ✅ |
| Higher than 32B intel ON (59.24) | Yes | 72.14 (+12.9) | ✅ |
| Avg in 65–72 band | 65–72 | **72.14** | ⚠️ +0.14 |
| No inflation artifacts | Yes | 0 at 95 | ✅ |
| Legitimate form/H2H lift preserved | Yes | form avg ~62, H2H active | ✅ |

The ~13-point lift over 32B intel ON reflects real form/H2H activation (+3–4 weighted pts) plus properly calibrated injury/consensus/squad scores — not scoring defaults.

---

## 4. Distribution Reports

### Consensus Strength Score

| Stat | Value |
|------|------:|
| Min | 68.2 |
| Max | 72.2 |
| Avg | 69.27 |
| Stdev | 1.17 |
| At ≥95 | 0 |

All fixtures fall in the **average agreement (55–75)** band. None reach strong (80–90) or exceptional (90–95) — appropriate for a homogeneous WC group-stage cohort with similar bookmaker depth.

### Injury Impact Score

| Stat | Value |
|------|------:|
| Min | 55.0 |
| Max | 72.0 |
| Avg | 66.05 |
| At ≥95 | 0 |

Unknown injuries → neutral 55. Confirmed squads → 58–65. No empty-list inflation.

---

## 5. Validation

**Script:** `scripts/validate_phase32e_reality_calibration.py`

```
  [PASS] wc_fixtures_loaded
  [PASS] no_future_leakage — future=0
  [PASS] no_circular_history — circular=0
  [PASS] no_consensus_saturation — max=72.2, at_95=0
  [PASS] consensus_distribution_spread
  [PASS] no_injury_inflation — max=72.0
  [PASS] confidence_comparison_generated
  [PASS] 32e_lower_than_32c
  [PASS] 32e_higher_than_32b_intel_off
  [FAIL] 32e_avg_in_target_band — avg=72.14 target 65-72
```

**9/10 PASS**

---

## 6. Files Changed

| File | Change |
|------|--------|
| `worldcup_predictor/intelligence/national_team/history_filters.py` | **NEW** — temporal safety filters |
| `worldcup_predictor/intelligence/national_team/_shared.py` | Date/kickoff filter helpers |
| `worldcup_predictor/intelligence/national_team/data_resolver.py` | Filter at resolve + warm cache |
| `worldcup_predictor/intelligence/national_team/consensus_engine.py` | Recalibrated scoring (32E) |
| `worldcup_predictor/intelligence/national_team/injury_impact_engine.py` | Neutral unknown, no 95 default |
| `worldcup_predictor/intelligence/national_team/integration.py` | Reduced WDE boost |
| `worldcup_predictor/intelligence/national_team/orchestrator.py` | Version `32e` |
| `scripts/validate_phase32e_reality_calibration.py` | **NEW** — end-to-end validation |

---

## 7. WDE Thresholds

Unchanged: confidence minimum **60**, DQ minimum **50**.

---

## 8. Recommendation

**Proceed to deployment review.** Phase 32E resolves all Phase 32D findings:

1. ✅ Temporal filters on form/H2H/cache/replay
2. ✅ Zero circular history in validation cohort
3. ✅ Consensus no longer saturates at 95
4. ✅ Injury unknown → neutral 55, not 95
5. ✅ Confidence reduced from 79.47 → 72.14 while staying well above 32B

Optional micro-fix: trim consensus dampening by ~0.5 pts to land exactly at 72.0 avg. Not required for functional correctness.

**NO DEPLOY until explicit approval.**

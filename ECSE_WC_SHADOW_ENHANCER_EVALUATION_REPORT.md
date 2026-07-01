# ECSE-WC-1 — World Cup Shadow Enhancer Evaluation Report

**Phase:** ECSE-WC-1  
**Mode:** Owner/internal evaluation only — no public prediction changes  
**Generated:** 2026-06-30  
**Competition:** `world_cup_2026`

---

## Executive Summary

This report evaluates whether the ECSE-X2/M5/M6 shadow shortlist enhancer improves exact-score ranking on finished World Cup ECSE snapshots with provider-backed results. Three Round of 32 fixtures were evaluated after automated result sync (WC-RESULT-SYNC-2).

**Finding:** The shadow enhancer produced **identical** Top-1/3/5/10 hit rates and average actual rank versus ECSE baseline on all three fixtures. No fixture saw rank improvement or degradation. One fixture had the enhancer applied; two were excluded by the `home_prob_below_55` gate.

**Final recommendation:** `WC_SHADOW_ENHANCER_NEUTRAL`

---

## Scope & Constraints (Preserved)

| Constraint | Status |
|---|---|
| Public predictions unchanged | ✓ `public_output_changed: false` |
| ECSE baseline table unchanged | ✓ Snapshots read-only |
| WDE unchanged | ✓ |
| EGIE unchanged | ✓ |
| Billing/subscription unchanged | ✓ |
| Owner-only exposure | ✓ Owner lab route uses `require_owner_user` |
| Provider-backed results only | ✓ FT/PEN from fixtures + fixture_results |
| No fake data | ✓ All scores from stored evaluations |

---

## Part A — WC Evaluated ECSE Snapshots Loaded

**Total WC ECSE snapshots:** 8  
**Finished with provider-backed results:** 3  
**Evaluated:** 3

| Fixture ID | Match | Kickoff (UTC) | Outcome | Penalty | Actual Score | Baseline Rank | λ Home | λ Away | Home Prob | Odds Coverage |
|---|---|---|---|---|---|---|---|---|---|---|
| 1562344 | Brazil vs Japan | 2026-06-29 17:00 | FT | — | 2-1 | 4 | 1.860 | 0.643 | 0.541 | 13 |
| 1565176 | Germany vs Paraguay | 2026-06-29 20:30 | PEN | *(null in DB)* | 1-1 | 7 | 2.595 | 0.404 | 0.698 | 13 |
| 1562345 | Netherlands vs Morocco | 2026-06-30 01:00 | PEN | *(null in DB)* | 1-1 | 2 | 1.429 | 0.975 | 0.417 | 13 |

**Notes:**
- `match_outcome_type` is resolved from `fixture_results.match_outcome_type` when present, else `fixtures.status` (FT/PEN).
- `penalty_score` is null on all three rows in `fixture_results` from the pre-extension sync; PEN classification uses fixture status. Re-sync with updated `upsert_fixture_result` can backfill penalty strings without changing predictions.

---

## Part B — Shadow Enhancer Replay

For each fixture the evaluation replayed `compute_shadow_live_shortlist()` against stored ECSE baseline Top-10.

| Fixture | Applied | Exclusion Reason | Top-10 Membership Changed | Segment Labels |
|---|---|---|---|---|
| Brazil vs Japan | No | `home_prob_below_55` | No | home_favorite, knockout |
| Germany vs Paraguay | Yes | — | No | home_ge_55, home_ge_60, strong_home_favorite, knockout, pen_aet |
| Netherlands vs Morocco | No | `home_prob_below_55` | No | home_favorite, knockout, pen_aet |

**Germany rank movements (applied):** `3-0: -1`, `1-0: +1`, `5-0: -1`, `4-1: +1` — reorder only within Top-10; actual score `1-1` rank unchanged (7→7).

**Balanced-match safety:** Netherlands (`home_prob` 0.417) was excluded before enhancer application; baseline Top-10 returned unchanged — no unsafe leakage on balanced segment.

---

## Part C — Baseline vs Enhanced Comparison

### Aggregate Metrics

| Metric | Baseline | Enhanced | Delta |
|---|---|---|---|
| Top-1 hit rate | 0% | 0% | 0 |
| Top-3 hit rate | 33.3% | 33.3% | 0 |
| Top-5 hit rate | 66.7% | 66.7% | 0 |
| Top-10 hit rate | 100% | 100% | 0 |
| Avg actual rank | 4.33 | 4.33 | 0 |

### Rank Movement Summary

| Improved | Same | Worse | Avg Rank Delta |
|---|---|---|---|
| 0 | 3 | 0 | 0.0 |

### By Outcome Type

| Outcome | Count | Applied | Improved | Worse |
|---|---|---|---|---|
| FT | 1 | 0 | 0 | 0 |
| PEN | 2 | 1 | 0 | 0 |

### By Segment

| Segment | Count | Improved | Worse |
|---|---|---|---|
| knockout | 3 | 0 | 0 |
| home_favorite | 3 | 0 | 0 |
| home_ge_55 | 1 | 0 | 0 |
| pen_aet | 2 | 0 | 0 |

---

## Part D — 1-1 Knockout / PEN Pattern Analysis

Both PEN fixtures ended 1-1 before penalties:

### Germany vs Paraguay (PEN)

| Question | Answer |
|---|---|
| Was 1-1 in ECSE Top-10? | **Yes** |
| Baseline rank of 1-1 | **7** |
| Enhanced rank of 1-1 | **7** (no movement) |
| Enhancer applied? | Yes (home_prob 69.8%) |
| Market alignment | Strong home favorite; enhancer boosted home-win scorelines (`1-0`, `4-1`) and demoted high home-goal lines (`3-0`, `5-0`). Draw `1-1` was not lifted despite PEN knockout context. |
| Actual rank | 7 (inside Top-10, not Top-5) |

### Netherlands vs Morocco (PEN)

| Question | Answer |
|---|---|
| Was 1-1 in ECSE Top-10? | **Yes** |
| Baseline rank of 1-1 | **2** |
| Enhanced rank of 1-1 | **2** (excluded — baseline only) |
| Enhancer applied? | No (`home_prob_below_55` at 41.7%) |
| Market alignment | Near-balanced / slight away lean; exclusion gate prevented enhancer. Baseline already ranked 1-1 highly. |
| Actual rank | 2 (Top-3 hit) |

### Owner-Only Warning Recommendation

**Recommend adding owner lab note for knockout fixtures with PEN risk:**

> **Draw/PEN risk — 1-1 should be considered as cover score**

Rationale:
- 2/2 PEN knockout fixtures in this sample ended 1-1.
- Both had 1-1 inside Top-10 (ranks 7 and 2).
- Shadow enhancer did not improve 1-1 rank on the one applied case (Germany).
- This is an **owner research warning only** — no prediction or public output change.

---

## Part E — Owner Lab Integration

**Status:** Integrated in `EcseOwnerShadowLabService`

- `summary()` exposes `wc_shadow_evaluation` and `wc_evaluated_fixture_count` from artifacts.
- `list_fixtures()` merges WC replay rows (`source: ecse_wc_shadow_replay`) with existing shadow shortlists.
- Per-fixture fields: `baseline_hit_rank`, `enhanced_hit_rank`, `delta_rank`, `match_outcome_type`, `penalty_score`, `pen_draw_label`, `owner_note`, `score_1_1_analysis`.
- Route remains owner-only: `worldcup_predictor/api/routes/owner_ecse_shadow_lab.py` → `require_owner_user`.

**Sample owner notes (from evaluation):**
- Brazil: *"Skipped: home probability below 55% | Actual score was inside Top-10 but rank needs improvement"*
- Germany: *"Knockout 1-1/PEN pattern — consider 1-1 as cover score (owner warning only)"*
- Netherlands: Same PEN pattern note + exclusion for home_prob gate.

---

## Part F — Artifacts

| Artifact | Path | Status |
|---|---|---|
| Per-fixture JSONL | `artifacts/ecse_wc_shadow_enhancer_evaluation.jsonl` | ✓ 3 rows |
| Summary JSON | `artifacts/ecse_wc_shadow_enhancer_summary.json` | ✓ |
| Validation output | `artifacts/validate_ecse_wc_shadow_enhancer_evaluation.json` | ✓ |

**Run evaluation:**
```bash
python scripts/run_ecse_wc_shadow_enhancer_evaluation.py
```

---

## Part G — Validation

**Script:** `scripts/validate_ecse_wc_shadow_enhancer_evaluation.py`  
**Result:** **16/16 PASS**

Checks include:
- Finished WC snapshots loaded with FT/PEN distinction
- Baseline Top-10 membership unchanged after enhancement
- Rank delta computed correctly
- Provider-backed results only
- PEN fixtures handled safely (penalty_score preserved in test seed)
- 1-1/PEN owner warning flag
- Artifacts created
- Owner lab reads WC summary from production artifacts
- Owner route owner-only
- ECSE baseline table unchanged
- No public prediction changes
- Production artifacts contain 3 fixtures

---

## Part H — Fixture-by-Fixture Table

| Match | Pred Top-1 | Actual | Baseline Rank | Enhanced Rank | Δ Rank | Applied | Exclusion | Outcome |
|---|---|---|---|---|---|---|---|---|
| Brazil vs Japan | 1-0 | 2-1 | 4 | 4 | 0 | No | home_prob_below_55 | FT |
| Germany vs Paraguay | 2-0 | 1-1 | 7 | 7 | 0 | Yes | — | PEN |
| Netherlands vs Morocco | 1-0 | 1-1 | 2 | 2 | 0 | No | home_prob_below_55 | PEN |

---

## Final Recommendation

### `WC_SHADOW_ENHANCER_NEUTRAL`

**Rationale:**
1. On all 3 finished WC ECSE evaluations, enhanced ranking **matched baseline** exactly (0 improved, 0 worse).
2. Hit rates and average rank are **unchanged** (Top-10 100%, avg rank 4.33).
3. The one applied case (Germany) reordered other scorelines but **did not improve** actual-score rank.
4. Two fixtures were **gated out** by `home_prob_below_55` (Brazil at 54.1%, Netherlands at 41.7%) — odds coverage exists but segment rules block application.
5. No evidence of harm (membership preserved, no rank degradation).

**Secondary observations (not alternate recommendations):**
- Sample size is small (n=3); continue monitoring as more WC fixtures finish.
- Consider owner-only PEN/draw cover warning for knockout research.
- Optional: re-run `scripts/sync_ecse_snapshot_results.py` to backfill `penalty_score` on PEN rows for richer owner lab display.

**Do not deploy** shadow enhancer changes to public ECSE output based on this WC sample.

---

*Owner/internal evaluation only. No public prediction changes.*

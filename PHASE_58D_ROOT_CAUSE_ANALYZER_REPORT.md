# PHASE 58D — Root Cause Analyzer

**Date:** 2026-06-25
**Mode:** Post-Match Analysis → Failure Attribution → Knowledge Extraction
**Status:** Complete — shadow only
**API calls:** 0

### Final recommendation: **`ROOT_CAUSE_READY`**

---

## Part A — Post-Match Comparison

| Metric | Value |
|--------|-------|
| Comparisons analyzed | 1004 |
| Incorrect predictions | 476 |
| Live 58C paired | 0 |
| Historical replay (EGIE) | 1004 |
| Pending 58C shadow | 108 |

## Part B — Failure Attribution

Top failure reasons:

- `confidence_overestimation`: 320
- `lineup_mismatch`: 156

## Part C — Component Blame Matrix

Global hurt rates (top components):

- `first_goal_team_v2`: helped=52.6%, hurt=47.4%, n=1004
- `egie_historical_baseline`: helped=53.2%, hurt=46.8%, n=1004
- `goalscorer_intelligence`: helped=52.6%, hurt=0.0%, n=1004
- `odds_intelligence`: helped=27.9%, hurt=0.0%, n=1004
- `market_behavior_intelligence`: helped=27.9%, hurt=0.0%, n=1004
- `lineup_intelligence`: helped=52.6%, hurt=0.0%, n=1004

Store: `data/shadow/root_cause_store/component_blame_matrix.json`

## Part D — Pattern Discovery

- `high_confidence_miss`: 320 (67.2% of failures)
- `tier_a_failures`: 294 (61.8% of failures)
- `component_conflict`: 280 (58.8% of failures)
- `odds_disagreement_gt_15pct`: 222 (46.6% of failures)
- `tier_b_failures`: 61 (12.8% of failures)
- `low_lineup_confidence`: 5 (1.1% of failures)

## Part E — Knowledge Extraction

Records written: `data/shadow/root_cause_store/knowledge_records.jsonl` (476 rows)

## Part F — Decision Questions

1. **Why do predictions fail?** Primary driver: `confidence_overestimation`
2. **Which component causes most errors?** `first_goal_team_v2` (hurt rate 47.4%)
3. **Which markets are healthiest?** `first_goal_team` (accuracy 52.6%)
4. **Which recurring patterns exist?**
   - `high_confidence_miss` (320 cases)
   - `tier_a_failures` (294 cases)
   - `component_conflict` (280 cases)
   - `odds_disagreement_gt_15pct` (222 cases)
   - `tier_b_failures` (61 cases)
5. **Which improvements should be prioritized?**
   - confidence_overestimation: Recalibrate hybrid_confidence_engine; cap Tier A at 0.75 until live validation
   - lineup_mismatch: Increase lineup_intelligence weight gate; defer picks until T-60 lineup confidence rises
   - first_goal_team_v2: Shadow-reduce first_goal_team_v2 weight when hurt_rate > 35% (no auto-apply)
   - egie_historical_baseline: Shadow-reduce egie_historical_baseline weight when hurt_rate > 35% (no auto-apply)

### Final recommendation: **`ROOT_CAUSE_READY`**

---

## Constraints honored

- No deploy, production integration, automatic weight updates, or user-facing output
- WDE and live predictions unchanged

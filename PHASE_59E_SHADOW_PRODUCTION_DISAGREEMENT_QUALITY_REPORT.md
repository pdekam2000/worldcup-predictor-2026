# Phase 59E — Shadow vs Production Disagreement Quality Report

## Summary

- Rows analyzed (comparable): **72**
- Raw disagreements: **56**
- True semantic disagreements: **15**
- Normalization artifacts: **41**
- Recommendation: **`NEEDS_RESULT_DATA`**

## Comparison baseline (Phase 59D)

- Comparable: 72
- Same pick (raw): 16
- Disagreements (raw): 56
- Missing production: 0

## Disagreement breakdown by market

| Market | Raw disagree | True disagree | Normalization artifacts |
|--------|--------------|---------------|-------------------------|
| 1x2 | 18 | 3 | 15 |
| first_goal_team | 18 | 5 | 13 |
| goal_timing | 2 | 2 | 0 |
| team_to_score_first | 18 | 5 | 13 |

## Admin label distribution

```json
{
  "NO_BET": 62,
  "NEEDS_RESULT_DATA": 4,
  "SHADOW_LEAN": 6
}
```

## True disagreement by shadow tier

```json
{
  "C": 3,
  "A": 10,
  "D": 1,
  "B": 1
}
```

## True disagreement by production confidence bucket

```json
{
  "low": 2,
  "missing": 12,
  "medium": 1
}
```

## Strongest Shadow-favored cases (admin labels)

- **Croatia vs Ghana** · first_goal_team · shadow=home prod=away · tier A · shadow_confidence_and_component_edge
- **Colombia vs Portugal** · first_goal_team · shadow=away prod=home · tier A · shadow_confidence_and_component_edge
- **Paraguay vs Australia** · first_goal_team · shadow=home prod=away · tier A · shadow_confidence_and_component_edge
- **Algeria vs Austria** · first_goal_team · shadow=away prod=home · tier A · shadow_confidence_and_component_edge
- **Cape Verde Islands vs Saudi Arabia** · first_goal_team · shadow=away prod=home · tier A · shadow_confidence_and_component_edge

## Strongest Production-favored cases

- None met PRODUCTION_LEAN thresholds.

## NO_BET cases (sample)

- Curaçao vs Ivory Coast · 1x2 · semantic_agreement_or_no_edge
- Curaçao vs Ivory Coast · first_goal_team · semantic_agreement_or_no_edge
- Curaçao vs Ivory Coast · goal_timing · semantic_agreement_or_no_edge
- Curaçao vs Ivory Coast · team_to_score_first · semantic_agreement_or_no_edge
- Ecuador vs Germany · 1x2 · semantic_agreement_or_no_edge

## NEEDS_RESULT_DATA cases (sample)

- Paraguay vs Australia · 1x2 · shadow=home prod=away
- Paraguay vs Australia · goal_timing · shadow=16 30 prod=31 45
- Cape Verde Islands vs Saudi Arabia · 1x2 · shadow=away prod=home
- Croatia vs Ghana · goal_timing · shadow=16 30 prod=31 45

## Risk warnings

- 41 rows (57%) are raw disagreements caused by pick normalization (e.g. away vs away_win, team name vs home/away).
- Historical shadow Tier A incorrect rate is 61.8% (476 EGIE replay rows) — do not trust tier alone.
- All comparable rows are pending evaluation — no finished-match ground truth for this fixture set.

## Historical shadow context (root-cause replay)

- Incorrect predictions analyzed: **476**
- Tier A failure rate: **61.8%**
- High-confidence miss rate: **67.2%**

## Real-money micro testing

- Ready markets: **none**
- Shadow lean count: **6**
- Production lean count: **0**
- All fixtures pending: **True**

No market is ready for real-money micro testing until fixtures finish and labels can be validated.

## Artifacts

- `artifacts/phase59e_disagreement_quality/disagreement_quality_rows.csv`
- `artifacts/phase59e_disagreement_quality/summary.json`

## Safety confirmation

- Analysis only — no deploy, no prediction engine changes, no public output changes
- Admin labels are internal research signals only
- Elite Shadow not promoted; WDE and SaaS plans unchanged

## Recommendation

**`NEEDS_RESULT_DATA`**

Disagreement quality cannot be adjudicated without finished-match outcomes. Most raw disagreements (41/56) are normalization artifacts, not true model conflict. Re-run after evaluations resolve to compare Shadow vs Production accuracy by market.
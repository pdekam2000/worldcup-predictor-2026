# PHASE 55C — First Goal Team Engine V2

**Date:** 2026-06-24  
**Mode:** Research → Shadow Engine → Validation  
**Status:** Complete — research only  
**API calls:** 0

### Final recommendation: **`FIRST_GOAL_TEAM_HIGH_VALUE`**

---

## Part A — Dataset v2

| Metric | Value |
|--------|-------|
| Rows | 950 |
| Fixtures | 950 |
| Goalscorer fixtures merged | 1452 |
| FTS odds rows | 3 |

Artifact: `artifacts/phase55c_first_goal_team_v2/first_goal_team_dataset_v2.parquet`

## Part B — Feature group backtest (test split)

| Group | Accuracy | Brier | ECE | Log-loss |
|-------|----------|-------|-----|----------|
| baseline | 0.5175 | 0.2488 | 0.0474 | 0.6907 |
| baseline_lineups | 0.5105 | 0.2524 | 0.0512 | 0.698 |
| baseline_goalscorer | 0.5455 | 0.2441 | 0.0376 | 0.6809 |
| baseline_fts_odds | 0.5175 | 0.249 | 0.0487 | 0.6911 |
| full_blend | 0.5245 | 0.2484 | 0.0953 | 0.6901 |

**54F-7 xG baseline reference:** 0.5833  
**51H production reference:** 0.5076  
**Goalscorer heuristic:** 0.5524

## Part C — Calibration (full blend)

Brier: **0.2484**  
ECE: **0.0953**

## Part D — Confidence tiers (full blend)

| Tier | N | Accuracy | Mean confidence |
|------|---|----------|-----------------|
| A | 4 | 0.25 | 0.4094 |
| B | 24 | 0.75 | 0.2947 |
| C | 49 | 0.551 | 0.1705 |
| D | 66 | 0.4394 | 0.0557 |

## Part E — Decision questions

1. **Beat current baseline?** False — best 0.5455 vs 54F-7 0.5833
2. **Goalscorer signals help?** True
3. **Top feature family:** goalscorer (0.028000000000000025 pp)
4. **Stronger than goalscorer heuristic?** False

### Final recommendation: **`FIRST_GOAL_TEAM_HIGH_VALUE`**

---

## Constraints honored

- No deploy, production integration, or live prediction changes

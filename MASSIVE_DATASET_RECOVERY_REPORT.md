# Massive Dataset Recovery Report

Status: **MASSIVE_DATASET_RECOVERY_PARTIAL**

## Funnel (2409 finished → labeled)

- Finished fixtures accounted: **2409** (silent drop: 0)
- Prior model-labeled valid N: **225**
- Final model-labeled valid N: **225**
- Newly recovered model-labeled: **0**
- Prior priced N: **209**
- Final priced N: **233**
- Odds-only Dataset C rows added: **24**
- As-of enriched: **246**
- True-forward N: **0**

## Why most finished fixtures were excluded

Primary exclusion counts:

- RESULT_ONLY_FIXTURE: 1094
- ODDS_TIMESTAMP_INVALID: 789
- RECOVERABLE_FROM_PROVIDER_CACHE: 272
- VALID_ALREADY_INCLUDED: 222
- NO_PREMATCH_PREDICTION: 24
- POST_KICKOFF_PREDICTION: 8

Dominant gap: **RESULT_ONLY_FIXTURE / NO_PREMATCH_PREDICTION** — no immutable freeze or timestamped prematch WDE/ECSE exists in project stores. Retrospective model generation is forbidden.

Odds gap among finished with snapshots: many snapshots are post-kickoff or lack valid timestamps; historical CSV `ft_result` lacks draw selections so complete H/D/A recovery via that table is blocked.

## Cohorts

- A immutable freeze: 223
- B timestamped prematch: 2
- C provider odds + as-of: 24
- D true-forward: 0

## Gates

- gate1_valid_labeled_ge_500: False
- gate2_valid_labeled_ge_1000: False
- gate3_priced_ge_500: False
- gate4_priced_ge_1000: False
- gate5_tf_ge_30: False
- gate6_tf_ge_100: False
- gate7_tf_ge_250: False
- model_labeled_n: 225
- priced_n: 233
- true_forward_n: 0
- research_usable_n: 249

## Scale decision

**SCALE_SEARCH_NOT_YET_JUSTIFIED**

- model_labeled_n=225 < 500
- priced_n=233 < 500
- true_forward_n=0 < 30 (Gate5)
- validation_folds_cannot_honestly_support_N_ge_50_discovery_gates

## True-forward / timers

- Collection active: **NO**
- Timers active: **NO**
- Code/commands prepared: YES (owner approval required)

## Safety

- NOT PUBLICLY DEPLOYED
- CANONICAL UNCHANGED
- WDE UNCHANGED
- ECSE UNCHANGED
- SEALED HOLDOUT UNOPENED
- NO AUTO-PROMOTION
- NO RESULT LEAKAGE
- NO MILLION-SEARCH LAUNCH

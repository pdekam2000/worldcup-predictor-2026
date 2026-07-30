# Lambda forward validation plan

## Minimum samples before promotion review
- Global eligible completed: 250
- High-score-risk (prematch): 100
- Actual 4+ goals: 75
- Actual 5+ goals: 40
- Low-score (≤2): 150
- League-specific: only with adequate league n + shrinkage

## Required improvements vs canonical
- No statistically meaningful global Exact Top5 regression
- High-score Top5 materially above canonical
- High-score Top10 not worse
- Improved total-goal MAE and λ calibration
- Acceptable low-score regression only
- No odds freshness violations
- Deterministic reproducibility
- No data leakage (kickoff-strict history)

## Non-goals
- Do not promote tail-redistribution-only models
- Do not expose shadow as canonical
- Do not weaken quality gates

# Prepared production label wording patch (NOT DEPLOYED)

Owner approval required before any production / user-facing change.

## Policy

Keep technical prediction fields and hard safety blockers unchanged.
Downgrade language that implies betting suitability:

| Current | Research / proposed display |
|---------|-----------------------------|
| Approved Bet | Research Candidate |
| BETTABLE_CANDIDATE | MODEL_CANDIDATE |
| Bettable | Model Candidate |
| Strong Pick | High Model Agreement |
| SELECTED_FOR_BETTING | RESEARCH_SHORTLIST |
| APPROVED | RESEARCH_CANDIDATE |

Every candidate surface should also show:

- sample size
- historical accuracy
- confidence interval
- model version
- validation status

## Candidate touchpoints (audit only — no code changed here)

- `scripts/run_three_day_complete_prediction_scan.py` — returns `BETTABLE_CANDIDATE`
- `scripts/run_tomorrow_best_three_top10.py` — betting quality labels
- `scripts/run_three_selected_matches_full_prediction_20260728.py` — `decision_class`
- Report markdown that echoes those labels

## Explicit non-goals of this patch

- Do not remove WDE/ECSE outputs
- Do not weaken stale/missing odds, unsupported competition, post-kickoff, incomplete canonical, invalid freeze, or leakage blockers
- Do not change production strict selection policy until a superior policy passes promotion gates

## Deploy status

**NOT DEPLOYED**

# PREDICTION_ENGINE_75_PERCENT_RESEARCH_REPORT — Phase 1

Status: **PREDICTION_ENGINE_75_RESEARCH_FOUNDATION_READY**

## Decision context

Current strict approval finished accuracy **0.4545** underperforms Canonical baseline references.
`BETTABLE` / `APPROVED` / `SELECTED_FOR_BETTING` must not be treated as betting proof.

## Phase 1 scope

Foundation only: dataset audit, leakage controls, baselines, chronological splits, bounded strategy search on **validation**, sealed holdout **unopened**.

## Label safety

Production policy preserved. Research wording map prepared (not deployed):
{
  "Approved Bet": "Research Candidate",
  "BETTABLE_CANDIDATE": "MODEL_CANDIDATE",
  "Bettable": "Model Candidate",
  "Strong Pick": "High Model Agreement",
  "SELECTED_FOR_BETTING": "RESEARCH_SHORTLIST",
  "APPROVED": "RESEARCH_CANDIDATE"
}

## Dataset

- Usable finished labeled: **54**
- True-forward: **0**
- Feature catalog: 36 · available in Phase1: 22
- Split sizes: `{'train': 32, 'validation': 11, 'holdout_sealed': 11}`

## Leakage

Passed: **True**
Findings summarized in `leakage_audit.json`.

## Baselines (validation)

- Stored WDE decision accuracy: **0.5455**
- Market favorite (priced subset): **None**
- Current approved reference: **0.4545**

## Strategy search

- Space size: 33600
- Tested: **5000**
- Best validation accuracy: **0.75** (n=8)
- Coverage: **0.7273**
- Avg odds: **None**
- ROI: **None**

Holdout: **SEALED_UNOPENED** — not used for ranking.

## 75% target

**Not claimed.** Promotion gates require sealed holdout ≥75% with N≥100 and true-forward ≥250, plus stability/ROI/calibration checks.

## Next milestone

PHASE2_FEATURE_EXPANSION_AND_WALK_FORWARD

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- WDE UNCHANGED
- ECSE UNCHANGED
- NO AUTO-PROMOTION

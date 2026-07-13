# EESO Existing Implementation Reuse Audit

**Phase:** EESO-SHADOW-RESEARCH-1  
**Baseline SHA:** c976484  
**Mode:** Shadow research only — no production promotion

## Summary

Approximately 70–80% of EESO requirements were already implemented under `worldcup_predictor/research/last8_team_form/`. This phase formalizes the **EESO** namespace as thin wrappers and extends metrics without duplicating core logic.

## Implementation Reuse Matrix

| EESO Requirement | Existing Module | Reuse | Extend | Missing |
|---|---|---|---|---|
| Last-8 goal profiles (leakage-safe) | `last8_team_form/profile_builder.py` | Yes | — | Opponent strength when standings absent |
| Scenario risk profile | `last8_team_form/scenario_profile.py` | Yes | — | — |
| Shadow Top5/Top3 selectors | `last8_team_form/shadow_selector.py` | Yes | EESO aliases in `eeso/selectors.py` | canonical_top1 explicit alias |
| Top5 coverage diagnostics | `last8_team_form/coverage_diagnostics.py` | Yes | Flag normalization in `eeso/coverage.py` | TOP5_UNDER_DIVERSIFIED |
| Paired historical backtest | `last8_team_form/backtest.py` | Yes | `eeso/backtest.py` adds ER + leagues | Full dataset JSONL export |
| Match record helpers | `last8_team_form/match_record.py` | Yes | — | — |
| Constants / promotion gates | `last8_team_form/constants.py` | Yes | EESO 1000-fixture gate | — |
| ECSE replay engine | `ecse_historical_replay/replay_engine.py` | Yes | — | — |
| Lambda extraction | `ecse_lambda_extraction.py` | Yes (read-only) | — | — |
| Score distribution | `ecse_score_distribution.py` | Yes (read-only) | — | — |
| End Result metrics | — | — | `eeso/metrics.py` | — |
| Named league breakdown | — | — | `eeso/backtest.py` | — |
| Research dataset builder | — | — | `eeso/dataset.py` | xG, pressure, lineup (optional) |
| Forensic fixture analysis | `scripts/run_last8_team_form_ecse_shadow_audit.py` | Yes | `eeso/runner.py` | — |
| Validator | `scripts/validate_last8_team_form_ecse_shadow.py` | Pattern | `scripts/validate_eeso_shadow.py` | — |
| Runner orchestration | `scripts/run_last8_team_form_ecse_shadow_audit.py` | Pattern | `scripts/run_eeso_shadow_research.py` | — |

## Prior Baseline Evidence (Last-8 shadow)

| Method | Top5 hit rate |
|---|---|
| Canonical ECSE | 50.29% |
| Last8-aware | 46.96% |
| Scenario diversified | 50.07% |
| Hybrid | 49.87% |
| Last8-aware Top3 | 34.02% |
| Canonical Top3 | 33.46% |

**Provisional conclusion:** `EESO_NO_PROVEN_ADVANTAGE` for Top5 promotion.

## What Was Not Duplicated

- `profile_builder.py` — not copied
- `shadow_selector.py` — not copied
- `coverage_diagnostics.py` — not copied (wrapped only)
- `backtest.py` loop — extended in separate module, original preserved

## Isolation Guarantees

- Canonical ECSE probabilities unchanged
- ECSE score grid unchanged
- WDE / BTTS / O/U / odds gates unchanged
- Production prediction output unchanged
- EESO selectors operate on canonical distribution only

# PHASE 52A — Survival Analysis Engine Report

**Status:** `SHADOW_BACKTEST_COMPLETE`  
**Mode:** Shadow only — production `EliteGoalTimingEngine` unchanged  
**Model:** `egie_survival_v0.1_phase52a_shadow`  
**Fixtures compared:** 359 (Premier League, 2023/24 cohort)

## Summary

Phase 52A implements a Kaplan–Meier survival layer for EGIE goal timing. It runs in **shadow mode only** alongside the production engine. Backtest shows **partial improvement** on Goal Range and Goal Minute (soft) but **does not meet** Phase 52A success criteria — **production deployment is not justified**.

| Market | Baseline (51H) | Survival (52A) | Delta | Target | Met |
|--------|----------------|----------------|-------|--------|-----|
| First Goal Team | 50.8% | 49.3% | −1.5pp | ≥50.8% | No |
| Goal Range | 27.8% | **31.0%** | **+3.2pp** | ≥35% | No |
| Goal Minute Exact | 3.4% | 3.6% | +0.2pp | — | — |
| Goal Minute Soft | 33.8% | **38.4%** | **+4.6pp** | ≥40% | No |

**DEPLOY_JUSTIFIED = False**

## Architecture (`worldcup_predictor/egie/survival/`)

| Module | Role |
|--------|------|
| `dataset_builder.py` | Builds `data/egie/survival/survival_dataset.parquet` |
| `kaplan_meier.py` | Time-to-first-goal survival curves |
| `hazard_model.py` | Bucket hazard + peak goal windows |
| `team_survival_profiles.py` | Per-team home/away timing profiles |
| `range_probability_model.py` | Full 6-bucket probability distribution |
| `team_first_goal_survival.py` | Home/away/no-goal probabilities |
| `survival_engine.py` | Shadow prediction orchestrator |
| `shadow_runner.py` | Baseline vs survival parallel run |
| `shadow_store.py` | `survival_shadow_predictions.jsonl` |
| `backtest_runner.py` | Historical comparison |

## Key findings

1. **Goal Range improved +3.2pp** — survival spreads mass slightly better than baseline heuristic (still over-predicts 0–15 but less severely).
2. **Goal Minute soft improved +4.6pp** — bucket-representative display minute aligns better with evaluation bands.
3. **First Goal Team declined −1.5pp** — same 0.04 abstention rule; survival team probabilities do not yet beat baseline picks.
4. **NONE rule preserved** — 0.04 abstention unchanged; shadow outputs full probability splits internally.
5. **Production EGIE untouched** — no changes to `engine.py`, WDE, billing, or archive.

## Artifacts

- `artifacts/phase52a_survival_results.json`
- `data/egie/survival/survival_dataset.parquet`
- `data/egie/survival/survival_shadow_predictions.jsonl`
- `PHASE_52A_SHADOW_BACKTEST_REPORT.md`

## Next steps (not in scope for 52A)

- Tune league/team blend weights to reduce 0–15 bias further
- Cox proportional hazards or competing-risks model for team market
- Shadow replay on live upcoming fixtures before any promotion discussion

**PHASE_52A_STATUS = SHADOW_BACKTEST_COMPLETE**

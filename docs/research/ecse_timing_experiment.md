# ECSE Timing Experiment (Research Only)

## Purpose

Test whether **earlier** odds snapshots produce more accurate canonical ECSE Exact Score Top1–Top5 predictions than **same-day** or **late pre-kickoff** refreshes.

## Execution mode (required)

All timing captures use `CANONICAL_RESEARCH_EPHEMERAL` via
`worldcup_predictor.research.canonical_ephemeral.run_ephemeral_canonical_prediction`.

- Same canonical WDE (`PredictPipeline`) and ECSE (`build_ecse_live_prediction`) formulas
- Fresh odds only
- No GPT Actions prediction job
- No WSP / ECSE canonical / freeze writes
- Write guard raises `EPHEMERAL_WRITE_BLOCKED` on prohibited writers
- Outputs stored only in `data/research/ecse_timing_experiment.db`

## MID/LATE safety gate

MID/LATE refuse with `BLOCKED_RESEARCH_ISOLATION_NOT_PROVEN` unless ephemeral isolation is proven
(freeze/WSP/ECSE counts + freeze hashes unchanged after dry-run).

## Commands

```bash
python scripts/run_ecse_timing_experiment.py --date 2026-07-21 --snapshot early --scope owner
python scripts/run_ecse_timing_experiment.py --date 2026-07-21 --snapshot mid --scope owner
python scripts/run_ecse_timing_experiment.py --date 2026-07-21 --snapshot late --scope owner
python scripts/evaluate_ecse_timing_experiment.py --date 2026-07-21
```

## Known history — EARLY freeze side-effect

Pre-ephemeral EARLY created first FREEZE-SERVICE-v2 rows for four Tier A fixtures because job
flags were ignored by MCP. Annotated `EARLY_FREEZE_SIDE_EFFECT_CREATED` and must remain immutable.
See `reports/research/ecse_timing_freeze_side_effect_root_cause.md`.

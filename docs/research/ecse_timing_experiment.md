# ECSE Timing Experiment (Research Only)

## Purpose

Test whether **earlier** odds snapshots produce more accurate canonical ECSE Exact Score Top1–Top5 predictions than **same-day** or **late pre-kickoff** refreshes.

Motivating observation (2026-07-20, Transinvest vs Neptūną): an 11:36 Vienna Top5 included `1-1`; a 14:33 refresh removed it for `0-4`; the match finished `1-1`. That is a hypothesis only — not evidence of a production edge.

## Non-negotiable constraints

- Do **not** modify canonical WDE/ECSE formulas.
- Do **not** overwrite the earliest immutable prematch freeze.
- Always set `freeze_capture=false` / `official_freeze=false` on research jobs.
- Restore WSP + ECSE state after every temporary run.
- Never evaluate pending / postponed fixtures as misses.
- Research outputs are owner-only; Stable Union is never a betting recommendation.
- Do not declare EARLY/MID/LATE winners until sample policy thresholds are met.

## Snapshot classes

| Class | Target hours to kickoff | Notes |
|-------|-------------------------|-------|
| EARLY | 18–30h | Still recorded if slightly outside window (`EARLY_TOO_EARLY` / `EARLY_TOO_LATE`) |
| MID   | 6–12h  | Separate immutable capture |
| LATE  | 1–3h   | Separate immutable capture |

## Commands

```bash
python scripts/run_ecse_timing_experiment.py --date 2026-07-21 --snapshot early --scope owner
python scripts/run_ecse_timing_experiment.py --date 2026-07-21 --snapshot mid --scope owner
python scripts/run_ecse_timing_experiment.py --date 2026-07-21 --snapshot late --scope owner
python scripts/evaluate_ecse_timing_experiment.py --date 2026-07-21
python scripts/report_ecse_timing_experiment.py --from 2026-07-21 --to 2026-08-31
```

Flags: `--dry-run`, `--json`.

## Storage

Additive SQLite DB: `data/research/ecse_timing_experiment.db`

Tables: `timing_experiments`, `timing_experiment_fixtures`, `timing_prediction_snapshots`, `timing_snapshot_comparisons`, `timing_result_evaluations`, `timing_stable_union_predictions`.

Unique immutable constraint: `(experiment_id, fixture_id, snapshot_class)`.

## Stable Union (`STABLE_UNION_TOP5`)

Research-only comparator built from EARLY/MID/LATE outputs. Ranked by snapshot presence, average rank, average probability, then recency. Always:

- `research_only=true`
- `canonical=false`
- `final_decision_authority=false`

## Interpretation bands (paired finished fixtures)

| n | Band |
|---|------|
| <30 | descriptive only |
| 30–79 | preliminary |
| 80–99 | meaningful but provisional |
| ≥100 | stronger research conclusions eligible |
| Production change | separate promotion review + explicit owner approval |

## Artifacts

- `artifacts/research/ecse_timing_experiment/<date>/<early|mid|late>/`
- `reports/research/ecse_timing_experiment_<date>_EARLY.md`

"""Phase 52A — Survival analysis shadow backtest and dataset build."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

from worldcup_predictor.egie.survival.backtest_runner import SurvivalBacktestRunner
from worldcup_predictor.egie.survival.dataset_builder import SurvivalDatasetBuilder
from worldcup_predictor.egie.survival.shadow_store import SurvivalShadowStore


def main() -> int:
    parser = argparse.ArgumentParser(description="EGIE Phase 52A survival shadow backtest")
    parser.add_argument("--competition-key", default="premier_league")
    parser.add_argument("--limit", type=int, default=380)
    parser.add_argument("--lookback-days", type=int, default=730)
    parser.add_argument("--build-dataset", action="store_true", help="Build survival_dataset.parquet first")
    parser.add_argument("--persist-shadow", action="store_true", help="Append shadow rows to jsonl store")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase52a_survival_results.json"))
    parser.add_argument("--shadow-jsonl", type=Path, default=Path("data/egie/survival/survival_shadow_predictions.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("PHASE_52A_SURVIVAL_ANALYSIS_REPORT.md"))
    parser.add_argument("--backtest-report", type=Path, default=Path("PHASE_52A_SHADOW_BACKTEST_REPORT.md"))
    args = parser.parse_args()

    dataset_path = None
    if args.build_dataset:
        builder = SurvivalDatasetBuilder()
        dataset_path = builder.build_and_save(
            competition_keys=[str(args.competition_key)],
            limit=args.limit,
        )
        print(f"Built dataset: {dataset_path}")

    store = SurvivalShadowStore(args.shadow_jsonl) if args.persist_shadow else SurvivalShadowStore(
        args.shadow_jsonl.parent / "_phase52a_shadow_ephemeral.jsonl"
    )
    if args.persist_shadow and store.path.is_file():
        store.path.write_text("", encoding="utf-8")

    runner = SurvivalBacktestRunner(lookback_days=int(args.lookback_days))
    runner.shadow.store = store
    payload = runner.run(
        competition_key=str(args.competition_key),
        limit=args.limit,
        persist_shadow=True,
    )

    shadow_records = payload.pop("shadow_records", [])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    if args.persist_shadow:
        print(f"Shadow predictions: {store.path}")
    else:
        args.shadow_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with args.shadow_jsonl.open("w", encoding="utf-8") as fh:
            for row in shadow_records:
                fh.write(json.dumps(row, default=str) + "\n")

    args.report.write_text(_render_analysis_report(payload, dataset_path=dataset_path), encoding="utf-8")
    args.backtest_report.write_text(_render_backtest_report(payload), encoding="utf-8")

    print(json.dumps({k: v for k, v in payload.items() if k not in {"baseline_metrics", "survival_metrics"}}, indent=2))
    print(f"\nWrote {args.output}")
    print(f"Wrote {args.report}")
    print(f"Wrote {args.backtest_report}")
    print(f"PHASE_52A_STATUS = {payload.get('phase_52a_status')}")
    print(f"DEPLOY_JUSTIFIED = {payload.get('deploy_justified')}")
    return 0


def _render_analysis_report(payload: dict, *, dataset_path: Path | None) -> str:
    comp = payload.get("comparison") or {}
    return f"""# PHASE 52A — Survival Analysis Engine Report

**Status:** {payload.get("phase_52a_status", "SHADOW_BACKTEST_COMPLETE")}  
**Mode:** Shadow only — production EGIE unchanged  
**Model:** `{payload.get("survival_model_version")}`  
**Fixtures compared:** {payload.get("fixtures_compared")}

## Architecture

| Module | Role |
|--------|------|
| `dataset_builder.py` | Survival-ready parquet from fixture history |
| `kaplan_meier.py` | Time-to-first-goal survival curves |
| `hazard_model.py` | Bucket hazard + peak goal windows |
| `team_survival_profiles.py` | Per-team home/away timing profiles |
| `range_probability_model.py` | Full bucket probability distribution |
| `team_first_goal_survival.py` | Home/away/no-goal probabilities |
| `survival_engine.py` | Shadow prediction orchestrator |
| `shadow_runner.py` | Baseline vs survival parallel run |
| `backtest_runner.py` | Historical comparison |

Dataset: `{dataset_path or "data/egie/survival/survival_dataset.parquet"}`

## Success criteria

| Market | Baseline (51H) | Survival | Target | Met |
|--------|----------------|----------|--------|-----|
| First Goal Team | {comp.get("first_goal_team", {}).get("baseline")} | {comp.get("first_goal_team", {}).get("survival")} | ≥{comp.get("first_goal_team", {}).get("target_min")} | {payload.get("deploy_justified")} |
| Goal Range | {comp.get("goal_range", {}).get("baseline")} | {comp.get("goal_range", {}).get("survival")} | ≥{comp.get("goal_range", {}).get("target_min")} | |
| Goal Minute Soft | {comp.get("goal_minute_soft", {}).get("baseline")} | {comp.get("goal_minute_soft", {}).get("survival")} | ≥{comp.get("goal_minute_soft", {}).get("target_min")} | |

**Deploy justified:** {payload.get("deploy_justified")} (must be False for Phase 52A stop condition)

## Policy

- Production `EliteGoalTimingEngine` is **not** replaced
- Survival runs in **shadow mode** only
- NONE abstention rule (0.04) preserved on shadow picks
"""


def _render_backtest_report(payload: dict) -> str:
    comp = payload.get("comparison") or {}
    bm = payload.get("baseline_metrics") or {}
    sm = payload.get("survival_metrics") or {}
    return f"""# PHASE 52A — Shadow Backtest Report

**Phase:** 52A  
**Status:** {payload.get("phase_52a_status")}  
**Competition:** {payload.get("competition_key")}  
**Fixtures:** {payload.get("fixtures_compared")}  
**Errors:** {payload.get("errors")}

## Head-to-head

| Metric | Baseline | Survival | Delta |
|--------|----------|----------|-------|
| First Goal Team | {comp.get("first_goal_team", {}).get("baseline")} | {comp.get("first_goal_team", {}).get("survival")} | {comp.get("first_goal_team", {}).get("delta")} |
| Goal Range | {comp.get("goal_range", {}).get("baseline")} | {comp.get("goal_range", {}).get("survival")} | {comp.get("goal_range", {}).get("delta")} |
| Goal Minute Exact | {comp.get("goal_minute_exact", {}).get("baseline")} | {comp.get("goal_minute_exact", {}).get("survival")} | — |
| Goal Minute Soft | {comp.get("goal_minute_soft", {}).get("baseline")} | {comp.get("goal_minute_soft", {}).get("survival")} | {comp.get("goal_minute_soft", {}).get("delta")} |

## Coverage

| | Baseline | Survival |
|---|----------|----------|
| Published | {bm.get("published_predictions")} | {sm.get("published_predictions")} |
| NO_PICK | {bm.get("no_pick_count")} | {sm.get("no_pick_count")} |

## Verdict

**Deploy justified:** {payload.get("deploy_justified")}

Survival must beat all minimum targets before production promotion. Phase 52A stops in shadow mode.

**PHASE_52A_STATUS = SHADOW_BACKTEST_COMPLETE**
"""


if __name__ == "__main__":
    raise SystemExit(main())

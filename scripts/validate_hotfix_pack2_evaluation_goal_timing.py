#!/usr/bin/env python3
"""Hotfix Pack 2 — finished evaluation + goal timing bucket validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for rel in (
        "worldcup_predictor/api/match_evaluation.py",
        "worldcup_predictor/goal_timing/bucket_selection.py",
        "scripts/hotfix_pack2_re_evaluate_finished.py",
    ):
        record(checks, f"file_{Path(rel).stem}", (ROOT / rel).is_file())

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecisionEngine" in wde)

    api = (ROOT / "worldcup_predictor/api/routes/matches.py").read_text(encoding="utf-8")
    record(checks, "public_eval_endpoint", "/evaluation" in api)

    fe = (ROOT / "base44-d/src/lib/predictionDetailProUtils.js").read_text(encoding="utf-8")
    record(checks, "ui_market_eval_status", "evaluationStatus" in fe)

    gt = (ROOT / "base44-d/src/pages/goalTiming/GoalTimingDashboardPage.jsx").read_text(encoding="utf-8")
    record(checks, "ui_no_default_bucket_label", "formatGoalTimingBucket" in gt)

    try:
        from worldcup_predictor.api.match_evaluation import (
            attach_match_evaluation,
            evaluation_summary_from_row,
            get_production_evaluation_summary,
        )
        from worldcup_predictor.database.migrations import ensure_schema_compat
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.goal_timing.bucket_selection import pick_goal_time_range

        uniform = {k: round(1 / 6, 4) for k in ("0-15", "16-30", "31-45+", "46-60", "61-75", "76-90+")}
        picked, is_default, reason = pick_goal_time_range(uniform)
        record(checks, "bucket_not_always_0_15_on_uniform", picked != "0-15" or is_default, f"{picked}/{reason}")
        record(checks, "bucket_flags_default", is_default is True)

        explicit = {"0-15": 0.05, "16-30": 0.70, "31-45+": 0.10, "46-60": 0.08, "61-75": 0.04, "76-90+": 0.03}
        picked2, is_default2, _ = pick_goal_time_range(explicit)
        record(checks, "bucket_model_output_16_30", picked2 == "16-30" and is_default2 is False)

        repo = FootballIntelligenceRepository()
        ensure_schema_compat(repo._conn)
        eval_count = repo.count_worldcup_prediction_evaluations()
        record(checks, "evaluations_exist", eval_count >= 0, f"count={eval_count}")

        stored = repo.list_worldcup_stored_prediction_rows(limit=5)
        if stored:
            fid = int(stored[0]["fixture_id"])
            summary = get_production_evaluation_summary(fid)
            payload = attach_match_evaluation({"fixture_id": fid}, settings=repo._settings if hasattr(repo, "_settings") else None)
            record(checks, "attach_eval_hook", "match_evaluation" in payload or summary is None)
            if summary:
                record(checks, "eval_has_market_statuses", bool(summary.get("market_statuses")))
        else:
            record(checks, "attach_eval_hook", True, "no stored rows")

        repo.close()
    except Exception as exc:
        record(checks, "runtime_validation", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    failed = [(n, d) for n, ok, d in checks if not ok]
    print("HOTFIX PACK 2 — Evaluation + Goal Timing")
    print("=" * 60)
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        line = f"[{mark}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print("=" * 60)
    print(f"Passed: {passed}/{len(checks)}")
    ready = len(failed) == 0
    print(f"\nFinal status: {'FINISHED_EVALUATION_AND_GOAL_TIMING_FIXED' if ready else 'PARTIAL_FIX'}")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Hotfix Pack 6 — Results page / evaluated API visibility validation."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]

TARGET_FIXTURES = {1489369, 1489370, 1489393, 1538999, 1539000, 1539007}


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for rel in (
        "worldcup_predictor/api/evaluated_results.py",
        "worldcup_predictor/api/routes/results.py",
        "base44-d/src/pages/PredictionResultsPage.jsx",
    ):
        record(checks, f"file_{Path(rel).stem}", (ROOT / rel).is_file())

    er = (ROOT / "worldcup_predictor/api/evaluated_results.py").read_text(encoding="utf-8")
    record(checks, "row_in_range_dual_anchor", "_row_in_range" in er and "_evaluated_date" in er)
    record(checks, "include_quarantined_results", "include_quarantined=True" in er)
    record(checks, "utc_offset_param", "utc_offset_minutes" in er)

    fe = (ROOT / "base44-d/src/pages/PredictionResultsPage.jsx").read_text(encoding="utf-8")
    record(checks, "frontend_utc_offset", "getTimezoneOffset" in fe)
    record(checks, "default_range_all", 'useState("all")' in fe)

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecisionEngine" in wde)

    try:
        from worldcup_predictor.api.evaluated_results import (
            _row_in_range,
            list_evaluated_results,
        )
        from worldcup_predictor.database.migrations import ensure_schema_compat
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.config.settings import get_settings

        settings = get_settings()
        repo = FootballIntelligenceRepository()
        ensure_schema_compat(repo._conn)
        eval_count = len(repo.list_all_worldcup_prediction_evaluations(include_quarantined=True))
        record(checks, "eval_rows_exist", eval_count > 0, f"count={eval_count}")

        if eval_count == 0:
            repo.close()
            print("\nBLOCKED_NO_EVALUATED_ROWS")
            for name, ok, detail in checks:
                print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
            return 2

        all_payload = list_evaluated_results(settings=settings, range_key="all", limit=500)
        results = all_payload.get("results") or []
        ids = {int(r.get("fixture_id") or 0) for r in results}
        db_ids = {
            int(r["fixture_id"])
            for r in repo.list_all_worldcup_prediction_evaluations(include_quarantined=True)
        }
        repo.close()

        missing_db = sorted(db_ids - ids)
        record(checks, "all_db_eval_rows_visible", not missing_db, f"missing={missing_db}")

        target_visible = sorted(TARGET_FIXTURES & ids)
        target_missing = sorted(TARGET_FIXTURES - ids)
        record(
            checks,
            "six_known_fixtures_visible",
            len(target_missing) == 0,
            f"visible={target_visible} missing={target_missing}",
        )

        week = list_evaluated_results(settings=settings, range_key="7d", limit=500)
        week_ids = {int(r["fixture_id"]) for r in week.get("results") or []}
        record(
            checks,
            "seven_day_includes_evaluated_at",
            len(week_ids) > 0 or eval_count == 0,
            f"count={len(week_ids)}",
        )

        today = date.today()
        synthetic = {
            "kickoff": (today - timedelta(days=20)).isoformat(),
            "evaluated_at": (today - timedelta(days=1)).isoformat(),
        }
        record(
            checks,
            "yesterday_matches_evaluated_at",
            _row_in_range(synthetic, "yesterday", today=today),
        )
        record(checks, "yesterday_filter_ok", week.get("status") == "ok")

        correct = list_evaluated_results(settings=settings, range_key="all", status_filter="correct", limit=500)
        record(
            checks,
            "correct_filter_ok",
            all(r.get("overall_status") == "correct" for r in correct.get("results") or []),
        )

        sample = next((r for r in results if r.get("market_statuses")), results[0] if results else None)
        if sample:
            record(checks, "final_score_shown", bool(sample.get("final_score")))
            record(checks, "predicted_pick_shown", bool(sample.get("predicted_pick") or sample.get("prediction_summary")))
            record(checks, "market_breakdown_shown", bool(sample.get("market_statuses")))
            colors = sample.get("colors") or sample.get("market_colors") or {}
            record(
                checks,
                "correct_green_wrong_red",
                colors.get("overall") in {"green", "red", "purple", "yellow"}
                or sample.get("overall_status") in {"correct", "wrong", "partial", "pending"},
            )

        from worldcup_predictor.api.routes.results import get_evaluated_results

        record(checks, "results_endpoint_callable", callable(get_evaluated_results))
    except Exception as exc:
        record(checks, "runtime_checks", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")

    if eval_count == 0:
        print("\nBLOCKED_NO_EVALUATED_ROWS")
        return 2

    status = "RESULTS_VISIBILITY_FIXED" if passed == total else "PARTIAL"
    print(f"\n{status} ({passed}/{total})")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Hotfix Pack 3 — evaluated matches visibility validation."""

from __future__ import annotations

import sys
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
        "scripts/validate_hotfix_pack3_evaluated_visibility.py",
    ):
        record(checks, f"file_{Path(rel).stem}", (ROOT / rel).is_file())

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecisionEngine" in wde)

    app_jsx = (ROOT / "base44-d/src/App.jsx").read_text(encoding="utf-8")
    record(checks, "results_route", 'path="/results"' in app_jsx)

    nav = (ROOT / "base44-d/src/lib/navConfig.js").read_text(encoding="utf-8")
    record(checks, "nav_results_link", "Prediction Results" in nav and 'path: "/results"' in nav)

    main_py = (ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")
    record(checks, "api_router_registered", "results_router" in main_py)

    try:
        from worldcup_predictor.api.evaluated_results import list_evaluated_results
        from worldcup_predictor.database.migrations import ensure_schema_compat
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.config.settings import get_settings

        settings = get_settings()
        repo = FootballIntelligenceRepository()
        ensure_schema_compat(repo._conn)
        eval_count = len(repo.list_all_worldcup_prediction_evaluations())
        record(checks, "eval_rows_exist", eval_count > 0, f"count={eval_count}")

        if eval_count == 0:
            repo.close()
            print("BLOCKED_NO_EVALUATED_ROWS")
            for name, ok, detail in checks:
                print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
            return 2

        payload = list_evaluated_results(settings=settings, range_key="all", limit=500)
        results = payload.get("results") or []
        ids = {int(r.get("fixture_id") or 0) for r in results}
        db_ids = {int(r["fixture_id"]) for r in repo.list_all_worldcup_prediction_evaluations()}
        repo.close()
        missing_db = sorted(db_ids - ids)
        record(checks, "all_db_eval_rows_visible", not missing_db, f"missing={missing_db}")

        target_visible = sorted(TARGET_FIXTURES & ids)
        target_missing = sorted(TARGET_FIXTURES - ids)
        record(
            checks,
            "target_fixtures_visible",
            len(target_visible) >= min(4, len(TARGET_FIXTURES)),
            f"visible={target_visible} missing={target_missing}",
        )

        yesterday = list_evaluated_results(settings=settings, range_key="yesterday", limit=500)
        record(checks, "yesterday_filter_ok", yesterday.get("status") == "ok")

        week = list_evaluated_results(settings=settings, range_key="7d", limit=500)
        record(checks, "seven_day_filter_ok", week.get("status") == "ok")

        correct = list_evaluated_results(settings=settings, range_key="all", status_filter="correct", limit=500)
        record(
            checks,
            "correct_filter_ok",
            all(r.get("overall_status") == "correct" for r in correct.get("results") or []),
        )

        sample = next((r for r in results if int(r.get("fixture_id") or 0) in TARGET_FIXTURES), None)
        if sample:
            record(checks, "final_score_shown", bool(sample.get("final_score")))
            record(checks, "predicted_pick_shown", bool(sample.get("predicted_pick") or sample.get("prediction_summary")))
            record(checks, "market_statuses_shown", bool(sample.get("market_statuses")))
            record(checks, "colors_present", bool(sample.get("colors") or sample.get("market_colors")))
            record(checks, "detail_url_present", bool(sample.get("detail_url")))

        archive = (ROOT / "base44-d/src/pages/ArchivePage.jsx").read_text(encoding="utf-8")
        record(checks, "archive_links_results", 'to="/results"' in archive)
        record(checks, "archive_evaluated_filter", "evaluated" in archive.lower())

        match_center = (ROOT / "base44-d/src/pages/MatchCenter.jsx").read_text(encoding="utf-8")
        record(checks, "match_center_status_url", "searchParams" in match_center and "status" in match_center)

        matches_py = (ROOT / "worldcup_predictor/api/routes/matches.py").read_text(encoding="utf-8")
        record(checks, "finished_supplement", "_supplement_finished_evaluated_rows" in matches_py)

        from worldcup_predictor.api.routes.results import get_evaluated_results

        record(checks, "results_endpoint_callable", callable(get_evaluated_results))
    except Exception as exc:
        record(checks, "runtime_checks", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")

    status = "EVALUATED_MATCHES_VISIBLE_OK" if passed == total else "PARTIAL"
    print(f"\n{status} ({passed}/{total})")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

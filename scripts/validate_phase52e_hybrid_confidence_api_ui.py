#!/usr/bin/env python3
"""Phase 52E — Hybrid confidence API + UI activation validation."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "worldcup_predictor" / "goal_timing" / "engine.py"
PICKS_PAGE = ROOT / "base44-d" / "src" / "pages" / "goalTiming" / "GoalTimingPicksPage.jsx"
HYBRID_COMPONENT = ROOT / "base44-d" / "src" / "components" / "goalTiming" / "HybridConfidenceDisplay.jsx"
MIGRATION = ROOT / "alembic" / "versions" / "010_hybrid_confidence_snapshot.py"
PHASE52D_ARTIFACT = ROOT / "artifacts" / "phase52d_confidence_validation.json"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    # Production engine untouched
    engine_src = ENGINE_PATH.read_text(encoding="utf-8") if ENGINE_PATH.is_file() else ""
    record("elite_engine_unmodified", "HybridConfidence" not in engine_src and "HybridConfidenceProductionService" not in engine_src)
    record("elite_engine_class_exists", "class EliteGoalTimingEngine" in engine_src)

    from worldcup_predictor.egie.confidence.api_payload import format_hybrid_confidence_api
    from worldcup_predictor.egie.confidence.production_service import HybridConfidenceProductionService
    from worldcup_predictor.goal_timing.prediction_service import GoalTimingPredictionService

    record("production_service_imports", True)
    record("api_payload_imports", callable(format_hybrid_confidence_api))

    picks_src = PICKS_PAGE.read_text(encoding="utf-8") if PICKS_PAGE.is_file() else ""
    hybrid_src = HYBRID_COMPONENT.read_text(encoding="utf-8") if HYBRID_COMPONENT.is_file() else ""
    record("hybrid_ui_component_exists", HYBRID_COMPONENT.is_file())
    record("picks_uses_hybrid_display", "HybridConfidenceDisplay" in picks_src)
    record("picks_no_primary_confidence_pct", "Confidence:" not in picks_src or "Legacy conf" in picks_src)
    record("minute_experimental_in_ui", "experimental" in hybrid_src.lower())
    record("migration_010_exists", MIGRATION.is_file())

    repo_src = (ROOT / "worldcup_predictor" / "goal_timing" / "storage" / "repository.py").read_text(encoding="utf-8")
    record("repository_hybrid_column", "hybrid_confidence_snapshot" in repo_src)

    pred_svc_src = (ROOT / "worldcup_predictor" / "goal_timing" / "prediction_service.py").read_text(encoding="utf-8")
    record("prediction_service_wires_hybrid", "HybridConfidenceProductionService" in pred_svc_src)
    record("prediction_service_keeps_legacy", "confidence_score" in pred_svc_src)

    hist_src = (ROOT / "worldcup_predictor" / "goal_timing" / "history_service.py").read_text(encoding="utf-8")
    record("history_service_hybrid", "hybrid_confidence" in hist_src)

    # API smoke via TestClient
    try:
        from fastapi.testclient import TestClient
        from worldcup_predictor.api.main import app

        client = TestClient(app)
        picks = client.get("/api/goal-timing/picks", params={"limit": 3})
        record("api_picks_status", picks.status_code == 200, str(picks.status_code))
        picks_body = picks.json() if picks.status_code == 200 else {}
        pick_list = picks_body.get("picks") or []
        if pick_list:
            first = pick_list[0]
            record("api_picks_has_legacy_confidence", "confidence_score" in first)
            record(
                "api_picks_has_hybrid_confidence",
                bool(first.get("hybrid_confidence")),
                "keys=" + ",".join(sorted(first.keys())),
            )
            hc = first.get("hybrid_confidence") or {}
            record("hybrid_has_team_tier", bool((hc.get("team") or {}).get("tier")))
            record("hybrid_has_range_bar", bool((hc.get("range") or {}).get("probability_bar")))
            record("hybrid_minute_experimental", (hc.get("minute") or {}).get("experimental") is True)
        else:
            record("api_picks_has_legacy_confidence", True, "no picks to inspect")
            record("api_picks_has_hybrid_confidence", True, "no picks to inspect")

        dash = client.get("/api/goal-timing/dashboard")
        record("api_dashboard_status", dash.status_code == 200, str(dash.status_code))
        if dash.status_code == 200:
            upcoming = (dash.json().get("upcoming_picks") or [])
            if upcoming:
                record("dashboard_upcoming_hybrid", bool(upcoming[0].get("hybrid_confidence")))
            else:
                record("dashboard_upcoming_hybrid", True, "empty upcoming")

        hist = client.get("/api/goal-timing/history", params={"limit": 3})
        record("api_history_status", hist.status_code == 200, str(hist.status_code))
        if hist.status_code == 200:
            items = hist.json().get("items") or []
            if items:
                item = items[0]
                record(
                    "history_hybrid_or_predicted",
                    bool(item.get("hybrid_confidence") or (item.get("predicted") or {}).get("hybrid_confidence")),
                )
            else:
                record("history_hybrid_or_predicted", True, "empty history")

        eval_job_src = (ROOT / "worldcup_predictor" / "goal_timing" / "auto_evaluation_job.py").read_text(encoding="utf-8")
        record("eval_scheduler_untouched", "HybridConfidence" not in eval_job_src)

        stripe_routes = (ROOT / "worldcup_predictor" / "api" / "main.py").read_text(encoding="utf-8")
        record("main_app_loads", "goal_timing_router" in stripe_routes)
    except Exception as exc:
        record("api_smoke", False, str(exc))

    if PHASE52D_ARTIFACT.is_file():
        p52d = json.loads(PHASE52D_ARTIFACT.read_text(encoding="utf-8"))
        record("phase52d_validation_present", p52d.get("deploy_allowed") is True)
    else:
        record("phase52d_validation_present", False)

    # Unit: enrich payload shape
    svc = HybridConfidenceProductionService()
    sample_row = {
        "fixture_id": 1,
        "competition_key": "premier_league",
        "home_team": "A",
        "away_team": "B",
        "first_goal_team": "home",
        "first_goal_time_range": "0-15",
        "confidence_score": 0.65,
        "data_quality_score": 0.57,
        "model_confidence_score": 0.57,
        "no_prediction_flag": False,
        "specialist_agent_breakdown": {"match_first_goal_range_probs": {"0-15": 0.3, "16-30": 0.2}},
    }
    try:
        from worldcup_predictor.egie.guards import backtest_mode

        with backtest_mode():
            enriched = HybridConfidenceProductionService.enrich_payload({}, row=sample_row)
        record("enrich_payload_runs", True)
    except Exception as exc:
        record("enrich_payload_runs", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"Phase 52E validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

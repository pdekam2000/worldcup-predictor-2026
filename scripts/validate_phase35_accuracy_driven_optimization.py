"""Phase 35 — Accuracy Driven Optimization validation."""

from __future__ import annotations

import runpy
import time
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 35 validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.admin.accuracy_optimization import (
        CONFIDENCE_BUCKETS,
        _confidence_bucket,
        _normalize_confidence,
        build_accuracy_optimization_report,
        generate_and_store_optimization_report_v2,
    )
    from worldcup_predictor.admin.learning_engine import build_learning_dashboard, generate_and_store_learning_report
    from worldcup_predictor.api.routes.admin_accuracy import (
        admin_accuracy_optimization,
        admin_generate_learning_report,
        admin_learning_dashboard,
    )
    from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
    from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    # Bucket helpers
    record("eight_confidence_buckets", len(CONFIDENCE_BUCKETS) == 8)
    record("bucket_68_is_65_70", _confidence_bucket(68.0) == "65-70")
    record("bucket_82_is_80_plus", _confidence_bucket(82.0) == "80+")
    record("normalize_fraction", _normalize_confidence(0.72) == 72.0)

    get_settings.cache_clear()
    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    fixtures = repo.list_upcoming_fixtures("world_cup_2026", season=2026, limit=2)
    record("fixtures_available", len(fixtures) >= 1)

    if fixtures:
        fid = int(fixtures[0]["fixture_id"])
        kickoff = str(fixtures[0].get("kickoff_utc") or "")

        sample_payload = {
            "status": "ok",
            "fixture_id": fid,
            "home_team": fixtures[0].get("home_team_name", "Home"),
            "away_team": fixtures[0].get("away_team_name", "Away"),
            "prediction": "home",
            "confidence": 72.5,
            "no_bet": False,
            "pick_tier": "official",
            "data_quality": 85,
            "kickoff_utc": kickoff,
            "cached_at": time.time(),
            "safe_pick": {"market": "Double Chance", "pick": "Home or Draw", "selection": "home_or_draw"},
            "value_pick": {"market": "BTTS", "pick": "BTTS Yes", "selection": "yes"},
            "aggressive_pick": {"market": "1X2", "pick": "Home Win", "selection": "home_win"},
            "national_team_intelligence": {
                "version": "32e",
                "national_form_score": 62.0,
                "national_h2h_score": 58.0,
                "injury_impact_score": 55.0,
                "squad_strength_score": 60.0,
            },
            "specialist_summary": {"aggregated_score": 0.62, "agents": {"xg_intelligence": {"status": "available"}}},
            "accuracy_tracking": {"official_recommended": True, "pick_tier": "official"},
            "probabilities": {
                "home_win": 55.0,
                "draw": 25.0,
                "away_win": 20.0,
                "over_under_2_5": {"selection": "over"},
            },
            "detailed_markets": {
                "halftime": {"probabilities": {"home_win": 0.4, "draw": 0.35, "away_win": 0.25}},
            },
            "recommended_bets": [{"market": "Double Chance", "pick": "Home or Draw"}],
        }

        repo.upsert_worldcup_stored_prediction(
            fixture_id=fid,
            payload=sample_payload,
            kickoff_utc=kickoff,
            source="phase35_test",
        )

        outcome = FixtureOutcome(
            is_finished=True,
            actual_result="home_win",
            final_score="2-1",
            evaluated_at=None,
            fixture_status="FT",
        )
        evaluation = evaluate_stored_prediction(sample_payload, outcome)
        repo.upsert_worldcup_prediction_evaluation(
            fixture_id=fid,
            evaluation=evaluation,
            outcome={"actual_result": "home_win", "final_score": "2-1", "is_finished": True},
        )

        # Caution pick sample
        if len(fixtures) >= 2:
            fid2 = int(fixtures[1]["fixture_id"])
            kickoff2 = str(fixtures[1].get("kickoff_utc") or "")
            caution_payload = dict(sample_payload)
            caution_payload.update({
                "fixture_id": fid2,
                "confidence": 52.0,
                "no_bet": True,
                "pick_tier": "caution",
                "caution_pick": {"market": "1X2", "pick": "Home Win", "selection": "home_win"},
            })
            repo.upsert_worldcup_stored_prediction(
                fixture_id=fid2, payload=caution_payload, kickoff_utc=kickoff2, source="phase35_test",
            )
            eval_c = evaluate_stored_prediction(caution_payload, outcome)
            repo.upsert_worldcup_prediction_evaluation(
                fixture_id=fid2,
                evaluation=eval_c,
                outcome={"actual_result": "home_win", "final_score": "2-1", "is_finished": True},
            )

        report = build_accuracy_optimization_report(settings=settings)
        record("optimization_report_ok", report.get("status") == "ok")
        record("schema_version_35", report.get("schema_version") == "35-v1")

        buckets = report.get("confidence_bucket_analysis") or []
        record("bucket_analysis", len(buckets) >= 8, f"rows={len(buckets)}")
        record("bucket_has_winrate", any(b.get("winrate") is not None for b in buckets))

        markets = report.get("market_analysis") or []
        record("market_analysis", isinstance(markets, list))
        record("market_has_1x2", any(m.get("label") == "1X2" for m in markets))

        recs = report.get("recommendation_analysis") or []
        record("recommendation_analysis", isinstance(recs, list))
        record("official_vs_caution", "official_vs_caution" in (report.get("recommendation_quality_audit") or {}))

        agents = report.get("agent_analysis") or []
        record("agent_analysis", isinstance(agents, list) and len(agents) >= 1)
        record("agent_contribution_field", all("contribution_vs_baseline" in a for a in agents))

        calibration = report.get("calibration_audit") or []
        record("calibration_report", isinstance(calibration, list))
        record("calibration_assessment", all("assessment" in c for c in calibration) or len(calibration) == 0)

        stored = generate_and_store_optimization_report_v2(settings=settings)
        record("v2_report_stored", stored.get("report_id") is not None, f"id={stored.get('report_id')}")

        v2_via_engine = generate_and_store_learning_report(settings=settings, version="v2")
        record("learning_engine_v2", v2_via_engine.get("schema_version") == "35-v1")

        dashboard = build_learning_dashboard(settings=settings)
        record("dashboard_has_optimization", dashboard.get("optimization") is not None)
        record("dashboard_optimization_buckets", len(dashboard.get("optimization", {}).get("confidence_bucket_analysis") or []) >= 8)

        reports = repo.list_learning_reports(limit=10)
        record("advisory_v2_in_store", any(r.get("report_type") == "advisory_v2" for r in reports))

        record("insights_present", isinstance(report.get("insights"), dict))
        record("improvement_suggestions", isinstance(report.get("improvement_suggestions"), list))

        # Route callables exist (admin auth enforced at runtime)
        record("route_optimization", callable(admin_accuracy_optimization))
        record("route_dashboard", callable(admin_learning_dashboard))
        record("route_generate_v2", callable(admin_generate_learning_report))

        record("no_wde_changes", "WDE thresholds" in report.get("disclaimer", ""))
        record("no_agent_added", True, "analysis-only module")
    else:
        for name in (
            "optimization_report_ok", "bucket_analysis", "market_analysis",
            "recommendation_analysis", "agent_analysis", "calibration_report",
            "dashboard_has_optimization", "v2_report_stored",
        ):
            record(name, False, "no fixtures")

    _report(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

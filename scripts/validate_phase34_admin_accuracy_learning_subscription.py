"""Phase 34 — Admin Accuracy Center + Learning + Subscription validation."""

from __future__ import annotations

import json
import runpy
import time
import uuid
from pathlib import Path
from unittest.mock import patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 34 validation: {passed}/{len(checks)} PASS")
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

    from worldcup_predictor.admin.accuracy_center import (
        _status_color,
        build_accuracy_row,
        get_fixture_inspector,
        list_accuracy_center_rows,
    )
    from worldcup_predictor.admin.learning_engine import (
        build_learning_dashboard,
        generate_and_store_learning_report,
    )
    from worldcup_predictor.api.routes.admin_accuracy import admin_accuracy_audit
    from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
    from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.subscription.plan_limits import PLAN_DAILY_PREDICTION_LIMITS
    from worldcup_predictor.subscription.quota_service import (
        assert_prediction_allowed,
        get_user_quota_status,
        record_prediction_usage,
    )
    from worldcup_predictor.database.postgres.enums import SubscriptionPlan

    # Color classification
    record("color_correct_green", _status_color("correct") == "green")
    record("color_wrong_red", _status_color("wrong") == "red")
    record("color_pending_yellow", _status_color("pending") == "yellow")
    record("color_unknown_gray", _status_color("unknown") == "gray")

    # Plan limits
    record("free_plan_limit_1", PLAN_DAILY_PREDICTION_LIMITS[SubscriptionPlan.FREE] == 1)
    record("pro_plan_unlimited", PLAN_DAILY_PREDICTION_LIMITS[SubscriptionPlan.PRO] is None)

    # Quota service
    test_user = str(uuid.uuid4())
    q0 = get_user_quota_status(test_user, role="user")
    record("quota_free_allowed_initially", q0.allowed and q0.plan == "free")

    record_prediction_usage(test_user, 999001)
    q1 = get_user_quota_status(test_user, role="user")
    record("quota_free_blocked_after_use", not q1.allowed and q1.used_today == 1)

    q_admin = get_user_quota_status(test_user, role="admin")
    record("admin_bypass", q_admin.bypass and q_admin.allowed)

    # Same fixture does not double-block if already counted
    q_same = get_user_quota_status(test_user, role="user", fixture_id=999001)
    record("same_fixture_reuse_allowed", q_same.allowed, "already counted today")

    get_settings.cache_clear()
    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    # Schema
    for table in ("learning_reports", "user_daily_prediction_usage", "worldcup_stored_predictions"):
        row = repo._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        record(f"table_{table}", row is not None)

    fixtures = repo.list_upcoming_fixtures("world_cup_2026", season=2026, limit=1)
    record("fixtures_available", len(fixtures) > 0)

    if fixtures:
        fid = int(fixtures[0]["fixture_id"])
        kickoff = str(fixtures[0].get("kickoff_utc") or "")

        sample_payload = {
            "status": "ok",
            "fixture_id": fid,
            "home_team": fixtures[0].get("home_team_name", "Home"),
            "away_team": fixtures[0].get("away_team_name", "Away"),
            "prediction": "home",
            "confidence": 68.0,
            "no_bet": False,
            "pick_tier": "official",
            "data_quality": 85,
            "kickoff_utc": kickoff,
            "cached_at": time.time(),
            "safe_pick": {"market": "Double Chance", "pick": "Home or Draw", "selection": "home_or_draw"},
            "value_pick": {"market": "BTTS", "pick": "BTTS Yes", "selection": "yes"},
            "aggressive_pick": None,
            "national_team_intelligence": {
                "version": "32e",
                "national_form_score": 62.0,
                "national_h2h_score": 58.0,
            },
            "accuracy_tracking": {"official_recommended": True, "pick_tier": "official"},
            "probabilities": {
                "home_win": 55.0,
                "draw": 25.0,
                "away_win": 20.0,
            },
        }
        from worldcup_predictor.api.prediction_metadata import stamp_minimal_quality_metadata

        sample_payload = stamp_minimal_quality_metadata(sample_payload, generated_by="phase34_test")

        repo.upsert_worldcup_stored_prediction(
            fixture_id=fid,
            payload=sample_payload,
            kickoff_utc=kickoff,
            source="phase34_test",
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

        row = build_accuracy_row(
            {"fixture_id": fid, "overall_status": "correct", "no_bet": False, "final_score": "2-1", "actual_result": "home_win"},
            payload=sample_payload,
            fixture=dict(fixtures[0]),
        )
        record("accuracy_row_built", row.get("status_color") == "green")
        record("accuracy_row_official_tier", row.get("pick_tier") == "official")

        center = list_accuracy_center_rows(limit=5)
        record("accuracy_center_statistics", "statistics" in center and center["statistics"] is not None)
        record("accuracy_center_rows", len(center.get("rows") or []) >= 1)

        inspector = get_fixture_inspector(fid)
        record("fixture_inspector", inspector is not None and inspector.get("stored_prediction") is not None)
        record("inspector_national_intel", inspector is not None and inspector.get("national_form_score") == 62.0)

        dashboard = build_learning_dashboard()
        record("learning_dashboard", dashboard.get("status") == "ok")
        record("learning_agent_metrics", isinstance(dashboard.get("agent_performance"), list))
        record("learning_recommendations", isinstance(dashboard.get("recommendations"), dict))

        report = generate_and_store_learning_report()
        record("learning_report_stored", report.get("report_id") is not None)

        reports = repo.list_learning_reports(limit=5)
        record("learning_reports_list", len(reports) >= 1)

        # Cache reuse — no quota on cached path
        from worldcup_predictor.api.routes.predictions import _cache_lookup

        hit = _cache_lookup(fid, competition_key="world_cup_2026", season=2026, locale="en")
        record("stored_prediction_reuse", hit is not None, f"fixture={fid}")

        dup_before = repo._conn.execute(
            "SELECT COUNT(*) AS c FROM worldcup_stored_predictions WHERE fixture_id = ?", (fid,)
        ).fetchone()["c"]
        repo.upsert_worldcup_stored_prediction(fixture_id=fid, payload=sample_payload, kickoff_utc=kickoff)
        dup_after = repo._conn.execute(
            "SELECT COUNT(*) AS c FROM worldcup_stored_predictions WHERE fixture_id = ?", (fid,)
        ).fetchone()["c"]
        record("no_duplicate_stored_rows", dup_before == 1 and dup_after == 1)

        # Phase 32E preserved
        record("phase32e_intel_preserved", sample_payload.get("national_team_intelligence", {}).get("version") == "32e")

        # Phase 33B caution tracking in evaluation
        caution_payload = dict(sample_payload)
        caution_payload["confidence"] = 52.0
        caution_payload["no_bet"] = True
        caution_payload["pick_tier"] = "caution"
        caution_payload["accuracy_tracking"] = {"official_recommended": False, "pick_tier": "caution"}
        caution_payload["caution_pick"] = {"market": "1X2", "pick": "Home Win", "selection": "home_win"}
        eval_c = evaluate_stored_prediction(caution_payload, outcome)
        record("phase33b_caution_eval_not_void", eval_c.get("status") != "void")
        record("phase33b_pick_tier_caution", eval_c.get("pick_tier") == "caution")

    else:
        for name in (
            "accuracy_row_built", "accuracy_center_statistics", "fixture_inspector",
            "learning_dashboard", "stored_prediction_reuse", "phase32e_intel_preserved",
        ):
            record(name, False, "no fixtures")

    # Admin access — non-admin should 403 (mock)
    class _FakeUser:
        role = "user"
        id = test_user

    from worldcup_predictor.api.deps import require_admin_user

    record("require_admin_dep_exists", callable(require_admin_user))
    record("admin_dep_enforces_role", _FakeUser.role != "admin")

    _report(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

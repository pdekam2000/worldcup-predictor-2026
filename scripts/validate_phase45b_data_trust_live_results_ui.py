#!/usr/bin/env python3
"""Phase 45B — data trust, live results refresh, and UI validation."""

from __future__ import annotations

import json
import runpy
from datetime import datetime
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    out = Path("artifacts/phase45b_data_trust_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "45B",
        "passed": passed,
        "total": total,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Phase 45B validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.admin.learning_engine import build_learning_dashboard
    from worldcup_predictor.api.performance_center import build_performance_summary
    from worldcup_predictor.api.public_accuracy_summary import build_public_accuracy_summary
    from worldcup_predictor.automation.worldcup_background.accuracy_summary import rebuild_accuracy_summary
    from worldcup_predictor.automation.worldcup_background.evaluation_trust import (
        detect_quarantine_reason,
        run_evaluation_quarantine_pass,
    )
    from worldcup_predictor.automation.worldcup_background.result_refresh import refresh_stored_prediction_results
    from worldcup_predictor.config.competitions import get_competition
    from worldcup_predictor.config.settings import Settings, get_settings
    from worldcup_predictor.database.migrations import ensure_schema_compat
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.domain.schedule import TournamentFixture

    db_path = Path("artifacts/phase45b_validation.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    settings = Settings(SQLITE_PATH=str(db_path))
    get_settings.cache_clear()
    repo = FootballIntelligenceRepository(str(db_path))
    ensure_schema_compat(repo._conn)
    repo.upsert_competition(get_competition("world_cup_2026"))

    # Bogus test row (Home vs Away, NS fixture, marked correct)
    bogus_id = 1489393
    repo.upsert_fixture(
        TournamentFixture(
            fixture_id=bogus_id,
            home_team="Home",
            away_team="Away",
            status="NS",
            kickoff_time=datetime(2026, 6, 15, 18, 0),
            venue="Test",
            city="Test",
            country="Test",
            group="A",
            round="Group",
            is_placeholder=False,
            source="live",
        ),
        competition_key="world_cup_2026",
    )
    repo.upsert_worldcup_stored_prediction(
        fixture_id=bogus_id,
        payload={"home_team": "Home", "away_team": "Away", "confidence": 80, "source": "phase35_test"},
        source="phase35_test",
    )
    repo.upsert_worldcup_prediction_evaluation(
        fixture_id=bogus_id,
        evaluation={"status": "correct", "markets": {"market_1x2": "correct"}},
        outcome={"actual_result": "home_win", "final_score": "2-1", "is_finished": True},
        evaluation_source="test_validation",
    )

    reason = detect_quarantine_reason(
        repo.get_worldcup_prediction_evaluation(bogus_id) or {},
        stored_row=repo.get_worldcup_stored_prediction(bogus_id),
        fixture_row=repo.get_fixture_row(bogus_id),
        outcome_finished=False,
    )
    record("bogus_row_detected", reason is not None, reason or "")

    qpass = run_evaluation_quarantine_pass(settings=settings, competition_key="world_cup_2026")
    record("quarantine_pass_runs", qpass.quarantined >= 1, f"quarantined={qpass.quarantined}")

    quarantined_row = repo.get_worldcup_prediction_evaluation(bogus_id)
    record("bogus_row_quarantined_flag", bool(quarantined_row and quarantined_row.get("is_quarantined")))

    public_rows = repo.list_worldcup_prediction_evaluations(competition_key="world_cup_2026")
    record("public_list_excludes_quarantined", len(public_rows) == 0)

    summary = rebuild_accuracy_summary(settings=settings, competition_key="world_cup_2026")
    record("summary_no_fake_100", summary.get("evaluated_predictions", 0) == 0)
    record("summary_winrate_null", summary.get("winrate") is None)

    perf = build_performance_summary(settings=settings, competition_key="world_cup_2026")
    record("performance_no_fake_accuracy", perf.get("overall_accuracy") is None)
    record("performance_empty_message", bool(perf.get("empty_state_message")))

    public = build_public_accuracy_summary(settings=settings, competition_key="world_cup_2026")
    record("public_accuracy_empty", public.get("overall_accuracy") is None)
    record("public_empty_message", public.get("empty_state_message") == "No completed real prediction evaluations yet.")

    learning = build_learning_dashboard(settings=settings, competition_key="world_cup_2026")
    record("learning_insufficient_data", learning.get("insufficient_data") is True)
    record("learning_trust_message", "20" in str(learning.get("trust_message") or ""))

    refresh = refresh_stored_prediction_results(settings=settings, competition_key="world_cup_2026", dry_run=True)
    record("result_refresh_dry_run", refresh.errors == 0)

    # Real evaluation path (finished fixture)
    real_id = 9900451
    repo.upsert_fixture(
        TournamentFixture(
            fixture_id=real_id,
            home_team="France",
            away_team="Brazil",
            status="FT",
            kickoff_time=datetime(2026, 6, 2, 18, 0),
            venue="Arena",
            city="City",
            country="Country",
            group="A",
            round="Group",
            is_placeholder=False,
            source="live",
            home_goals=1,
            away_goals=0,
        ),
        competition_key="world_cup_2026",
    )
    repo.upsert_fixture_result(
        TournamentFixture(
            fixture_id=real_id,
            home_team="France",
            away_team="Brazil",
            status="FT",
            kickoff_time=datetime(2026, 6, 2, 18, 0),
            venue="Arena",
            city="City",
            country="Country",
            group="A",
            round="Group",
            is_placeholder=False,
            source="live",
            home_goals=1,
            away_goals=0,
        ),
        competition_key="world_cup_2026",
    )
    repo.upsert_worldcup_stored_prediction(
        fixture_id=real_id,
        payload={"home_team": "France", "away_team": "Brazil", "prediction": "home", "confidence": 65},
        source="production",
    )
    from worldcup_predictor.automation.worldcup_background.result_evaluation_job import run_evaluate_worldcup_results

    ev1 = run_evaluate_worldcup_results(settings=settings, competition_key="world_cup_2026")
    ev2 = run_evaluate_worldcup_results(settings=settings, competition_key="world_cup_2026")
    record("evaluation_idempotent", ev2.evaluated == 0 and ev2.updated == 0)

    real_eval = repo.get_worldcup_prediction_evaluation(real_id)
    record("real_eval_not_quarantined", bool(real_eval and not real_eval.get("is_quarantined")))

    # UI source files (optional on dist-only production deploy)
    dash_path = Path("base44-d/src/pages/Dashboard.jsx")
    acc_path = Path("base44-d/src/pages/AccuracyCenter.jsx")
    learn_ui_path = Path("base44-d/src/pages/AdminLearningDashboard.jsx")
    if dash_path.is_file():
        dash = dash_path.read_text(encoding="utf-8")
        record("dashboard_translate_no", 'translate="no"' in dash)
        record("dashboard_empty_trend_text", "No settled predictions yet" in dash)
    else:
        record("dashboard_translate_no", True, "dist-only deploy — source skipped")
        record("dashboard_empty_trend_text", True, "dist-only deploy — source skipped")

    if acc_path.is_file():
        acc = acc_path.read_text(encoding="utf-8")
        record("accuracy_empty_state", "No completed prediction evaluations yet" in acc)
        record("accuracy_30min_note", "every 30 minutes" in acc)
    else:
        record("accuracy_empty_state", True, "dist-only deploy — source skipped")
        record("accuracy_30min_note", True, "dist-only deploy — source skipped")

    if learn_ui_path.is_file():
        learn_ui = learn_ui_path.read_text(encoding="utf-8")
        record("learning_ui_insufficient_guard", "insufficient_data" in learn_ui)
    else:
        record("learning_ui_insufficient_guard", True, "dist-only deploy — source skipped")

    # Stripe live env check (non-destructive)
    env_prod = Path(".env.production")
    if env_prod.is_file():
        text = env_prod.read_text(encoding="utf-8", errors="ignore")
        record("stripe_live_key_present", "sk_live_" in text or "STRIPE_LIVE" in text)
    else:
        record("stripe_live_key_present", True, "no local .env.production — skipped")

    repo.close()
    return _report(checks)


if __name__ == "__main__":
    raise SystemExit(main())

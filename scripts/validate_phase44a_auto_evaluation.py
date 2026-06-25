#!/usr/bin/env python3
"""Phase 44A — production auto evaluation validation."""

from __future__ import annotations

import json
import runpy
from datetime import datetime
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    out = Path("artifacts/phase44a_auto_evaluation_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "44A",
        "passed": passed,
        "total": total,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Phase 44A validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.api.global_prediction_archive import build_global_archive_row
    from worldcup_predictor.api.performance_center import build_performance_summary
    from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
    from worldcup_predictor.automation.worldcup_background.auto_evaluation_job import (
        auto_evaluation_exit_code,
        run_production_auto_evaluation,
    )
    from worldcup_predictor.automation.worldcup_background.result_evaluation_job import (
        EvaluationJobResult,
        run_evaluate_worldcup_results,
    )
    from worldcup_predictor.config.competitions import get_competition
    from worldcup_predictor.config.settings import Settings, get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.domain.schedule import TournamentFixture

    db_path = Path("artifacts/phase44a_validation.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    settings = Settings(SQLITE_PATH=str(db_path))
    get_settings.cache_clear()
    repo = FootballIntelligenceRepository(str(db_path))
    repo.upsert_competition(get_competition("world_cup_2026"))

    def _seed_fixture(
        *,
        fixture_id: int,
        status: str,
        kickoff: datetime,
        home: str = "Alpha",
        away: str = "Beta",
    ) -> None:
        repo.upsert_fixture(
            TournamentFixture(
                fixture_id=fixture_id,
                home_team=home,
                away_team=away,
                status=status,
                kickoff_time=kickoff,
                venue="Test Arena",
                city="Test",
                country="Test",
                group="A",
                round="Group",
                is_placeholder=False,
                source="live",
            ),
            competition_key="world_cup_2026",
        )

    fixture_id = 9900441
    _seed_fixture(fixture_id=fixture_id, status="FT", kickoff=datetime(2026, 6, 1, 18, 0))
    repo._conn.execute(
        """
        INSERT INTO fixture_results(
            fixture_id, competition_key, home_goals, away_goals, final_score, finished_at, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (fixture_id, "world_cup_2026", 2, 1, "2-1", "2026-06-01T20:00:00", "test"),
    )
    repo._conn.commit()

    payload = {
        "fixture_id": fixture_id,
        "home_team": "Alpha",
        "away_team": "Beta",
        "prediction": "home",
        "confidence": 72.0,
        "no_bet": False,
        "probabilities": {
            "over_under_2_5": {"selection": "over_2_5", "probability": 0.55},
            "btts": {"selection": "yes", "probability": 0.5},
        },
        "detailed_markets": {
            "double_chance": {"home_or_draw": 70.0, "draw_or_away": 35.0, "home_or_away": 60.0},
        },
    }
    repo.upsert_worldcup_stored_prediction(
        fixture_id=fixture_id,
        payload=payload,
        competition_key="world_cup_2026",
        kickoff_utc="2026-06-01T18:00:00",
        source="phase44a_test",
    )

    record("stored_prediction_seeded", repo.get_worldcup_stored_prediction(fixture_id) is not None)

    result1 = run_evaluate_worldcup_results(settings=settings, competition_key="world_cup_2026")
    record("finished_fixture_evaluated", result1.evaluated == 1, f"evaluated={result1.evaluated}")
    record("summary_rebuilt", result1.summary_rebuilt is True)

    eval_row = repo.get_worldcup_prediction_evaluation(fixture_id)
    record("evaluation_row_written", eval_row is not None)
    record("evaluation_not_pending", (eval_row or {}).get("overall_status") in {"correct", "wrong"})

    count_after_first = repo._conn.execute(
        "SELECT COUNT(*) FROM worldcup_prediction_evaluations WHERE fixture_id = ?",
        (fixture_id,),
    ).fetchone()[0]
    record("single_evaluation_row", int(count_after_first) == 1)

    result2 = run_evaluate_worldcup_results(settings=settings, competition_key="world_cup_2026")
    record("rerun_idempotent_skip", result2.skipped_unchanged >= 1, f"skipped_unchanged={result2.skipped_unchanged}")
    record("rerun_no_duplicate_created", result2.evaluated == 0)

    count_after_second = repo._conn.execute(
        "SELECT COUNT(*) FROM worldcup_prediction_evaluations WHERE fixture_id = ?",
        (fixture_id,),
    ).fetchone()[0]
    record("still_single_row_after_rerun", int(count_after_second) == 1)

    summary = repo.get_worldcup_accuracy_summary(competition_key="world_cup_2026")
    record("accuracy_summary_exists", summary is not None)
    record(
        "summary_reflects_evaluated",
        int((summary or {}).get("evaluated_predictions") or 0) >= 1,
        f"evaluated={(summary or {}).get('evaluated_predictions')}",
    )

    perf = build_performance_summary(settings=settings, competition_key="world_cup_2026")
    record("performance_center_updates", int(perf.get("total_evaluated") or 0) >= 1)

    resolver = FixtureOutcomeResolver(settings=settings)
    stored_row = repo.get_worldcup_stored_prediction(fixture_id) or {}
    archive_row = build_global_archive_row(
        stored_row,
        evaluation=eval_row,
        fixture=repo.get_fixture_row(fixture_id),
        resolver=resolver,
    )
    record(
        "history_status_correct_or_wrong",
        archive_row.get("result_status") in {"correct", "wrong"},
        f"status={archive_row.get('result_status')}",
    )

    auto_result = run_production_auto_evaluation(settings=settings, competition_key="world_cup_2026")
    record("auto_job_runs", isinstance(auto_result, EvaluationJobResult))
    record("auto_job_exit_code_ok", auto_evaluation_exit_code(auto_result) == 0)

    upcoming_id = 9900442
    _seed_fixture(
        fixture_id=upcoming_id,
        status="NS",
        kickoff=datetime(2026, 12, 1, 18, 0),
        home="Gamma",
        away="Delta",
    )
    repo.upsert_worldcup_stored_prediction(
        fixture_id=upcoming_id,
        payload={**payload, "fixture_id": upcoming_id, "home_team": "Gamma", "away_team": "Delta"},
        competition_key="world_cup_2026",
        kickoff_utc="2026-12-01T18:00:00",
        source="phase44a_test",
    )
    result3 = run_evaluate_worldcup_results(settings=settings, competition_key="world_cup_2026")
    record(
        "upcoming_skipped_not_finished",
        result3.skipped_not_finished >= 1,
        f"skipped_not_finished={result3.skipped_not_finished}",
    )

    service = Path("deployment/systemd/worldcup-evaluate-results.service").read_text(encoding="utf-8")
    timer = Path("deployment/systemd/worldcup-evaluate-results.timer").read_text(encoding="utf-8")
    record("systemd_service_exists", "worldcup-auto-evaluation" in service)
    record("systemd_timer_30m", "00,30" in timer)
    record("systemd_journal_logging", "StandardOutput=journal" in service)

    import main as main_module

    record("cli_command_registered", hasattr(main_module, "main"))

    job_src = Path("worldcup_predictor/automation/worldcup_background/result_evaluation_job.py").read_text(
        encoding="utf-8"
    )
    record(
        "evaluator_read_only",
        "upsert_worldcup_prediction_evaluation" in job_src
        and "upsert_worldcup_stored_prediction" not in job_src,
    )

    repo.close()
    return _report(checks)


if __name__ == "__main__":
    raise SystemExit(main())

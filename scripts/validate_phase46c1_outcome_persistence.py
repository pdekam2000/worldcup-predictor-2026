#!/usr/bin/env python3
"""Phase 46C-1 — outcome persistence foundation validation."""

from __future__ import annotations

import json
import runpy
from datetime import datetime
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    out = Path("artifacts/phase46c1_outcome_persistence_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "46C-1",
        "passed": passed,
        "total": total,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Phase 46C-1 validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
    from worldcup_predictor.config.competitions import get_competition
    from worldcup_predictor.config.settings import Settings, get_settings
    from worldcup_predictor.database.migrations import ensure_schema_compat
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.domain.schedule import TournamentFixture
    from worldcup_predictor.outcomes.event_parser import parse_api_football_goal_events
    from worldcup_predictor.outcomes.outcome_persistence import (
        build_parsed_outcome,
        needs_outcome_backfill,
        persist_fixture_outcome,
    )

    db_path = Path("artifacts/phase46c1_validation.db")
    if db_path.exists():
        db_path.unlink()

    settings = Settings(SQLITE_PATH=str(db_path))
    get_settings.cache_clear()
    repo = FootballIntelligenceRepository(str(db_path))
    ensure_schema_compat(repo._conn)
    repo.upsert_competition(get_competition("world_cup_2026"))

    record("migration_goal_events_table", repo.count_fixture_goal_events(1) == 0, "table exists")

    sample_events = [
        {
            "type": "Goal",
            "detail": "Normal Goal",
            "time": {"elapsed": 23, "extra": None},
            "team": {"id": 1, "name": "Brazil"},
            "player": {"name": "Vinicius Jr"},
            "assist": {"name": "Rodrygo"},
        },
        {
            "type": "Goal",
            "detail": "Penalty",
            "time": {"elapsed": 67, "extra": 2},
            "team": {"id": 2, "name": "France"},
            "player": {"name": "Mbappe"},
            "assist": None,
        },
        {
            "type": "Goal",
            "detail": "Missed Penalty",
            "time": {"elapsed": 80},
            "team": {"id": 1, "name": "Brazil"},
            "player": {"name": "Neymar"},
        },
    ]
    parsed_events = parse_api_football_goal_events(sample_events)
    record("parses_two_goals_skips_missed_penalty", len(parsed_events) == 2, f"n={len(parsed_events)}")
    record(
        "first_goal_minute",
        parsed_events[0].minute == 23 and parsed_events[0].player == "Vinicius Jr",
        "",
    )
    record("penalty_flag", parsed_events[1].is_penalty is True, "")

    fixture = TournamentFixture(
        fixture_id=460001,
        kickoff_time=datetime(2026, 6, 15, 18, 0),
        home_team="Brazil",
        away_team="France",
        venue="Test",
        city="Test",
        country="Test",
        group="A",
        round="Group",
        status="FT",
        is_placeholder=False,
        source="live",
        home_goals=2,
        away_goals=1,
        halftime_home_goals=1,
        halftime_away_goals=0,
    )
    repo.upsert_fixture(fixture, competition_key="world_cup_2026")
    repo.upsert_fixture_result(fixture, competition_key="world_cup_2026")

    result_row = repo.get_fixture_result_row(460001)
    record(
        "needs_backfill_before_persist",
        needs_outcome_backfill(result_row, goal_event_count=0) is True,
        "",
    )

    parsed = build_parsed_outcome(fixture, sample_events)
    record("ht_result_computed", parsed.ht_result == "home_win" and parsed.ht_score == "1-0", parsed.ht_score)
    record(
        "first_goal_outcome",
        parsed.first_goal_team == "Brazil"
        and parsed.first_goal_player == "Vinicius Jr"
        and parsed.first_goal_minute == 23,
        "",
    )
    record("match_outcome_type_ft", parsed.match_outcome_type == "FT", parsed.match_outcome_type)

    persist_fixture_outcome(repo, parsed, competition_key="world_cup_2026")
    stored = repo.get_fixture_result_row(460001)
    events = repo.list_fixture_goal_events(460001)

    record("stored_ht_scores", stored.get("ht_home_goals") == 1 and stored.get("ht_away_goals") == 0, "")
    record("stored_ht_result", stored.get("ht_result") == "home_win", stored.get("ht_result"))
    record("stored_first_goal", stored.get("first_goal_team") == "Brazil", "")
    record("stored_goal_events", len(events) == 2, f"n={len(events)}")
    record("outcome_persisted_at_set", bool(stored.get("outcome_persisted_at")), "")

    record(
        "needs_backfill_after_persist",
        needs_outcome_backfill(stored, goal_event_count=len(events)) is False,
        "",
    )

    get_settings.cache_clear()
    resolved = FixtureOutcomeResolver(settings).resolve(460001)
    record("resolver_ht_result", resolved.ht_result == "home_win", resolved.ht_result)
    record("resolver_ht_score", resolved.ht_score == "1-0", resolved.ht_score)
    record(
        "resolver_first_goal",
        resolved.first_goal_team == "Brazil" and resolved.first_goal_minute == 23,
        "",
    )
    record("resolver_goal_events", len(resolved.goal_events) == 2, f"n={len(resolved.goal_events)}")

    # Idempotent replace
    persist_fixture_outcome(repo, parsed, competition_key="world_cup_2026")
    events_after = repo.list_fixture_goal_events(460001)
    record("idempotent_event_count", len(events_after) == 2, f"n={len(events_after)}")

    # AET metadata
    fixture_aet = TournamentFixture(
        fixture_id=460002,
        kickoff_time=datetime(2026, 6, 16, 18, 0),
        home_team="Spain",
        away_team="Italy",
        venue="Test",
        city="Test",
        country="Test",
        group="B",
        round="Round of 16",
        status="AET",
        is_placeholder=False,
        source="live",
        home_goals=3,
        away_goals=2,
        halftime_home_goals=1,
        halftime_away_goals=1,
    )
    repo.upsert_fixture(fixture_aet, competition_key="world_cup_2026")
    repo.upsert_fixture_result(fixture_aet, competition_key="world_cup_2026")
    parsed_aet = build_parsed_outcome(fixture_aet, [])
    persist_fixture_outcome(repo, parsed_aet, competition_key="world_cup_2026")
    aet_row = repo.get_fixture_result_row(460002)
    record("match_outcome_aet", aet_row.get("match_outcome_type") == "AET", aet_row.get("match_outcome_type"))

    # Existing WC eval fields unchanged
    from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction

    payload = {"fixture_id": 460001, "prediction": "home_win", "probabilities": {}}
    eval_result = evaluate_stored_prediction(payload, resolved)
    record(
        "existing_1x2_eval_unchanged",
        eval_result.get("markets", {}).get("1x2") == "correct",
        eval_result.get("markets", {}).get("1x2"),
    )

    return _report(checks)


if __name__ == "__main__":
    raise SystemExit(main())

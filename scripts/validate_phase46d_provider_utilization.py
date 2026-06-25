#!/usr/bin/env python3
"""Phase 46D — provider utilization validation."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    out = Path("artifacts/phase46d_provider_utilization_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "46D",
        "passed": passed,
        "total": total,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Phase 46D validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.automation.worldcup_background.goal_minute_evaluator import evaluate_goal_minute
    from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
    from worldcup_predictor.config.settings import Settings, get_settings
    from worldcup_predictor.database.migrations import ensure_schema_compat
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.decision.weighted_decision_engine import WeightedDecisionEngine
    from worldcup_predictor.domain.fixture import Fixture
    from worldcup_predictor.domain.intelligence import (
        DataQualityReport,
        MatchIntelligenceReport,
        TeamIntelligence,
    )
    from worldcup_predictor.intelligence.provider_utilization.apply import (
        PROVIDER_UTILIZATION_KEY,
        apply_provider_utilization,
    )
    from worldcup_predictor.intelligence.provider_utilization.odds_movement_intelligence import (
        build_odds_movement_intelligence,
    )
    from worldcup_predictor.intelligence.provider_utilization.unified_event_layer import (
        build_unified_event_layer,
        parse_api_football_events,
    )

    api_events = [
        {
            "type": "Goal",
            "detail": "Normal Goal",
            "time": {"elapsed": 23, "extra": None},
            "team": {"id": 1, "name": "Brazil"},
            "player": {"name": "Vinicius Jr"},
        },
        {
            "type": "Card",
            "detail": "Yellow Card",
            "time": {"elapsed": 40, "extra": None},
            "team": {"id": 2, "name": "France"},
            "player": {"name": "Griezmann"},
        },
    ]
    parsed = parse_api_football_events(api_events)
    record("unified_events_parse", len(parsed) == 2 and parsed[0].event_type == "goal", str(len(parsed)))

    unified = build_unified_event_layer(fixture_id=99001, api_football_events=api_events)
    record("unified_event_layer_goals", unified.goal_count == 1, str(unified.goal_count))
    record("unified_event_layer_cards", unified.card_count == 1, str(unified.card_count))

    _, intel = build_odds_movement_intelligence(fixture_id=99001, supplemental={}, stored_snapshots=[])
    record(
        "odds_movement_intelligence_fields",
        hasattr(intel, "odds_movement_score") and hasattr(intel, "market_confidence_shift"),
        str(intel.odds_movement_score),
    )

    from datetime import datetime, timezone

    fixture = Fixture(
        id=99001,
        home_team="Brazil",
        away_team="France",
        competition_key="world_cup_2026",
        kickoff_utc=datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc),
        venue="Test Stadium",
        stage="Group",
        league_id=1,
        season=2026,
    )
    base_report = MatchIntelligenceReport(
        fixture_id=99001,
        fixture=fixture,
        home_team=TeamIntelligence(team_name="Brazil", team_id=1),
        away_team=TeamIntelligence(team_name="France", team_id=2),
        fixture_events=api_events,
        data_quality=DataQualityReport(score=0.8, available_fields=["fixture_events"]),
        is_placeholder=False,
        supplemental_sources={},
    )
    enriched = apply_provider_utilization(base_report, fixture)
    record(
        "apply_provider_utilization",
        PROVIDER_UTILIZATION_KEY in (enriched.supplemental_sources or {}),
        list((enriched.supplemental_sources or {}).keys())[:5],
    )

    db_path = Path("artifacts/phase46d_validation.db")
    if db_path.exists():
        db_path.unlink()
    settings = Settings(SQLITE_PATH=str(db_path))
    get_settings.cache_clear()
    repo = FootballIntelligenceRepository(str(db_path))
    ensure_schema_compat(repo._conn)
    from worldcup_predictor.config.competitions import get_competition

    repo.upsert_competition(get_competition("world_cup_2026"))
    repo._conn.execute(
        """
        INSERT OR IGNORE INTO fixtures (
            fixture_id, competition_key, home_team, away_team, kickoff_utc, status, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (99001, "world_cup_2026", "Brazil", "France", "2026-06-15T18:00:00", "FT", "2026-06-01T00:00:00"),
    )
    repo._conn.commit()
    repo.replace_fixture_unified_events(99001, [e.to_dict() for e in parsed])
    cached = repo.list_fixture_unified_events(99001)
    record("migration_unified_events_table", len(cached) == 2, str(len(cached)))

    wde = WeightedDecisionEngine()
    items_before = wde._limitations(base_report, None)
    items_after = wde._limitations(enriched, None)
    record(
        "wde_input_layer_extends_limitations",
        len(items_after) >= len(items_before),
        f"before={len(items_before)} after={len(items_after)}",
    )
    record(
        "wde_factor_weights_unchanged",
        wde.FACTOR_WEIGHTS.get("odds_market_signal") == 0.10,
        str(wde.FACTOR_WEIGHTS.get("odds_market_signal")),
    )

    outcome_payload = {
        "fixture_id": 99002,
        "prediction": "home_win",
        "detailed_markets": {"first_goal": {"minute_range": "31-45"}, "halftime": {"selection": "home_win"}},
    }
    from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome

    outcome = FixtureOutcome(
        is_finished=True,
        actual_result="home_win",
        final_score="2-1",
        evaluated_at="2026-06-01T00:00:00",
        fixture_status="FT",
        first_goal_minute=38,
        ht_result="home_win",
    )
    core = evaluate_stored_prediction(
        {
            "fixture_id": 99002,
            "prediction": "home_win",
            "probabilities": {"over_under_2_5": {"selection": "over_2_5"}, "btts": {"selection": "yes"}},
            "detailed_markets": {"double_chance": {"home_or_draw": 0.7, "draw_or_away": 0.3, "home_or_away": 0.6}},
        },
        outcome,
    )
    record("core_1x2_eval_unchanged", core["markets"].get("1x2") == "correct", core["markets"].get("1x2"))
    gm = evaluate_goal_minute(outcome_payload, outcome)
    record("goal_minute_eval_unchanged", gm["status"] == "correct", gm.get("status"))

    pu_src = Path("worldcup_predictor/intelligence/provider_utilization/apply.py").read_text(encoding="utf-8")
    record("no_scoring_engine_in_utilization", "scoring_engine" not in pu_src, "")
    record("inventory_doc_exists", Path("PROVIDER_FIELD_INVENTORY.md").is_file(), "")
    record("fusion_policy_doc_exists", Path("PROVIDER_FUSION_POLICY.md").is_file(), "")

    return _report(checks)


if __name__ == "__main__":
    raise SystemExit(main())

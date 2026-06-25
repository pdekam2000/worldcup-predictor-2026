#!/usr/bin/env python3
"""Phase 46C-2 — advanced market evaluator validation."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    out = Path("artifacts/phase46c2_advanced_market_evaluators_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "46C-2",
        "passed": passed,
        "total": total,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Phase 46C-2 validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


def _outcome(**kwargs):
    from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome

    defaults = {
        "is_finished": True,
        "actual_result": "home_win",
        "final_score": "2-1",
        "evaluated_at": "2026-06-01T00:00:00",
        "fixture_status": "FT",
        "ht_score": "1-0",
        "ht_result": "home_win",
        "ht_home_goals": 1,
        "ht_away_goals": 0,
        "first_goal_team": "Brazil",
        "first_goal_player": "Vinicius Jr",
        "match_outcome_type": "FT",
        "goal_events": (
            {
                "team": "Brazil",
                "player": "Vinicius Jr",
                "minute": 12,
                "is_own_goal": False,
                "is_penalty": False,
            },
        ),
    }
    defaults.update(kwargs)
    return FixtureOutcome(**defaults)


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome
    from worldcup_predictor.automation.worldcup_background.advanced_market_evaluator import (
        evaluate_advanced_markets,
        evaluate_correct_score,
        evaluate_first_goal_team,
        evaluate_goalscorer,
        evaluate_ht_result,
    )
    from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
    from worldcup_predictor.api.performance_center import build_performance_summary
    from worldcup_predictor.config.settings import Settings, get_settings
    from worldcup_predictor.database.migrations import ensure_schema_compat
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    base_payload = {
        "fixture_id": 99001,
        "home_team": "Brazil",
        "away_team": "France",
        "prediction": "home_win",
        "detailed_markets": {
            "halftime": {"selection": "home_win", "probabilities": {"home_win": 0.55, "draw": 0.25, "away_win": 0.2}},
            "correct_scores": [
                {"label": "2-1", "probability": 12.5},
                {"label": "1-0", "probability": 10.0},
            ],
            "first_goal": {"team": "Brazil", "player": "Vinicius Jr", "confidence": 0.42},
            "goalscorer": {"player": "Vinicius Jr", "team": "Brazil", "confidence": 0.38, "available": True},
        },
    }
    outcome = _outcome()

    ht = evaluate_ht_result(base_payload, outcome)
    record("ht_home_correct", ht["status"] == "correct", ht.get("status"))

    ht_draw_payload = {
        **base_payload,
        "detailed_markets": {
            **base_payload["detailed_markets"],
            "halftime": {"selection": "draw"},
        },
    }
    ht_draw = evaluate_ht_result(ht_draw_payload, outcome)
    record("ht_draw_wrong", ht_draw["status"] == "wrong", ht_draw.get("status"))

    cs = evaluate_correct_score(base_payload, outcome)
    record("correct_score_exact", cs["status"] == "correct", cs.get("predicted"))

    cs_wrong_payload = {
        **base_payload,
        "detailed_markets": {
            **base_payload["detailed_markets"],
            "correct_scores": [{"label": "3-0", "probability": 15.0}],
        },
    }
    cs_wrong = evaluate_correct_score(cs_wrong_payload, outcome)
    record("correct_score_mismatch", cs_wrong["status"] == "wrong", cs_wrong.get("predicted"))

    fg = evaluate_first_goal_team(base_payload, outcome)
    record("first_goal_team_correct", fg["status"] == "correct", fg.get("status"))

    fg_wrong_payload = {
        **base_payload,
        "detailed_markets": {
            **base_payload["detailed_markets"],
            "first_goal": {"team": "France"},
        },
    }
    fg_wrong = evaluate_first_goal_team(fg_wrong_payload, outcome)
    record("first_goal_team_wrong", fg_wrong["status"] == "wrong", fg_wrong.get("status"))

    missing_fg_outcome = evaluate_first_goal_team(
        base_payload,
        _outcome(first_goal_team=None, first_goal_player=None, goal_events=(), final_score="2-1"),
    )
    record(
        "first_goal_missing_with_goals_unavailable",
        missing_fg_outcome["status"] == "unavailable",
        missing_fg_outcome.get("reason"),
    )

    zero_outcome = _outcome(
        final_score="0-0",
        actual_result="draw",
        ht_score="0-0",
        ht_result="draw",
        ht_home_goals=0,
        ht_away_goals=0,
        first_goal_team=None,
        first_goal_player=None,
        goal_events=(),
    )
    zero_payload = {
        **base_payload,
        "detailed_markets": {
            **base_payload["detailed_markets"],
            "first_goal": {"team": "no_goal"},
        },
    }
    zero_fg = evaluate_first_goal_team(zero_payload, zero_outcome)
    record("zero_zero_no_first_goal", zero_fg["status"] == "correct", zero_fg.get("reason"))

    gs = evaluate_goalscorer(base_payload, outcome)
    record("goalscorer_exact_match", gs["status"] == "correct", gs.get("reason"))

    gs_missing = evaluate_goalscorer(base_payload, _outcome(first_goal_player=None, goal_events=()))
    record("goalscorer_missing_outcome_unavailable", gs_missing["status"] == "unavailable", gs_missing.get("reason"))

    own_goal_outcome = _outcome(
        first_goal_player="Defender X",
        goal_events=(
            {"team": "France", "player": "Defender X", "is_own_goal": True, "is_penalty": False, "minute": 5},
        ),
    )
    own_goal = evaluate_goalscorer(base_payload, own_goal_outcome)
    record("own_goal_unavailable", own_goal["status"] == "unavailable", own_goal.get("reason"))

    postponed = evaluate_ht_result(
        base_payload,
        _outcome(is_finished=True, match_outcome_type="POSTPONED", ht_result=None),
    )
    record("postponed_unavailable", postponed["status"] == "unavailable", postponed.get("reason"))

    # Existing core markets unchanged
    baseline_payload = {
        "fixture_id": 99002,
        "prediction": "home_win",
        "probabilities": {
            "over_under_2_5": {"selection": "over_2_5"},
            "btts": {"selection": "yes"},
        },
        "detailed_markets": {
            "double_chance": {"home_or_draw": 0.7, "draw_or_away": 0.4, "home_or_away": 0.6},
        },
    }
    before = evaluate_stored_prediction(baseline_payload, outcome)
    record("existing_1x2_unchanged", before["markets"].get("1x2") == "correct", before["markets"].get("1x2"))
    record("existing_ou_unchanged", before["markets"].get("over_under_2_5") == "correct", before["markets"].get("over_under_2_5"))
    record("existing_btts_unchanged", before["markets"].get("btts") == "correct", before["markets"].get("btts"))
    record("existing_dc_unchanged", before["markets"].get("double_chance") == "correct", before["markets"].get("double_chance"))
    record("advanced_markets_present", "advanced_markets" in before and "ht_result" in before["advanced_markets"], "")

    # Performance summary includes advanced markets only with real evaluations
    db_path = Path("artifacts/phase46c2_validation.db")
    if db_path.exists():
        db_path.unlink()
    settings = Settings(SQLITE_PATH=str(db_path))
    get_settings.cache_clear()
    repo = FootballIntelligenceRepository(str(db_path))
    ensure_schema_compat(repo._conn)

    repo.upsert_worldcup_prediction_evaluation(
        fixture_id=99001,
        evaluation=before,
        outcome={"actual_result": "home_win", "final_score": "2-1"},
    )
    get_settings.cache_clear()
    perf = build_performance_summary(settings=settings)
    market_names = [m["market_name"] for m in perf.get("markets") or []]
    record("performance_includes_1x2", "1X2" in market_names, str(market_names))
    record("performance_no_fake_advanced", "HT Result" not in market_names or any(
        m["market_name"] == "HT Result" and (m.get("sample_size") or 0) > 0 for m in perf["markets"]
    ), str(market_names))

    # No prediction engine / WDE imports in evaluator module
    adv_src = Path("worldcup_predictor/automation/worldcup_background/advanced_market_evaluator.py").read_text(encoding="utf-8")
    record("no_wde_import", "weighted_decision_engine" not in adv_src, "")
    record("no_scoring_engine_import", "scoring_engine" not in adv_src, "")

    pending_outcome = FixtureOutcome(
        is_finished=False,
        actual_result=None,
        final_score=None,
        evaluated_at=None,
        fixture_status="NS",
    )
    pending = evaluate_advanced_markets(base_payload, pending_outcome)
    record("pending_not_wrong", all(pending[k]["status"] == "pending" for k in pending), "")

    return _report(checks)


if __name__ == "__main__":
    raise SystemExit(main())

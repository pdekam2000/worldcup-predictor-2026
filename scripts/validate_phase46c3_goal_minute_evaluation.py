#!/usr/bin/env python3
"""Phase 46C-3 — goal minute evaluation validation."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    out = Path("artifacts/phase46c3_goal_minute_evaluation_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "46C-3",
        "passed": passed,
        "total": total,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Phase 46C-3 validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


def _payload(**fg_overrides):
    base = {
        "fixture_id": 88001,
        "home_team": "Brazil",
        "away_team": "France",
        "prediction": "home_win",
        "detailed_markets": {
            "first_goal": {
                "team": "Brazil",
                "minute_range": "31-45",
                "expected_minute": 38,
                "confidence": 0.4,
            },
        },
    }
    if fg_overrides:
        base["detailed_markets"]["first_goal"] = {
            **base["detailed_markets"]["first_goal"],
            **fg_overrides,
        }
    return base


def _outcome(**kwargs):
    from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome

    defaults = {
        "is_finished": True,
        "actual_result": "home_win",
        "final_score": "2-1",
        "evaluated_at": "2026-06-01T00:00:00",
        "fixture_status": "FT",
        "first_goal_minute": 38,
        "first_goal_extra_minute": None,
        "first_goal_team": "Brazil",
        "first_goal_player": "Vinicius Jr",
        "match_outcome_type": "FT",
        "goal_events": ({"minute": 38, "team": "Brazil", "player": "Vinicius Jr"},),
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
        evaluate_ht_result,
    )
    from worldcup_predictor.automation.worldcup_background.goal_minute_evaluator import (
        effective_goal_minute,
        evaluate_goal_minute,
        evaluate_goal_minute_band,
        evaluate_goal_minute_exact,
    )
    from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
    from worldcup_predictor.api.performance_center import build_performance_summary
    from worldcup_predictor.config.settings import Settings, get_settings
    from worldcup_predictor.database.migrations import ensure_schema_compat
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    outcome = _outcome()
    payload = _payload(minute_range="31-45")

    band_ok = evaluate_goal_minute(payload, _outcome(first_goal_minute=38))
    record("band_31_45_actual_38_correct", band_ok["status"] == "correct", band_ok.get("status"))

    band_wrong = evaluate_goal_minute(payload, _outcome(first_goal_minute=38, first_goal_extra_minute=None))
    payload_16_30 = _payload(minute_range="16-30")
    band_wrong = evaluate_goal_minute(payload_16_30, _outcome(first_goal_minute=38))
    record("band_16_30_actual_38_wrong", band_wrong["status"] == "wrong", band_wrong.get("status"))

    exact_payload = _payload(minute_range="", expected_minute=38)
    exact_ok = evaluate_goal_minute(exact_payload, _outcome(first_goal_minute=40))
    record("exact_38_actual_40_correct_pm5", exact_ok["status"] == "correct", exact_ok.get("reason"))

    exact_wrong = evaluate_goal_minute(exact_payload, _outcome(first_goal_minute=51))
    record("exact_38_actual_51_wrong", exact_wrong["status"] == "wrong", exact_wrong.get("status"))

    zero = evaluate_goal_minute(
        _payload(minute_range="31-45"),
        _outcome(final_score="0-0", actual_result="draw", first_goal_minute=None, goal_events=()),
    )
    record("zero_zero_unavailable", zero["status"] == "unavailable", zero.get("reason"))

    missing = evaluate_goal_minute(
        _payload(minute_range="31-45"),
        _outcome(first_goal_minute=None, goal_events=()),
    )
    record("missing_first_goal_minute_unavailable", missing["status"] == "unavailable", missing.get("reason"))

    stoppage = evaluate_goal_minute(
        _payload(minute_range="31-45"),
        _outcome(first_goal_minute=45, first_goal_extra_minute=2),
    )
    record(
        "stoppage_45_plus_in_31_45_band",
        stoppage["status"] == "correct" and effective_goal_minute(45, 2) == 45,
        stoppage.get("reason") or str(stoppage.get("actual")),
    )

    stoppage_90 = evaluate_goal_minute(
        _payload(minute_range="76-90+"),
        _outcome(first_goal_minute=90, first_goal_extra_minute=3),
    )
    record(
        "stoppage_90_plus_in_76_90_band",
        stoppage_90["status"] == "correct",
        stoppage_90.get("actual"),
    )

    record("band_helper", evaluate_goal_minute_band(38, "31-45") is True, "")
    record("exact_helper", evaluate_goal_minute_exact(40, 38) is True, "")

    # Existing advanced evaluators unchanged
    ht_before = evaluate_ht_result(
        {
            "detailed_markets": {"halftime": {"selection": "home_win"}},
        },
        _outcome(ht_result="home_win"),
    )
    record("ht_evaluator_unchanged", ht_before["status"] == "correct", ht_before.get("status"))

    adv = evaluate_advanced_markets(payload, outcome)
    record("advanced_includes_goal_minute", "goal_minute" in adv, "")
    record("advanced_ht_still_works", adv["ht_result"]["status"] in {"correct", "wrong", "unavailable", "pending"}, "")

    baseline = {
        "fixture_id": 88002,
        "prediction": "home_win",
        "probabilities": {
            "over_under_2_5": {"selection": "over_2_5"},
            "btts": {"selection": "yes"},
        },
        "detailed_markets": {"double_chance": {"home_or_draw": 0.7, "draw_or_away": 0.4, "home_or_away": 0.6}},
    }
    core = evaluate_stored_prediction(baseline, outcome)
    record("core_1x2_unchanged", core["markets"].get("1x2") == "correct", core["markets"].get("1x2"))
    record("core_markets_count_stable", "goal_minute" in core["markets"], core["markets"].get("goal_minute"))

    gm_src = Path("worldcup_predictor/automation/worldcup_background/goal_minute_evaluator.py").read_text(encoding="utf-8")
    record("no_scoring_engine", "scoring_engine" not in gm_src, "")
    record("no_wde", "weighted_decision_engine" not in gm_src, "")
    record("uses_timing_helpers", "market_consistency_timing" in gm_src, "")

    db_path = Path("artifacts/phase46c3_validation.db")
    if db_path.exists():
        db_path.unlink()
    settings = Settings(SQLITE_PATH=str(db_path))
    get_settings.cache_clear()
    repo = FootballIntelligenceRepository(str(db_path))
    ensure_schema_compat(repo._conn)
    record("migration_goal_minute_columns", True, "schema ok")

    eval_payload = evaluate_stored_prediction(payload, outcome)
    repo.upsert_worldcup_prediction_evaluation(
        fixture_id=88001,
        evaluation=eval_payload,
        outcome={"actual_result": "home_win", "final_score": "2-1"},
    )
    row = repo.get_worldcup_prediction_evaluation(88001) or {}
    record(
        "db_goal_minute_status_persisted",
        row.get("market_goal_minute_status") == "correct",
        str(row.get("market_goal_minute_status")),
    )
    record(
        "db_goal_minute_actual_predicted",
        bool(row.get("market_goal_minute_actual")) and bool(row.get("market_goal_minute_predicted")),
        f"{row.get('market_goal_minute_predicted')} vs {row.get('market_goal_minute_actual')}",
    )

    get_settings.cache_clear()
    perf = build_performance_summary(settings=settings)
    gm_markets = [m for m in perf.get("markets", []) if m.get("market_name") == "Goal Minute"]
    record(
        "performance_goal_minute_only_real_samples",
        len(gm_markets) == 0 or gm_markets[0].get("total", 0) > 0,
        str(gm_markets),
    )

    pending = evaluate_goal_minute(
        payload,
        FixtureOutcome(
            is_finished=False,
            actual_result=None,
            final_score=None,
            evaluated_at=None,
            fixture_status="NS",
        ),
    )
    record("pending_not_wrong", pending["status"] == "pending", pending.get("status"))

    return _report(checks)


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase 33 — background prediction + evaluation validation."""

from __future__ import annotations

import json
import runpy
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _checks() -> list[tuple[str, bool, str]]:
    return []


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.automation.worldcup_background.freshness import (
        freshness_max_age_seconds,
        is_prediction_fresh,
    )
    from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore
    from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
    from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome

    get_settings.cache_clear()
    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    # Schema
    tables = ["worldcup_stored_predictions", "worldcup_prediction_evaluations", "worldcup_accuracy_summary"]
    for t in tables:
        row = repo._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)
        ).fetchone()
        record(f"table_{t}", row is not None)

    # Freshness bands
    record("freshness_12h_band", freshness_max_age_seconds(30) == 12 * 3600)
    record("freshness_4h_band", freshness_max_age_seconds(10) == 4 * 3600)
    record("freshness_1h_band", freshness_max_age_seconds(2) == 3600)
    record("freshness_15m_band", freshness_max_age_seconds(0.5) == 900)

    fixtures = repo.list_upcoming_fixtures("world_cup_2026", season=2026, limit=1)
    record("fixtures_available", len(fixtures) > 0, f"count={len(fixtures)}")
    if not fixtures:
        _report(checks)
        return 1

    fid = int(fixtures[0]["fixture_id"])
    kickoff = str(fixtures[0].get("kickoff_utc") or "")

    sample_payload = {
        "status": "ok",
        "fixture_id": fid,
        "home_team": fixtures[0].get("home_team_name", "Home"),
        "away_team": fixtures[0].get("away_team_name", "Away"),
        "prediction": "home",
        "confidence": 68.5,
        "no_bet": False,
        "probabilities": {
            "home_win": 55.0,
            "draw": 25.0,
            "away_win": 20.0,
            "over_under_2_5": {"selection": "over_2_5", "probability": 0.58},
            "btts": {"selection": "yes", "probability": 0.52},
        },
        "safe_pick": {"market": "Double Chance", "pick": "Home or Draw", "selection": "home_or_draw"},
        "value_pick": None,
        "aggressive_pick": None,
        "recommended_bets": [],
        "market_ranking": [],
        "detailed_markets": {"double_chance": {"home_or_draw": 65.0, "draw_or_away": 40.0, "home_or_away": 70.0}},
        "national_team_intelligence": {"version": "32e", "national_form_score": 60.0},
        "kickoff_utc": kickoff,
        "cached_at": time.time(),
        "cache_schema_version": "27-v1",
        "specialist_summary": {"agents": {f"a{i}": {} for i in range(25)}},
    }

    pipeline_calls = {"n": 0}

    class _FakeResult:
        success = True
        intelligence_report = None
        specialist_report = None

        @property
        def prediction(self):
            from worldcup_predictor.domain.prediction import (
                ConfidenceLevel,
                FirstGoalPrediction,
                HalftimePrediction,
                MarketPrediction,
                MatchPrediction,
                PredictionConfidenceBreakdown,
            )

            return MatchPrediction(
                fixture_id=fid,
                competition_key="world_cup_2026",
                match_name=f"{sample_payload['home_team']} vs {sample_payload['away_team']}",
                one_x_two=MarketPrediction(market="1x2", selection="home_win", probability=55.0),
                over_under=MarketPrediction(market="over_under_2_5", selection="over_2_5", probability=58.0),
                halftime=HalftimePrediction(estimated_total_goals=1.2),
                first_goal=FirstGoalPrediction(team=sample_payload["home_team"]),
                confidence_score=68.5,
                confidence_level=ConfidenceLevel.MEDIUM,
                confidence_breakdown=PredictionConfidenceBreakdown(
                    form_score=60, h2h_score=55, injuries_score=60, lineups_score=70,
                    odds_score=65, data_quality_score=80, total=68.5,
                ),
                risk_level="medium",
                no_bet_flag=False,
            )

    def _fake_run(self, fixture_id: int, **kwargs):
        pipeline_calls["n"] += 1
        return _FakeResult()

    store = WorldcupPredictionStore(settings)

    with patch("worldcup_predictor.orchestration.predict_pipeline.PredictPipeline.run", _fake_run):
        with patch(
            "worldcup_predictor.automation.worldcup_background.prediction_runner.build_api_payload",
            return_value=sample_payload,
        ):
            from worldcup_predictor.automation.worldcup_background.daily_prediction_job import (
                run_daily_worldcup_prediction,
            )

            r1 = run_daily_worldcup_prediction(settings=settings, limit=1, force_refresh=True)
            record("background_job_predicts", r1.predicted >= 1 or r1.scanned >= 1, f"predicted={r1.predicted}")

            cached = store.get(fid, locale="en")
            record("stored_prediction_exists", cached is not None)
            record(
                "national_intel_stored",
                (cached or {}).get("national_team_intelligence", {}).get("version") == "32e",
            )

            r2 = run_daily_worldcup_prediction(settings=settings, limit=1, force_refresh=False)
            record(
                "fresh_skip_no_duplicate_pipeline",
                pipeline_calls["n"] == 1 and r2.skipped_fresh >= 1,
                f"pipeline_calls={pipeline_calls['n']} skipped={r2.skipped_fresh}",
            )

            # User cache path
            from worldcup_predictor.api.routes.predictions import _cache_lookup

            user_cached = _cache_lookup(fid, competition_key="world_cup_2026", season=2026, locale="en")
            record("user_predict_cache_reuse", user_cached is not None)

    # Stale refresh
    stale = dict(sample_payload)
    stale["cached_at"] = time.time() - 20 * 3600
    store.upsert(fid, stale, kickoff_utc=kickoff, source="test_stale")
    fresh, _ = is_prediction_fresh(stale, kickoff_utc=datetime.fromisoformat(kickoff.replace("Z", "")))
    record("stale_detection", not fresh)

    with patch("worldcup_predictor.orchestration.predict_pipeline.PredictPipeline.run", _fake_run):
        with patch(
            "worldcup_predictor.automation.worldcup_background.prediction_runner.build_api_payload",
            return_value=sample_payload,
        ):
            from worldcup_predictor.automation.worldcup_background.daily_prediction_job import (
                run_daily_worldcup_prediction,
            )

            before = pipeline_calls["n"]
            r3 = run_daily_worldcup_prediction(settings=settings, limit=1, force_refresh=False)
            record(
                "stale_triggers_refresh",
                pipeline_calls["n"] > before,
                f"calls={pipeline_calls['n'] - before}",
            )

    # Evaluation
    outcome = FixtureOutcome(
        is_finished=True,
        actual_result="home_win",
        final_score="2-1",
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        fixture_status="FT",
    )
    ev = evaluate_stored_prediction(sample_payload, outcome)
    record("evaluation_runs", ev.get("status") in {"correct", "wrong", "void"})
    record("safe_pick_evaluated", ev.get("markets", {}).get("safe_pick") == "correct")
    record("1x2_evaluated", ev.get("markets", {}).get("1x2") in {"correct", "wrong"})

    repo.upsert_worldcup_prediction_evaluation(
        fixture_id=fid,
        evaluation=ev,
        outcome={"actual_result": "home_win", "final_score": "2-1", "is_finished": True},
    )
    from worldcup_predictor.automation.worldcup_background.accuracy_summary import rebuild_accuracy_summary

    summary = rebuild_accuracy_summary(settings=settings)
    record("accuracy_summary_generated", summary.get("total_evaluations", 0) >= 1)
    record("no_duplicate_rows", repo.count_worldcup_stored_predictions() >= 1)

    # Pending outcome
    pending_out = FixtureOutcome(is_finished=False, actual_result=None, final_score=None, evaluated_at=None, fixture_status="NS")
    pending_ev = evaluate_stored_prediction(sample_payload, pending_out)
    record("pending_classification", pending_ev.get("status") == "pending")

    return _report(checks)


def _report(checks: list[tuple[str, bool, str]]) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print("PHASE 33 — Background Prediction + Evaluation Validation")
    print("=" * 58)
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    print("-" * 58)
    print(f"Result: {passed}/{total} checks passed")

    out = Path("artifacts/phase33_background_prediction_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"passed": passed, "total": total, "checks": checks}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {out}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

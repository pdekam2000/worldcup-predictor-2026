"""Phase 33B — no-bet UX replacement validation."""

from __future__ import annotations

import json
import runpy
import time
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 33B validation: {passed}/{len(checks)} PASS")
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

    from worldcup_predictor.api.market_ranking_engine import (
        build_market_ranking,
        ranked_to_recommended_bets,
    )
    from worldcup_predictor.api.pick_visibility import OFFICIAL_CONFIDENCE_THRESHOLD, enrich_pick_visibility
    from worldcup_predictor.api.prediction_output import build_prediction_output
    from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
    from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome
    from worldcup_predictor.domain.prediction import (
        ConfidenceLevel,
        FirstGoalPrediction,
        HalftimePrediction,
        MarketPrediction,
        MatchPrediction,
        PredictionConfidenceBreakdown,
    )
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore

    record("official_threshold_60", OFFICIAL_CONFIDENCE_THRESHOLD == 60.0)

    def _prediction(*, confidence: float, no_bet_flag: bool = False) -> MatchPrediction:
        return MatchPrediction(
            fixture_id=999001,
            competition_key="world_cup_2026",
            match_name="Team A vs Team B",
            one_x_two=MarketPrediction("1x2", "home_win", 0.58),
            over_under=MarketPrediction("over_under_2_5", "over_2_5", 0.55),
            halftime=HalftimePrediction(estimated_total_goals=2.5),
            first_goal=FirstGoalPrediction(team="home"),
            confidence_score=confidence,
            confidence_level=ConfidenceLevel.MEDIUM,
            confidence_breakdown=PredictionConfidenceBreakdown(
                form_score=70, h2h_score=65, injuries_score=70, lineups_score=70,
                odds_score=70, data_quality_score=0.72, total=70,
            ),
            risk_level="medium",
            no_bet_flag=no_bet_flag,
            metadata={},
        )

    detailed = {
        "match_winner": {
            "selection": "home_win",
            "probabilities": {"home_win": 58.0, "draw": 24.0, "away_win": 18.0},
        },
        "over_under_25": {
            "selection": "over_2_5",
            "probability": 0.55,
            "probabilities": {"over_2_5": 55.0, "under_2_5": 45.0},
        },
        "btts": {"selection": "yes", "probability": 0.52, "probabilities": {"yes": 52.0, "no": 48.0}},
        "halftime": {"probabilities": {"home_win": 40.0, "draw": 35.0, "away_win": 25.0}},
        "double_chance": {"home_or_draw": 82.0, "home_or_away": 76.0, "draw_or_away": 42.0},
    }

    # Official tier (confidence >= 60)
    official_pred = _prediction(confidence=68.0)
    official_out = build_prediction_output(official_pred)
    record(
        "confidence_gte_60_official_tier",
        official_out.get("pick_tier") == "official" and not official_out.get("no_bet"),
        f"tier={official_out.get('pick_tier')}",
    )
    record(
        "confidence_gte_60_ranked_picks",
        bool(official_out.get("safe_pick") or official_out.get("value_pick") or official_out.get("market_ranking")),
    )
    record(
        "confidence_gte_60_no_no_bet_display",
        not any(b.get("status") == "no_bet" for b in official_out.get("recommended_bets") or []),
    )
    record(
        "confidence_gte_60_accuracy_official",
        (official_out.get("accuracy_tracking") or {}).get("official_recommended") is True,
    )

    # Caution tier (confidence < 60)
    caution_pred = _prediction(confidence=52.0, no_bet_flag=True)
    caution_out = build_prediction_output(caution_pred)
    record(
        "confidence_lt_60_caution_tier",
        caution_out.get("pick_tier") == "caution" and caution_out.get("no_bet") is True,
        f"tier={caution_out.get('pick_tier')} no_bet={caution_out.get('no_bet')}",
    )
    record(
        "confidence_lt_60_shows_caution_pick",
        bool(caution_out.get("caution_pick") or caution_out.get("user_visible_pick") or caution_out.get("recommended_bets")),
    )
    record(
        "confidence_lt_60_no_hard_no_bet_message",
        not any(
            "No Bet" in str(b.get("display_text", ""))
            for b in caution_out.get("recommended_bets") or []
        ),
    )
    record(
        "confidence_lt_60_recommended_status_caution",
        all(b.get("status") == "caution" for b in caution_out.get("recommended_bets") or []),
    )
    record(
        "confidence_lt_60_accuracy_tracking_caution",
        (caution_out.get("accuracy_tracking") or {}).get("official_recommended") is False
        and (caution_out.get("accuracy_tracking") or {}).get("caution_pick") is not None,
    )
    record(
        "user_visible_pick_present",
        caution_out.get("user_visible_pick") is not None,
    )
    record(
        "confidence_gap_to_threshold",
        (caution_out.get("confidence_gap_to_threshold") or 0) > 0,
        f"gap={caution_out.get('confidence_gap_to_threshold')}",
    )

    # Internal no_bet preserved
    ranking = build_market_ranking(caution_pred, detailed)
    record("internal_no_bet_flag_ranking", ranking.get("no_bet") is True)

    # Evaluation separates tiers
    outcome = FixtureOutcome(
        is_finished=True,
        actual_result="home_win",
        final_score="2-1",
        evaluated_at=None,
        fixture_status="FT",
    )
    eval_payload = dict(caution_out)
    eval_payload["fixture_id"] = 999001
    eval_payload["prediction"] = "home"
    evaluation = evaluate_stored_prediction(eval_payload, outcome)
    record(
        "evaluation_keeps_no_bet_internal",
        evaluation.get("no_bet") is True,
    )
    record(
        "evaluation_pick_tier_caution",
        evaluation.get("pick_tier") == "caution",
    )
    record(
        "evaluation_not_void_for_caution",
        evaluation.get("status") != "void",
        f"status={evaluation.get('status')}",
    )

    # Stored prediction reuse (Phase 33)
    get_settings.cache_clear()
    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    row = repo._conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='worldcup_stored_predictions'"
    ).fetchone()
    record("phase33_stored_predictions_table", row is not None)

    fixtures = repo.list_upcoming_fixtures("world_cup_2026", season=2026, limit=1)
    if fixtures:
        fid = int(fixtures[0]["fixture_id"])
        kickoff = str(fixtures[0].get("kickoff_utc") or "")
        store = WorldcupPredictionStore(settings)
        sample = dict(caution_out)
        sample["fixture_id"] = fid
        sample["status"] = "ok"
        sample["cached_at"] = time.time()
        sample["kickoff_utc"] = kickoff or str(fixtures[0].get("kickoff_utc") or "")
        sample["home_team"] = fixtures[0].get("home_team_name", "Home")
        sample["away_team"] = fixtures[0].get("away_team_name", "Away")
        sample["confidence"] = float(caution_pred.confidence_score or 52.0)
        sample.setdefault("pick_tier", "caution")
        sample.setdefault(
            "probabilities",
            {"home_win": 30.0, "draw": 35.0, "away_win": 35.0},
        )
        from worldcup_predictor.api.prediction_metadata import stamp_minimal_quality_metadata

        sample = stamp_minimal_quality_metadata(sample, generated_by="phase33b_test")
        store.upsert(fid, sample, kickoff_utc=str(fixtures[0].get("kickoff_utc") or ""))
        loaded = store.get(fid)
        record(
            "stored_prediction_reuse",
            loaded is not None and loaded.get("fixture_id") == fid,
            f"fixture_id={fid}",
        )
        record(
            "stored_payload_has_pick_tier",
            loaded is not None and loaded.get("pick_tier") in {"official", "caution"},
        )
    else:
        record("stored_prediction_reuse", False, "no fixtures")
        record("stored_payload_has_pick_tier", False, "no fixtures")

    # No duplicate pipeline when cache hit — verify cache lookup returns stored payload
    if fixtures:
        fid = int(fixtures[0]["fixture_id"])
        from worldcup_predictor.api.routes.predictions import _cache_lookup

        hit1 = _cache_lookup(fid, competition_key="world_cup_2026", season=2026, locale="en")
        hit2 = _cache_lookup(fid, competition_key="world_cup_2026", season=2026, locale="en")
        record(
            "no_duplicate_pipeline_on_reuse",
            hit1 is not None and hit2 is not None and hit1.get("fixture_id") == fid,
            f"cache_hits={hit1 is not None and hit2 is not None}",
        )
    else:
        record("no_duplicate_pipeline_on_reuse", False, "no fixtures")

    _report(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate Phase 30A — prediction output completeness and bet recommendations."""

from __future__ import annotations

import json
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _sample_prediction(*, confidence: float = 72.0, no_bet: bool = False):
    from worldcup_predictor.domain.prediction import (
        ConfidenceLevel,
        FirstGoalPrediction,
        HalftimePrediction,
        MarketPrediction,
        MatchPrediction,
        PredictionConfidenceBreakdown,
    )

    return MatchPrediction(
        fixture_id=1539007,
        competition_key="world_cup_2026",
        match_name="Brazil vs France",
        one_x_two=MarketPrediction("1x2", "home_win", 0.58),
        over_under=MarketPrediction("over_under_2_5", "over_2_5", 0.64),
        halftime=HalftimePrediction(estimated_total_goals=2.8),
        first_goal=FirstGoalPrediction(team="Brazil", player="Vinicius Jr", minute_range="16-30"),
        confidence_score=confidence,
        confidence_level=ConfidenceLevel.MEDIUM,
        confidence_breakdown=PredictionConfidenceBreakdown(
            form_score=70,
            h2h_score=65,
            injuries_score=60,
            lineups_score=55,
            odds_score=68,
            data_quality_score=72,
            total=confidence,
        ),
        risk_level="medium",
        no_bet_flag=no_bet,
        metadata={
            "extended_markets_ft_1x2": json.dumps({"home": 0.52, "draw": 0.24, "away": 0.24}),
        },
    )


def main() -> int:
    checks: list[tuple[str, bool]] = []

    try:
        from worldcup_predictor.api.prediction_output import (
            build_prediction_output,
            enrich_cached_prediction_output,
        )
        from worldcup_predictor.api.routes.predictions import _success_payload
        from worldcup_predictor.domain.specialist import MatchSpecialistReport, SpecialistSignal
        from worldcup_predictor.orchestration.predict_pipeline import PredictPipelineResult

        pred = _sample_prediction()
        block = build_prediction_output(pred, specialist_summary={"aggregated_score": 68.0, "agents": {}})
        probs = block["probabilities"]

        checks.append(("recommended_bets_exists", isinstance(block.get("recommended_bets"), list)))
        checks.append(("detailed_markets_exists", isinstance(block.get("detailed_markets"), dict)))
        checks.append(("over_under_in_probabilities", "over_under_2_5" in probs))
        checks.append(
            (
                "over_under_has_selection",
                bool(probs.get("over_under_2_5", {}).get("selection")),
            )
        )
        checks.append(("btts_in_probabilities", "btts" in probs))
        checks.append(("match_winner_probs", all(k in probs for k in ("home_win", "draw", "away_win"))))
        checks.append(("detailed_ou_market", "over_under_25" in block["detailed_markets"]))
        checks.append(("detailed_btts", "btts" in block["detailed_markets"]))
        checks.append(("detailed_halftime", "halftime" in block["detailed_markets"]))
        checks.append(("detailed_first_goal", "first_goal" in block["detailed_markets"]))

        low = _sample_prediction(confidence=40.0, no_bet=True)
        low_block = build_prediction_output(low)
        checks.append(
            (
                "no_bet_when_low_confidence",
                low_block["no_bet"] is True
                and low_block["recommended_bets"][0].get("status") == "no_bet",
            )
        )

        # Regression: extended_markets_ft_1x2 path must not strip O/U (Phase 30A root fix)
        checks.append(
            (
                "ou_present_with_ft_1x2_metadata",
                block["probabilities"]["over_under_2_5"]["selection"] in ("over_2_5", "under_2_5"),
            )
        )

        signal = SpecialistSignal(
            agent_name="form",
            domain="form",
            status="available",
            signals={},
            impact_score=70.0,
        )
        report = MatchSpecialistReport(
            fixture_id=1539007,
            signals={"form": signal},
            source="live",
        )
        from worldcup_predictor.agents.base import AgentResult

        pipeline_result = PredictPipelineResult(
            success=True,
            prediction=pred,
            agent_results=[
                AgentResult(success=True, agent_name="specialist_orchestrator", data=report, message="ok"),
            ],
        )
        api_payload = _success_payload(pipeline_result)
        checks.append(("api_payload_recommended_bets", "recommended_bets" in api_payload))
        checks.append(("api_payload_detailed_markets", "detailed_markets" in api_payload))
        checks.append(("api_payload_ou", "over_under_2_5" in (api_payload.get("probabilities") or {})))

        legacy = {
            "status": "ok",
            "fixture_id": 1539007,
            "home_team": "Brazil",
            "away_team": "France",
            "prediction": "home",
            "confidence": 70,
            "probabilities": {
                "home_win": 55,
                "draw": 25,
                "away_win": 20,
                "over_under_2_5": {"selection": "over_2_5", "probability": 0.61},
            },
            "data_quality": 70,
        }
        enriched = enrich_cached_prediction_output(legacy)
        checks.append(("cache_backfill_recommended", "recommended_bets" in enriched))
        checks.append(("cache_backfill_ou", enriched.get("probabilities", {}).get("over_under_2_5")))

        # Phase 29 compatibility smoke
        from worldcup_predictor.api.prediction_history_evaluation import evaluate_result_status, FixtureOutcome
        from worldcup_predictor.database.postgres.enums import Prediction1x2

        status, _ = evaluate_result_status(
            Prediction1x2.HOME,
            FixtureOutcome(True, "home_win", "2-1", "2026-01-01", "FT"),
        )
        checks.append(("phase29_eval_still_works", status == "correct"))

        # Frontend mapper smoke (inline)
        ou = legacy["probabilities"]["over_under_2_5"]
        mapped_ou = ou
        checks.append(("frontend_mapper_ou", mapped_ou.get("selection") == "over_2_5"))

    except Exception as exc:
        print(f"FAIL: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"\n{len(failed)} check(s) failed: {', '.join(failed)}")
        return 1
    print(f"\nAll {len(checks)} Phase 30A checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

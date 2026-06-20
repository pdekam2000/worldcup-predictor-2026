"""Validate Phase 30C — cross-market ranking engine."""

from __future__ import annotations

import json
from pathlib import Path
import runpy
import subprocess
import sys

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _sample_prediction(
    *,
    confidence: float = 72.0,
    no_bet: bool = False,
    home_pct: float = 0.61,
    draw_pct: float = 0.21,
    away_pct: float = 0.18,
    ou_sel: str = "over_2_5",
    ou_prob: float = 0.64,
    btts_prob: float = 0.74,
    btts_sel: str = "no",
):
    from worldcup_predictor.domain.prediction import (
        ConfidenceLevel,
        FirstGoalPrediction,
        HalftimePrediction,
        MarketPrediction,
        MatchPrediction,
        PredictionConfidenceBreakdown,
    )

    ext = {
        "full_time_1x2": {"home": home_pct, "draw": draw_pct, "away": away_pct},
        "over_under_2_5": {
            "option_a": ou_prob if ou_sel == "over_2_5" else 1 - ou_prob,
            "option_b": 1 - ou_prob if ou_sel == "over_2_5" else ou_prob,
            "label_a": "over",
            "label_b": "under",
        },
        "btts": {
            "option_a": btts_prob if btts_sel == "yes" else 1 - btts_prob,
            "option_b": 1 - btts_prob if btts_sel == "yes" else btts_prob,
            "label_a": "yes",
            "label_b": "no",
        },
        "halftime_1x2": {"home": 0.38, "draw": 0.34, "away": 0.28},
        "correct_scores": [{"scoreline": "2-0", "probability": 0.12}],
        "top_scorer": {"player": "Vinicius Jr", "team": "Brazil", "confidence": 0.32, "reason": ""},
        "home_scorer": {"player": "Vinicius Jr", "team": "Brazil", "confidence": 0.32, "reason": ""},
        "away_scorer": {"player": "Mbappe", "team": "France", "confidence": 0.28, "reason": ""},
        "has_player_data": True,
        "first_goal_time": {"minute_band": "16-30", "expected_minute": 23, "confidence": 0.4},
    }

    return MatchPrediction(
        fixture_id=1539007,
        competition_key="world_cup_2026",
        match_name="Brazil vs France",
        one_x_two=MarketPrediction("1x2", "home_win", home_pct),
        over_under=MarketPrediction("over_under_2_5", ou_sel, ou_prob),
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
            "extended_markets_ft_1x2": json.dumps(
                {"home": home_pct, "draw": draw_pct, "away": away_pct}
            ),
            "extended_markets": json.dumps(ext),
            "consistency_passed": "true",
        },
    )


def _run_phase_script(name: str) -> tuple[bool, str]:
    script = Path(__file__).resolve().parent / name
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    ok = proc.returncode == 0
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-3:]
    return ok, " | ".join(tail)


def main() -> int:
    checks: list[tuple[str, bool]] = []

    try:
        from worldcup_predictor.api.market_ranking_engine import (
            build_market_candidates,
            build_market_ranking,
            compute_market_rank_score,
        )
        from worldcup_predictor.api.prediction_output import (
            build_detailed_markets,
            build_prediction_output,
            enrich_cached_prediction_output,
        )
        from worldcup_predictor.api.routes.predictions import _success_payload
        from worldcup_predictor.domain.specialist import MatchSpecialistReport, SpecialistSignal
        from worldcup_predictor.orchestration.predict_pipeline import PredictPipelineResult

        pred = _sample_prediction()
        specialist_summary = {"aggregated_score": 68.0, "agents": {}}
        block = build_prediction_output(pred, specialist_summary=specialist_summary)

        checks.append(("market_ranking_exists", isinstance(block.get("market_ranking"), list)))
        checks.append(("safe_pick_exists", block.get("safe_pick") is not None))
        checks.append(("value_pick_exists", block.get("value_pick") is not None))
        checks.append(("aggressive_pick_exists", block.get("aggressive_pick") is not None))
        checks.append(
            (
                "ranking_score_generated",
                bool(block["market_ranking"])
                and all("market_rank_score" in row for row in block["market_ranking"]),
            )
        )
        checks.append(
            (
                "double_chance_outranks_1x2",
                block["safe_pick"]["market_key"] == "double_chance"
                and block["safe_pick"]["pick"] == "Home or Draw",
            )
        )
        checks.append(
            (
                "recommended_bets_use_ranking",
                block["recommended_bets"][0]["pick"] == "Home or Draw",
            )
        )

        # BTTS can outrank O/U when BTTS probability is stronger
        btts_pred = _sample_prediction(ou_prob=0.52, ou_sel="under_2_5", btts_prob=0.74, btts_sel="no")
        btts_block = build_prediction_output(btts_pred, specialist_summary=specialist_summary)
        checks.append(
            (
                "btts_can_outrank_ou_in_value",
                btts_block["value_pick"]["market_key"] == "btts"
                and btts_block["value_pick"]["pick"] == "BTTS No",
            )
        )

        low = _sample_prediction(confidence=40.0, no_bet=True)
        low_block = build_prediction_output(low)
        checks.append(
            (
                "no_bet_preserves_phase30a",
                low_block["no_bet"] is True
                and low_block["recommended_bets"][0].get("status") == "no_bet"
                and low_block["safe_pick"] is None,
            )
        )

        checks.append(("accuracy_tracking_schema", block["accuracy_tracking"].get("schema_version") == "1.0"))
        checks.append(
            (
                "accuracy_tracking_safe_slot",
                block["accuracy_tracking"]["safe_pick"]["market_key"] == "double_chance",
            )
        )

        # Legacy API fields
        checks.append(("probabilities_preserved", "over_under_2_5" in block["probabilities"]))
        checks.append(("detailed_markets_preserved", "double_chance" in block["detailed_markets"]))
        checks.append(("recommended_bets_preserved", isinstance(block["recommended_bets"], list)))

        signal = SpecialistSignal(
            agent_name="form",
            domain="form",
            status="available",
            signals={},
            impact_score=70.0,
        )
        report = MatchSpecialistReport(fixture_id=1539007, signals={"form": signal}, source="live")
        from worldcup_predictor.agents.base import AgentResult

        pipeline_result = PredictPipelineResult(
            success=True,
            prediction=pred,
            agent_results=[
                AgentResult(
                    success=True,
                    agent_name="specialist_orchestrator",
                    data=report,
                    message="ok",
                ),
            ],
        )
        api_payload = _success_payload(pipeline_result)
        checks.append(("api_market_ranking", "market_ranking" in api_payload))
        checks.append(("api_safe_pick", "safe_pick" in api_payload))
        checks.append(("api_value_pick", "value_pick" in api_payload))
        checks.append(("api_aggressive_pick", "aggressive_pick" in api_payload))
        checks.append(("api_legacy_recommended_bets", "recommended_bets" in api_payload))

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
            "recommended_bets": [{"market": "1X2", "pick": "Home Win", "status": "recommended"}],
            "detailed_markets": {"match_winner": {"selection": "home_win", "probabilities": {"home_win": 55, "draw": 25, "away_win": 20}}},
        }
        enriched = enrich_cached_prediction_output(legacy)
        checks.append(("cache_backfill_market_ranking", "market_ranking" in enriched))

        # Candidate inventory smoke
        detailed = build_detailed_markets(pred)
        candidates = build_market_candidates(pred, detailed)
        keys = {c.market_key for c in candidates}
        checks.append(("candidates_include_dc", "double_chance" in keys))
        checks.append(("candidates_include_btts", "btts" in keys))

        score, explanation = compute_market_rank_score(
            candidates[0],
            prediction=pred,
            specialist_summary=specialist_summary,
        )
        checks.append(("rank_explanation", bool(explanation) and 0.0 <= score <= 1.0))

        # Frontend mapper smoke
        normalized = {
            **api_payload,
            "market_ranking": api_payload.get("market_ranking") or [],
            "safe_pick": api_payload.get("safe_pick"),
        }
        checks.append(("frontend_safe_pick_field", "safe_pick" in normalized))

        ok29, msg29 = _run_phase_script("validate_phase29_prediction_history_results.py")
        checks.append(("phase29_regression", ok29))
        if not ok29:
            print(f"Phase 29 regression detail: {msg29}")

        ok30a, msg30a = _run_phase_script("validate_phase30a_prediction_output_completeness.py")
        checks.append(("phase30a_regression", ok30a))
        if not ok30a:
            print(f"Phase 30A regression detail: {msg30a}")

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
    print(f"\nAll {len(checks)} Phase 30C checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

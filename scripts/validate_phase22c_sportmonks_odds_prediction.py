"""Phase 22C — Sportmonks odds + prediction benchmark validation (offline)."""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    from worldcup_predictor.agents.specialists.helpers import make_signal
    from worldcup_predictor.agents.specialists.sportmonks_prediction_agent import SportmonksPredictionAgent
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport, TeamIntelligence
    from worldcup_predictor.intelligence.sportmonks_odds_prediction_engine import (
        build_sportmonks_prediction_intelligence,
        normalize_sportmonks_odds,
        normalize_sportmonks_predictions,
        parse_odds_predictions_from_fixture,
    )
    from worldcup_predictor.providers.sportmonks_consumption import (
        SPORTMONKS_ODDS_PREDICTION_KEY,
        apply_sportmonks_consumption,
    )
    from worldcup_predictor.providers.sportmonks_enrichment import (
        PHASE_22C_REQUIRED_INCLUDES,
        WORLD_CUP_FIXTURE_INCLUDES,
    )

    checks: list[tuple[str, bool]] = []

    checks.append(("includes_odds", "odds" in WORLD_CUP_FIXTURE_INCLUDES))
    checks.append(("includes_predictions", "predictions" in WORLD_CUP_FIXTURE_INCLUDES))
    checks.append(("includes_metadata", "metadata" in WORLD_CUP_FIXTURE_INCLUDES))
    checks.append(("phase22c_required", PHASE_22C_REQUIRED_INCLUDES == ("odds", "predictions", "metadata")))

    sample_odds = [
        {"bookmaker_id": 2, "market_id": 1, "label": "Home", "value": "2.00"},
        {"bookmaker_id": 2, "market_id": 1, "label": "Draw", "value": "3.40"},
        {"bookmaker_id": 2, "market_id": 1, "label": "Away", "value": "4.00"},
    ]
    odds_norm = normalize_sportmonks_odds(sample_odds)
    checks.append(("odds_available", odds_norm["available"] is True))
    checks.append(("odds_implied_sum", abs(sum(odds_norm["implied_probabilities"].values()) - 1.0) < 0.01))

    sample_pred = [{"predictions": {"home": 45, "draw": 28, "away": 27, "goals_home": 1.4, "goals_away": 1.1}}]
    pred_norm = normalize_sportmonks_predictions(sample_pred, {"predictions": True})
    checks.append(("pred_available", pred_norm["available"] is True))
    checks.append(("pred_expected_score", pred_norm["expected_score"] == "1.4-1.1"))

    fixture = {
        "id": 88002,
        "league_id": 732,
        "odds": sample_odds,
        "predictions": sample_pred,
        "metadata": {"predictions": True},
        "participants": [],
    }
    block = parse_odds_predictions_from_fixture(fixture)
    checks.append(("parse_block", block["raw_odds_present"] and block["raw_predictions_present"]))

    mc_signal = make_signal(
        "market_consensus_agent",
        "market_consensus",
        "available",
        {
            "home_implied_probability": 0.50,
            "draw_implied_probability": 0.28,
            "away_implied_probability": 0.22,
            "market_favorite": "home_win",
        },
    )
    intel = build_sportmonks_prediction_intelligence(
        odds_prediction_block=block,
        specialist_signals={"market_consensus_agent": mc_signal},
    )
    checks.append(("intel_has_probs", intel.sportmonks_home_probability is not None))
    checks.append(("intel_conflict_level", intel.conflict_level in {"low", "medium", "high"}))
    checks.append(("intel_recommendation", intel.recommendation in {"support_internal", "caution", "no_bet_review"}))
    checks.append(("intel_disagreement", intel.disagreement_vs_internal is not None))

    report = MatchIntelligenceReport(
        fixture_id=1489388,
        fixture=None,
        home_team=TeamIntelligence(team_name="Mexico", team_id=10),
        away_team=TeamIntelligence(team_name="South Korea", team_id=11),
        provider_metadata={"sportmonks_fixture": fixture},
    )
    consumed = apply_sportmonks_consumption(report)
    sm_block = (consumed.supplemental_sources or {}).get(SPORTMONKS_ODDS_PREDICTION_KEY) or {}
    checks.append(("consumption_odds_prediction", sm_block.get("raw_odds_present") is True))

    class _Ctx:
        shared = {
            "intelligence_reports": {1489388: consumed},
            "specialist_signals": {"market_consensus_agent": mc_signal},
        }

    agent = SportmonksPredictionAgent(_Ctx())
    result = agent.run(fixture_id=1489388)
    checks.append(("agent_success", result.success))
    sig = _Ctx.shared["specialist_signals"]["sportmonks_prediction_agent"]
    checks.append(("agent_outputs", sig.signals.get("sportmonks_home_probability") is not None))
    checks.append(("agent_conflict", sig.signals.get("conflict_level") in {"low", "medium", "high"}))
    checks.append(
        ("agent_no_override_disclaimer",
         "never overrides" in str(sig.signals.get("disclaimer", "")).lower()),
    )

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

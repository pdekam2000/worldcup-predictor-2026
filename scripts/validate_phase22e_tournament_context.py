"""Phase 22E — Tournament context intelligence validation (offline)."""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    from worldcup_predictor.agents.specialists.helpers import make_signal
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
    from worldcup_predictor.agents.specialists.tournament_context_agent import TournamentContextAgent
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport, TeamIntelligence
    from worldcup_predictor.intelligence.sportmonks_standings_service import (
        STANDINGS_INCLUDES,
        normalize_sportmonks_standings_payload,
    )
    from worldcup_predictor.intelligence.tournament_context_engine import (
        SPORTMONKS_TOURNAMENT_STANDINGS_KEY,
        build_tournament_context_intelligence,
    )
    from worldcup_predictor.providers.enrichment_service import EnrichmentService
    from worldcup_predictor.quota.cache_policy import DAILY_TTL_SECONDS

    checks: list[tuple[str, bool]] = []

    checks.append(("standings_includes_form", "form" in STANDINGS_INCLUDES))
    checks.append(("standings_includes_group", "group" in STANDINGS_INCLUDES))
    checks.append(("daily_ttl_positive", DAILY_TTL_SECONDS >= 86400))

    sample_payload = {
        "data": [
            {
                "position": 2,
                "points": 4,
                "participant": {"name": "Mexico", "id": 10},
                "group": {"name": "Group A"},
                "form": "WDL",
                "details": [{"type": {"name": "Goal Difference"}, "value": 2}],
            },
            {
                "position": 3,
                "points": 3,
                "participant": {"name": "South Korea", "id": 11},
                "group": {"name": "Group A"},
                "form": "LWD",
                "details": [{"type": {"name": "Goal Difference"}, "value": -1}],
            },
        ]
    }
    normalized = normalize_sportmonks_standings_payload(sample_payload)
    checks.append(("normalize_available", normalized["available"] is True))
    checks.append(("normalize_team_count", normalized["team_count"] == 2))
    checks.append(("normalize_mexico_gd", normalized["teams"]["mexico"]["goal_difference"] == 2))

    standings_context = {
        "available": True,
        "groups": [
            {
                "standings": [
                    [
                        {
                            "rank": 2,
                            "points": 4,
                            "goalsDiff": 2,
                            "form": "WDL",
                            "team": {"name": "Mexico", "id": 10},
                        },
                        {
                            "rank": 3,
                            "points": 3,
                            "goalsDiff": -1,
                            "form": "LWD",
                            "team": {"name": "South Korea", "id": 11},
                        },
                    ]
                ]
            }
        ],
    }

    report = MatchIntelligenceReport(
        fixture_id=1489388,
        fixture=None,
        home_team=TeamIntelligence(team_name="Mexico", team_id=10, form=["W", "D", "L"]),
        away_team=TeamIntelligence(team_name="South Korea", team_id=11, form=["L", "W", "D"]),
        standings_context=standings_context,
        group_context={
            "available": True,
            "group": "Group A",
            "home": {"team": "Mexico", "rank": 2, "points": 4, "goal_diff": 2},
            "away": {"team": "South Korea", "rank": 3, "points": 3, "goal_diff": -1},
        },
    )

    mot_sig = make_signal(
        "motivation_psychology_agent",
        "motivation",
        "available",
        {
            "motivation_score_home": 62.0,
            "motivation_score_away": 58.0,
            "home_qualification_status": "must_win",
            "away_qualification_status": "goal_difference_critical",
        },
    )

    intel = build_tournament_context_intelligence(
        report,
        tournament_context={
            "round": "Group Stage - 3",
            "home_qualification_status": "must_win",
            "away_qualification_status": "goal_difference_critical",
        },
        sportmonks_standings=normalized,
        specialist_signals={"motivation_psychology_agent": mot_sig},
    )
    checks.append(("intel_home_rank", intel.group_position_home == 2))
    checks.append(("intel_away_rank", intel.group_position_away == 3))
    checks.append(("intel_must_win", intel.must_win_flag is True))
    checks.append(("intel_pressure", intel.pressure_rating >= 0))
    checks.append(("intel_rotation", intel.rotation_risk in {"Low", "Medium", "High"}))
    checks.append(("intel_advanced_conservatism", intel.expected_conservatism in {"low", "balanced", "high"}))
    checks.append(("intel_advanced_aggression", intel.expected_aggression in {"low", "medium", "high", "balanced"}))
    checks.append(("intel_comparison_agreement", 0 <= intel.agreement_score <= 100))
    checks.append(("intel_comparison_disagreement", 0 <= intel.disagreement_score <= 1))
    checks.append(("intel_sources", "api_football_standings" in intel.data_sources))
    checks.append(("intel_sportmonks_source", "sportmonks_standings" in intel.data_sources))
    checks.append(("intel_strength", intel.group_context_strength > 0))

    class _Overview:
        def context_for_fixture(self, _fid: int) -> dict[str, object]:
            return {
                "round": "Group Stage - 3",
                "home_qualification_status": "must_win",
                "away_qualification_status": "goal_difference_critical",
            }

    class _Ctx:
        shared = {
            "intelligence_reports": {1489388: report},
            "specialist_signals": {"motivation_psychology_agent": mot_sig},
            "tournament_context": _Overview(),
        }

    agent = TournamentContextAgent(_Ctx())
    result = agent.run(fixture_id=1489388)
    checks.append(("agent_success", result.success))
    sig = _Ctx.shared["specialist_signals"]["tournament_context_agent"]
    checks.append(("agent_must_win_flag", sig.signals.get("must_win_flag") is True))
    checks.append(("agent_agreement_score", "agreement_score" in sig.signals))
    checks.append(("agent_context_supports", "context_supports_internal" in sig.signals))
    checks.append(("agent_disclaimer", "does not override" in str(sig.signals.get("disclaimer", "")).lower()))

    orch_agents = [cls.__name__ for cls in SpecialistOrchestrator.AGENT_CLASSES]
    checks.append(("orchestrator_has_agent", "TournamentContextAgent" in orch_agents))
    mot_idx = orch_agents.index("MotivationPsychologyAgent")
    tour_idx = orch_agents.index("TournamentIntelligenceAgent")
    tcx_idx = orch_agents.index("TournamentContextAgent")
    master_idx = orch_agents.index("MasterAnalysisAgent")
    checks.append(("orchestrator_order", mot_idx < tour_idx < tcx_idx < master_idx))

    checks.append(("supplemental_key", SPORTMONKS_TOURNAMENT_STANDINGS_KEY == "sportmonks_tournament_standings"))
    checks.append(("enrichment_has_standings_method", hasattr(EnrichmentService, "_maybe_enrich_sportmonks_standings")))

    failed = [name for name, ok in checks if not ok]
    passed = len(checks) - len(failed)
    print(f"Phase 22E tournament context: {passed}/{len(checks)} passed")
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print("Failed:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

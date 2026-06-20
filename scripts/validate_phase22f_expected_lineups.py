"""Phase 22F — Expected lineup intelligence validation (offline)."""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    from worldcup_predictor.agents.specialists.expected_lineup_agent import ExpectedLineupAgent
    from worldcup_predictor.agents.specialists.helpers import make_signal
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
    from worldcup_predictor.domain.intelligence import InjuryReport, MatchIntelligenceReport, TeamIntelligence
    from worldcup_predictor.lineups.expected_lineup_intelligence_engine import (
        build_expected_lineup_intelligence,
        reconcile_expected_with_prior,
    )
    from worldcup_predictor.lineups.expected_lineup_store import ExpectedLineupAccuracyStore
    from worldcup_predictor.quota.cache_policy import LINEUPS_TTL_NEAR_SECONDS, should_fetch_lineups

    checks: list[tuple[str, bool]] = []

    checks.append(("lineups_near_ttl", LINEUPS_TTL_NEAR_SECONDS == 900))
    checks.append(("should_fetch_import", callable(should_fetch_lineups)))

    lineups_items = [
        {
            "team": {"id": 10, "name": "Mexico"},
            "formation": "4-3-3",
            "startXI": [
                {"player": {"name": "GK One", "pos": "G", "number": 1}},
                {"player": {"name": "Striker A", "pos": "F", "number": 9}},
                {"player": {"name": "Mid B", "pos": "M", "number": 8}},
            ],
        },
        {
            "team": {"id": 11, "name": "South Korea"},
            "formation": "4-4-2",
            "startXI": [
                {"player": {"name": "GK Two", "pos": "G", "number": 1}},
                {"player": {"name": "Striker C", "pos": "F", "number": 10}},
            ],
        },
    ]

    report = MatchIntelligenceReport(
        fixture_id=1489388,
        fixture=None,
        home_team=TeamIntelligence(
            team_name="Mexico",
            team_id=10,
            injuries=InjuryReport(
                team_name="Mexico",
                team_id=10,
                players=[{"player": {"name": "Striker A", "pos": "F"}}],
                available=True,
            ),
        ),
        away_team=TeamIntelligence(team_name="South Korea", team_id=11),
        lineups={"items": lineups_items, "available": True, "source": "api_football"},
    )

    lineup_v2 = make_signal(
        "lineup_intelligence_agent",
        "lineup_intelligence_v2",
        "partial",
        {
            "home": {"lineup_strength": 62.0, "confidence": 55.0, "risk_flags": []},
            "away": {"lineup_strength": 58.0, "confidence": 52.0, "risk_flags": []},
        },
    )

    intel = build_expected_lineup_intelligence(
        report,
        api_client=None,
        specialist_signals={"lineup_intelligence_agent": lineup_v2},
    )
    checks.append(("intel_confidence", intel.lineup_confidence >= 0))
    checks.append(("intel_strength_delta", isinstance(intel.lineup_strength_delta, float)))
    checks.append(("intel_gk_home", intel.expected_goalkeeper_home == "GK One"))
    checks.append(("intel_missing_attackers", intel.missing_attackers >= 0))
    checks.append(("intel_rotation_risk", intel.rotation_risk in {"Low", "Medium", "High"}))
    checks.append(("intel_formation", intel.expected_formation is not None))
    checks.append(("intel_xi_quality", intel.expected_xi_quality > 0))
    checks.append(("intel_supports_internal", isinstance(intel.lineup_supports_internal, bool)))
    checks.append(("intel_star_absence", intel.star_player_absence_score >= 0))
    checks.append(("intel_chemistry", intel.chemistry_risk in {"low", "medium", "high"}))
    checks.append(("intel_continuity", 0 <= intel.continuity_score <= 100))
    checks.append(("intel_bench", 0 <= intel.bench_strength_score <= 100))
    checks.append(("intel_late_news", intel.late_news_risk in {"low", "medium", "high"}))
    checks.append(("intel_sources", "lineups_api_football" in intel.data_sources))

    prior = {
        "expected_snapshot": {
            "home": {
                "starters": [
                    {"name": "GK One", "pos": "G"},
                    {"name": "Striker A", "pos": "F"},
                    {"name": "Mid B", "pos": "M"},
                ],
                "formation": "4-3-3",
                "available": True,
            },
            "away": {"starters": [], "available": False},
        }
    }

    class _Fix:
        status = "1H"
        kickoff_utc = None
        home_team = "Mexico"
        away_team = "South Korea"

    report_live = MatchIntelligenceReport(
        fixture_id=1489388,
        fixture=_Fix(),
        home_team=TeamIntelligence(team_name="Mexico", team_id=10),
        away_team=TeamIntelligence(team_name="South Korea", team_id=11),
        lineups={"items": lineups_items, "available": True, "source": "api_football"},
    )
    live_intel = build_expected_lineup_intelligence(report_live, specialist_signals={"lineup_intelligence_agent": lineup_v2})
    reconciled = reconcile_expected_with_prior(live_intel, prior)
    checks.append(("live_confirmed", reconciled.confirmed_available is True))
    checks.append(("reconcile_comparison", reconciled.comparison_available is True))
    checks.append(("reconcile_overlap", reconciled.player_overlap_pct is not None))

    store = ExpectedLineupAccuracyStore(path=Path("data/shadow/_phase22f_test_accuracy.jsonl"))
    store.append(
        __import__(
            "worldcup_predictor.lineups.expected_lineup_store",
            fromlist=["ExpectedLineupAccuracyRecord"],
        ).ExpectedLineupAccuracyRecord(
            fixture_id=1489388,
            prediction_timestamp="2026-06-01T12:00:00",
            expected_lineup_snapshot=prior["expected_snapshot"],
            confirmed_lineup_snapshot=reconciled.confirmed_snapshot,
            comparison_available=True,
            player_overlap_pct=reconciled.player_overlap_pct,
        )
    )
    checks.append(("store_append", store.path.exists()))
    checks.append(("store_stats", store.summary_stats()["count"] >= 1))

    class _Ctx:
        settings = __import__("worldcup_predictor.config.settings", fromlist=["get_settings"]).get_settings()
        shared = {
            "intelligence_reports": {1489388: report},
            "specialist_signals": {"lineup_intelligence_agent": lineup_v2},
        }

    agent = ExpectedLineupAgent(_Ctx())
    result = agent.run(fixture_id=1489388)
    checks.append(("agent_success", result.success))
    sig = _Ctx.shared["specialist_signals"]["expected_lineup_agent"]
    checks.append(("agent_lineup_confidence", "lineup_confidence" in sig.signals))
    checks.append(("agent_supports_flag", "lineup_supports_internal" in sig.signals))
    checks.append(("agent_disclaimer", "does not override" in str(sig.signals.get("disclaimer", "")).lower()))

    orch = [cls.__name__ for cls in SpecialistOrchestrator.AGENT_CLASSES]
    checks.append(("orchestrator_has_agent", "ExpectedLineupAgent" in orch))
    li_idx = orch.index("LineupIntelligenceAgent")
    exp_idx = orch.index("ExpectedLineupAgent")
    inj_idx = orch.index("InjurySuspensionAgent")
    checks.append(("orchestrator_order", li_idx < exp_idx < inj_idx))

    failed = [name for name, ok in checks if not ok]
    passed = len(checks) - len(failed)
    print(f"Phase 22F expected lineups: {passed}/{len(checks)} passed")
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print("Failed:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

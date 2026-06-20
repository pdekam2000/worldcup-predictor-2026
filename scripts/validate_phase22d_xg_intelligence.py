"""Phase 22D — Sportmonks xG intelligence validation (offline)."""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    from worldcup_predictor.agents.specialists.helpers import make_signal
    from worldcup_predictor.agents.specialists.xg_intelligence_agent import XGIntelligenceAgent
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport, TeamIntelligence
    from worldcup_predictor.intelligence.sportmonks_xg_intelligence_engine import (
        build_sportmonks_xg_intelligence,
        parse_sportmonks_xg_from_fixture,
        verify_xg_plan_access,
    )
    from worldcup_predictor.providers.sportmonks_consumption import (
        SPORTMONKS_XG_INTELLIGENCE_KEY,
        apply_sportmonks_consumption,
    )
    from worldcup_predictor.providers.sportmonks_enrichment import (
        CACHE_REQUIRED_INCLUDES,
        WORLD_CUP_FIXTURE_INCLUDES,
    )

    checks: list[tuple[str, bool]] = []

    checks.append(("includes_xg_fixture", "xGFixture" in WORLD_CUP_FIXTURE_INCLUDES))
    checks.append(("cache_requires_xg", "xGFixture" in CACHE_REQUIRED_INCLUDES))

    sample_fixture = {
        "id": 88003,
        "league_id": 732,
        "xGFixture": {
            "expected": [
                {
                    "fixture_id": 88003,
                    "type_id": 5304,
                    "participant_id": 10,
                    "location": "home",
                    "data": {"value": 1.65},
                },
                {
                    "fixture_id": 88003,
                    "type_id": 5304,
                    "participant_id": 11,
                    "location": "away",
                    "data": {"value": 0.92},
                },
                {
                    "fixture_id": 88003,
                    "type_id": 5305,
                    "participant_id": 10,
                    "location": "home",
                    "data": {"value": 1.10},
                },
            ]
        },
        "participants": [
            {"id": 10, "meta": {"location": "home"}},
            {"id": 11, "meta": {"location": "away"}},
        ],
    }

    plan = verify_xg_plan_access(sample_fixture)
    checks.append(("plan_support_full", plan["plan_support"] == "full"))
    checks.append(("plan_expected_rows", plan["expected_row_count"] == 3))

    xg_block = parse_sportmonks_xg_from_fixture(sample_fixture)
    checks.append(("parse_available", xg_block["available"] is True))
    checks.append(("parse_source_xgfixture", xg_block["source"] == "xGFixture"))
    checks.append(("parse_home_xg", xg_block["home_xg"] == 1.65))
    checks.append(("parse_away_xg", xg_block["away_xg"] == 0.92))

    empty_plan = verify_xg_plan_access({"id": 1, "xGFixture": {"expected": []}})
    checks.append(("plan_partial_empty", empty_plan["plan_support"] == "partial"))

    report = MatchIntelligenceReport(
        fixture_id=1489388,
        fixture=None,
        home_team=TeamIntelligence(
            team_name="Mexico",
            team_id=10,
            statistics={
                "goals": {
                    "for": {"expected": {"average": 1.5}},
                    "against": {"expected": {"average": 1.0}},
                }
            },
        ),
        away_team=TeamIntelligence(
            team_name="South Korea",
            team_id=11,
            statistics={
                "goals": {
                    "for": {"expected": {"average": 1.1}},
                    "against": {"expected": {"average": 1.3}},
                }
            },
        ),
        provider_metadata={"sportmonks_fixture": sample_fixture},
    )
    consumed = apply_sportmonks_consumption(report)
    sm_xg = (consumed.supplemental_sources or {}).get(SPORTMONKS_XG_INTELLIGENCE_KEY) or {}
    checks.append(("consumption_xg_key", sm_xg.get("available") is True))

    xg_v2 = make_signal(
        "xg_chance_quality_intelligence_agent",
        "xg_chance_quality_intelligence_v2",
        "available",
        {
            "home": {"xg_per_match": 1.55},
            "away": {"xg_per_match": 0.88},
        },
    )
    intel = build_sportmonks_xg_intelligence(
        xg_block=sm_xg,
        report=consumed,
        xg_chance_quality_signal=xg_v2.signals,
    )
    checks.append(("intel_xg_total", intel.xg_total == 2.57))
    checks.append(("intel_xg_diff", intel.xg_difference == 0.73))
    checks.append(("intel_strength", intel.xg_strength_rating is not None))
    checks.append(("intel_comparison", intel.comparison_available is True))
    checks.append(("intel_agreement", 0 <= intel.agreement_score <= 100))

    class _Ctx:
        shared = {
            "intelligence_reports": {1489388: consumed},
            "specialist_signals": {"xg_chance_quality_intelligence_agent": xg_v2},
        }

    agent = XGIntelligenceAgent(_Ctx())
    result = agent.run(fixture_id=1489388)
    checks.append(("agent_success", result.success))
    sig = _Ctx.shared["specialist_signals"]["xg_intelligence_agent"]
    checks.append(("agent_home_xg", sig.signals.get("home_xg") == 1.65))
    checks.append(("agent_supports_flag", "xg_supports_internal" in sig.signals))
    checks.append(("agent_disclaimer", "does not override" in str(sig.signals.get("disclaimer", "")).lower()))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

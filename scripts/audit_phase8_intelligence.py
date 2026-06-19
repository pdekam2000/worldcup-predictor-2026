"""Run intelligence + key specialists for fixture — measures Sportmonks consumption impact."""

from __future__ import annotations

import sys
from pathlib import Path

import runpy

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

FIXTURE_ID = 1489388


def _run_specialists(context, fixture_id: int) -> dict[str, str]:
    from worldcup_predictor.agents.specialists.agents import (
        InjurySuspensionAgent,
        LineupAgent,
        PlayerQualityAgent,
        TacticsAgent,
    )
    from worldcup_predictor.agents.specialists.injury_suspension_intelligence_agent import (
        InjurySuspensionIntelligenceAgent,
    )
    from worldcup_predictor.agents.specialists.lineup_intelligence_agent import LineupIntelligenceAgent
    from worldcup_predictor.agents.specialists.xg_chance_quality_intelligence_agent import (
        XGChanceQualityIntelligenceAgent,
    )

    agents = [
        InjurySuspensionAgent(context),
        InjurySuspensionIntelligenceAgent(context),
        LineupAgent(context),
        LineupIntelligenceAgent(context),
        PlayerQualityAgent(context),
        TacticsAgent(context),
        XGChanceQualityIntelligenceAgent(context),
    ]
    out: dict[str, str] = {}
    for agent in agents:
        result = agent.run(fixture_id=fixture_id)
        signal = (context.shared.get("specialist_signals") or {}).get(agent.name)
        status = getattr(signal, "status", None) if signal else None
        out[agent.name] = str(status or ("ok" if result.success else "fail"))
    return out


def main() -> int:
    from dataclasses import replace

    from worldcup_predictor.agents.base import AgentContext
    from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
    from worldcup_predictor.config.settings import Settings, get_settings
    from worldcup_predictor.providers.sportmonks_consumption import apply_sportmonks_consumption

    fixture_id = FIXTURE_ID
    for arg in sys.argv[1:]:
        if arg.isdigit():
            fixture_id = int(arg)

    settings = get_settings()
    print(f"fixture_id: {fixture_id}")
    print(f"sportmonks_configured: {settings.sportmonks_configured}")

    ctx = AgentContext(settings=settings, competition_key="world_cup_2026", locale="en")
    ctx.shared["smart_prediction_fetch"] = True
    collector = DataCollectorAgent(ctx)
    result = collector.run(fixture_id=fixture_id)
    if not result.success:
        print(f"collector failed: {result.message}")
        return 1

    report = (ctx.shared.get("intelligence_reports") or {}).get(fixture_id)
    if report is None:
        print("no intelligence report")
        return 1

    sm_raw = (report.provider_metadata or {}).get("sportmonks_fixture")
    print(f"sportmonks_provider_metadata_present: {bool(sm_raw)}")
    supplemental_before = (report.supplemental_sources or {}).get("sportmonks")
    print(f"sportmonks_supplemental_before: {bool(supplemental_before)}")

    # BEFORE: strip sportmonks consumption effects for comparison
    ctx_before = AgentContext(settings=settings, competition_key="world_cup_2026", locale="en")
    stripped = report
    if supplemental_before:
        stripped = replace(report, supplemental_sources={
            k: v for k, v in (report.supplemental_sources or {}).items() if k != "sportmonks"
        })
    ctx_before.shared["intelligence_reports"] = {fixture_id: stripped}
    before = _run_specialists(ctx_before, fixture_id)

    ctx_after = AgentContext(settings=settings, competition_key="world_cup_2026", locale="en")
    consumed = apply_sportmonks_consumption(report)
    ctx_after.shared["intelligence_reports"] = {fixture_id: consumed}
    after = _run_specialists(ctx_after, fixture_id)

    print("\nSPECIALIST STATUS (before -> after):")
    for name in sorted(set(before) | set(after)):
        print(f"  {name}: {before.get(name, '—')} -> {after.get(name, '—')}")

    sm = (consumed.supplemental_sources or {}).get("sportmonks") or {}
    print(f"\nsportmonks_fields: {(sm.get('field_map') or {}).get('fields_present')}")
    print(f"sportmonks_home_injuries: {len(sm.get('home_injuries') or [])}")
    print(f"sportmonks_lineups: {len(sm.get('lineups_api') or [])}")
    print(f"sportmonks_xg: {sm.get('xg')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
import json
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.agents.base import AgentContext
from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
from worldcup_predictor.intelligence.national_team.orchestrator import build_national_team_intelligence
from worldcup_predictor.intelligence.national_team.data_resolver import resolve_match_history
from worldcup_predictor.intelligence.national_team.history_filters import count_history_violations, history_filter_context

FIDS = {
    1539007: "Netherlands vs Sweden",
    1489393: "Germany vs Ivory Coast",
    1489397: "Spain vs Saudi Arabia",
}

get_settings.cache_clear()
s = get_settings()
rows = []
total_future = total_circular = 0
for fid, label in FIDS.items():
    ctx = AgentContext(settings=s, competition_key="world_cup_2026", locale="en")
    ctx.shared["smart_prediction_fetch"] = True
    DataCollectorAgent(ctx).run(fixture_id=fid)
    SpecialistOrchestrator(ctx).run(fixture_id=fid)
    report = (ctx.shared.get("intelligence_reports") or {}).get(fid)
    block = build_national_team_intelligence(
        report,
        specialist_report=(ctx.shared.get("specialist_reports") or {}).get(fid),
    ) if report else {}
    hist = resolve_match_history(report) if report else {}
    kick, ex = history_filter_context(report) if report else (None, fid)
    for key in ("home_recent_fixtures", "away_recent_fixtures", "h2h_meetings"):
        v = count_history_violations(hist.get(key), before_kickoff=kick, exclude_fixture_id=ex)
        total_future += v["future_leaks"]
        total_circular += v["circular_refs"]
    rows.append({
        "fixture_id": fid,
        "label": label,
        "national_form_score": block.get("national_form_score"),
        "national_h2h_score": block.get("national_h2h_score"),
        "injury_impact_score": block.get("injury_impact_score"),
        "consensus_strength_score": block.get("consensus_strength_score"),
        "version": block.get("version"),
        "data_coverage": block.get("data_coverage"),
    })

print(json.dumps({
    "national_scores": rows,
    "leakage_audit": {"future_leaks": total_future, "circular_refs": total_circular},
    "nat_enabled": s.national_team_intelligence_enabled,
}, indent=2))

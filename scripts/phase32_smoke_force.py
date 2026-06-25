#!/usr/bin/env python3
import json
import time
import urllib.request

FIDS = [1539007, 1489393, 1489397]  # NL-SWE, GER-IVC, ESP-KSA


def predict(fid):
    req = urllib.request.Request(
        f"http://127.0.0.1:8000/api/predict/{fid}?force_refresh=true", method="POST"
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def nat_block(fid):
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.agents.base import AgentContext
    from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
    from worldcup_predictor.intelligence.national_team.orchestrator import build_national_team_intelligence

    get_settings.cache_clear()
    ctx = AgentContext(settings=get_settings(), competition_key="world_cup_2026", locale="en")
    ctx.shared["smart_prediction_fetch"] = True
    DataCollectorAgent(ctx).run(fixture_id=fid)
    SpecialistOrchestrator(ctx).run(fixture_id=fid)
    report = (ctx.shared.get("intelligence_reports") or {}).get(fid)
    if not report:
        return {}
    return build_national_team_intelligence(
        report, specialist_report=(ctx.shared.get("specialist_reports") or {}).get(fid)
    )


rows = []
for i, fid in enumerate(FIDS):
    if i:
        time.sleep(15)
    d = predict(fid)
    block = nat_block(fid)
    rows.append({
        "fixture_id": fid,
        "match": f"{d.get('home_team')} vs {d.get('away_team')}",
        "confidence": d.get("confidence"),
        "no_bet": d.get("no_bet"),
        "safe_pick": d.get("safe_pick"),
        "value_pick": d.get("value_pick"),
        "aggressive_pick": d.get("aggressive_pick"),
        "cache_source": d.get("cache_source"),
        "data_quality": d.get("data_quality"),
        "national_form_score": block.get("national_form_score"),
        "national_h2h_score": block.get("national_h2h_score"),
        "injury_impact_score": block.get("injury_impact_score"),
        "consensus_strength_score": block.get("consensus_strength_score"),
        "version": block.get("version"),
    })

print(json.dumps(rows, indent=2))

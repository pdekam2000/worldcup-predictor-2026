#!/usr/bin/env python3
"""Post-deploy smoke with force_refresh=true."""
import json
import urllib.parse
import urllib.request

def predict(fid, force=True):
    q = "?force_refresh=true" if force else ""
    req = urllib.request.Request(f"http://127.0.0.1:8000/api/predict/{fid}{q}", method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())

def nat_scores(fid):
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.agents.base import AgentContext
    from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
    from worldcup_predictor.intelligence.national_team.orchestrator import build_national_team_intelligence
    get_settings.cache_clear()
    s = get_settings()
    ctx = AgentContext(settings=s, competition_key="world_cup_2026", locale="en")
    ctx.shared["smart_prediction_fetch"] = True
    DataCollectorAgent(ctx).run(fixture_id=fid)
    SpecialistOrchestrator(ctx).run(fixture_id=fid)
    report = (ctx.shared.get("intelligence_reports") or {}).get(fid)
    if not report:
        return {}
    block = build_national_team_intelligence(
        report,
        specialist_report=(ctx.shared.get("specialist_reports") or {}).get(fid),
    )
    return {
        "national_form_score": block.get("national_form_score"),
        "national_h2h_score": block.get("national_h2h_score"),
        "injury_impact_score": block.get("injury_impact_score"),
        "consensus_strength_score": block.get("consensus_strength_score"),
        "version": block.get("version"),
        "data_coverage": block.get("data_coverage"),
    }

fixtures = [
    (1539007, "Netherlands vs Sweden"),
    (1489393, "Germany vs Ivory Coast"),
]
try:
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    for r in FootballIntelligenceRepository().list_upcoming_fixtures("world_cup_2026", season=2026, limit=40):
        m = f"{r.get('home_team_name','')} vs {r.get('away_team_name','')}"
        if "France" in m:
            fixtures.append((int(r["fixture_id"]), m))
            break
except Exception:
    pass

results = []
for fid, label in fixtures:
    d = predict(fid)
    nat = nat_scores(fid)
    results.append({
        "fixture_id": fid,
        "label": label,
        "confidence": d.get("confidence"),
        "no_bet": d.get("no_bet"),
        "safe_pick": d.get("safe_pick"),
        "value_pick": d.get("value_pick"),
        "aggressive_pick": d.get("aggressive_pick"),
        "cache_source": d.get("cache_source"),
        "data_quality": d.get("data_quality"),
        "national_team_intelligence": nat,
    })

for r in FootballIntelligenceRepository().list_upcoming_fixtures("world_cup_2026", season=2026, limit=30):
    fid = int(r["fixture_id"])
    if any(x["fixture_id"] == fid for x in results):
        continue
    d = predict(fid)
    if not d.get("no_bet", True):
        nat = nat_scores(fid)
        results.append({
            "fixture_id": fid,
            "label": f"{r.get('home_team_name')} vs {r.get('away_team_name')} (no_bet=false)",
            "confidence": d.get("confidence"),
            "no_bet": d.get("no_bet"),
            "safe_pick": d.get("safe_pick"),
            "value_pick": d.get("value_pick"),
            "aggressive_pick": d.get("aggressive_pick"),
            "national_team_intelligence": nat,
        })
        break

print(json.dumps(results, indent=2))

#!/usr/bin/env python3
import json
import sqlite3
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline

get_settings.cache_clear()
s = get_settings()
print("nat_enabled", s.national_team_intelligence_enabled)
print("sqlite", s.sqlite_path)

conn = sqlite3.connect(s.sqlite_path or "data/football_intelligence.db")
conn.row_factory = sqlite3.Row
for table in ("national_team_form_cache", "national_team_h2h_cache", "fixture_team_resolution"):
    try:
        n = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
        print(f"{table}_count", n)
    except Exception as e:
        print(f"{table}_error", e)

pipe = PredictPipeline(settings=s)
result = pipe.run(fixture_id=1539007)
pred = result.prediction
print("confidence", pred.confidence_score, "no_bet", pred.no_bet_flag)

# intelligence from shared via re-run collector path
from worldcup_predictor.agents.base import AgentContext
from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
ctx = AgentContext(settings=s, competition_key="world_cup_2026", locale="en")
ctx.shared["smart_prediction_fetch"] = True
col = DataCollectorAgent(ctx).run(fixture_id=1539007)
report = (ctx.shared.get("intelligence_reports") or {}).get(1539007)
if report:
    from worldcup_predictor.intelligence.national_team.orchestrator import build_national_team_intelligence
    block = build_national_team_intelligence(report)
    print("national_block", json.dumps({k: block.get(k) for k in [
        "version", "national_form_score", "national_h2h_score", "injury_impact_score",
        "consensus_strength_score", "data_coverage", "applicable"
    ]}, default=str))
else:
    print("no_intelligence_report")

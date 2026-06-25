#!/usr/bin/env bash
set -euo pipefail
cd /opt/worldcup-predictor
OUT="${1:-/tmp/phase32_smoke_force.json}"
FIDS="1539007 1489393 1489397"
results="[]"
for fid in $FIDS; do
  sleep 12
  raw=$(curl -sf -X POST "http://127.0.0.1:8000/api/predict/${fid}?force_refresh=true")
  PYTHONPATH=/opt/worldcup-predictor NATIONAL_TEAM_INTELLIGENCE_ENABLED=true .venv/bin/python - <<PY
import json, os
raw = '''${raw}'''
d = json.loads(raw)
fid = int(d["fixture_id"])
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
block = build_national_team_intelligence(report, specialist_report=(ctx.shared.get("specialist_reports") or {}).get(fid)) if report else {}
row = {
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
}
print(json.dumps(row))
PY
done > /tmp/_rows.ndjson
python3 - <<'PY'
import json
from pathlib import Path
rows=[json.loads(l) for l in Path("/tmp/_rows.ndjson").read_text().splitlines() if l.strip()]
Path("$OUT").write_text(json.dumps(rows, indent=2))
print(json.dumps(rows, indent=2))
PY

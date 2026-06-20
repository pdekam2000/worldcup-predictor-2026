#!/usr/bin/env bash
# Specialist agent audit — read-only, no secrets printed.
set -uo pipefail
cd /opt/worldcup-predictor
set -a && source .env.production && set +a
export PYTHONPATH=/opt/worldcup-predictor

.venv/bin/python <<'PY'
import json
import os
import sys

from worldcup_predictor.agents.base import AgentContext
from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
from worldcup_predictor.config.competitions import DEFAULT_COMPETITION_KEY
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.schedule.competition_schedule import build_schedule_service

settings = get_settings()
ctx = AgentContext(settings=settings, competition_key=DEFAULT_COMPETITION_KEY, locale="en")

# Pick real upcoming World Cup fixture
schedule = build_schedule_service(settings, competition_key=DEFAULT_COMPETITION_KEY)
upcoming = schedule.get_upcoming_matches(limit=10)
fixture_id = None
fixture_label = ""
for f in upcoming:
    if getattr(f, "is_placeholder", False) or getattr(f, "source", "") == "placeholder":
        continue
    if f.fixture_id:
        fixture_id = int(f.fixture_id)
        fixture_label = f"{f.home_team} vs {f.away_team} ({f.kickoff_time})"
        break

if not fixture_id:
    print("FAIL\tNo real upcoming World Cup fixture found")
    sys.exit(1)

print(f"INFO\tFixture ID: {fixture_id}")
print(f"INFO\tMatch: {fixture_label}")
print(f"INFO\tAPI_FOOTBALL configured: {settings.api_football_configured}")
print(f"INFO\tSportmonks configured: {settings.sportmonks_configured}")
print("---")

collector = DataCollectorAgent(ctx)
col_result = collector.run(fixture_id=fixture_id)
if not col_result.success:
    print(f"FAIL\tDataCollectorAgent: {col_result.message}")
    sys.exit(1)

report = col_result.data
print(f"INFO\tIntelligence source: {report.source}")
print(f"INFO\tIs placeholder: {report.is_placeholder}")
print(f"INFO\tData quality score: {getattr(report.data_quality, 'score', 'n/a')}")
print(f"INFO\tMissing data: {', '.join(report.missing_data) or 'none'}")
print(f"INFO\tEnrichment sources: {', '.join(getattr(report, 'enrichment_sources', []) or []) or 'none'}")
print(f"INFO\tWeather available: {bool((report.weather or {}).get('available'))}")
print(f"INFO\tReferee: {report.fixture.referee if report.fixture else 'n/a'}")
print(f"INFO\tLineups items: {len((report.lineups or {}).get('items') or [])}")
print(f"INFO\tHome injuries count: {len(report.home_team.injuries.players if report.home_team.injuries else [])}")
print(f"INFO\tAway injuries count: {len(report.away_team.injuries.players if report.away_team.injuries else [])}")
print(f"INFO\tOdds available: {bool(report.odds and report.odds.available)}")
pm = getattr(report, "provider_metadata", None) or {}
if pm.get("sportmonks_fixture"):
    print("INFO\tSportmonks enrichment: applied")
else:
    print("INFO\tSportmonks enrichment: not in provider_metadata")
print("---")

orch = SpecialistOrchestrator(ctx)
orch_result = orch.run(fixture_id=fixture_id)
if not orch_result.success:
    print(f"FAIL\tSpecialistOrchestrator: {orch_result.message}")
    sys.exit(1)

spec_report = orch_result.data
print("AGENT\tSTATUS\tDATA_SOURCE\tREASON")
for name, sig in spec_report.signals.items():
    status = sig.status
    missing = "; ".join(sig.missing_data) if sig.missing_data else ""
    warnings = "; ".join(sig.warnings[:2]) if sig.warnings else ""
    notes = (sig.notes or "")[:120]
    reason = notes or warnings or missing or "ok"

    # infer data source from domain/signals
    src = "fallback/default"
    if name == "weather_agent":
        src = (sig.signals.get("weather_source") or "none") if status == "available" else "no weather provider data"
    elif name in ("lineup_agent", "lineup_intelligence_agent", "injury_suspension_agent", "injury_suspension_intelligence_agent", "referee_agent", "team_form_agent"):
        src = "API-Football intelligence report"
    elif "odds" in name or "market" in name or "sharp" in name:
        src = "API-Football odds" if status != "unavailable" else "no odds snapshots"
    elif name == "elo_team_strength_intelligence_agent":
        src = "API-Football recent fixtures + form"
    elif name == "xg_chance_quality_intelligence_agent":
        src = "API-Football stats/xG" if status != "unavailable" else "no xG/stats"
    elif name == "tournament_intelligence_agent":
        src = "standings/group context"
    elif name == "motivation_psychology_agent":
        src = "stage + tournament table heuristics"
    elif name == "master_analysis_agent":
        src = "aggregates other specialist signals"
    elif name == "tactics_agent" or name == "player_quality_agent":
        src = "API-Football stats/lineups + optional RapidAPI"

    print(f"{name}\t{status}\t{src}\t{reason}")

print("---")
usable = sum(1 for s in spec_report.signals if s.is_usable)
unavail = sum(1 for s in spec_report.signals if s.status == "unavailable")
partial = sum(1 for s in spec_report.signals if s.status == "partial")
avail = sum(1 for s in spec_report.signals if s.status == "available")
placeholder = sum(1 for s in spec_report.signals if s.status == "placeholder")
print(f"SUMMARY\tavailable={avail} partial={partial} placeholder={placeholder} unavailable={unavail} usable={usable}/{len(spec_report.signals)}")
print(f"SUMMARY\taggregated_signal_score={spec_report.aggregated_signal_score}")
PY

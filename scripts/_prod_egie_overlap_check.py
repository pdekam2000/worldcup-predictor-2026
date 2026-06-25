#!/usr/bin/env python3
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.readers.api_football_raw import load_goal_events_from_egie
from worldcup_predictor.database.postgres.session import session_scope
from sqlalchemy import text

repo = FootballIntelligenceRepository()
before = "2024-05-19T15:00:00"
for team in ("Sheffield Utd", "Tottenham"):
    rows = repo.list_team_finished_fixtures_before(
        team_name=team,
        before_kickoff=before,
        competition_keys=["premier_league"],
        limit=40,
    )
    with session_scope(get_settings()) as s:
        egie_fids = {
            int(r[0])
            for r in s.execute(
                text(
                    "SELECT DISTINCT fixture_id FROM egie_provider_raw_responses "
                    "WHERE resource_type='events' AND fixture_id IS NOT NULL"
                )
            ).fetchall()
        }
    overlap = [int(r["fixture_id"]) for r in rows if int(r["fixture_id"]) in egie_fids]
    print(f"{team}: history={len(rows)} egie_events_fids={len(egie_fids)} overlap={len(overlap)}")
    if overlap:
        fid = overlap[0]
        row = repo.get_fixture_row(fid)
        ev = load_goal_events_from_egie(fid, home_team=row["home_team"], away_team=row["away_team"])
        print(f"  sample fid={fid} egie_goal_events={len(ev)}")

#!/usr/bin/env python3
"""Hotfix Pack 2 — audit yesterday finished fixtures on production."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.config.settings import get_settings

s = get_settings()
repo = FootballIntelligenceRepository(s.sqlite_path)
yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
rows = repo._conn.execute(
    """
    SELECT f.fixture_id, f.home_team, f.away_team, f.kickoff_utc, f.status_class,
           sp.fixture_id as has_pred,
           ev.fixture_id as has_eval, ev.overall_status, ev.final_score,
           ev.is_quarantined
    FROM fixtures f
    LEFT JOIN worldcup_stored_predictions sp ON sp.fixture_id = f.fixture_id
    LEFT JOIN worldcup_prediction_evaluations ev ON ev.fixture_id = f.fixture_id
    WHERE date(f.kickoff_utc) = ?
      AND f.status_class = 'finished'
    ORDER BY f.kickoff_utc DESC
    LIMIT 30
    """,
    (yesterday,),
).fetchall()
print("YESTERDAY", yesterday, "finished", len(rows))
missing_eval = 0
for r in rows:
    d = dict(r)
    has_pred = bool(d["has_pred"])
    has_eval = bool(d["has_eval"])
    if has_pred and not has_eval:
        missing_eval += 1
    print(
        d["fixture_id"],
        d["home_team"],
        "vs",
        d["away_team"],
        "pred",
        has_pred,
        "eval",
        has_eval,
        d.get("overall_status"),
        d.get("final_score"),
        "quarantine",
        d.get("is_quarantined"),
    )
print("MISSING_EVAL_WITH_PRED", missing_eval)
repo.close()

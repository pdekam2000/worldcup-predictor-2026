#!/usr/bin/env python3
"""Read-only production EGIE / Goal Timing data readiness report."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/opt/worldcup-predictor")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "football_intelligence.db"
FINISHED = ("FT", "AET", "PEN", "FINISHED")
UPCOMING = ("NS", "TBD", "SCHEDULED", "TIMED")


def sqlite_inventory() -> dict:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    ph_f = ",".join("?" * len(FINISHED))
    ph_u = ",".join("?" * len(UPCOMING))

    def scalar(sql: str, params: tuple = ()) -> int:
        row = conn.execute(sql, params).fetchone()
        return int(row[0]) if row else 0

    pl_finished = scalar(
        f"SELECT COUNT(*) FROM fixtures WHERE competition_key='premier_league' AND is_placeholder=0 AND status IN ({ph_f})",
        FINISHED,
    )
    finished_with_events = scalar(
        f"""
        SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
        JOIN fixture_goal_events g ON g.fixture_id = f.fixture_id
        WHERE f.competition_key='premier_league' AND f.is_placeholder=0 AND f.status IN ({ph_f})
        """,
        FINISHED,
    )
    missing_events = scalar(
        f"""
        SELECT COUNT(*) FROM fixtures f
        LEFT JOIN (SELECT fixture_id, COUNT(*) c FROM fixture_goal_events GROUP BY fixture_id) g
          ON g.fixture_id = f.fixture_id
        WHERE f.competition_key='premier_league' AND f.is_placeholder=0
          AND f.status IN ({ph_f}) AND COALESCE(g.c, 0) = 0
        """,
        FINISHED,
    )
    upcoming = scalar(
        f"""
        SELECT COUNT(*) FROM fixtures WHERE competition_key='premier_league' AND is_placeholder=0
          AND status IN ({ph_u}) AND kickoff_utc > ?
        """,
        (*UPCOMING, now),
    )
    sample_upcoming = [
        dict(r)
        for r in conn.execute(
            f"""
            SELECT fixture_id, home_team, away_team, kickoff_utc, status FROM fixtures
            WHERE competition_key='premier_league' AND is_placeholder=0
              AND status IN ({ph_u}) AND kickoff_utc > ?
            ORDER BY kickoff_utc ASC LIMIT 10
            """,
            (*UPCOMING, now),
        ).fetchall()
    ]
    fid_row = conn.execute(
        "SELECT fixture_id, home_team, away_team, status, kickoff_utc, competition_key FROM fixtures WHERE fixture_id=1035553"
    ).fetchone()
    ev103 = scalar("SELECT COUNT(*) FROM fixture_goal_events WHERE fixture_id=1035553")

    return {
        "sqlite_path": str(DB),
        "premier_league": {
            "total_fixtures": scalar(
                "SELECT COUNT(*) FROM fixtures WHERE competition_key='premier_league' AND is_placeholder=0"
            ),
            "finished_fixtures": pl_finished,
            "upcoming_fixtures": upcoming,
            "finished_with_goal_events": finished_with_events,
            "finished_missing_goal_events": missing_events,
            "goal_event_coverage_pct_finished": round(100 * finished_with_events / pl_finished, 1) if pl_finished else 0.0,
            "with_first_goal_minute": scalar(
                """
                SELECT COUNT(*) FROM fixtures f
                JOIN fixture_results r ON r.fixture_id = f.fixture_id
                WHERE f.competition_key='premier_league' AND f.is_placeholder=0
                  AND r.first_goal_minute IS NOT NULL
                """
            ),
        },
        "fixture_1035553": {
            "row": dict(fid_row) if fid_row else None,
            "goal_event_rows": ev103,
        },
        "sample_upcoming": sample_upcoming,
    }


def egie_inventory() -> dict:
    try:
        from sqlalchemy import text

        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.database.postgres.session import postgres_configured, session_scope

        settings = get_settings()
        if not postgres_configured(settings):
            return {"configured": False}
        with session_scope(settings) as sess:
            runs = sess.execute(text("SELECT COUNT(*) FROM egie_ingest_runs")).scalar() or 0
            raw = sess.execute(text("SELECT COUNT(*) FROM egie_provider_raw_responses")).scalar() or 0
            by_type = dict(
                sess.execute(
                    text(
                        """
                        SELECT resource_type, COUNT(*) FROM egie_provider_raw_responses
                        WHERE competition_key = 'premier_league' GROUP BY resource_type ORDER BY resource_type
                        """
                    )
                ).fetchall()
            )
            events_fids = sess.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT fixture_id) FROM egie_provider_raw_responses
                    WHERE competition_key='premier_league' AND resource_type='events' AND fixture_id IS NOT NULL
                    """
                )
            ).scalar() or 0
            ev103 = sess.execute(
                text(
                    "SELECT COUNT(*) FROM egie_provider_raw_responses WHERE fixture_id=1035553 AND resource_type='events'"
                )
            ).scalar() or 0
            last_run = sess.execute(
                text(
                    """
                    SELECT status, stats, started_at, finished_at
                    FROM egie_ingest_runs ORDER BY started_at DESC LIMIT 1
                    """
                )
            ).fetchone()
        last_run_dict = None
        if last_run:
            m = last_run._mapping
            last_run_dict = {
                "status": m.get("status"),
                "stats": m.get("stats"),
                "started_at": str(m.get("started_at")),
                "finished_at": str(m.get("finished_at")),
            }
        return {
            "configured": True,
            "ingest_runs": runs,
            "raw_rows_total": raw,
            "pl_by_resource_type": by_type,
            "pl_fixtures_with_events": events_fids,
            "fixture_1035553_events_rows": ev103,
            "last_ingest_run": last_run_dict,
        }
    except Exception as exc:
        return {"configured": True, "error": str(exc)}


def coverage_report() -> dict:
    from worldcup_predictor.goal_timing.service import GoalTimingFeatureService

    return GoalTimingFeatureService().coverage_report()


def api_call_estimate(missing_finished: int, include_upcoming_list: bool = True) -> dict:
    """Estimate live API-Football calls for EGIE PL ingest."""
    base = 2  # standings + fixture list
    per_finished = 4  # events, lineups, statistics, injuries
    fixtures_only = 0
    detail_calls = {}
    for n in (10, 25, 50):
        detail_calls[str(n)] = base + min(n, missing_finished) * per_finished
    return {
        "notes": "EGIE ingest skips duplicate raw rows; live calls may be lower on re-run.",
        "base_calls": base,
        "per_finished_fixture_max": per_finished,
        "estimates_max_live_calls": detail_calls,
        "fixtures_only_mode_calls": base,
    }


def main() -> int:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sqlite": sqlite_inventory(),
        "egie_postgres": egie_inventory(),
        "goal_timing_coverage": coverage_report(),
        "api_call_estimates": api_call_estimate(
            sqlite_inventory()["premier_league"]["finished_missing_goal_events"]
        ),
    }
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

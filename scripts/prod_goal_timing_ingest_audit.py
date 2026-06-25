#!/usr/bin/env python3
"""Read-only production Goal Timing / EGIE ingest audit — no API calls."""

from __future__ import annotations

import json
import os
import sqlite3
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("WORLDCUP_PREDICTOR_ROOT", str(Path(__file__).resolve().parents[1])))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "football_intelligence.db"
FINISHED = ("FT", "AET", "PEN", "FINISHED", "AWD", "WO")
UPCOMING = ("NS", "TBD", "SCHEDULED", "TIMED")
LIVE = ("1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT")


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


def sqlite_pl_audit(conn: sqlite3.Connection) -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    ph_f = ",".join("?" * len(FINISHED))
    ph_u = ",".join("?" * len(UPCOMING))
    ph_l = ",".join("?" * len(LIVE))

    pl_finished = _scalar(
        conn,
        f"SELECT COUNT(*) FROM fixtures WHERE competition_key='premier_league' AND is_placeholder=0 AND status IN ({ph_f})",
        FINISHED,
    )
    with_events = _scalar(
        conn,
        f"""
        SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
        JOIN fixture_goal_events g ON g.fixture_id = f.fixture_id
        WHERE f.competition_key='premier_league' AND f.is_placeholder=0 AND f.status IN ({ph_f})
        """,
        FINISHED,
    )
    missing_events = _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM fixtures f
        LEFT JOIN (SELECT fixture_id, COUNT(*) c FROM fixture_goal_events GROUP BY fixture_id) g
          ON g.fixture_id = f.fixture_id
        WHERE f.competition_key='premier_league' AND f.is_placeholder=0
          AND f.status IN ({ph_f}) AND COALESCE(g.c, 0) = 0
        """,
        FINISHED,
    )
    seasons = [
        dict(r)
        for r in conn.execute(
            """
            SELECT season, status, COUNT(*) AS count
            FROM fixtures WHERE competition_key='premier_league' AND is_placeholder=0
            GROUP BY season, status ORDER BY season, status
            """
        ).fetchall()
    ]
    kickoff_range = conn.execute(
        """
        SELECT MIN(kickoff_utc) AS min_kickoff, MAX(kickoff_utc) AS max_kickoff
        FROM fixtures WHERE competition_key='premier_league' AND is_placeholder=0
        """
    ).fetchone()

    return {
        "total_fixtures": _scalar(
            conn, "SELECT COUNT(*) FROM fixtures WHERE competition_key='premier_league' AND is_placeholder=0"
        ),
        "finished_fixtures": pl_finished,
        "upcoming_fixtures": _scalar(
            conn,
            f"""
            SELECT COUNT(*) FROM fixtures WHERE competition_key='premier_league' AND is_placeholder=0
              AND status IN ({ph_u}) AND kickoff_utc > ?
            """,
            (*UPCOMING, now),
        ),
        "live_fixtures": _scalar(
            conn,
            f"""
            SELECT COUNT(*) FROM fixtures WHERE competition_key='premier_league' AND is_placeholder=0
              AND status IN ({ph_l})
            """,
            LIVE,
        ),
        "finished_with_goal_events": with_events,
        "finished_missing_goal_events": missing_events,
        "goal_event_coverage_pct": round(100 * with_events / pl_finished, 2) if pl_finished else 0.0,
        "with_first_goal_minute": _scalar(
            conn,
            """
            SELECT COUNT(*) FROM fixtures f
            JOIN fixture_results r ON r.fixture_id = f.fixture_id
            WHERE f.competition_key='premier_league' AND f.is_placeholder=0
              AND r.first_goal_minute IS NOT NULL
            """,
        ),
        "by_season_status": seasons,
        "kickoff_range": dict(kickoff_range) if kickoff_range else {},
        "audit_time_utc": now,
    }


def egie_audit() -> dict:
    try:
        from sqlalchemy import text

        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.database.postgres.session import postgres_configured, session_scope

        settings = get_settings()
        if not postgres_configured(settings):
            return {"configured": False}
        with session_scope(settings) as sess:
            runs = int(sess.execute(text("SELECT COUNT(*) FROM egie_ingest_runs")).scalar() or 0)
            raw_total = int(sess.execute(text("SELECT COUNT(*) FROM egie_provider_raw_responses")).scalar() or 0)
            pl_by_type = dict(
                sess.execute(
                    text(
                        """
                        SELECT resource_type, COUNT(*) FROM egie_provider_raw_responses
                        WHERE competition_key='premier_league' GROUP BY resource_type ORDER BY resource_type
                        """
                    )
                ).fetchall()
            )
            pl_event_fids = int(
                sess.execute(
                    text(
                        """
                        SELECT COUNT(DISTINCT fixture_id) FROM egie_provider_raw_responses
                        WHERE competition_key='premier_league' AND resource_type='events'
                          AND fixture_id IS NOT NULL
                        """
                    )
                ).scalar()
                or 0
            )
            last_run = sess.execute(
                text(
                    "SELECT status, stats, started_at FROM egie_ingest_runs ORDER BY started_at DESC LIMIT 1"
                )
            ).fetchone()
        last = None
        if last_run:
            m = last_run._mapping
            last = {"status": m["status"], "stats": m["stats"], "started_at": str(m["started_at"])}
        return {
            "configured": True,
            "ingest_runs": runs,
            "raw_rows_total": raw_total,
            "pl_by_resource_type": pl_by_type,
            "pl_fixtures_with_events": pl_event_fids,
            "last_ingest_run": last,
        }
    except Exception as exc:
        return {"configured": True, "error": str(exc)}


def fillable_from_stored(conn: sqlite3.Connection) -> dict:
    """Estimate how many missing-event fixtures could be filled without live API."""
    ph_f = ",".join("?" * len(FINISHED))
    missing_fids = [
        int(r[0])
        for r in conn.execute(
            f"""
            SELECT f.fixture_id FROM fixtures f
            LEFT JOIN (SELECT fixture_id, COUNT(*) c FROM fixture_goal_events GROUP BY fixture_id) g
              ON g.fixture_id = f.fixture_id
            WHERE f.competition_key='premier_league' AND f.is_placeholder=0
              AND f.status IN ({ph_f}) AND COALESCE(g.c, 0) = 0
            """,
            FINISHED,
        ).fetchall()
    ]
    egie_fids: set[int] = set()
    try:
        from sqlalchemy import text

        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.database.postgres.session import postgres_configured, session_scope

        if postgres_configured(get_settings()):
            with session_scope(get_settings()) as sess:
                egie_fids = {
                    int(r[0])
                    for r in sess.execute(
                        text(
                            """
                            SELECT DISTINCT fixture_id FROM egie_provider_raw_responses
                            WHERE resource_type='events' AND fixture_id IS NOT NULL
                              AND competition_key='premier_league'
                            """
                        )
                    ).fetchall()
                }
    except Exception:
        pass

    fillable_egie = sum(1 for fid in missing_fids if fid in egie_fids)
    need_api = len(missing_fids) - fillable_egie
    return {
        "finished_missing_goal_events_sqlite": len(missing_fids),
        "fillable_from_egie_postgres": fillable_egie,
        "would_require_api_football": need_api,
        "egie_event_fixture_ids": len(egie_fids),
    }


def sample_data_quality(conn: sqlite3.Connection, *, limit: int = 40) -> dict:
    from worldcup_predictor.goal_timing.config import MIN_DATA_QUALITY_FOR_PREDICTION
    from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
    from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter

    stored = StoredGoalTimingAdapter()
    builder = GoalTimingFeatureBuilder(stored=stored, max_api_event_fetches=0)

    rows = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, status
        FROM fixtures
        WHERE competition_key='premier_league' AND is_placeholder=0 AND status IN ('FT','AET','PEN','FINISHED')
        ORDER BY kickoff_utc DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()

    scores: list[float] = []
    missing_fields: Counter[str] = Counter()
    no_pick_reasons: Counter[str] = Counter()
    samples: list[dict] = []

    for row in rows:
        fid = int(row["fixture_id"])
        try:
            features = builder.build(
                fid,
                competition_key="premier_league",
                context={
                    "home_team": row["home_team"],
                    "away_team": row["away_team"],
                    "match_date": stored.parse_kickoff(row["kickoff_utc"]),
                },
            )
        except Exception as exc:
            no_pick_reasons["build_error"] += 1
            continue
        dq = float(features.get("data_quality_score") or 0)
        scores.append(dq)
        manifest = features.get("provider_manifest") or {}
        for key, ok in (
            ("stored_goal_events", manifest.get("stored_goal_events")),
            ("stored_fixtures", manifest.get("stored_fixtures")),
            ("postgres_historical", manifest.get("postgres_historical")),
            ("api_football_fallback_used", manifest.get("api_football_fallback_used")),
            ("sportmonks_xg_in_sample", manifest.get("sportmonks_xg_in_sample")),
        ):
            if not ok:
                missing_fields[key] += 1
        would_publish = dq >= MIN_DATA_QUALITY_FOR_PREDICTION
        if not would_publish:
            no_pick_reasons["data_quality_below_threshold"] += 1
        if not manifest.get("stored_goal_events"):
            no_pick_reasons["missing_stored_goal_events"] += 1
        hist = features.get("history_samples") or {}
        if int(hist.get("home_with_goal_minutes") or 0) == 0:
            no_pick_reasons["home_no_goal_minute_history"] += 1
        if int(hist.get("away_with_goal_minutes") or 0) == 0:
            no_pick_reasons["away_no_goal_minute_history"] += 1

        samples.append(
            {
                "fixture_id": fid,
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "data_quality_score": round(dq, 4),
                "would_publish": would_publish,
            }
        )

    samples.sort(key=lambda x: x["data_quality_score"])
    return {
        "sample_size": len(scores),
        "min_data_quality_threshold": MIN_DATA_QUALITY_FOR_PREDICTION,
        "average_data_quality_score": round(statistics.mean(scores), 4) if scores else None,
        "median_data_quality_score": round(statistics.median(scores), 4) if scores else None,
        "best_fixtures": samples[-5:][::-1] if samples else [],
        "worst_fixtures": samples[:5] if samples else [],
        "would_publish_count": sum(1 for s in samples if s["would_publish"]),
        "no_pick_count": sum(1 for s in samples if not s["would_publish"]),
        "common_missing_manifest_fields": dict(missing_fields.most_common()),
        "no_pick_reason_counts": dict(no_pick_reasons.most_common()),
    }


def upcoming_picks_audit(conn: sqlite3.Connection) -> dict:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.goal_timing.config import MIN_DATA_QUALITY_FOR_PREDICTION
    from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
    from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
    from worldcup_predictor.goal_timing.prediction_service import GoalTimingPredictionService

    repo = FootballIntelligenceRepository(get_settings().sqlite_path or None)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    upcoming = repo.list_upcoming_fixtures("premier_league", limit=50)
    stored = StoredGoalTimingAdapter()
    builder = GoalTimingFeatureBuilder(stored=stored, max_api_event_fetches=0)

    audit_rows: list[dict] = []
    for row in upcoming:
        fid = int(row["fixture_id"])
        try:
            features = builder.build(
                fid,
                competition_key="premier_league",
                context={
                    "home_team": row.get("home_team"),
                    "away_team": row.get("away_team"),
                    "match_date": stored.parse_kickoff(row.get("kickoff_utc")),
                },
            )
            dq = float(features.get("data_quality_score") or 0)
            would_publish = dq >= MIN_DATA_QUALITY_FOR_PREDICTION
            reasons = []
            if dq < MIN_DATA_QUALITY_FOR_PREDICTION:
                reasons.append(f"data_quality_{dq:.2f}_below_{MIN_DATA_QUALITY_FOR_PREDICTION}")
            manifest = features.get("provider_manifest") or {}
            if not manifest.get("stored_goal_events"):
                reasons.append("missing_stored_goal_events")
            audit_rows.append(
                {
                    "fixture_id": fid,
                    "home_team": row.get("home_team"),
                    "away_team": row.get("away_team"),
                    "kickoff_utc": row.get("kickoff_utc"),
                    "data_quality_score": round(dq, 4),
                    "would_publish": would_publish,
                    "no_pick_reasons": reasons,
                }
            )
        except Exception as exc:
            audit_rows.append(
                {
                    "fixture_id": fid,
                    "error": str(exc),
                    "would_publish": False,
                    "no_pick_reasons": ["build_error"],
                }
            )

    try:
        picks_payload = GoalTimingPredictionService().list_today_picks(limit=20)
        live_picks_count = int(picks_payload.get("count") or 0)
    except Exception as exc:
        live_picks_count = -1
        picks_error = str(exc)

    result = {
        "audit_time_utc": now,
        "upcoming_in_sqlite": len(upcoming),
        "upcoming_sample": audit_rows[:10],
        "would_publish_from_upcoming": sum(1 for r in audit_rows if r.get("would_publish")),
        "no_pick_from_upcoming": sum(1 for r in audit_rows if not r.get("would_publish")),
        "live_api_picks_count": live_picks_count,
    }
    if live_picks_count == -1:
        result["live_api_picks_error"] = picks_error
    return result


def api_estimates(fillable: dict) -> dict:
    need_api = int(fillable.get("would_require_api_football") or 0)
    base = 2
    per_fixture = 4
    batches = {}
    for n in (10, 25, 50, 100):
        batches[str(n)] = base + min(n, need_api) * per_fixture
    full_season = base + need_api * per_fixture
    return {
        "base_calls_standings_and_fixture_list": base,
        "per_finished_fixture_max_detail_calls": per_fixture,
        "incremental_batches_max_live_calls": batches,
        "full_pl_missing_events_max_calls": full_season,
        "safe_first_batch_recommendation": {
            "batch_size": 25,
            "max_live_api_calls": batches["25"],
            "note": "Target late-season / team-relevant fixtures; first-25 API order had zero overlap with probe teams in pilot.",
        },
    }


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    pl = sqlite_pl_audit(conn)
    fillable = fillable_from_stored(conn)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_no_api",
        "production_commit": None,
        "premier_league_fixtures": pl,
        "egie_postgres": egie_audit(),
        "stored_vs_api_fill": fillable,
        "data_quality_sample": sample_data_quality(conn, limit=40),
        "upcoming_picks_readiness": upcoming_picks_audit(conn),
        "api_usage_estimates": api_estimates(fillable),
    }
    try:
        import subprocess

        report["production_commit"] = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        )
    except Exception:
        pass

    from worldcup_predictor.goal_timing.service import GoalTimingFeatureService

    report["goal_timing_coverage_api"] = GoalTimingFeatureService().coverage_report()

    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

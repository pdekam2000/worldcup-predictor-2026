"""Forward shadow jobs: collect CS → select pairs → freeze → evaluate → report."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.database.process_lock import ProcessLockError, single_instance_lock
from worldcup_predictor.research.correct_score_odds.forward_collector import build_forward_plan
from worldcup_predictor.research.correct_score_odds.ingest import ingest_from_odds_snapshots
from worldcup_predictor.research.correct_score_odds.ddl import ensure_correct_score_odds_schema
from worldcup_predictor.research.two_fixture_forward_shadow.constants import (
    BOOKMAKER_MODE_CROSS,
    BOOKMAKER_MODE_SINGLE,
    PRIMARY_STAKE_BENCHMARK,
    SNAPSHOT_WINDOWS,
)
from worldcup_predictor.research.two_fixture_forward_shadow.ddl import ensure_tfps_schema
from worldcup_predictor.research.two_fixture_forward_shadow.eligibility import (
    classify_fixture,
    persist_eligibility,
)
from worldcup_predictor.research.two_fixture_forward_shadow.evaluate import (
    completed_count,
    evaluate_pending,
)
from worldcup_predictor.research.two_fixture_forward_shadow.freeze import (
    freeze_parallel_strategies,
    persist_freeze,
)
from worldcup_predictor.research.two_fixture_forward_shadow.observability import build_status, set_obs
from worldcup_predictor.research.two_fixture_forward_shadow.pair_selection import (
    persist_pairs,
    primary_selected,
    select_pairs,
)
from worldcup_predictor.research.two_fixture_forward_shadow.reports import (
    write_daily_report,
    write_weekly_monthly,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def report_date_vienna(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(ZoneInfo("Europe/Vienna")).date().isoformat()


def _log_run(conn, job: str, status: str, details: dict) -> str:
    run_id = f"{job}_{uuid.uuid4().hex[:10]}"
    conn.execute(
        """
        INSERT INTO tfps_run_log(run_id, job, started_at_utc, finished_at_utc, status, details_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, job, _utc_now(), _utc_now(), status, json.dumps(details, default=str)),
    )
    conn.commit()
    return run_id


def discover_upcoming_fixtures(conn, *, report_date: str) -> list[dict[str, Any]]:
    """Upcoming fixtures for Vienna day ±1 with optional lambdas from live snapshots."""
    rows = []
    # Prefer fixtures table for forward
    try:
        for r in conn.execute(
            """
            SELECT fixture_id, kickoff_utc, home_team, away_team,
                   COALESCE(competition_key, '') AS league
            FROM fixtures
            WHERE kickoff_utc IS NOT NULL
              AND date(kickoff_utc) >= date(?)
              AND date(kickoff_utc) <= date(?, '+14 days')
            ORDER BY kickoff_utc ASC
            LIMIT 400
            """,
            (report_date, report_date),
        ):
            rows.append(dict(r))
    except Exception as exc:
        # fallback: broader upcoming window without date() quirks
        try:
            for r in conn.execute(
                """
                SELECT fixture_id, kickoff_utc, home_team, away_team,
                       COALESCE(competition_key, '') AS league
                FROM fixtures
                WHERE kickoff_utc IS NOT NULL AND kickoff_utc >= ?
                ORDER BY kickoff_utc ASC
                LIMIT 400
                """,
                (report_date,),
            ):
                rows.append(dict(r))
        except Exception:
            rows = []
            _ = exc
    # attach lambdas from ecse_prediction_snapshots (canonical live store)
    from worldcup_predictor.research.ecse_live.store import get_snapshot

    out = []
    for fx in rows:
        fid = int(fx["fixture_id"])
        lh = la = dq = None
        freeze_id = None
        try:
            snap = get_snapshot(conn, fid)
            if snap:
                lh = snap.get("lambda_home")
                la = snap.get("lambda_away")
                dq = snap.get("data_quality_score")
                freeze_id = str(snap.get("id") or snap.get("snapshot_id") or "")
        except Exception:
            pass
        if lh is None:
            try:
                row = conn.execute(
                    """
                    SELECT lambda_home, lambda_away, data_quality_score, id
                    FROM ecse_prediction_snapshots
                    WHERE fixture_id=?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (fid,),
                ).fetchone()
                if row:
                    lh, la = row["lambda_home"], row["lambda_away"]
                    dq = row["data_quality_score"] if "data_quality_score" in row.keys() else None
                    freeze_id = str(row["id"])
            except Exception:
                pass
        if lh is None:
            try:
                row = conn.execute(
                    """
                    SELECT lf.lambda_home, lf.lambda_away, lf.data_quality_score
                    FROM ecse_lambda_features lf
                    JOIN historical_provider_mapping hpm
                      ON hpm.registry_fixture_id = lf.registry_fixture_id
                     AND hpm.provider='api_football'
                    WHERE hpm.provider_fixture_id=?
                    LIMIT 1
                    """,
                    (fid,),
                ).fetchone()
                if row:
                    lh, la, dq = row["lambda_home"], row["lambda_away"], row["data_quality_score"]
            except Exception:
                pass
        out.append(
            {
                **fx,
                "lambda_home": lh,
                "lambda_away": la,
                "data_quality": dq,
                "prediction_freeze_id": freeze_id,
                "has_prediction_freeze": bool(freeze_id) or (lh is not None and la is not None),
            }
        )
    return out


def job_collect_odds(conn, *, max_api_calls: int = 0) -> dict[str, Any]:
    """Cache-first CS extraction; optional bounded live fetch (default 0)."""
    ensure_correct_score_odds_schema(conn)
    ensure_tfps_schema(conn)
    extract = ingest_from_odds_snapshots(conn)
    upcoming = discover_upcoming_fixtures(conn, report_date=report_date_vienna())
    plan = build_forward_plan(
        conn,
        [{"fixture_id": u["fixture_id"], "kickoff_utc": u.get("kickoff_utc")} for u in upcoming],
    )
    details = {
        "extract": extract,
        "forward_plan": plan,
        "api_calls": 0,
        "max_api_calls_allowed": max_api_calls,
        "note": "Live API fetch disabled by default to protect quota; cache-first only",
    }
    _log_run(conn, "collect_odds", "ok", details)
    set_obs(conn, "last_collection", details)
    return details


def job_freeze_portfolios(conn) -> dict[str, Any]:
    ensure_tfps_schema(conn)
    ensure_correct_score_odds_schema(conn)
    report_date = report_date_vienna()
    upcoming = discover_upcoming_fixtures(conn, report_date=report_date)
    classified = []
    for u in upcoming:
        c = classify_fixture(
            conn,
            fixture_id=int(u["fixture_id"]),
            kickoff_utc=u.get("kickoff_utc"),
            league=u.get("league"),
            lambda_home=u.get("lambda_home"),
            lambda_away=u.get("lambda_away"),
            data_quality=u.get("data_quality"),
            has_prediction_freeze=bool(u.get("has_prediction_freeze")),
        )
        c["league"] = u.get("league")
        c["home_team"] = u.get("home_team")
        c["away_team"] = u.get("away_team")
        classified.append(c)
    persist_eligibility(conn, report_date, classified)

    pairs = select_pairs(classified, report_date=report_date)
    persist_pairs(conn, pairs)
    primary = primary_selected(pairs)

    inserted = 0
    freezes: list[dict] = []
    done = completed_count(conn)
    if primary:
        # freeze FINAL_PREMATCH window as default executable snapshot
        for window in ("FINAL_PREMATCH", "APPROX_1H", "APPROX_6H"):
            batch = freeze_parallel_strategies(
                primary,
                snapshot_window=window,
                completed_count=done,
            )
            for fz in batch:
                if persist_freeze(conn, fz):
                    inserted += 1
                    freezes.append(fz)

    daily = write_daily_report(conn, report_date, freezes=freezes, pair=primary)
    details = {
        "report_date": report_date,
        "fixtures_classified": len(classified),
        "eligible": sum(1 for c in classified if c["eligibility"] in {"PORTFOLIO_ELIGIBLE", "PORTFOLIO_PARTIAL_ODDS"}),
        "pairs": len(pairs),
        "primary_pair": primary["pair_id"] if primary else None,
        "freezes_inserted": inserted,
        "daily_report": daily,
        "betting_enabled": False,
    }
    _log_run(conn, "freeze_portfolios", "ok" if primary else "no_pair", details)
    return details


def job_evaluate(conn) -> dict[str, Any]:
    ensure_tfps_schema(conn)
    results = evaluate_pending(conn)
    details = {
        "evaluated": len(results),
        "statuses": {},
        "betting_enabled": False,
    }
    for r in results:
        st = r.get("result_status") or "?"
        details["statuses"][st] = details["statuses"].get(st, 0) + 1
    _log_run(conn, "evaluate", "ok", details)
    return details


def job_report(conn) -> dict[str, Any]:
    status = build_status(conn)
    wm = write_weekly_monthly(conn)
    details = {"status": status, "reports": wm}
    _log_run(conn, "report", "ok", details)
    return details


def run_cycle(
    conn,
    *,
    jobs: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run selected jobs under exclusive lock.
    jobs subset of: collect, freeze, evaluate, report, all
    """
    jobs = jobs or ["all"]
    if "all" in jobs:
        jobs = ["collect", "freeze", "evaluate", "report"]
    try:
        with single_instance_lock("two_fixture_forward_shadow", blocking=False):
            out: dict[str, Any] = {"jobs": {}, "lock": "acquired", "betting_enabled": False}
            if "collect" in jobs:
                out["jobs"]["collect"] = job_collect_odds(conn)
            if "freeze" in jobs:
                out["jobs"]["freeze"] = job_freeze_portfolios(conn)
            if "evaluate" in jobs:
                out["jobs"]["evaluate"] = job_evaluate(conn)
            if "report" in jobs:
                out["jobs"]["report"] = job_report(conn)
            out["observability"] = build_status(conn)
            return out
    except ProcessLockError:
        return {
            "lock": "busy",
            "status": "FORWARD_COLLECTION_PARTIAL",
            "error": "overlapping_run_prevented",
            "betting_enabled": False,
        }

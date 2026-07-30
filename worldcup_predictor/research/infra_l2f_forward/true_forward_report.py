"""True-forward cohort reporting for Phase 1 hook + Phase 3 accumulation."""

from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any

from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE
from worldcup_predictor.research.infra_l2f_forward.historical_replay import EVAL_TABLE, ensure_replay_schema
from worldcup_predictor.research.infra_l2f_forward.job_store import JOB_TABLE, ensure_job_schema


def true_forward_summary(fi_conn: sqlite3.Connection, eval_conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    ensure_job_schema(fi_conn)
    ensure_replay_schema(fi_conn)

    jobs = fi_conn.execute(
        f"""
        SELECT status, COUNT(*) AS n
        FROM {JOB_TABLE}
        WHERE run_id = 'l2f-forward-v1'
        GROUP BY status
        """
    ).fetchall()
    by_status = {r[0]: r[1] for r in jobs}
    all_jobs = fi_conn.execute(f"SELECT status, COUNT(*) AS n FROM {JOB_TABLE} GROUP BY status").fetchall()

    try:
        lam = fi_conn.execute(
            f"SELECT COUNT(*) FROM {SHADOW_TABLE} WHERE model_id LIKE 'LAMBDA_V2_%'"
        ).fetchone()[0]
        ex = fi_conn.execute(
            f"SELECT COUNT(*) FROM {SHADOW_TABLE} WHERE model_id LIKE 'EXACT_V2_%'"
        ).fetchone()[0]
    except Exception:
        lam, ex = 0, 0

    timing = fi_conn.execute(
        f"""
        SELECT duration_ms
        FROM {JOB_TABLE}
        WHERE status='success' AND run_id='l2f-forward-v1' AND duration_ms IS NOT NULL
        ORDER BY duration_ms ASC
        """
    ).fetchall()
    durs = [float(r[0]) for r in timing if r[0] is not None]
    median = None
    p95 = None
    if durs:
        median = durs[len(durs) // 2]
        p95 = durs[min(len(durs) - 1, int(0.95 * (len(durs) - 1)))]

    evaluated = fi_conn.execute(
        f"SELECT COUNT(DISTINCT fixture_id) FROM {EVAL_TABLE} WHERE cohort_type='true_forward'"
    ).fetchone()[0]

    # Unresolved: success jobs whose fixture has no actual_results yet
    unresolved = []
    oldest = None
    by_league: Counter[str] = Counter()
    by_date: Counter[str] = Counter()
    if eval_conn is not None:
        success_fx = fi_conn.execute(
            f"""
            SELECT fixture_id, freeze_id, created_at_utc, updated_at_utc, duration_ms
            FROM {JOB_TABLE}
            WHERE status='success' AND run_id='l2f-forward-v1'
            """
        ).fetchall()
        for r in success_fx:
            fid = int(r[0])
            has = eval_conn.execute(
                "SELECT 1 FROM actual_results WHERE fixture_id=? AND actual_home_goals IS NOT NULL",
                (fid,),
            ).fetchone()
            fr = eval_conn.execute(
                """
                SELECT competition, kickoff, frozen_at FROM frozen_predictions
                WHERE fixture_id=? ORDER BY frozen_at ASC LIMIT 1
                """,
                (fid,),
            ).fetchone()
            comp = fr[0] if fr else "unknown"
            ko = (fr[1] if fr else "") or ""
            by_league[str(comp or "unknown")] += 1
            by_date[ko[:10]] += 1
            if not has:
                unresolved.append(
                    {
                        "fixture_id": fid,
                        "freeze_id": r[1],
                        "created_at_utc": r[2],
                        "kickoff": ko,
                        "competition": comp,
                    }
                )
        if unresolved:
            unresolved.sort(key=lambda x: str(x.get("created_at_utc") or ""))
            oldest = unresolved[0]

    return {
        "cohort": "true_forward",
        "discovered": sum(by_status.values()),
        "queued": by_status.get("queued", 0) + by_status.get("running", 0),
        "success": by_status.get("success", 0),
        "skipped": by_status.get("skipped", 0),
        "blocked": by_status.get("blocked", 0),
        "failed": by_status.get("failed", 0),
        "jobs_by_status": by_status,
        "all_jobs_by_status": {r[0]: r[1] for r in all_jobs},
        "unresolved_result_count": len(unresolved),
        "unresolved_fixtures": unresolved[:50],
        "oldest_unresolved": oldest,
        "evaluated": evaluated,
        "lambda_v2_rows_total": lam,
        "exact_v2_rows_total": ex,
        "median_shadow_latency_ms": median,
        "p95_shadow_latency_ms": p95,
        "by_league": dict(by_league.most_common(30)),
        "by_date": dict(by_date.most_common(30)),
        "note": "true_forward jobs use run_id=l2f-forward-v1 (non-backfill).",
    }

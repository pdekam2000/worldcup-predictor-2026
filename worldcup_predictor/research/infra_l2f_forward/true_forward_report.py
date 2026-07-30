"""True-forward cohort reporting for Phase 1 hook jobs."""

from __future__ import annotations

import sqlite3
from typing import Any

from worldcup_predictor.research.infra_l2f_forward.job_store import JOB_TABLE, ensure_job_schema
from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE


def true_forward_summary(fi_conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_job_schema(fi_conn)
    # True-forward jobs use run_id l2f-forward-v1 (non-backfill). Historical uses *-backfill.
    jobs = fi_conn.execute(
        f"""
        SELECT status, COUNT(*) AS n
        FROM {JOB_TABLE}
        WHERE run_id = 'l2f-forward-v1'
          AND IFNULL(run_id, '') NOT LIKE '%backfill%'
        GROUP BY status
        """
    ).fetchall()
    by_status = {r[0]: r[1] for r in jobs}
    all_jobs = fi_conn.execute(
        f"SELECT status, COUNT(*) AS n FROM {JOB_TABLE} GROUP BY status"
    ).fetchall()
    try:
        lam = fi_conn.execute(
            f"SELECT COUNT(*) FROM {SHADOW_TABLE} WHERE model_id LIKE 'LAMBDA_V2_%'"
        ).fetchone()[0]
        ex = fi_conn.execute(
            f"SELECT COUNT(*) FROM {SHADOW_TABLE} WHERE model_id LIKE 'EXACT_V2_%'"
        ).fetchone()[0]
    except Exception:
        lam, ex = 0, 0
    # Age / duration from successful non-backfill jobs if present
    timing = fi_conn.execute(
        f"""
        SELECT AVG(duration_ms), COUNT(*)
        FROM {JOB_TABLE}
        WHERE status='success' AND run_id='l2f-forward-v1'
        """
    ).fetchone()
    return {
        "cohort": "true_forward",
        "jobs_by_status": by_status,
        "all_jobs_by_status": {r[0]: r[1] for r in all_jobs},
        "lambda_v2_rows_total": lam,
        "exact_v2_rows_total": ex,
        "avg_duration_ms_true_forward": timing[0] if timing else None,
        "true_forward_success_count": timing[1] if timing else 0,
        "note": "Inventory eligible_true_forward requires future kickoff + valid freeze; Phase 2 cohort was historical_replay only.",
    }

"""Owner-only true-forward observability (read-only)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import sqlite3

from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE
from worldcup_predictor.research.infra_l2f_forward.historical_replay import EVAL_TABLE, ensure_replay_schema
from worldcup_predictor.research.infra_l2f_forward.job_store import JOB_TABLE, ensure_job_schema
from worldcup_predictor.research.infra_l2f_forward.forward_hook import RUN_ID

SCHEMA_VERSION = "l2f-observability-v1"
VIENNA = ZoneInfo("Europe/Vienna")


def _pct(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = min(len(sorted_vals) - 1, max(0, int(round(p * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def _vienna_date(raw: str | None) -> str | None:
    if not raw:
        return None
    s = str(raw).strip().replace(" ", "T")
    try:
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(VIENNA).date().isoformat()
    except Exception:
        return (raw or "")[:10] or None


def build_observability_report(
    fi_conn: sqlite3.Connection,
    eval_conn: sqlite3.Connection | None = None,
    *,
    limit_details: int = 50,
) -> dict[str, Any]:
    ensure_job_schema(fi_conn)
    ensure_replay_schema(fi_conn)

    jobs = fi_conn.execute(
        f"SELECT * FROM {JOB_TABLE} WHERE run_id=? ORDER BY created_at_utc DESC",
        (RUN_ID,),
    ).fetchall()
    by_status: Counter[str] = Counter()
    by_class: Counter[str] = Counter()
    by_reason: Counter[str] = Counter()
    by_league: Counter[str] = Counter()
    by_utc_date: Counter[str] = Counter()
    by_vienna_date: Counter[str] = Counter()
    durs: list[float] = []
    unresolved: list[dict[str, Any]] = []
    newest_success: dict[str, Any] | None = None
    details: list[dict[str, Any]] = []

    for r in jobs:
        row = dict(r)
        st = str(row.get("status") or "unknown")
        by_status[st] += 1
        cls = str(row.get("classification") or "unclassified")
        by_class[cls] += 1
        if row.get("reason"):
            by_reason[str(row["reason"])[:120]] += 1
        if row.get("duration_ms") is not None and st == "success":
            durs.append(float(row["duration_ms"]))
        ko = row.get("kickoff_utc")
        created = row.get("created_at_utc")
        utc_d = (str(ko or created or "")[:10]) or "unknown"
        by_utc_date[utc_d] += 1
        vd = _vienna_date(str(ko or created) if (ko or created) else None)
        if vd:
            by_vienna_date[vd] += 1

        league = "unknown"
        if eval_conn is not None:
            fr = eval_conn.execute(
                """
                SELECT competition, kickoff FROM frozen_predictions
                WHERE fixture_id=? ORDER BY frozen_at ASC LIMIT 1
                """,
                (int(row["fixture_id"]),),
            ).fetchone()
            if fr:
                league = str(fr[0] or "unknown")
                if not ko:
                    ko = fr[1]
        by_league[league] += 1

        if st == "success":
            if newest_success is None:
                newest_success = {
                    "fixture_id": int(row["fixture_id"]),
                    "freeze_id": row.get("freeze_id"),
                    "completed_at_utc": row.get("completed_at_utc") or row.get("updated_at_utc"),
                    "kickoff_utc": ko,
                    "competition": league,
                }
            has_result = False
            if eval_conn is not None:
                has_result = bool(
                    eval_conn.execute(
                        "SELECT 1 FROM actual_results WHERE fixture_id=? AND actual_home_goals IS NOT NULL",
                        (int(row["fixture_id"]),),
                    ).fetchone()
                )
            evaluated = bool(
                fi_conn.execute(
                    f"SELECT 1 FROM {EVAL_TABLE} WHERE fixture_id=? AND cohort_type='true_forward' LIMIT 1",
                    (int(row["fixture_id"]),),
                ).fetchone()
            )
            link_status = "evaluated" if evaluated else ("result_present" if has_result else "unresolved_result")
            if not has_result:
                unresolved.append(
                    {
                        "fixture_id": int(row["fixture_id"]),
                        "freeze_id": row.get("freeze_id"),
                        "created_at_utc": row.get("created_at_utc"),
                        "kickoff_utc": ko,
                        "competition": league,
                        "result_link_status": link_status,
                    }
                )
            if len(details) < limit_details:
                details.append(
                    {
                        "fixture_id": int(row["fixture_id"]),
                        "status": st,
                        "classification": cls,
                        "reason": row.get("reason"),
                        "duration_ms": row.get("duration_ms"),
                        "result_link_status": link_status,
                        "evaluation_status": "evaluated" if evaluated else "not_evaluated",
                    }
                )

    durs_sorted = sorted(durs)
    evaluated_n = fi_conn.execute(
        f"SELECT COUNT(DISTINCT fixture_id) FROM {EVAL_TABLE} WHERE cohort_type='true_forward'"
    ).fetchone()[0]
    hist_n = fi_conn.execute(
        f"SELECT COUNT(DISTINCT fixture_id) FROM {EVAL_TABLE} WHERE cohort_type='historical_replay'"
    ).fetchone()[0]
    recovered_n = fi_conn.execute(
        f"SELECT COUNT(DISTINCT fixture_id) FROM {EVAL_TABLE} WHERE cohort_type='historical_replay_result_recovered'"
    ).fetchone()[0]
    try:
        lam = fi_conn.execute(
            f"SELECT COUNT(*) FROM {SHADOW_TABLE} WHERE model_id LIKE 'LAMBDA_V2_%'"
        ).fetchone()[0]
        ex = fi_conn.execute(
            f"SELECT COUNT(*) FROM {SHADOW_TABLE} WHERE model_id LIKE 'EXACT_V2_%'"
        ).fetchone()[0]
    except Exception:
        lam, ex = 0, 0

    unresolved.sort(key=lambda x: str(x.get("created_at_utc") or ""))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "cohorts": {
            "true_forward": {
                "discovered": sum(by_status.values()),
                "queued": by_status.get("queued", 0),
                "running": by_status.get("running", 0),
                "success": by_status.get("success", 0),
                "skipped": by_status.get("skipped", 0),
                "blocked": by_status.get("blocked", 0),
                "failed": by_status.get("failed", 0),
                "already_processed": by_class.get("already_success_idempotent", 0),
                "unresolved_results": len(unresolved),
                "evaluated_results": int(evaluated_n),
            },
            "historical_replay_evaluated": int(hist_n),
            "historical_replay_result_recovered_evaluated": int(recovered_n),
        },
        "lambda_v2_row_count": int(lam),
        "exact_v2_row_count": int(ex),
        "latency_ms": {
            "median": _pct(durs_sorted, 0.50),
            "p95": _pct(durs_sorted, 0.95),
            "max": durs_sorted[-1] if durs_sorted else None,
            "n": len(durs_sorted),
        },
        "oldest_unresolved_result": unresolved[0] if unresolved else None,
        "newest_successful_true_forward": newest_success,
        "counts_by_league": dict(by_league.most_common(40)),
        "counts_by_utc_date": dict(by_utc_date.most_common(40)),
        "counts_by_vienna_date": dict(by_vienna_date.most_common(40)),
        "failure_reasons": dict(by_reason.most_common(40)),
        "block_and_skip_classifications": dict(by_class.most_common(40)),
        "jobs_by_status": dict(by_status),
        "details_bounded": details,
        "secrets_redacted": True,
        "read_only": True,
    }

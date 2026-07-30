"""Promotion-readiness evaluator — never promotes, never changes routing."""

from __future__ import annotations

import math
import random
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.infra_l2f_forward.forward_hook import RUN_ID
from worldcup_predictor.research.infra_l2f_forward.historical_replay import EVAL_TABLE, ensure_replay_schema
from worldcup_predictor.research.infra_l2f_forward.job_store import JOB_TABLE, ensure_job_schema
from worldcup_predictor.research.infra_l2f_forward.observability import build_observability_report

STATUS_INSUFFICIENT = "NOT_READY_INSUFFICIENT_TRUE_FORWARD"
STATUS_INTEGRITY = "NOT_READY_INTEGRITY_FAILURE"
STATUS_OPERATIONAL = "NOT_READY_OPERATIONAL_FAILURE"
STATUS_NO_LIFT = "NOT_READY_NO_PERFORMANCE_LIFT"
STATUS_READY_REVIEW = "READY_FOR_MANUAL_REVIEW"
# Explicitly never emitted:
FORBIDDEN_PROMOTED = "PROMOTED"

HARD_MIN_TF = 100
PREFERRED_TF = 250
MIN_LEAGUES = 4
MAX_LEAGUE_SHARE = 0.50
MIN_CALENDAR_DAYS = 21
MIN_SHADOW_SUCCESS = 0.98
MAX_INTERNAL_FAIL = 0.01


def _wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom))


def _bootstrap_mean_diff(a: list[float], b: list[float], n_boot: int = 1000, seed: int = 7) -> dict[str, float]:
    n = min(len(a), len(b))
    if n == 0:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0}
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(a[i] - b[i] for i in idx) / n)
    diffs.sort()
    mean = sum(a[i] - b[i] for i in range(n)) / n
    return {
        "mean": mean,
        "lo": diffs[int(0.025 * (n_boot - 1))],
        "hi": diffs[int(0.975 * (n_boot - 1))],
    }


def _tf_eval_rows(fi_conn: sqlite3.Connection, model_id: str) -> list[dict[str, Any]]:
    ensure_replay_schema(fi_conn)
    rows = fi_conn.execute(
        f"""
        SELECT fixture_id, top1, top3, top5, top10, log_loss, actual_rank, p_actual,
               canonical_top5, lambda_home_err, lambda_away_err, lambda_total_err
        FROM {EVAL_TABLE}
        WHERE cohort_type='true_forward' AND model_id=?
        """,
        (model_id,),
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "fixture_id": int(r[0]),
                "top1": r[1],
                "top3": r[2],
                "top5": r[3],
                "top10": r[4],
                "log_loss": r[5],
                "actual_rank": r[6],
                "p_actual": r[7],
                "canonical_top5": r[8],
                "lambda_home_err": r[9],
                "lambda_away_err": r[10],
                "lambda_total_err": r[11],
            }
        )
    return out


def evaluate_readiness(
    fi_conn: sqlite3.Connection,
    eval_conn: sqlite3.Connection | None = None,
    *,
    obs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Returns readiness statuses for Exact V2, Lambda V2, and detector.
    Never returns PROMOTED. Never mutates routing.
    """
    ensure_job_schema(fi_conn)
    obs = obs or build_observability_report(fi_conn, eval_conn)
    tf = obs["cohorts"]["true_forward"]
    evaluated = int(tf.get("evaluated_results") or 0)
    discovered = int(tf.get("discovered") or 0)
    success = int(tf.get("success") or 0)
    failed = int(tf.get("failed") or 0)

    # Integrity / operational gates shared
    integrity_ok = True
    integrity_reasons: list[str] = []
    # Unexplained duplicates: >1 success job per fixture for true_forward run
    dups = fi_conn.execute(
        f"""
        SELECT fixture_id, COUNT(*) c FROM {JOB_TABLE}
        WHERE run_id=? AND status='success'
        GROUP BY fixture_id HAVING c>1
        """,
        (RUN_ID,),
    ).fetchall()
    if dups:
        integrity_ok = False
        integrity_reasons.append(f"duplicate_success_jobs:{len(dups)}")

    denom = max(1, success + failed)
    success_rate = success / denom if (success + failed) else 0.0
    fail_rate = failed / denom if (success + failed) else 0.0
    operational_ok = success_rate >= MIN_SHADOW_SUCCESS and fail_rate <= MAX_INTERNAL_FAIL
    if discovered == 0:
        operational_ok = True  # no traffic yet — not an operational failure

    leagues = obs.get("counts_by_league") or {}
    n_leagues = len([k for k, v in leagues.items() if v > 0 and k != "unknown"])
    max_share = 0.0
    if success > 0 and leagues:
        max_share = max(leagues.values()) / max(1, sum(leagues.values()))
    dates = [d for d in (obs.get("counts_by_utc_date") or {}) if d and d != "unknown"]
    calendar_span = 0
    if len(dates) >= 2:
        try:
            ds = sorted(datetime.strptime(d, "%Y-%m-%d") for d in dates)
            calendar_span = (ds[-1] - ds[0]).days + 1
        except Exception:
            calendar_span = len(dates)
    elif len(dates) == 1:
        calendar_span = 1

    sample_ok = (
        evaluated >= HARD_MIN_TF
        and n_leagues >= MIN_LEAGUES
        and max_share <= MAX_LEAGUE_SHARE
        and calendar_span >= MIN_CALENDAR_DAYS
    )

    def _status_for(model_key: str, performance_lift: bool | None) -> str:
        if not integrity_ok:
            return STATUS_INTEGRITY
        if discovered > 0 and not operational_ok:
            return STATUS_OPERATIONAL
        if not sample_ok:
            return STATUS_INSUFFICIENT
        if performance_lift is False:
            return STATUS_NO_LIFT
        if performance_lift is True:
            return STATUS_READY_REVIEW
        return STATUS_INSUFFICIENT

    # Exact V2 performance (only meaningful with evaluated TF)
    exact_rows = _tf_eval_rows(fi_conn, "EXACT_V2_SELECTED")
    exact_perf = None
    exact_metrics: dict[str, Any] = {"n": len(exact_rows), "primary_metric": "top5_hit_rate"}
    if exact_rows:
        e5 = [float(r["top5"] or 0) for r in exact_rows]
        c5 = [float(r["canonical_top5"]) for r in exact_rows if r.get("canonical_top5") is not None]
        top5 = sum(e5) / len(e5)
        exact_metrics.update(
            {
                "top5": top5,
                "top1": sum(float(r["top1"] or 0) for r in exact_rows) / len(exact_rows),
                "top3": sum(float(r["top3"] or 0) for r in exact_rows) / len(exact_rows),
                "top10": sum(float(r["top10"] or 0) for r in exact_rows) / len(exact_rows),
                "log_loss": sum(float(r["log_loss"] or 0) for r in exact_rows) / len(exact_rows),
                "mean_actual_rank": sum(float(r["actual_rank"] or 0) for r in exact_rows) / len(exact_rows),
                "top5_wilson_95": _wilson(int(sum(e5)), len(e5)),
            }
        )
        if len(c5) == len(e5) and e5:
            boot = _bootstrap_mean_diff(e5, c5)
            exact_metrics["bootstrap_diff_vs_canonical"] = boot
            # Lift if mean diff > 0 and CI lower bound not deeply negative (soft gate)
            exact_perf = boot["mean"] > 0 and boot["lo"] > -0.02
        else:
            exact_perf = None

    # Lambda V2
    lam_rows = _tf_eval_rows(fi_conn, "LAMBDA_V2_BLENDED_ADAPTIVE")
    lam_perf = None
    lam_metrics: dict[str, Any] = {"n": len(lam_rows), "primary_metric": "mae_total_lambda_error"}
    if lam_rows:
        mae = sum(float(r["lambda_total_err"] or 0) for r in lam_rows) / len(lam_rows)
        lam_metrics.update(
            {
                "mae_total": mae,
                "mae_home": sum(float(r["lambda_home_err"] or 0) for r in lam_rows) / len(lam_rows),
                "mae_away": sum(float(r["lambda_away_err"] or 0) for r in lam_rows) / len(lam_rows),
                "rmse_total": math.sqrt(
                    sum(float(r["lambda_total_err"] or 0) ** 2 for r in lam_rows) / len(lam_rows)
                ),
            }
        )
        # Without a locked canonical lambda-error baseline on TF, performance remains undetermined.
        lam_perf = None

    detector = {
        "status": STATUS_INSUFFICIENT,
        "research_only": True,
        "routing_activated": False,
        "note": "Detector may only be scored on untouched true-forward; currently not activated.",
        "evaluated_true_forward_n": evaluated,
        "tuning_on_true_forward_forbidden": True,
    }
    if evaluated >= HARD_MIN_TF:
        detector["status"] = STATUS_INSUFFICIENT  # still no TF-scored detector run stored
        detector["note"] = (
            "Sample gate met for eventual scoring, but detector remains research-only and "
            "must not be tuned on true-forward outcomes."
        )

    report = {
        "schema_version": "l2f-readiness-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "never_auto_promotes": True,
        "forbidden_status": FORBIDDEN_PROMOTED,
        "gates": {
            "hard_min_true_forward_evaluated": HARD_MIN_TF,
            "preferred_true_forward_evaluated": PREFERRED_TF,
            "min_leagues": MIN_LEAGUES,
            "max_single_league_share": MAX_LEAGUE_SHARE,
            "min_calendar_days": MIN_CALENDAR_DAYS,
            "min_shadow_success_rate": MIN_SHADOW_SUCCESS,
            "max_internal_failure_rate": MAX_INTERNAL_FAIL,
        },
        "sample": {
            "true_forward_discovered": discovered,
            "true_forward_success": success,
            "true_forward_evaluated": evaluated,
            "league_count": n_leagues,
            "max_league_share": max_share,
            "calendar_span_days": calendar_span,
            "sample_ok": sample_ok,
        },
        "integrity": {"ok": integrity_ok, "reasons": integrity_reasons},
        "operational": {
            "ok": operational_ok,
            "shadow_success_rate": success_rate,
            "internal_failure_rate": fail_rate,
            "latency_ms": obs.get("latency_ms"),
        },
        "exact_v2": {
            "model_id": "EXACT_V2_SELECTED",
            "status": _status_for("exact", exact_perf),
            "metrics": exact_metrics,
            "performance_lift_detected": exact_perf,
        },
        "lambda_v2": {
            "model_id": "LAMBDA_V2_BLENDED_ADAPTIVE",
            "status": _status_for("lambda", lam_perf),
            "metrics": lam_metrics,
            "performance_lift_detected": lam_perf,
        },
        "detector_et_gte_3_0": detector,
        "promotion_occurred": False,
        "routing_activation_occurred": False,
    }
    # Hard assertion: never emit PROMOTED
    for key in ("exact_v2", "lambda_v2", "detector_et_gte_3_0"):
        assert report[key]["status"] != FORBIDDEN_PROMOTED
    return report

"""Phase 6 daily and cumulative true-forward reports."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.infra_l2f_forward.historical_replay import (
    EVAL_TABLE,
    aggregate_eval_metrics,
    ensure_replay_schema,
)
from worldcup_predictor.research.infra_l2f_forward.hv_batch import BATCH_ITEM_TABLE, CHECKPOINT_TABLE, ensure_hv_schema
from worldcup_predictor.research.infra_l2f_forward.job_store import JOB_TABLE, ensure_job_schema
from worldcup_predictor.research.infra_l2f_forward.readiness import evaluate_readiness
from worldcup_predictor.research.infra_l2f_forward.storage_policy import storage_outlook
from worldcup_predictor.research.infra_l2f_forward.true_forward_report import true_forward_summary


def build_daily_report(
    *,
    vienna_date: str,
    batch_result: dict[str, Any] | None = None,
    fi_conn: sqlite3.Connection | None = None,
    eval_conn: sqlite3.Connection | None = None,
    disk_line: str | None = None,
    services_ok: bool | None = None,
) -> dict[str, Any]:
    br = batch_result or {}
    sampling = br.get("sampling") or {}
    uni = br.get("universe_summary") or {}
    items = br.get("items") or []
    block_reasons = Counter(str(i.get("reason") or "none") for i in items if i.get("canonical_status") in {
        "blocked",
        "odds_blocked",
        "quality_gate",
        "post_kickoff",
        "failed",
        "freeze_failed",
        "freeze_missing",
    } or i.get("status") in {"blocked", "failed"})

    tf = true_forward_summary(fi_conn, eval_conn) if fi_conn is not None else {}

    return {
        "report_type": "phase6_daily",
        "vienna_date": vienna_date,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "discovered_universe": uni.get("discovered_count") or br.get("discovered"),
        "eligible_count": uni.get("eligible_count") or br.get("eligible"),
        "exclusion_counts": uni.get("exclusion_counts"),
        "selected_count": br.get("selected"),
        "processed_count": br.get("processed"),
        "canonical_successes": br.get("canonical_success"),
        "canonical_blocked_failed": {
            "blocked": br.get("canonical_blocked"),
            "failed": br.get("canonical_failed"),
        },
        "true_forward_shadow": {
            "success": br.get("shadow_success"),
            "failed": br.get("shadow_failed"),
            "skipped": br.get("shadow_skipped"),
        },
        "block_and_failure_reasons": dict(block_reasons),
        "league_distribution": sampling.get("league_distribution"),
        "odds_bucket_distribution": sampling.get("odds_strength_distribution"),
        "expected_total_distribution": sampling.get("expected_total_distribution"),
        "market_balance_distribution": sampling.get("market_balance_distribution"),
        "sampling_policy_version": sampling.get("sampling_policy_version"),
        "sampling_seed": sampling.get("seed"),
        "reproducibility": sampling.get("reproducibility"),
        "cohort_true_forward_snapshot": {
            "success_jobs": tf.get("success"),
            "evaluated": tf.get("evaluated"),
            "unresolved_results": tf.get("unresolved_result_count"),
        },
        "disk_and_health": {
            "disk_before": br.get("disk_before") or disk_line,
            "disk_after": br.get("disk_after"),
            "disk_alert": br.get("disk_alert"),
            "stopped_reason": br.get("stopped_reason"),
            "services_ok": services_ok,
        },
        "promotion_occurred": False,
        "routing_activation_occurred": False,
        "explicit": "No promotion and no routing activation occurred.",
    }


def build_cumulative_report(
    *,
    fi_conn: sqlite3.Connection,
    eval_conn: sqlite3.Connection | None = None,
    fixtures_per_day_assumption: int = 100,
) -> dict[str, Any]:
    ensure_job_schema(fi_conn)
    ensure_replay_schema(fi_conn)
    ensure_hv_schema(fi_conn)
    tf = true_forward_summary(fi_conn, eval_conn)
    metrics_tf = aggregate_eval_metrics(fi_conn, cohort_type="true_forward")
    metrics_hist = aggregate_eval_metrics(fi_conn, cohort_type="historical_replay")
    metrics_rec = aggregate_eval_metrics(fi_conn, cohort_type="historical_replay_result_recovered")

    try:
        readiness = evaluate_readiness(fi_conn, eval_conn)
    except TypeError:
        readiness = evaluate_readiness(fi_conn)
    except Exception as exc:  # noqa: BLE001
        readiness = {"status": "error", "error": str(exc)}

    cp_rows = fi_conn.execute(
        f"SELECT stage, COUNT(*), SUM(processed), SUM(canonical_success), SUM(shadow_success) FROM {CHECKPOINT_TABLE} GROUP BY stage"
    ).fetchall()
    stages = {
        r[0]: {
            "checkpoints": r[1],
            "processed_sum": r[2],
            "canonical_success_sum": r[3],
            "shadow_success_sum": r[4],
        }
        for r in cp_rows
    }

    return {
        "report_type": "phase6_cumulative",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "total_true_forward_frozen_jobs": tf.get("success"),
        "total_completed_shadow": tf.get("success"),
        "total_evaluated": tf.get("evaluated"),
        "unresolved_results": tf.get("unresolved_result_count"),
        "success_rates": {
            "jobs_by_status": tf.get("jobs_by_status"),
        },
        "latency_ms": {
            "median": tf.get("median_shadow_latency_ms"),
            "p95": tf.get("p95_shadow_latency_ms"),
        },
        "metrics_by_cohort": {
            "true_forward": metrics_tf,
            "historical_replay": metrics_hist,
            "historical_replay_result_recovered": metrics_rec,
        },
        "hv_stages": stages,
        "storage_outlook": storage_outlook(fixtures_per_day=fixtures_per_day_assumption),
        "readiness": readiness,
        "promotion_occurred": False,
        "routing_activation_occurred": False,
        "explicit": "No promotion and no routing activation occurred.",
    }


def write_report(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path

"""PHASE ECSE-LIVE-1 — Orchestrate snapshot + evaluation cycle (internal only)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_live.evaluator import run_ecse_evaluations
from worldcup_predictor.research.ecse_live.runner import run_ecse_snapshot_runner
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables

PHASE = "ECSE-LIVE-1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def run_ecse_live_cycle(
    *,
    settings: Settings | None = None,
    snapshot_limit: int = 100,
    eval_limit: int = 200,
) -> dict[str, Any]:
    """Run ECSE live snapshot (T-60) and evaluation (FT+15) in one internal cycle."""
    settings = settings or get_settings()
    if not settings.ecse_live_enabled:
        return {
            "phase": PHASE,
            "status": "disabled",
            "reason": "ECSE_LIVE_ENABLED=false",
        }

    conn = connect(get_db_path(settings.sqlite_path))
    started = time.time()
    try:
        ensure_ecse_live_tables(conn)
        snapshot_result = run_ecse_snapshot_runner(
            conn,
            settings=settings,
            limit=snapshot_limit,
        )
        from worldcup_predictor.research.ecse_live.result_sync import refresh_ecse_snapshot_results

        result_sync = refresh_ecse_snapshot_results(
            settings=settings,
            competition_key="world_cup_2026",
            limit=eval_limit,
            dry_run=settings.ecse_live_dry_run,
        )
        eval_result = run_ecse_evaluations(
            conn,
            settings=settings,
            limit=eval_limit,
        )
        report: dict[str, Any] = {
            "phase": PHASE,
            "status": "ok",
            "started_at_utc": _utc_now(),
            "duration_seconds": round(time.time() - started, 2),
            "snapshot": snapshot_result.to_dict(),
            "result_sync": result_sync.to_dict(),
            "evaluation": eval_result.to_dict(),
            "policy": {
                "snapshot_minutes_before_kickoff": settings.ecse_live_snapshot_minutes_before,
                "eval_minutes_after_ft": settings.ecse_live_eval_minutes_after_ft,
                "dry_run": settings.ecse_live_dry_run,
                "use_providers": settings.ecse_live_use_providers,
            },
        }
        conn.execute(
            """
            INSERT INTO ecse_live_cycle_runs (started_at, finished_at, status, report_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                report["started_at_utc"],
                _utc_now(),
                "ok",
                json.dumps(report, default=str),
            ),
        )
        conn.commit()
        return report
    except Exception as exc:
        fail = {
            "phase": PHASE,
            "status": "error",
            "error": str(exc),
            "started_at_utc": _utc_now(),
        }
        try:
            conn.execute(
                """
                INSERT INTO ecse_live_cycle_runs (started_at, finished_at, status, report_json)
                VALUES (?, ?, ?, ?)
                """,
                (fail["started_at_utc"], _utc_now(), "error", json.dumps(fail, default=str)),
            )
            conn.commit()
        except Exception:
            pass
        return fail
    finally:
        conn.close()

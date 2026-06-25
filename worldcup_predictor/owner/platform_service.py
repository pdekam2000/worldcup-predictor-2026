"""Phase 63 — owner command center services (monitoring, autonomous, notifications)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.admin.autonomous_performance import AutonomousPerformanceService
from worldcup_predictor.autonomous.completion_detector import detect_completed_fixtures
from worldcup_predictor.autonomous.evaluation_engine import run_autonomous_evaluations
from worldcup_predictor.autonomous.orchestrator import run_autonomous_cycle
from worldcup_predictor.autonomous.performance_certification import run_performance_certification
from worldcup_predictor.autonomous.store import AutonomousStore
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.session import ping_postgres
from worldcup_predictor.database.saas_factory import saas_uow
from worldcup_predictor.quota.quota_guard import quota_risk_level
from worldcup_predictor.quota.quota_tracker import get_quota_tracker

REQUIRED_CONSECUTIVE_SUCCESSES = 3
STATE_FILE = Path("data/enterprise/owner_runtime_state.json")
TIMER_UNIT = "worldcup-autonomous.timer"
SERVICE_UNIT = "worldcup-autonomous.service"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state() -> dict[str, Any]:
    if not STATE_FILE.is_file():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _utc_now()
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _system_metrics() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        import psutil

        out["cpu_percent"] = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        out["ram"] = {
            "total_gb": round(mem.total / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "percent": mem.percent,
        }
        disk = shutil.disk_usage("/")
        out["disk"] = {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "percent": round(disk.used / disk.total * 100, 1),
        }
    except Exception as exc:
        out["error"] = str(exc)
    return out


def _timer_status() -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", TIMER_UNIT],
            capture_output=True,
            text=True,
            timeout=5,
        )
        active = proc.stdout.strip() == "active"
        enabled_proc = subprocess.run(
            ["systemctl", "is-enabled", TIMER_UNIT],
            capture_output=True,
            text=True,
            timeout=5,
        )
        enabled = enabled_proc.stdout.strip() in ("enabled", "static")
        return {"timer_unit": TIMER_UNIT, "active": active, "enabled": enabled}
    except Exception as exc:
        return {"timer_unit": TIMER_UNIT, "active": False, "enabled": False, "error": str(exc)}


class OwnerPlatformService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = AutonomousStore(self.settings)
        self.performance = AutonomousPerformanceService()

    def overview(self) -> dict[str, Any]:
        postgres_ok = ping_postgres()
        snap = get_quota_tracker().snapshot()
        with saas_uow() as uow:
            from sqlalchemy import func, select
            from worldcup_predictor.database.postgres.models import Subscription, User
            from worldcup_predictor.database.postgres.enums import SubscriptionPlan

            session = uow.session
            total_users = int(session.scalar(select(func.count()).select_from(User)) or 0)
            paid_users = int(
                session.scalar(
                    select(func.count())
                    .select_from(Subscription)
                    .where(Subscription.plan.not_in([SubscriptionPlan.FREE]))
                )
                or 0
            )

        state = _load_state()
        today_preds = self._count_today_snapshots()
        today_evals = self._count_today_evaluations()

        return {
            "status": "ok",
            "health": {
                "postgres": "operational" if postgres_ok else "down",
                "api": "operational",
                "prediction_engine": "operational",
            },
            "users": {"total": total_users, "paid": paid_users},
            "api_quota": {
                "calls_today": snap.live_requests,
                "risk": quota_risk_level(),
                "cache_hit_rate": snap.cache_hit_rate,
            },
            "autonomous": {
                **self.autonomous_status(),
                "predictions_today": today_preds,
                "evaluations_today": today_evals,
            },
            "scheduler": _timer_status(),
            "runtime_state": state,
            "generated_at": _utc_now(),
        }

    def monitoring(self) -> dict[str, Any]:
        settings = self.settings
        sqlite_path = settings.sqlite_path or "data/football_intelligence.db"
        sqlite_size_mb = None
        if Path(sqlite_path).is_file():
            sqlite_size_mb = round(Path(sqlite_path).stat().st_size / (1024**2), 2)

        snap = get_quota_tracker().snapshot()
        return {
            "status": "ok",
            "system": _system_metrics(),
            "postgres": {"reachable": ping_postgres()},
            "sqlite": {"path": sqlite_path, "size_mb": sqlite_size_mb},
            "scheduler": _timer_status(),
            "api_quota": {
                "stat_date": snap.stat_date,
                "live_requests": snap.live_requests,
                "cache_hit_rate": snap.cache_hit_rate,
                "quota_risk": quota_risk_level(),
            },
            "autonomous_cycles": self._recent_cycles(limit=5),
            "generated_at": _utc_now(),
        }

    def autonomous_status(self) -> dict[str, Any]:
        state = _load_state()
        latest = self._latest_cycle()
        return {
            "platform_enabled": self.settings.autonomous_platform_enabled,
            "dry_run": self.settings.autonomous_dry_run,
            "scheduler_enabled": bool(state.get("scheduler_enabled")),
            "consecutive_successes": int(state.get("consecutive_successes") or 0),
            "required_for_scheduler": REQUIRED_CONSECUTIVE_SUCCESSES,
            "can_enable_scheduler": int(state.get("consecutive_successes") or 0) >= REQUIRED_CONSECUTIVE_SUCCESSES,
            "last_run": latest,
            "last_error": state.get("last_error"),
            "recent_runs": state.get("recent_runs") or [],
        }

    def run_once(
        self,
        *,
        dry_run: bool | None = None,
        fixture_limit: int | None = None,
    ) -> dict[str, Any]:
        report = run_autonomous_cycle(
            settings=self.settings,
            dry_run=dry_run,
            fixture_limit=fixture_limit,
        )
        state = _load_state()
        runs: list[dict[str, Any]] = list(state.get("recent_runs") or [])
        entry = {
            "at": _utc_now(),
            "status": report.get("status"),
            "cycle_id": report.get("cycle_id"),
            "duration_seconds": report.get("duration_seconds"),
            "api_calls_used": report.get("api_calls_used"),
            "dry_run": dry_run if dry_run is not None else self.settings.autonomous_dry_run,
            "fixture_limit": fixture_limit,
            "fixtures_discovered": (report.get("discovery") or {}).get("fixture_count"),
            "predictions_created": (report.get("predictions") or {}).get("production_snapshots"),
            "elite_snapshots": (report.get("predictions") or {}).get("elite_snapshots"),
            "evaluations_pending": (report.get("evaluation") or {}).get("pending"),
            "duplicate_skipped": (report.get("predictions") or {}).get("skipped_cache"),
        }
        runs.insert(0, entry)
        state["recent_runs"] = runs[:20]

        if report.get("status") == "ok":
            state["consecutive_successes"] = int(state.get("consecutive_successes") or 0) + 1
            state["last_error"] = None
        else:
            state["consecutive_successes"] = 0
            state["last_error"] = report.get("reason") or report.get("error") or str(report)

        state["last_run"] = entry
        _save_state(state)
        self._append_notification(
            title="Autonomous cycle completed" if report.get("status") == "ok" else "Autonomous cycle failed",
            level="info" if report.get("status") == "ok" else "error",
            detail=state.get("last_error") or "ok",
        )
        return {"status": "ok", "report": report, "autonomous": self.autonomous_status()}

    def run_evaluation(self) -> dict[str, Any]:
        completion = detect_completed_fixtures(settings=self.settings, limit=200)
        evaluation = run_autonomous_evaluations(settings=self.settings, limit=500)
        return {
            "status": "ok",
            "completion": completion.to_dict(),
            "evaluation": evaluation.to_dict(),
        }

    def run_certification(self) -> dict[str, Any]:
        report = run_performance_certification(settings=self.settings)
        return {"status": "ok", "certification": report.to_dict(), "summary": self.performance.certification_summary()}

    def enable_scheduler(self) -> dict[str, Any]:
        status = self.autonomous_status()
        if not status["can_enable_scheduler"]:
            return {
                "status": "blocked",
                "reason": f"Requires {REQUIRED_CONSECUTIVE_SUCCESSES} consecutive successful autonomous_once runs",
                "autonomous": status,
            }
        state = _load_state()
        state["scheduler_enabled"] = True
        _save_state(state)
        try:
            subprocess.run(["systemctl", "enable", "--now", TIMER_UNIT], check=False, timeout=15)
        except Exception as exc:
            state["scheduler_enable_error"] = str(exc)
            _save_state(state)
        self._append_notification("Scheduler enabled", "info", "Autonomous timer activated")
        return {"status": "ok", "scheduler": _timer_status(), "autonomous": self.autonomous_status()}

    def disable_scheduler(self) -> dict[str, Any]:
        state = _load_state()
        state["scheduler_enabled"] = False
        _save_state(state)
        try:
            subprocess.run(["systemctl", "disable", "--now", TIMER_UNIT], check=False, timeout=15)
        except Exception as exc:
            state["scheduler_disable_error"] = str(exc)
            _save_state(state)
        return {"status": "ok", "scheduler": _timer_status(), "autonomous": self.autonomous_status()}

    def notifications(self, *, limit: int = 50) -> dict[str, Any]:
        state = _load_state()
        items = list(state.get("notifications") or [])[:limit]
        risk = quota_risk_level()
        if risk in ("high", "critical"):
            items.insert(
                0,
                {
                    "id": "quota-risk",
                    "title": "API quota risk elevated",
                    "level": "warning",
                    "detail": f"Current risk: {risk}",
                    "at": _utc_now(),
                    "read": False,
                },
            )
        if not ping_postgres():
            items.insert(
                0,
                {
                    "id": "postgres-down",
                    "title": "PostgreSQL unreachable",
                    "level": "error",
                    "detail": "Database health check failed",
                    "at": _utc_now(),
                    "read": False,
                },
            )
        return {"status": "ok", "notifications": items}

    def model_center(self) -> dict[str, Any]:
        cert = self.performance.certification_summary()
        levels = cert.get("certification_levels") or {}
        markets = cert.get("markets") or {}
        engines = cert.get("engines") or {}

        production_markets = [
            "1x2",
            "double_chance",
            "btts",
            "over_under_2_5",
            "correct_score",
        ]
        elite_markets = production_markets + [
            "goal_timing",
            "first_goal_team",
            "team_to_score_first",
            "goalscorer",
        ]

        def _market_rows(engine_key: str, market_list: list[str]) -> list[dict[str, Any]]:
            rows = []
            for m in market_list:
                key = f"{engine_key}:{m}"
                metrics = markets.get(key) or markets.get(m) or {}
                rows.append(
                    {
                        "market": m,
                        "predictions": metrics.get("total") or metrics.get("predictions") or 0,
                        "evaluated": metrics.get("evaluated") or 0,
                        "pending": metrics.get("pending") or 0,
                        "winrate": metrics.get("winrate"),
                        "roi": metrics.get("roi"),
                        "certification": levels.get(key) or levels.get(m) or "BLOCKED",
                    }
                )
            return rows

        trusted = []
        needs_data = []
        no_bet = []
        for key, level in levels.items():
            if level == "PRODUCTION_READY":
                trusted.append(key)
            elif level in ("BLOCKED", "RESEARCH_ONLY"):
                needs_data.append(key)
            elif level == "PAPER_READY":
                no_bet.append(key)

        return {
            "status": "ok",
            "production_engine": {
                "name": "Production WDE",
                "status": "Public Active",
                "markets": production_markets,
                "metrics": engines.get("production") or {},
                "market_rows": _market_rows("production", production_markets),
            },
            "elite_engine": {
                "name": "Elite Shadow",
                "status": "Shadow / Research — Not promoted",
                "markets": elite_markets,
                "metrics": engines.get("elite_shadow") or {},
                "market_rows": _market_rows("elite_shadow", elite_markets),
            },
            "certification": cert,
            "recommendations": {
                "trusted_markets": trusted[:20],
                "needs_more_results": needs_data[:20],
                "no_bet_or_paper_only": no_bet[:20],
            },
            "generated_at": _utc_now(),
        }

    def research_lab(self, *, refresh_value: bool = False) -> dict[str, Any]:
        from worldcup_predictor.research.value_intelligence import load_value_summary, run_value_intelligence

        value_summary = load_value_summary()
        if refresh_value or value_summary is None:
            try:
                value_summary = run_value_intelligence(write_artifacts=True)
            except Exception as exc:
                value_summary = {"error": str(exc), "sample_size": 0}

        timing_path = Path("artifacts/phase60b_first_goal_timing_distribution/summary.json")
        timing_summary = None
        if timing_path.is_file():
            try:
                timing_summary = json.loads(timing_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                timing_summary = None

        odds_path = Path("artifacts/phase60c_goal_event_backfill/odds_bucket_summary.json")
        odds_summary = None
        if odds_path.is_file():
            try:
                odds_summary = json.loads(odds_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                odds_summary = None

        warnings = list(value_summary.get("data_quality_warnings") or []) if value_summary else []
        warnings.append("Research only — not betting advice.")

        return {
            "status": "ok",
            "disclaimer": "Research only — not betting advice.",
            "first_goal_timing": timing_summary,
            "odds_buckets": odds_summary,
            "value_intelligence": value_summary,
            "warnings": warnings,
            "generated_at": _utc_now(),
        }

    def _append_notification(self, title: str, level: str, detail: str) -> None:
        state = _load_state()
        notes = list(state.get("notifications") or [])
        notes.insert(
            0,
            {
                "id": f"n-{len(notes)+1}-{int(datetime.now(timezone.utc).timestamp())}",
                "title": title,
                "level": level,
                "detail": detail,
                "at": _utc_now(),
                "read": False,
            },
        )
        state["notifications"] = notes[:100]
        _save_state(state)

    def _latest_cycle(self) -> dict[str, Any] | None:
        row = self.store._conn.execute(  # noqa: SLF001
            "SELECT * FROM autonomous_cycle_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def _recent_cycles(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.store._conn.execute(  # noqa: SLF001
            "SELECT id, started_at, finished_at, status FROM autonomous_cycle_runs ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

    def _count_today_snapshots(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        row = self.store._conn.execute(  # noqa: SLF001
            "SELECT COUNT(*) AS c FROM autonomous_prediction_snapshots WHERE created_at >= ?",
            (today,),
        ).fetchone()
        return int(row["c"]) if row else 0

    def _count_today_evaluations(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        row = self.store._conn.execute(  # noqa: SLF001
            "SELECT COUNT(*) AS c FROM autonomous_snapshot_evaluations WHERE evaluated_at >= ?",
            (today,),
        ).fetchone()
        return int(row["c"]) if row else 0

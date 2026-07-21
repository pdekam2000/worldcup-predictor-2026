"""IMPLEMENT-1 — Production-safe prediction/evaluation pipeline runner."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.automation.worldcup_background.auto_evaluation_job import (
    run_production_auto_evaluation,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.owner.production_pipeline.lock import ProductionPipelineLock
from worldcup_predictor.owner_daily.constants import (
    ARTIFACTS_DIR,
    DAILY_SUPPORTED_COMPETITIONS,
    DEFAULT_TIMEZONE,
)
from worldcup_predictor.owner_daily.result_sync import run_daily_result_sync_and_evaluation
from worldcup_predictor.owner_predict_eval.control_panel import build_owner_daily_control_panel
from worldcup_predictor.owner_predict_eval.runner import run_owner_daily_prediction_and_eval
from worldcup_predictor.owner_predict_eval.tomorrow_league_batch import evaluate_all_pending_frozen_batches

PHASE = "IMPLEMENT-1-PRODUCTION-PIPELINE"
LOCK_PATH = Path("data/locks/production_prediction_pipeline.lock")
REPORT_MD = Path("PRODUCTION_PIPELINE_LAST_RUN.md")
ARTIFACT_DIR = Path("artifacts/production_pipeline")

SAFETY = {
    "PUBLIC_PUBLISH": False,
    "WDE_RETRAINED": False,
    "EGIE_RETRAINED": False,
    "HISTORICAL_CSV_PROMOTED": False,
    "ODDALERTS_ECSE_PRODUCTION": False,
    "ODDALERTS_ECSE_SHADOW_ONLY": True,
    "OWNER_ONLY": True,
}


@dataclass
class PipelineConfig:
    mode: str = "daily"
    date_arg: str = "today"
    timezone: str = DEFAULT_TIMEZONE
    dry_run: bool = False
    limit: int = 0
    include_tomorrow: bool = True
    include_shadow_monitor: bool = True
    max_api_football_calls: int = 80
    max_oddalerts_calls: int = 50
    max_sportmonks_calls: int = 50
    skip_lock: bool = False
    refresh_stale_odds: bool = False
    max_odds_provider_calls: int = 20
    strict_fresh_odds: bool = False
    fixture_id: int | None = None
    lock_wait_sec: float = 300.0
    skip_result_sync_in_daily: bool = True
    drain_concurrency: int = 1


@dataclass
class PipelineRunResult:
    phase: str = PHASE
    mode: str = ""
    dry_run: bool = False
    started_at: str = ""
    finished_at: str = ""
    lock_acquired: bool = False
    skipped_overlap: bool = False
    steps: dict[str, Any] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    provider_calls: dict[str, Any] = field(default_factory=dict)
    learning: dict[str, Any] = field(default_factory=dict)
    shadow: dict[str, Any] = field(default_factory=dict)
    report_paths: dict[str, str] = field(default_factory=dict)
    recommendation: str = "IMPLEMENT_1_DO_NOT_ENABLE"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **SAFETY,
            "phase": self.phase,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "lock_acquired": self.lock_acquired,
            "skipped_overlap": self.skipped_overlap,
            "steps": self.steps,
            "counts": self.counts,
            "provider_calls": self.provider_calls,
            "learning": self.learning,
            "shadow": self.shadow,
            "report_paths": self.report_paths,
            "recommendation": self.recommendation,
            "errors": self.errors,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _count_stored_predictions(db_path: str | None) -> int:
    if not db_path:
        return 0
    p = Path(db_path)
    if not p.exists():
        return 0
    conn = sqlite3.connect(p)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM worldcup_stored_predictions").fetchone()[0])
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def _run_learning_feedback(*, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"status": "skipped_dry_run"}
    try:
        from worldcup_predictor.learning.self_learning_engine_v2 import build_self_learning_report

        report = build_self_learning_report()
        summary = report.to_dict() if hasattr(report, "to_dict") else report
        keys = list(summary.keys())[:12] if isinstance(summary, dict) else []
        return {"status": "ok", "summary_keys": keys, "total_records": getattr(report, "total_records", None)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _run_shadow_monitor(*, date_arg: str, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"status": "skipped_dry_run", "shadow_only": True}
    try:
        from worldcup_predictor.owner.daily_oddalerts_ecse_pipeline import (
            DailyPipelineConfig,
            run_daily_oddalerts_ecse_owner_pipeline,
        )

        cfg = DailyPipelineConfig(
            process_date=date_arg,
            window_days=7,
            download_gmail=False,
            import_csv=False,
            promote_odds_safe=False,
            run_monitor=True,
            dry_run_promotion=True,
            pipeline_tag="production-pipeline-shadow",
        )
        out = run_daily_oddalerts_ecse_owner_pipeline(cfg)
        return {
            "status": "ok",
            "shadow_only": True,
            "run_id": out.run_id,
            "monitor": out.monitor,
            "recommendation": out.final_recommendation,
        }
    except Exception as exc:
        return {"status": "error", "shadow_only": True, "error": str(exc)}


def _cycle_step(
    *,
    date_arg: str,
    config: PipelineConfig,
    skip_result_sync: bool,
    fetch_odds: bool,
    force_predictions: bool,
) -> dict[str, Any]:
    from worldcup_predictor.owner_daily.pipeline.orchestrator import DailyPipelineConfig, run_daily_pipeline

    pipeline_cfg = DailyPipelineConfig(
        date_arg=date_arg,
        timezone=config.timezone,
        limit=config.limit,
        dry_run=config.dry_run,
        only_missing=True,
        force_refresh=False,
        fetch_missing_odds=fetch_odds or config.refresh_stale_odds,
        include_shadow=False,
        skip_result_sync=skip_result_sync,
        force_predictions=force_predictions,
        max_api_football_calls=config.max_api_football_calls,
        max_oddalerts_calls=config.max_oddalerts_calls,
        max_sportmonks_calls=config.max_sportmonks_calls,
        no_provider_calls=config.dry_run,
        refresh_stale_odds=config.refresh_stale_odds,
        max_odds_provider_calls=config.max_odds_provider_calls,
        strict_fresh_odds=config.strict_fresh_odds,
        fixture_id=config.fixture_id,
        discovery_scope="owner",
        emit_evaluation_report=not skip_result_sync,
        use_fixture_drain=True,
        drain_concurrency=config.drain_concurrency,
    )
    result = run_daily_pipeline(pipeline_cfg)
    return result.to_dict()


def _results_step(*, config: PipelineConfig, settings: Settings) -> dict[str, Any]:
    keys = list(DAILY_SUPPORTED_COMPETITIONS)
    sync = run_daily_result_sync_and_evaluation(
        competition_keys=keys,
        settings=settings,
        dry_run=config.dry_run,
        force=False,
    )
    auto = {}
    league_batches = {}
    if not config.dry_run:
        try:
            ev = run_production_auto_evaluation(settings=settings, competition_key="world_cup_2026", limit=200)
            auto = {
                "evaluated": ev.evaluated,
                "skipped": ev.skipped,
                "errors": ev.errors,
            }
        except Exception as exc:
            auto = {"error": str(exc)}
        try:
            league_batches = evaluate_all_pending_frozen_batches(settings=settings)
        except Exception as exc:
            league_batches = {"error": str(exc)}
    return {
        "result_sync": sync.to_dict(),
        "worldcup_auto_eval": auto,
        "frozen_league_batch_eval": league_batches,
    }


def _writable_artifact_dir() -> Path:
    """Prefer canonical dir; fall back if root-owned / unwritable by service user."""
    primary = ARTIFACT_DIR
    try:
        primary.mkdir(parents=True, exist_ok=True)
        probe = primary / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return primary
    except OSError:
        fallback = Path("artifacts") / "production_pipeline_www"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _write_reports(result: PipelineRunResult) -> None:
    art_dir = _writable_artifact_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    payload = json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
    json_path = art_dir / f"production_pipeline_{result.mode}_{ts}.json"
    latest = art_dir / "production_pipeline_latest.json"
    try:
        json_path.write_text(payload, encoding="utf-8")
        latest.write_text(payload, encoding="utf-8")
    except OSError as exc:
        result.errors.append(f"report_write_failed:{exc}")
        result.report_paths = {"error": str(exc)}
        return

    md = _render_markdown(result)
    md_path = REPORT_MD
    try:
        md_path.write_text(md, encoding="utf-8")
    except OSError:
        md_path = art_dir / "PRODUCTION_PIPELINE_LAST_RUN.md"
        try:
            md_path.write_text(md, encoding="utf-8")
        except OSError:
            md_path = None

    result.report_paths = {
        "json": str(json_path),
        "json_latest": str(latest),
        "markdown": str(md_path) if md_path else "",
        "artifact_dir": str(art_dir),
    }


def _render_markdown(result: PipelineRunResult) -> str:
    counts = result.counts
    lines = [
        "# Production Pipeline — Last Run",
        "",
        f"- **Mode:** {result.mode}",
        f"- **Dry run:** {result.dry_run}",
        f"- **Started:** {result.started_at}",
        f"- **Finished:** {result.finished_at}",
        f"- **Recommendation:** {result.recommendation}",
        "",
        "## Counts",
        "",
        f"- Fixtures discovered: {counts.get('fixtures_discovered', 0)}",
        f"- Predictions created: {counts.get('predictions_created', 0)}",
        f"- Predictions reused: {counts.get('predictions_reused', 0)}",
        f"- Results synced: {counts.get('results_synced', 0)}",
        f"- Predictions evaluated: {counts.get('predictions_evaluated', 0)}",
        f"- Stored predictions (before→after): {counts.get('stored_before', 0)} → {counts.get('stored_after', 0)}",
        "",
        "## Provider calls",
        "",
        f"```json\n{json.dumps(result.provider_calls, indent=2)}\n```",
        "",
        "## Errors",
        "",
    ]
    lines.extend(f"- {e}" for e in result.errors) or lines.append("- none")
    return "\n".join(lines) + "\n"


def _derive_recommendation(result: PipelineRunResult) -> str:
    if result.skipped_overlap:
        return "IMPLEMENT_1_DO_NOT_ENABLE"
    if result.errors:
        return "IMPLEMENT_1_NEEDS_PIPELINE_FIX"
    if result.dry_run:
        return "IMPLEMENT_1_BACKEND_READY_TIMER_REVIEW_REQUIRED"
    if result.mode in ("results-only", "hourly", "predictions-only", "daily"):
        return "IMPLEMENT_1_READY_TO_ENABLE_TIMERS"
    return "IMPLEMENT_1_BACKEND_READY_TIMER_REVIEW_REQUIRED"


def run_production_prediction_pipeline(
    config: PipelineConfig,
    *,
    settings: Settings | None = None,
) -> PipelineRunResult:
    settings = settings or get_settings()
    result = PipelineRunResult(
        mode=config.mode,
        dry_run=config.dry_run,
        started_at=_utc_now(),
    )
    effective_mode = "results-only" if config.mode == "hourly" else config.mode

    lock = ProductionPipelineLock(LOCK_PATH)
    if config.skip_lock or config.dry_run:
        result.lock_acquired = True
    elif lock.acquire(wait_sec=float(config.lock_wait_sec), poll_sec=5.0):
        result.lock_acquired = True
        result.steps["lock"] = {"path": str(lock.path), "wait_sec": config.lock_wait_sec}
    else:
        # Busy after wait — not a permanent failure; leave queue for resume
        result.skipped_overlap = True
        result.errors.append("PIPELINE_LOCK_BUSY_AFTER_WAIT")
        result.recommendation = "IMPLEMENT_1_NEEDS_PIPELINE_FIX"
        result.finished_at = _utc_now()
        _write_reports(result)
        return result

    stored_before = _count_stored_predictions(settings.sqlite_path)
    result.counts["stored_before"] = stored_before

    try:
        if effective_mode in ("daily", "predictions-only"):
            fetch = effective_mode == "daily" and not config.dry_run
            # Daily prediction must not block on result sync (handoff to eval timer).
            skip_sync = (
                effective_mode == "predictions-only"
                or (effective_mode == "daily" and config.skip_result_sync_in_daily)
            )
            today_cycle = _cycle_step(
                date_arg=config.date_arg,
                config=config,
                skip_result_sync=skip_sync,
                fetch_odds=fetch,
                force_predictions=False,
            )
            result.steps["today_cycle"] = today_cycle
            result.counts["fixtures_discovered"] = int(
                today_cycle.get("discovery", {}).get("count")
                or today_cycle.get("discovery", {}).get("fixture_count")
                or len(today_cycle.get("discovery", {}).get("fixtures") or [])
            )
            pred = today_cycle.get("predictions") or {}
            created = int(pred.get("wde_generated") or 0) + int(pred.get("ecse_generated") or 0)
            reused = int(pred.get("wde_skipped") or 0) + int(pred.get("ecse_skipped") or 0)
            result.counts["predictions_created"] = created
            result.counts["predictions_reused"] = reused

            if effective_mode == "daily" and config.include_tomorrow:
                tomorrow_cycle = _cycle_step(
                    date_arg="tomorrow",
                    config=config,
                    skip_result_sync=True,
                    fetch_odds=False,
                    force_predictions=False,
                )
                result.steps["tomorrow_cycle"] = tomorrow_cycle
                t_pred = tomorrow_cycle.get("predictions") or {}
                result.counts["predictions_created"] += int(t_pred.get("wde_generated") or 0) + int(
                    t_pred.get("ecse_generated") or 0
                )
                result.counts["predictions_reused"] += int(t_pred.get("wde_skipped") or 0) + int(
                    t_pred.get("ecse_skipped") or 0
                )

        # Result sync / evaluation: separate from prediction drain for daily mode
        if effective_mode in ("hourly", "results-only", "eval-only") or (
            effective_mode == "daily" and not config.skip_result_sync_in_daily
        ):
            results = _results_step(config=config, settings=settings)
            result.steps["results_eval"] = results
            rs = results.get("result_sync") or {}
            result.counts["results_synced"] = int(rs.get("result_synced") or 0)
            result.counts["predictions_evaluated"] = int(rs.get("wde_evaluated") or 0) + int(
                rs.get("ecse_evaluated") or 0
            )
            wae = results.get("worldcup_auto_eval") or {}
            if isinstance(wae.get("evaluated"), int):
                result.counts["predictions_evaluated"] += wae["evaluated"]
        elif effective_mode == "daily":
            result.steps["results_eval"] = {
                "status": "DEFERRED_TO_FORWARD_EVAL_TIMER",
                "note": "daily prediction drain does not block on result sync",
            }

        if effective_mode == "eval-only" and not config.dry_run:
            owner_eval = run_owner_daily_prediction_and_eval(
                date_arg=config.date_arg,
                timezone=config.timezone,
                limit=config.limit,
                settings=settings,
            )
            result.steps["owner_daily_eval"] = owner_eval.to_dict()
            ye = owner_eval.yesterday_evaluation or {}
            result.counts["yesterday_evaluated"] = int(ye.get("evaluated_count") or 0)

        if effective_mode == "daily" and not config.dry_run:
            panel = build_owner_daily_control_panel(
                date_arg=config.date_arg,
                timezone=config.timezone,
            )
            result.steps["control_panel"] = panel.to_dict()

        result.learning = _run_learning_feedback(dry_run=config.dry_run)
        if config.include_shadow_monitor:
            result.shadow = _run_shadow_monitor(date_arg=config.date_arg, dry_run=config.dry_run)

        for step_name, step_data in result.steps.items():
            if isinstance(step_data, dict):
                rp = step_data.get("report_paths") or {}
                plog = rp.get("provider_log")
                if plog and Path(plog).exists():
                    try:
                        result.provider_calls[step_name] = json.loads(
                            Path(plog).read_text(encoding="utf-8")
                        )
                    except (json.JSONDecodeError, OSError):
                        pass

    except Exception as exc:
        result.errors.append(str(exc))
    finally:
        stored_after = _count_stored_predictions(settings.sqlite_path)
        result.counts["stored_after"] = stored_after
        if not config.skip_lock and not config.dry_run:
            lock.release()
        result.finished_at = _utc_now()
        result.recommendation = _derive_recommendation(result)
        _write_reports(result)

    return result

"""Canonical daily prediction → freeze → evaluation → reporting orchestrator."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.gpt_actions.owner_scope import competition_keys_for_scope
from worldcup_predictor.owner_daily.cycle import DailyCycleConfig, DailyCycleResult, run_daily_owner_cycle
from worldcup_predictor.owner_daily.data_completeness import check_all_fixtures_completeness
from worldcup_predictor.owner_daily.fixture_discovery import discover_daily_fixtures, resolve_target_date
from worldcup_predictor.owner_daily.pipeline.archive import append_report_index
from worldcup_predictor.owner_daily.pipeline.constants import (
    PIPELINE_BLOCKED,
    PIPELINE_COMPLETE,
    PIPELINE_NO_FIXTURES,
    PIPELINE_PARTIAL,
    PHASE,
)
from worldcup_predictor.owner_daily.pipeline.eligibility import build_eligibility_manifest
from worldcup_predictor.owner_daily.pipeline.forensics import write_forensic_records
from worldcup_predictor.owner_daily.pipeline.manifests import (
    write_eligibility_decisions,
    write_fixture_discovery,
    write_freeze_manifest,
    write_pipeline_status,
)
from worldcup_predictor.owner_daily.pipeline.reports import (
    build_evaluation_reports,
    build_owner_summary_fa,
    build_prematch_reports,
)
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider


@dataclass
class DailyPipelineConfig(DailyCycleConfig):
    discovery_scope: str = "owner"  # Tier A + B
    emit_evaluation_report: bool = True
    max_retry_before_kickoff: int = 2
    use_fixture_drain: bool = True
    drain_concurrency: int = 1
    drain_simulate_only: bool = False


@dataclass
class DailyPipelineResult:
    phase: str = PHASE
    report_date: str = ""
    pipeline_status: str = PIPELINE_PARTIAL
    cycle: DailyCycleResult | None = None
    artifact_paths: dict[str, str] = field(default_factory=dict)
    report_paths: dict[str, str] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "report_date": self.report_date,
            "pipeline_status": self.pipeline_status,
            "artifact_paths": self.artifact_paths,
            "report_paths": self.report_paths,
            "stats": self.stats,
            "cycle": self.cycle.to_dict() if self.cycle else None,
        }


def _index_predictions(
    cycle: DailyCycleResult,
    fixtures: list,
    *,
    settings: Settings,
) -> dict[int, dict[str, Any]]:
    """Merge cycle samples with post-run DB state for every discovered fixture."""
    from worldcup_predictor.owner_daily.report import _load_ecse, _load_wde

    by_fid: dict[int, dict[str, Any]] = {}
    pred = cycle.predictions or {}
    for item in (pred.get("generated_sample") or []) + (pred.get("skipped_sample") or []):
        fid = int(item.get("fixture_id") or 0)
        if not fid:
            continue
        bucket = by_fid.setdefault(fid, {})
        if item.get("engine") == "wde":
            bucket["wde"] = item
        elif item.get("engine") == "ecse":
            bucket["ecse"] = item
    for cap in pred.get("forward_eval_captures") or []:
        fid = int(cap.get("fixture_id") or 0)
        if fid:
            by_fid.setdefault(fid, {})["freeze"] = cap

    conn = connect(settings.sqlite_path)
    try:
        for fx in fixtures:
            fid = int(fx.provider_fixture_id)
            bucket = by_fid.setdefault(fid, {})
            if not bucket.get("wde"):
                wde = _load_wde(fid, settings, fx.competition_key)
                if wde:
                    bucket["wde"] = {"fixture_id": fid, "engine": "wde", "wde_execution_status": "executed", **wde}
            if not bucket.get("ecse"):
                ecse = _load_ecse(conn, fid)
                if ecse:
                    bucket["ecse"] = {
                        "fixture_id": fid,
                        "engine": "ecse",
                        "snapshot_write": "inserted",
                        **ecse,
                    }
    finally:
        conn.close()
    return by_fid


def _freeze_rows_for_date(report_date: str) -> list[dict[str, Any]]:
    ev = connect_eval_db(project_root())
    try:
        rows = ev.execute(
            """
            SELECT prediction_id, fixture_id, frozen_at, kickoff, prediction_scope,
                   validation_tier, evaluation_status, content_hash, freeze_status
            FROM frozen_predictions
            WHERE date(kickoff) = date(?)
            ORDER BY kickoff
            """,
            (report_date,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        ev.close()


def run_daily_pipeline(
    config: DailyPipelineConfig | None = None,
    *,
    settings: Settings | None = None,
) -> DailyPipelineResult:
    """Highest-priority daily lifecycle — wraps owner_daily cycle + manifests + reports."""
    config = config or DailyPipelineConfig()
    settings = settings or get_settings()
    target = resolve_target_date(config.date_arg, config.timezone)
    report_date = target.isoformat()

    # Owner scope = Tier A production competitions + Tier B shadow leagues
    keys = config.competition_keys or competition_keys_for_scope("owner")
    config.competition_keys = keys

    result = DailyPipelineResult(report_date=report_date)

    discovery_pre = discover_daily_fixtures(
        date_arg=config.date_arg,
        timezone=config.timezone,
        competition_keys=keys,
        limit=config.limit,
        settings=settings,
        fetch_if_missing=not config.no_provider_calls,
        dry_run=config.dry_run,
    )
    fixtures = discovery_pre.fixtures

    disc_path = write_fixture_discovery(
        report_date,
        fixtures,
        timezone=config.timezone,
        discovery_meta=discovery_pre.to_dict(),
    )
    result.artifact_paths["fixture_discovery"] = str(disc_path)

    if not fixtures:
        result.pipeline_status = PIPELINE_NO_FIXTURES
        write_pipeline_status(report_date, result.to_dict())
        return result

    # When drain is enabled, cycle handles discovery/odds/fetch only; predict+freeze via drain.
    if config.use_fixture_drain:
        config.skip_predictions = True

    cycle = run_daily_owner_cycle(config, settings=settings)
    result.cycle = cycle

    # Refresh fixtures from cycle discovery (may include provider fetch)
    cycle_fixtures = discovery_pre.fixtures
    try:
        from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture as _DF

        raw = (cycle.discovery or {}).get("fixtures") or []
        if raw:
            rebuilt: list = []
            for item in raw:
                if isinstance(item, dict):
                    rebuilt.append(
                        _DF(
                            fixture_id=int(item.get("fixture_id") or item.get("provider_fixture_id") or 0),
                            provider_fixture_id=int(item.get("provider_fixture_id") or item.get("fixture_id") or 0),
                            competition_key=str(item.get("competition_key") or ""),
                            home_team=str(item.get("home_team") or ""),
                            away_team=str(item.get("away_team") or ""),
                            kickoff_utc=str(item.get("kickoff_utc") or ""),
                            status=str(item.get("status") or "NS"),
                            season=item.get("season"),
                            coverage_sources=list(item.get("coverage_sources") or ["local_db"]),
                        )
                    )
            if rebuilt:
                cycle_fixtures = rebuilt
                fixtures = rebuilt
    except Exception:
        pass

    drain_stats: dict[str, Any] = {"enabled": False}
    if config.use_fixture_drain:
        from worldcup_predictor.owner_daily.pipeline.drain_ledger import DrainLedger
        from worldcup_predictor.owner_daily.pipeline.drain_runner import DrainConfig, drain_daily_queue

        with DrainLedger() as ledger:
            drain = drain_daily_queue(
                fixtures,
                config=DrainConfig(
                    report_date=report_date,
                    concurrency=max(1, int(config.drain_concurrency or 1)),
                    dry_run=config.dry_run,
                    simulate_only=bool(config.drain_simulate_only or config.dry_run),
                    strict_fresh_odds=config.strict_fresh_odds,
                    force_predictions=config.force_predictions,
                ),
                ledger=ledger,
                settings=settings,
            )
        drain_stats = drain.to_dict()
        result.artifact_paths["fixture_drain"] = str(
            Path("data") / "daily_fixture_drain" / "ledger.db"
        )
        # Merge drain outcomes into cycle.predictions for eligibility indexing
        cycle.predictions = {
            **(cycle.predictions or {}),
            "fixture_drain": drain_stats,
            "wde_generated": sum(
                1
                for i in drain.items
                if i.get("queue_state") in ("FROZEN", "COMPLETED")
                and i.get("prediction_status") in ("OK", "PARTIAL", "SIMULATED_NO_WRITE")
            ),
            "ecse_generated": sum(
                1
                for i in drain.items
                if i.get("queue_state") in ("FROZEN", "COMPLETED")
            ),
            "forward_eval_captures": [
                {
                    "fixture_id": i.get("fixture_id"),
                    "capture_status": "reused"
                    if i.get("queue_state") == "FROZEN" and i.get("freeze_id")
                    else i.get("queue_state"),
                    "freeze_id": i.get("freeze_id"),
                }
                for i in drain.items
                if i.get("freeze_id")
            ],
        }

    conn = connect(settings.sqlite_path)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    sm = SportmonksProvider(settings)
    oa = OddAlertsClient()
    completeness_list = check_all_fixtures_completeness(
        conn,
        repo,
        fixtures,
        api_football_configured=settings.api_football_configured,
        sportmonks_configured=sm.is_configured,
        oddalerts_configured=oa.is_configured,
    )
    conn.close()
    comp_map = {c.fixture_id: c for c in completeness_list}

    pred_by_fid = _index_predictions(cycle, fixtures, settings=settings)
    eligibility = build_eligibility_manifest(
        fixtures,
        comp_map,
        pred_by_fid,
        timezone=config.timezone,
    )
    elig_path = write_eligibility_decisions(report_date, eligibility)
    result.artifact_paths["eligibility_decisions"] = str(elig_path)

    # Optional owner-only Correct Score odds enrichment (cache-first; never blocks prediction)
    cs_odds_stats: dict[str, Any] = {
        "status": "CS_ODDS_UNAVAILABLE",
        "prediction_jobs_created": 0,
        "blocked_prediction": False,
    }
    try:
        from worldcup_predictor.research.correct_score_odds.pipeline_hook import (
            enrich_correct_score_odds,
        )

        cs_conn = connect(settings.sqlite_path)
        try:
            cs_enrich = enrich_correct_score_odds(
                cs_conn,
                [int(fx.provider_fixture_id) for fx in fixtures],
                enabled=True,
            )
        finally:
            cs_conn.close()
        cs_odds_stats = {
            "status": cs_enrich.get("status"),
            "lines_inserted": (cs_enrich.get("extract") or {}).get("lines_inserted"),
            "prediction_jobs_created": cs_enrich.get("prediction_jobs_created", 0),
            "blocked_prediction": False,
        }
    except Exception as exc:
        cs_odds_stats = {
            "status": "CS_ODDS_UNAVAILABLE",
            "error": str(exc)[:200],
            "blocked_prediction": False,
            "prediction_jobs_created": 0,
        }

    freeze_rows = _freeze_rows_for_date(report_date)
    freeze_path = write_freeze_manifest(report_date, freeze_rows)
    result.artifact_paths["freeze_manifest"] = str(freeze_path)

    # Owner-only TeamFormH2HForensicAgent — after freeze, non-blocking, read-only
    forensic_stats: dict[str, Any] = {"status": "SKIPPED", "blocked_prediction": False}
    try:
        from worldcup_predictor.research.team_form_h2h_forensic.agent import run_forensic_batch

        forensic_out = run_forensic_batch(report_date=report_date, settings=settings)
        forensic_stats = {
            "status": forensic_out.get("final_status"),
            "fixture_count": forensic_out.get("fixture_count"),
            "artifact_path": forensic_out.get("artifact_path"),
            "report_fa_path": forensic_out.get("report_fa_path"),
            "blocked_prediction": False,
        }
        if forensic_out.get("artifact_path"):
            result.artifact_paths["team_form_h2h_forensics"] = str(forensic_out["artifact_path"])
        if forensic_out.get("report_fa_path"):
            result.report_paths["team_form_h2h_forensic_fa_md"] = str(forensic_out["report_fa_path"])
    except Exception as exc:
        forensic_stats = {
            "status": "TEAM_FORM_H2H_FORENSIC_ERROR",
            "error": str(exc)[:200],
            "blocked_prediction": False,
        }

    prematch = build_prematch_reports(
        report_date=report_date,
        timezone_name=config.timezone,
        fixtures=fixtures,
        eligibility=eligibility,
        completeness=completeness_list,
        settings=settings,
    )
    result.report_paths["prematch_md"] = str(prematch.prematch_md)
    result.report_paths["prematch_fa_md"] = str(prematch.prematch_fa_md)
    if prematch.legacy_md:
        result.report_paths["legacy_md"] = str(prematch.legacy_md)

    if config.emit_evaluation_report:
        eval_reports = build_evaluation_reports(
            report_date=report_date,
            timezone_name=config.timezone,
            settings=settings,
        )
        if eval_reports and eval_reports.evaluation_md:
            result.report_paths["evaluation_md"] = str(eval_reports.evaluation_md)
            result.report_paths["evaluation_fa_md"] = str(eval_reports.evaluation_fa_md)

    eligible_n = sum(1 for e in eligibility if e.get("eligible"))
    blocked_n = len(eligibility) - eligible_n
    frozen_n = len(freeze_rows)
    partial_n = sum(1 for e in eligibility if e.get("prediction_completeness") == "PARTIAL")

    stats = {
        "discovered": len(fixtures),
        "eligible": eligible_n,
        "blocked": blocked_n,
        "frozen": frozen_n,
        "partial_predictions": partial_n,
        "wde_generated": (cycle.predictions or {}).get("wde_generated"),
        "ecse_generated": (cycle.predictions or {}).get("ecse_generated"),
        "correct_score_odds": cs_odds_stats,
        "team_form_h2h_forensics": forensic_stats,
        "fixture_drain": drain_stats,
    }
    result.stats = stats

    # Drain reconciliation: queue must reach terminal for all items
    if config.use_fixture_drain and isinstance(drain_stats, dict):
        rec = drain_stats.get("reconcile") or {}
        if rec.get("pending", 0) == 0 and rec.get("total", 0) > 0:
            if frozen_n + blocked_n + int(rec.get("FAILED_FINAL") or 0) + int(
                rec.get("POST_KICKOFF_SKIPPED") or 0
            ) + int(rec.get("COMPLETED") or 0) + int(rec.get("FROZEN") or 0) >= int(rec.get("total") or 0):
                result.pipeline_status = PIPELINE_COMPLETE

    summary_path = build_owner_summary_fa(
        report_date=report_date,
        eligibility=eligibility,
        stats=stats,
    )
    result.report_paths["owner_summary_fa_md"] = str(summary_path)

    forensic_path = write_forensic_records(report_date, eligibility, pred_by_fid, settings=settings)
    if forensic_path:
        result.artifact_paths["forensics"] = str(forensic_path)

    # Pipeline completeness
    all_status = all(e.get("lifecycle_status") for e in eligibility)
    if all_status and frozen_n >= eligible_n and blocked_n + eligible_n == len(fixtures):
        result.pipeline_status = PIPELINE_COMPLETE
    elif blocked_n == len(fixtures):
        result.pipeline_status = PIPELINE_BLOCKED
    else:
        result.pipeline_status = PIPELINE_PARTIAL

    append_report_index(
        report_date=report_date,
        pipeline_status=result.pipeline_status,
        stats=stats,
        report_paths=result.report_paths,
    )
    status_path = write_pipeline_status(report_date, result.to_dict())
    result.artifact_paths["pipeline_status"] = str(status_path)
    return result

"""FastAPI application for GPT Actions REST bridge."""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from worldcup_predictor.gpt_actions.audit import GptActionsAuditLogger, new_request_id
from worldcup_predictor.gpt_actions.auth import require_gpt_actions_auth
from worldcup_predictor.gpt_actions.config import GptActionsConfig, load_gpt_actions_config
from worldcup_predictor.gpt_actions.delegation import (
    discover_today_matches,
    filter_matches_by_odds,
    get_daily_evaluation_report,
    get_daily_prediction_report,
    get_fixture_frozen_evaluation,
    get_latest_daily_evaluation_report,
    get_latest_prediction_report,
    get_monthly_accuracy_summary,
    get_prediction_report_by_date,
    get_system_status,
    get_weekly_frozen_evaluation_report,
    list_today_matches_broad,
)
from worldcup_predictor.gpt_actions.job_status import build_job_create_fields, build_job_status_fields
from worldcup_predictor.gpt_actions.jobs import JobStore
from worldcup_predictor.gpt_actions.policies import validate_iso_date
from worldcup_predictor.gpt_actions.rate_limit import RateLimiter
from worldcup_predictor.gpt_actions.schemas import (
    DiscoverMatchesQuery,
    FilterMatchesRequest,
    JobCreateResponse,
    JobStatusResponse,
    ListMatchesQuery,
    StartPredictionJobRequest,
)
from worldcup_predictor.gpt_actions.worker import enqueue_prediction_job

API_PREFIX = "/api/gpt-actions/v1"


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _trim_payload(payload: dict[str, Any], max_chars: int) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=False)
    if len(encoded) <= max_chars:
        return payload
    trimmed = dict(payload)
    if "content" in trimmed and isinstance(trimmed["content"], str):
        content = trimmed["content"]
        budget = max(1000, max_chars - 2000)
        trimmed["content"] = content[:budget] + "\n...[truncated]"
    if "predictions" in trimmed and isinstance(trimmed["predictions"], list):
        trimmed["predictions"] = trimmed["predictions"][:5]
        trimmed["truncated"] = True
    return trimmed


def create_app(config: GptActionsConfig | None = None) -> FastAPI:
    cfg = config or load_gpt_actions_config()
    app = FastAPI(
        title="WorldCup Predictor GPT Actions",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.gpt_actions_config = cfg
    app.state.job_store = JobStore(cfg.job_store_dir, max_retained=cfg.max_jobs_retained)
    app.state.audit_logger = GptActionsAuditLogger(cfg.audit_log_path)
    app.state.rate_limiter = RateLimiter(limit_per_minute=cfg.rate_limit_per_minute)

    @app.middleware("http")
    async def gpt_actions_middleware(request: Request, call_next):
        if not request.url.path.startswith(API_PREFIX):
            return await call_next(request)
        request_id = request.headers.get("X-Request-ID") or new_request_id()
        request.state.request_id = request_id
        started = time.perf_counter()
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        duration_ms = int((time.perf_counter() - started) * 1000)
        app.state.audit_logger.write(
            request_id=request_id,
            route=request.url.path,
            method=request.method,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if not request.url.path.startswith(API_PREFIX):
            return await call_next(request)
        if not app.state.rate_limiter.allow(_client_ip(request)):
            return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})
        return await call_next(request)

    auth_dep = [Depends(require_gpt_actions_auth)]

    @app.get(f"{API_PREFIX}/system/status", operation_id="getSystemStatus", dependencies=auth_dep)
    def get_system_status_route() -> dict[str, Any]:
        return get_system_status()

    @app.get(
        f"{API_PREFIX}/matches/discover",
        operation_id="discoverTodayMatches",
        dependencies=auth_dep,
    )
    def discover_today_matches_route(
        date: str, timezone: str = "Europe/Vienna", scope: str = "production"
    ) -> dict[str, Any]:
        try:
            DiscoverMatchesQuery(date=date, timezone=timezone, scope=scope)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return discover_today_matches(target_date=date, timezone=timezone, scope=scope)

    @app.get(
        f"{API_PREFIX}/matches/list",
        operation_id="listTodayMatches",
        dependencies=auth_dep,
    )
    def list_today_matches_route(
        date: str,
        timezone: str = "Europe/Vienna",
        listing_filter: str = "all",
    ) -> dict[str, Any]:
        try:
            ListMatchesQuery(date=date, timezone=timezone, listing_filter=listing_filter)  # type: ignore[arg-type]
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return list_today_matches_broad(
            target_date=date, timezone=timezone, listing_filter=listing_filter
        )

    @app.post(
        f"{API_PREFIX}/matches/filter-odds",
        operation_id="filterMatchesByOdds",
        dependencies=auth_dep,
    )
    def filter_matches_route(body: FilterMatchesRequest) -> dict[str, Any]:
        return filter_matches_by_odds(
            target_date=body.date,
            timezone=body.timezone,
            home_odds_gt=body.filter.home_odds_gt,
            away_odds_gt=body.filter.away_odds_gt,
            scope=body.scope,
        )

    @app.post(
        f"{API_PREFIX}/prediction-jobs",
        operation_id="startPredictionJob",
        dependencies=auth_dep,
        status_code=202,
    )
    def start_prediction_job_route(request: Request, body: StartPredictionJobRequest):
        idempotency_key = request.headers.get("Idempotency-Key")
        if idempotency_key:
            existing = app.state.job_store.get_by_idempotency_key(idempotency_key)
            if existing:
                if existing["status"] in ("queued", "running"):
                    return JobCreateResponse(**build_job_create_fields(existing, poll_after_seconds=cfg.poll_after_seconds))
                fields = build_job_status_fields(existing, poll_after_seconds=cfg.poll_after_seconds)
                result = fields.get("result")
                if isinstance(result, dict):
                    fields["result"] = _trim_payload(result, cfg.max_response_chars)
                return JobStatusResponse(**fields)
        try:
            record = app.state.job_store.create(
                payload=body.model_dump(),
                idempotency_key=idempotency_key,
            )
        except RuntimeError as exc:
            if str(exc) == "job_concurrency_limit":
                raise HTTPException(status_code=429, detail="another prediction job is active") from exc
            raise
        enqueue_prediction_job(record["job_id"], store=app.state.job_store, config=cfg)
        return JobCreateResponse(**build_job_create_fields(record, poll_after_seconds=cfg.poll_after_seconds))

    @app.get(
        f"{API_PREFIX}/prediction-jobs/{{job_id}}",
        operation_id="getPredictionJob",
        dependencies=auth_dep,
    )
    def get_prediction_job_route(job_id: str) -> JobStatusResponse:
        record = app.state.job_store.get(job_id)
        if not record:
            raise HTTPException(status_code=404, detail="job not found")
        fields = build_job_status_fields(record, poll_after_seconds=cfg.poll_after_seconds)
        result = fields.get("result")
        if isinstance(result, dict):
            fields["result"] = _trim_payload(result, cfg.max_response_chars)
        return JobStatusResponse(**fields)

    @app.get(
        f"{API_PREFIX}/reports/latest",
        operation_id="getLatestPredictionReport",
        dependencies=auth_dep,
    )
    def latest_report_route() -> dict[str, Any]:
        report = get_latest_prediction_report(max_bytes=cfg.max_response_chars)
        return _trim_payload(report, cfg.max_response_chars)

    @app.get(
        f"{API_PREFIX}/reports/{{report_date}}",
        operation_id="getPredictionReportByDate",
        dependencies=auth_dep,
    )
    def report_by_date_route(report_date: str) -> dict[str, Any]:
        try:
            validate_iso_date(report_date, field="report_date")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        report = get_prediction_report_by_date(report_date=report_date, max_bytes=cfg.max_response_chars)
        return _trim_payload(report, cfg.max_response_chars)

    @app.get(
        f"{API_PREFIX}/reports/daily/predictions/{{report_date}}",
        operation_id="getDailyPredictionReport",
        dependencies=auth_dep,
    )
    def daily_prediction_report_route(report_date: str) -> dict[str, Any]:
        try:
            validate_iso_date(report_date, field="report_date")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _trim_payload(
            get_daily_prediction_report(report_date=report_date, max_bytes=cfg.max_response_chars),
            cfg.max_response_chars,
        )

    @app.get(
        f"{API_PREFIX}/reports/daily/evaluation/{{report_date}}",
        operation_id="getDailyEvaluationReport",
        dependencies=auth_dep,
    )
    def daily_evaluation_report_route(report_date: str) -> dict[str, Any]:
        try:
            validate_iso_date(report_date, field="report_date")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _trim_payload(
            get_daily_evaluation_report(report_date=report_date, max_bytes=cfg.max_response_chars),
            cfg.max_response_chars,
        )

    @app.get(
        f"{API_PREFIX}/reports/daily/predictions/latest",
        operation_id="getLatestDailyPredictionReport",
        dependencies=auth_dep,
    )
    def latest_daily_prediction_route() -> dict[str, Any]:
        return _trim_payload(get_latest_prediction_report(max_bytes=cfg.max_response_chars), cfg.max_response_chars)

    @app.get(
        f"{API_PREFIX}/reports/daily/evaluation/latest",
        operation_id="getLatestDailyEvaluationReport",
        dependencies=auth_dep,
    )
    def latest_daily_evaluation_route() -> dict[str, Any]:
        return _trim_payload(
            get_latest_daily_evaluation_report(max_bytes=cfg.max_response_chars),
            cfg.max_response_chars,
        )

    @app.get(
        f"{API_PREFIX}/reports/weekly/frozen-evaluation",
        operation_id="getWeeklyFrozenEvaluationReport",
        dependencies=auth_dep,
    )
    def weekly_frozen_route(end_date: str | None = None) -> dict[str, Any]:
        if end_date:
            try:
                validate_iso_date(end_date, field="end_date")
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _trim_payload(
            get_weekly_frozen_evaluation_report(end_date=end_date, max_bytes=cfg.max_response_chars),
            cfg.max_response_chars,
        )

    @app.get(
        f"{API_PREFIX}/reports/monthly/accuracy",
        operation_id="getMonthlyAccuracySummary",
        dependencies=auth_dep,
    )
    def monthly_accuracy_route(year: int, month: int) -> dict[str, Any]:
        return _trim_payload(get_monthly_accuracy_summary(year=year, month=month), cfg.max_response_chars)

    @app.get(
        f"{API_PREFIX}/fixtures/{{fixture_id}}/frozen-evaluation",
        operation_id="getFixtureFrozenEvaluation",
        dependencies=auth_dep,
    )
    def fixture_frozen_eval_route(fixture_id: int) -> dict[str, Any]:
        return _trim_payload(get_fixture_frozen_evaluation(fixture_id=fixture_id), cfg.max_response_chars)

    @app.get(
        f"{API_PREFIX}/research/l2f-true-forward-observability",
        operation_id="getL2fTrueForwardObservability",
        dependencies=auth_dep,
    )
    def l2f_true_forward_observability_route() -> dict[str, Any]:
        """Owner-auth GPT Actions read-only observability for L2-F true-forward cohort."""
        import sqlite3

        from worldcup_predictor.config.env_loading import project_root
        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.research.infra_l2f_forward.observability import build_observability_report
        from worldcup_predictor.research.infra_l2f_forward.readiness import evaluate_readiness

        settings = get_settings()
        fi = sqlite3.connect(str(settings.sqlite_path))
        fi.row_factory = sqlite3.Row
        ev = sqlite3.connect(str(project_root() / "data/evaluation/forward_prediction_tracking.db"))
        ev.row_factory = sqlite3.Row
        try:
            obs = build_observability_report(fi, ev)
            ready = evaluate_readiness(fi, ev, obs=obs)
            return _trim_payload(
                {
                    "owner_only": True,
                    "read_only": True,
                    "secrets_redacted": True,
                    "observability": obs,
                    "readiness": ready,
                },
                cfg.max_response_chars,
            )
        finally:
            fi.close()
            ev.close()

    return app


app = create_app()

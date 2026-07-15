"""GPT Actions bridge policy — explicit REST allowlist only."""

from __future__ import annotations

import re
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

APPROVED_OPERATION_IDS: frozenset[str] = frozenset(
    {
        "getSystemStatus",
        "discoverTodayMatches",
        "listTodayMatches",
        "filterMatchesByOdds",
        "startPredictionJob",
        "getPredictionJob",
        "getLatestPredictionReport",
        "getPredictionReportByDate",
        "getDailyPredictionReport",
        "getDailyEvaluationReport",
        "getLatestDailyPredictionReport",
        "getLatestDailyEvaluationReport",
        "getWeeklyFrozenEvaluationReport",
        "getMonthlyAccuracySummary",
        "getFixtureFrozenEvaluation",
    }
)

APPROVED_ROUTES: frozenset[str] = frozenset(
    {
        "GET /api/gpt-actions/v1/system/status",
        "GET /api/gpt-actions/v1/matches/discover",
        "GET /api/gpt-actions/v1/matches/list",
        "POST /api/gpt-actions/v1/matches/filter-odds",
        "POST /api/gpt-actions/v1/prediction-jobs",
        "GET /api/gpt-actions/v1/prediction-jobs/{job_id}",
        "GET /api/gpt-actions/v1/reports/latest",
        "GET /api/gpt-actions/v1/reports/{report_date}",
        "GET /api/gpt-actions/v1/reports/daily/predictions/{report_date}",
        "GET /api/gpt-actions/v1/reports/daily/evaluation/{report_date}",
        "GET /api/gpt-actions/v1/reports/daily/predictions/latest",
        "GET /api/gpt-actions/v1/reports/daily/evaluation/latest",
        "GET /api/gpt-actions/v1/reports/weekly/frozen-evaluation",
        "GET /api/gpt-actions/v1/reports/monthly/accuracy",
        "GET /api/gpt-actions/v1/fixtures/{fixture_id}/frozen-evaluation",
    }
)

FORBIDDEN_ROUTE_PATTERNS: tuple[str, ...] = (
    "/mcp",
    "/execute",
    "/tools",
    "/shell",
    "/sql",
    "/admin",
    "/docs",
    "/openapi.json",
    "/redoc",
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_iso_date(value: str, *, field: str = "date") -> date:
    if not _ISO_DATE.match(str(value or "").strip()):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def validate_timezone(value: str) -> str:
    tz = str(value or "").strip()
    if not tz:
        raise ValueError("timezone is required")
    try:
        ZoneInfo(tz)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {tz}") from exc
    return tz


def validate_odds_threshold(value: float | None, *, field: str) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if num < 1.0 or num > 100.0:
        raise ValueError(f"{field} out of bounds")
    return num


def validate_select_best(value: int) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("select_best must be an integer") from exc
    if num < 1 or num > 10:
        raise ValueError("select_best must be between 1 and 10")
    return num


def validate_fixture_id_list(fixture_ids: list[int], *, max_count: int) -> list[int]:
    if not fixture_ids:
        raise ValueError("fixture_ids must not be empty")
    if len(fixture_ids) > max_count:
        raise ValueError(f"fixture_ids exceeds max {max_count}")
    out: list[int] = []
    for fid in fixture_ids:
        try:
            num = int(fid)
        except (TypeError, ValueError) as exc:
            raise ValueError("fixture_id must be integer") from exc
        if num <= 0:
            raise ValueError("fixture_id must be positive")
        out.append(num)
    return out

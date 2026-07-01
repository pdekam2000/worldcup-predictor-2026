"""Date resolution for owner predict/eval workflow."""

from __future__ import annotations

from datetime import date, timedelta

from worldcup_predictor.owner_daily.fixture_discovery import resolve_target_date
from worldcup_predictor.owner_predict_eval.constants import SUPPORTED_DATE_FORMATS


def resolve_process_date(date_arg: str, timezone: str = "Europe/Vienna") -> date:
    return resolve_target_date(date_arg, timezone)


def date_tag(d: date) -> str:
    return d.isoformat().replace("-", "")


def yesterday_of(target: date) -> date:
    return target - timedelta(days=1)


def tomorrow_of(target: date) -> date:
    return target + timedelta(days=1)


def resolve_yesterday_date(date_arg: str, timezone: str = "Europe/Vienna") -> date:
    """Resolve the calendar date to evaluate when --date is passed to yesterday eval."""
    key = date_arg.strip().lower()
    if key == "yesterday":
        return resolve_process_date("yesterday", timezone)
    if key in ("today", "now", "tomorrow"):
        return yesterday_of(resolve_process_date(date_arg, timezone))
    return resolve_process_date(date_arg, timezone)


def invalid_date_error_message(date_arg: str) -> str:
    return (
        f"Invalid date argument '{date_arg}'. Supported formats: {SUPPORTED_DATE_FORMATS}"
    )

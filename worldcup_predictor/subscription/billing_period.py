"""Billing cycle period helpers — Phase 38A."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import NamedTuple


class BillingPeriod(NamedTuple):
    key: str
    start: datetime
    end: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _add_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, _days_in_month(year, month))
    return dt.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        nxt = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    cur = datetime(year, month, 1, tzinfo=timezone.utc)
    return (nxt - cur).days


def resolve_billing_period(anchor: datetime | None, *, now: datetime | None = None) -> BillingPeriod:
    """Monthly cycle anchored on subscription start (or account creation)."""
    now = now or _utc_now()
    if anchor is None:
        anchor = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    start = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    while True:
        nxt = _add_months(start, 1)
        if nxt > now:
            period_key = start.strftime("%Y-%m-%d")
            return BillingPeriod(key=period_key, start=start, end=nxt - timedelta(microseconds=1))
        start = nxt

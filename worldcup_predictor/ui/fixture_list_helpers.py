"""Date grouping and quick filters for fixture lists."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

FilterKey = Literal["today", "tomorrow", "next_3_days", "favorites", "all"]


def _kickoff_dt(fixture: Any) -> datetime | None:
    kickoff = getattr(fixture, "kickoff_time", None) or getattr(fixture, "kickoff_utc", None)
    if kickoff is None:
        return None
    if isinstance(kickoff, datetime):
        if kickoff.tzinfo is None:
            return kickoff.replace(tzinfo=timezone.utc)
        return kickoff
    if isinstance(kickoff, str):
        try:
            dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None
    return None


def local_kickoff_date(fixture: Any) -> date | None:
    dt = _kickoff_dt(fixture)
    if dt is None:
        return None
    return dt.astimezone().date()


def is_kickoff_today(fixture: Any, *, today: date | None = None) -> bool:
    kd = local_kickoff_date(fixture)
    if kd is None:
        return False
    ref = today or date.today()
    return kd == ref


def filter_fixtures(
    fixtures: list[Any],
    filter_key: FilterKey,
    *,
    favorite_ids: set[int] | None = None,
    today: date | None = None,
) -> list[Any]:
    ref = today or date.today()
    tomorrow = ref + timedelta(days=1)
    end_3 = ref + timedelta(days=3)
    favs = favorite_ids or set()

    if filter_key == "all":
        return list(fixtures)
    if filter_key == "favorites":
        return [
            f
            for f in fixtures
            if int(getattr(f, "fixture_id", None) or getattr(f, "id", 0) or 0) in favs
        ]
    if filter_key == "today":
        return [f for f in fixtures if local_kickoff_date(f) == ref]
    if filter_key == "tomorrow":
        return [f for f in fixtures if local_kickoff_date(f) == tomorrow]
    if filter_key == "next_3_days":
        return [
            f
            for f in fixtures
            if (kd := local_kickoff_date(f)) is not None and ref <= kd <= end_3
        ]
    return list(fixtures)


def group_fixtures_by_date(
    fixtures: list[Any],
    *,
    today: date | None = None,
    locale_label_today: str = "Today",
    locale_label_tomorrow: str = "Tomorrow",
) -> list[tuple[str, list[Any]]]:
    ref = today or date.today()
    tomorrow = ref + timedelta(days=1)
    buckets: dict[date, list[Any]] = defaultdict(list)
    no_date: list[Any] = []

    for fixture in fixtures:
        kd = local_kickoff_date(fixture)
        if kd is None:
            no_date.append(fixture)
            continue
        buckets[kd].append(fixture)

    groups: list[tuple[str, list[Any]]] = []
    for kd in sorted(buckets.keys()):
        if kd == ref:
            label = f"{locale_label_today} — {kd.strftime('%d %b %Y')}"
        elif kd == tomorrow:
            label = f"{locale_label_tomorrow} — {kd.strftime('%d %b %Y')}"
        else:
            label = kd.strftime("%d %b %Y")
        groups.append((label, buckets[kd]))

    if no_date:
        groups.append(("Date TBD", no_date))
    return groups


def local_kickoff_time_display(fixture: Any) -> str:
    dt = _kickoff_dt(fixture)
    if dt is None:
        return "—"
    return dt.astimezone().strftime("%H:%M")

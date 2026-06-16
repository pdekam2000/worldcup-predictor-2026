"""Timezone-aware kickoff display — user local, venue local, UTC."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t

# World Cup 2026 host cities (extend as API data arrives)
_CITY_TIMEZONES: dict[str, str] = {
    "new york": "America/New_York",
    "new york city": "America/New_York",
    "east rutherford": "America/New_York",
    "philadelphia": "America/New_York",
    "boston": "America/New_York",
    "atlanta": "America/New_York",
    "miami": "America/New_York",
    "miami gardens": "America/New_York",
    "orlando": "America/New_York",
    "charlotte": "America/New_York",
    "nashville": "America/Chicago",
    "dallas": "America/Chicago",
    "arlington": "America/Chicago",
    "houston": "America/Chicago",
    "kansas city": "America/Chicago",
    "cincinnati": "America/New_York",
    "los angeles": "America/Los_Angeles",
    "inglewood": "America/Los_Angeles",
    "santa clara": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "guadalajara": "America/Mexico_City",
    "mexico city": "America/Mexico_City",
    "monterrey": "America/Monterrey",
    "toronto": "America/Toronto",
    "vancouver": "America/Vancouver",
}

_COUNTRY_TIMEZONES: dict[str, str] = {
    "usa": "America/New_York",
    "united states": "America/New_York",
    "us": "America/New_York",
    "mexico": "America/Mexico_City",
    "canada": "America/Toronto",
}


@dataclass(frozen=True)
class KickoffDisplay:
    user_local: str
    user_local_label: str
    venue_local: str | None
    venue_label: str | None
    utc: str
    venue_unavailable: bool


def _aware_utc(kickoff: datetime) -> datetime:
    if kickoff.tzinfo is None:
        return kickoff.replace(tzinfo=timezone.utc)
    return kickoff.astimezone(timezone.utc)


def resolve_venue_timezone(*, city: str | None = None, country: str | None = None) -> str | None:
    if city:
        key = city.strip().lower()
        if key in _CITY_TIMEZONES:
            return _CITY_TIMEZONES[key]
    if country:
        key = country.strip().lower()
        if key in _COUNTRY_TIMEZONES:
            return _COUNTRY_TIMEZONES[key]
    return None


def _format_in_zone(aware_utc: datetime, tz_name: str) -> tuple[str, str]:
    try:
        z = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return "—", tz_name
    local = aware_utc.astimezone(z)
    label = tz_name.split("/")[-1].replace("_", " ")
    return local.strftime("%d %b %Y %H:%M"), label


def format_kickoff_display(
    kickoff: datetime | None,
    *,
    venue_city: str | None = None,
    venue_country: str | None = None,
    locale: Locale | None = None,
) -> KickoffDisplay:
    """User local + venue local + UTC — never fakes venue time."""
    loc = locale or "en"  # type: ignore[assignment]
    if kickoff is None:
        return KickoffDisplay(
            user_local="—",
            user_local_label=gui_t("kickoff.user_local", loc),
            venue_local=None,
            venue_label=None,
            utc="—",
            venue_unavailable=True,
        )
    aware = _aware_utc(kickoff)
    user_dt = aware.astimezone().strftime("%d %b %Y %H:%M")
    user_label = gui_t("kickoff.user_local", loc)
    utc_str = aware.strftime("%d %b %Y %H:%M UTC")

    tz_name = resolve_venue_timezone(city=venue_city, country=venue_country)
    if tz_name:
        venue_dt, venue_lbl = _format_in_zone(aware, tz_name)
        return KickoffDisplay(
            user_local=user_dt,
            user_local_label=user_label,
            venue_local=venue_dt,
            venue_label=f"{gui_t('kickoff.venue_local', loc)} ({venue_lbl})",
            utc=utc_str,
            venue_unavailable=False,
        )
    return KickoffDisplay(
        user_local=user_dt,
        user_local_label=user_label,
        venue_local=None,
        venue_label=None,
        utc=utc_str,
        venue_unavailable=True,
    )


def format_kickoff_times(
    kickoff: datetime | None,
    *,
    venue_city: str | None = None,
    venue_country: str | None = None,
) -> tuple[str, str]:
    """Backward-compatible (user local, UTC)."""
    display = format_kickoff_display(kickoff, venue_city=venue_city, venue_country=venue_country)
    return display.user_local, display.utc

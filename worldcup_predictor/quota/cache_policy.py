"""TTL policies for API response cache and enrichment fetch gates."""

from __future__ import annotations

from datetime import datetime, timezone

# Legacy aliases (Phase 40A validators)
DAILY_TTL_SECONDS = 86400
MATCH_TTL_SECONDS = 1800
DEFAULT_TTL_SECONDS = 3600

# Quota protection TTL bands (seconds)
FIXTURES_LIST_TTL_SECONDS = 1800  # 30 min — within 15–60 min band
ODDS_TTL_SECONDS = 3600  # 60 min — within 30–120 min band
INJURIES_TTL_SECONDS = 28800  # 8 h — within 6–12 h band
LINEUPS_TTL_NEAR_SECONDS = 900  # 15 min when close to kickoff
WEATHER_TTL_SECONDS = 7200  # 2 h — within 1–3 h band
PREDICTION_RESULT_MIN_TTL_SECONDS = 1800  # 30 min
PREDICTION_RESULT_MAX_TTL_SECONDS = 7200  # 120 min

# Skip lineup API calls when kickoff is more than this many hours away
LINEUPS_FETCH_MAX_HOURS_BEFORE = 4.0

DAILY_ENDPOINT_PREFIXES: tuple[str, ...] = (
    "standings",
    "teams",
    "leagues",
    "players/",
)

MATCH_ENDPOINT_PREFIXES: tuple[str, ...] = (
    "fixtures/lineups",
    "fixtures/events",
    "odds",
)


def ttl_for_endpoint(endpoint: str, *, override: int | None = None) -> int:
    if override is not None:
        return override
    ep = endpoint.lstrip("/").lower()
    if ep == "injuries":
        return INJURIES_TTL_SECONDS
    if ep == "odds":
        return ODDS_TTL_SECONDS
    if ep == "fixtures":
        return FIXTURES_LIST_TTL_SECONDS
    for prefix in MATCH_ENDPOINT_PREFIXES:
        if ep.startswith(prefix) or ep == prefix.rstrip("/"):
            return LINEUPS_TTL_NEAR_SECONDS if "lineups" in ep else MATCH_TTL_SECONDS
    for prefix in DAILY_ENDPOINT_PREFIXES:
        if ep.startswith(prefix):
            return DAILY_TTL_SECONDS
    return DEFAULT_TTL_SECONDS


def is_daily_endpoint(endpoint: str) -> bool:
    ep = endpoint.lstrip("/").lower()
    return any(ep.startswith(p) for p in DAILY_ENDPOINT_PREFIXES)


def is_match_endpoint(endpoint: str) -> bool:
    ep = endpoint.lstrip("/").lower()
    return any(ep.startswith(p) for p in MATCH_ENDPOINT_PREFIXES)


def should_fetch_lineups(kickoff_utc: datetime | None) -> bool:
    """Lineups are only worth a live API call close to kickoff."""
    if kickoff_utc is None:
        return True
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    kickoff = kickoff_utc.replace(tzinfo=None) if kickoff_utc.tzinfo else kickoff_utc
    hours_until = (kickoff - now).total_seconds() / 3600.0
    if hours_until < 0:
        return True
    return hours_until <= LINEUPS_FETCH_MAX_HOURS_BEFORE


def prediction_result_ttl_seconds(kickoff_utc: datetime | None) -> int:
    """TTL envelope for file cache — Phase 33 bands via freshness check at read time."""
    try:
        from worldcup_predictor.automation.worldcup_background.freshness import (
            freshness_max_age_seconds,
            hours_until_kickoff,
        )

        hours = hours_until_kickoff(kickoff_utc)
        return int(freshness_max_age_seconds(hours)) + 300
    except ImportError:
        pass
    if kickoff_utc is None:
        return PREDICTION_RESULT_MIN_TTL_SECONDS + 900
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    kickoff = kickoff_utc.replace(tzinfo=None) if kickoff_utc.tzinfo else kickoff_utc
    hours_until = (kickoff - now).total_seconds() / 3600.0
    if hours_until < 2:
        return PREDICTION_RESULT_MIN_TTL_SECONDS
    if hours_until < 24:
        return 3600
    return PREDICTION_RESULT_MAX_TTL_SECONDS

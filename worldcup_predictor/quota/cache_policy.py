"""TTL policies for API-Football response cache — Phase 40A."""

from __future__ import annotations

DAILY_TTL_SECONDS = 86400  # 24 hours
MATCH_TTL_SECONDS = 1800  # 30 minutes
DEFAULT_TTL_SECONDS = 3600

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
    for prefix in MATCH_ENDPOINT_PREFIXES:
        if ep.startswith(prefix) or ep == prefix.rstrip("/"):
            return MATCH_TTL_SECONDS
    for prefix in DAILY_ENDPOINT_PREFIXES:
        if ep.startswith(prefix):
            return DAILY_TTL_SECONDS
    if ep == "fixtures" and _is_fixture_list_query(ep):
        return MATCH_TTL_SECONDS
    return DEFAULT_TTL_SECONDS


def _is_fixture_list_query(endpoint: str) -> bool:
    _ = endpoint
    return False


def is_daily_endpoint(endpoint: str) -> bool:
    ep = endpoint.lstrip("/").lower()
    return any(ep.startswith(p) for p in DAILY_ENDPOINT_PREFIXES)


def is_match_endpoint(endpoint: str) -> bool:
    ep = endpoint.lstrip("/").lower()
    return any(ep.startswith(p) for p in MATCH_ENDPOINT_PREFIXES)

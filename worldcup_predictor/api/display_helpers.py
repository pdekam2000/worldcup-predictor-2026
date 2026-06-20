"""Lightweight display metadata for API responses — no extra provider calls."""

from __future__ import annotations

from typing import Any, Literal

from worldcup_predictor.agents.specialists.status_reasons import (
    CACHE_HIT,
    DATA_NOT_PUBLISHED_YET,
    HEURISTIC_PARTIAL,
    LIVE_DATA_AVAILABLE,
    MISSING_REQUIRED_FIXTURE_FIELDS,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.quota.fixtures_list_cache import get_cached as get_fixtures_list_cached
from worldcup_predictor.api.prediction_output import enrich_cached_prediction_output
from worldcup_predictor.quota.quota_guard import refresh_cooldown_remaining_seconds

LineupCoverage = Literal["official", "projected", "pending", "missing"]

_LINEUP_AGENT_KEYS = ("lineup_agent", "lineup")
_EXPECTED_LINEUP_AGENT_KEYS = ("expected_lineup_agent",)
_LINEUP_INTEL_AGENT_KEYS = ("lineup_intelligence_agent",)
_INJURY_AGENT_KEYS = ("injury_suspension_agent", "injury")
_ODDS_AGENT_KEYS = (
    "odds_market_agent",
    "market_consensus_agent",
    "odds_control_agent",
    "odds",
)

_LIVE_FIXTURE_STATUSES = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"})


def fixture_to_match_display(fixture: TournamentFixture, *, league: str, season: int) -> dict[str, Any]:
    """Serialize fixture with team logos and venue hints for Match Center cards."""
    return {
        "fixture_id": fixture.fixture_id,
        "date": fixture.kickoff_time.isoformat(),
        "league": league,
        "season": season,
        "home_team": fixture.home_team,
        "away_team": fixture.away_team,
        "status": fixture.status or "NS",
        "home_team_logo": fixture.home_team_logo,
        "away_team_logo": fixture.away_team_logo,
        "country": fixture.country or None,
        "venue": fixture.venue or None,
        "city": fixture.city or None,
    }


def _match_from_cached_list(
    fixture_id: int,
    *,
    competition_key: str,
    season: int,
    settings: Settings,
) -> dict[str, Any] | None:
    limit = settings.upcoming_fixture_limit
    cached = get_fixtures_list_cached(competition_key, season, limit, settings=settings)
    if not cached:
        return None
    for row in cached.get("matches") or []:
        if int(row.get("fixture_id", 0)) == fixture_id:
            return row
    return None


def team_logos_for_fixture(
    fixture_id: int,
    *,
    competition_key: str,
    season: int,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Resolve logos from fixtures list cache only — never hits providers."""
    settings = settings or get_settings()
    row = _match_from_cached_list(fixture_id, competition_key=competition_key, season=season, settings=settings)
    if row is None:
        return {}
    out: dict[str, Any] = {}
    if row.get("home_team_logo"):
        out["home_team_logo"] = row["home_team_logo"]
    if row.get("away_team_logo"):
        out["away_team_logo"] = row["away_team_logo"]
    if row.get("country"):
        out["country"] = row["country"]
    return out


def data_quality_tier(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _agent_signal(agents: dict[str, Any], name: str) -> dict[str, Any]:
    raw = agents.get(name)
    return raw if isinstance(raw, dict) else {}


def _first_agent_signal(agents: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    for name in names:
        signal = _agent_signal(agents, name)
        if signal:
            return signal
    return {}


def _status_available(status: Any) -> bool:
    return str(status or "").lower() in ("available", "partial")


def _resolve_lineup_coverage(
    agents: dict[str, Any],
    *,
    fixture_status: str | None = None,
) -> LineupCoverage:
    lineup = _first_agent_signal(agents, _LINEUP_AGENT_KEYS)
    expected = _first_agent_signal(agents, _EXPECTED_LINEUP_AGENT_KEYS)
    lineup_intel = _first_agent_signal(agents, _LINEUP_INTEL_AGENT_KEYS)

    lineup_ok = _status_available(lineup.get("status"))
    expected_ok = _status_available(expected.get("status"))
    intel_ok = _status_available(lineup_intel.get("status"))

    if not (lineup_ok or expected_ok or intel_ok):
        lineup_reason = str(lineup.get("status_reason") or "")
        lineup_status = str(lineup.get("status") or "").lower()
        if lineup_reason in (DATA_NOT_PUBLISHED_YET, MISSING_REQUIRED_FIXTURE_FIELDS) or lineup_status in (
            "unavailable",
            "placeholder",
        ):
            return "missing"
        return "missing"

    status = (fixture_status or "NS").upper()
    if status in _LIVE_FIXTURE_STATUSES and lineup_ok:
        return "official"

    lineup_reason = str(lineup.get("status_reason") or "").lower()
    if expected_ok or lineup_reason in (DATA_NOT_PUBLISHED_YET, HEURISTIC_PARTIAL):
        return "pending"
    if str(lineup.get("status") or "").lower() == "partial":
        return "pending"
    if lineup_ok and not expected_ok:
        return "official"
    return "pending"


def _resolve_odds_available(agents: dict[str, Any]) -> bool:
    for name in _ODDS_AGENT_KEYS:
        signal = _agent_signal(agents, name)
        if not _status_available(signal.get("status")):
            continue
        reason = str(signal.get("status_reason") or "").lower()
        if name == "odds_market_agent" and reason and reason not in (
            LIVE_DATA_AVAILABLE,
            CACHE_HIT,
            "",
        ):
            continue
        return True
    return False


def _resolve_missing_injuries(agents: dict[str, Any]) -> bool:
    injury = _first_agent_signal(agents, _INJURY_AGENT_KEYS)
    injury_reason = str(injury.get("status_reason") or "")
    injury_status = str(injury.get("status") or "").lower()
    if injury_status in ("available", "partial"):
        return False
    return injury_status == "unavailable" or injury_reason in (
        DATA_NOT_PUBLISHED_YET,
        MISSING_REQUIRED_FIXTURE_FIELDS,
    )


def data_signals_from_specialist_summary(
    specialist_summary: dict[str, Any] | None,
    *,
    data_quality: float | None,
    fixture_status: str | None = None,
) -> dict[str, Any]:
    agents = (specialist_summary or {}).get("agents") or {}
    lineup_coverage = _resolve_lineup_coverage(agents, fixture_status=fixture_status)
    missing_lineups = lineup_coverage == "missing"
    official_lineup_pending = lineup_coverage == "pending"
    odds_available = _resolve_odds_available(agents)

    return {
        "tier": data_quality_tier(data_quality),
        "data_quality_pct": data_quality,
        "lineup_coverage": lineup_coverage,
        "missing_lineups": bool(missing_lineups),
        "official_lineup_pending": bool(official_lineup_pending),
        "missing_injuries": bool(_resolve_missing_injuries(agents)),
        "odds_available": bool(odds_available),
    }


def enrich_prediction_payload(
    payload: dict[str, Any],
    *,
    competition_key: str,
    season: int,
    user_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Add display-only fields; safe to call on cached payloads."""
    settings = settings or get_settings()
    out = dict(payload)
    fixture_id = int(out.get("fixture_id") or 0)
    logos = team_logos_for_fixture(fixture_id, competition_key=competition_key, season=season, settings=settings)
    for key, value in logos.items():
        out.setdefault(key, value)

    specialist = out.get("specialist_summary")
    dq = out.get("data_quality")
    try:
        dq_float = float(dq) if dq is not None else None
    except (TypeError, ValueError):
        dq_float = None
    fixture_status = out.get("fixture_status") or out.get("status")
    out["data_signals"] = data_signals_from_specialist_summary(
        specialist if isinstance(specialist, dict) else None,
        data_quality=dq_float,
        fixture_status=str(fixture_status) if fixture_status else None,
    )
    out["refresh_cooldown_seconds"] = int(settings.prediction_refresh_cooldown_seconds)
    if fixture_id:
        remaining = refresh_cooldown_remaining_seconds(
            fixture_id,
            user_id=user_id,
            settings=settings,
        )
        if remaining is not None:
            out["refresh_cooldown_remaining_seconds"] = remaining
    return enrich_cached_prediction_output(out)

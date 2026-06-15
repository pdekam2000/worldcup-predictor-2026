"""The Odds API v4 provider — sport discovery, event match, odds, consensus (Phase 50B)."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.fixture import Fixture
from worldcup_predictor.providers.base import ProviderCallResult, ProviderTier
from worldcup_predictor.providers.odds_api_credit.config import compute_odds_api_credits

logger = logging.getLogger(__name__)

DEFAULT_MARKETS = "h2h,totals"
DEFAULT_ODDS_FORMAT = "decimal"
TIME_MATCH_HOURS = 24

_TEAM_ALIASES: dict[str, str] = {
    "usa": "united states",
    "u.s.a.": "united states",
    "u.s.a": "united states",
    "curacao": "curaçao",
    "turkiye": "turkey",
    "korea republic": "south korea",
    "republic of korea": "south korea",
    "bosnia and herzegovina": "bosnia & herzegovina",
    "cote d'ivoire": "ivory coast",
    "côte d'ivoire": "ivory coast",
}

_sports_cache: dict[str, Any] = {}


@dataclass
class OddsApiConsensus:
    odds_api_bookmaker_count: int = 0
    odds_api_h2h_consensus: dict[str, float | None] = field(default_factory=dict)
    odds_api_ou25_consensus: dict[str, float | None] = field(default_factory=dict)
    odds_api_market_timestamp: str | None = None
    cross_source_agreement: float | None = None
    cross_source_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "odds_api_bookmaker_count": self.odds_api_bookmaker_count,
            "odds_api_h2h_consensus": self.odds_api_h2h_consensus,
            "odds_api_ou25_consensus": self.odds_api_ou25_consensus,
            "odds_api_market_timestamp": self.odds_api_market_timestamp,
            "cross_source_agreement": self.cross_source_agreement,
            "cross_source_note": self.cross_source_note,
        }


@dataclass
class OddsApiFetchResult:
    configured: bool = False
    sport_key: str | None = None
    event_matched: bool = False
    event_id: str | None = None
    event: dict[str, Any] | None = None
    odds_api_called: bool = False
    used_cache: bool = False
    credits_used: int = 0
    bookmaker_count: int = 0
    consensus: OddsApiConsensus | None = None
    error: str | None = None
    endpoint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "sport_key": self.sport_key,
            "event_matched": self.event_matched,
            "event_id": self.event_id,
            "odds_api_called": self.odds_api_called,
            "used_cache": self.used_cache,
            "credits_used": self.credits_used,
            "bookmaker_count": self.bookmaker_count,
            "consensus": self.consensus.to_dict() if self.consensus else None,
            "error": self.error,
            "endpoint": self.endpoint,
        }


def normalize_team_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9&'\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for drop in (" fc", " cf", " sc", " afc"):
        if text.endswith(drop):
            text = text[: -len(drop)].strip()
    return _TEAM_ALIASES.get(text, text)


def teams_match(expected: str, candidate: str) -> bool:
    a = normalize_team_name(expected)
    b = normalize_team_name(candidate)
    if not a or not b:
        return False
    if a == b:
        return True
    return a in b or b in a


def parse_commence_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def kickoff_within_window(
    commence_time: str | None,
    kickoff_utc: datetime | None,
    *,
    hours: int = TIME_MATCH_HOURS,
) -> bool:
    if kickoff_utc is None:
        return True
    commence = parse_commence_time(commence_time)
    if commence is None:
        return True
    if kickoff_utc.tzinfo is None:
        kickoff_utc = kickoff_utc.replace(tzinfo=timezone.utc)
    delta = abs(commence - kickoff_utc)
    return delta <= timedelta(hours=hours)


def decimal_to_implied(price: float) -> float | None:
    if price <= 1.0:
        return None
    return 1.0 / price


def remove_overround(probs: list[float]) -> list[float]:
    total = sum(probs)
    if total <= 0:
        return probs
    return [p / total for p in probs]


class TheOddsApiProvider:
    """Real The Odds API integration — secondary validation only."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.the_odds_api_base_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return self._settings.the_odds_api_configured

    @property
    def regions(self) -> str:
        return self._settings.the_odds_api_regions.strip() or "eu"

    @property
    def markets(self) -> str:
        return DEFAULT_MARKETS

    @property
    def credits_per_odds_call(self) -> int:
        return compute_odds_api_credits(self.regions, self.markets)

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        query = dict(params or {})
        query["apiKey"] = self._settings.the_odds_api_key
        url = f"{self._base_url}/{path.lstrip('/')}"
        with httpx.Client(timeout=25.0) as client:
            response = client.get(url, params=query)
            response.raise_for_status()
            return response.json()

    def list_sports(self) -> ProviderCallResult:
        if not self.is_configured:
            return ProviderCallResult(
                data=None,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint="sports",
                configured=False,
                error="THE_ODDS_API_KEY not configured",
            )
        try:
            data = self._get("sports")
            return ProviderCallResult(
                data=data,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint="sports",
            )
        except Exception as exc:
            logger.exception("The Odds API sports list failed")
            return ProviderCallResult(
                data=None,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint="sports",
                error=str(exc),
            )

    def resolve_sport_key(self, *, discover: bool = False) -> str | None:
        configured = self._settings.the_odds_api_sport.strip()
        if configured and not discover:
            return configured
        cache_key = "sports_list"
        sports = _sports_cache.get(cache_key)
        if sports is None:
            result = self.list_sports()
            if not result.available or not isinstance(result.data, list):
                return configured or None
            sports = result.data
            _sports_cache[cache_key] = sports

        preferred = (
            "soccer_fifa_world_cup",
            "soccer_world_cup",
        )
        keys = {str(s.get("key", "")): s for s in sports if isinstance(s, dict)}
        for key in preferred:
            if key in keys:
                return key
        for key, row in keys.items():
            title = str(row.get("title", "")).lower()
            if "world cup" in title or "fifa" in title:
                return key
        return configured or None

    def list_events(self, sport_key: str) -> ProviderCallResult:
        endpoint = f"sports/{sport_key}/events"
        if not self.is_configured:
            return ProviderCallResult(
                data=None,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
                configured=False,
                error="THE_ODDS_API_KEY not configured",
            )
        try:
            data = self._get(endpoint)
            return ProviderCallResult(
                data=data,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
            )
        except Exception as exc:
            return ProviderCallResult(
                data=None,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
                error=str(exc),
            )

    def match_event(
        self,
        events: list[dict[str, Any]],
        *,
        home_team: str,
        away_team: str,
        kickoff_utc: datetime | None,
    ) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        best_score = -1
        for event in events:
            if not isinstance(event, dict):
                continue
            eh = str(event.get("home_team", ""))
            ea = str(event.get("away_team", ""))
            if not teams_match(home_team, eh) or not teams_match(away_team, ea):
                continue
            if not kickoff_within_window(event.get("commence_time"), kickoff_utc):
                continue
            score = 2
            if teams_match(home_team, eh) and teams_match(away_team, ea):
                score += 2
            if kickoff_utc and parse_commence_time(event.get("commence_time")):
                score += 1
            if score > best_score:
                best = event
                best_score = score
        return best

    def fetch_event_odds(self, sport_key: str, event_id: str) -> ProviderCallResult:
        endpoint = f"sports/{sport_key}/events/{event_id}/odds"
        params = {
            "regions": self.regions,
            "markets": self.markets,
            "oddsFormat": DEFAULT_ODDS_FORMAT,
        }
        if not self.is_configured:
            return ProviderCallResult(
                data=None,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
                configured=False,
                error="THE_ODDS_API_KEY not configured",
            )
        try:
            data = self._get(endpoint, params=params)
            event = data[0] if isinstance(data, list) and data else data
            return ProviderCallResult(
                data=event if isinstance(event, dict) else None,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
            )
        except Exception as exc:
            return ProviderCallResult(
                data=None,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
                error=str(exc),
            )

    def fetch_sport_odds(self, sport_key: str) -> ProviderCallResult:
        endpoint = f"sports/{sport_key}/odds"
        params = {
            "regions": self.regions,
            "markets": self.markets,
            "oddsFormat": DEFAULT_ODDS_FORMAT,
        }
        if not self.is_configured:
            return ProviderCallResult(
                data=None,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
                configured=False,
                error="THE_ODDS_API_KEY not configured",
            )
        try:
            data = self._get(endpoint, params=params)
            return ProviderCallResult(
                data=data,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
            )
        except Exception as exc:
            return ProviderCallResult(
                data=None,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
                error=str(exc),
            )

    def fetch_for_fixture(
        self,
        fixture: Fixture,
        *,
        cached_event: dict[str, Any] | None = None,
        allow_live: bool = True,
        fallback_sport_odds: bool = False,
    ) -> OddsApiFetchResult:
        out = OddsApiFetchResult(configured=self.is_configured)
        if not self.is_configured:
            out.error = "not_configured"
            return out

        if cached_event:
            out.used_cache = True
            out.event = cached_event
            out.event_id = str(cached_event.get("id", "")) or None
            out.event_matched = bool(out.event_id)
            out.bookmaker_count = len(cached_event.get("bookmakers") or [])
            out.consensus = build_market_consensus(cached_event, home_team=fixture.home_team, away_team=fixture.away_team)
            return out

        if not allow_live:
            out.error = "guard_blocked"
            return out

        sport_key = self.resolve_sport_key(discover=True)
        out.sport_key = sport_key
        if not sport_key:
            out.error = "sport_key_not_found"
            return out

        events_result = self.list_events(sport_key)
        if not events_result.available or not isinstance(events_result.data, list):
            out.error = events_result.error or "events_unavailable"
            return out

        matched = self.match_event(
            events_result.data,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            kickoff_utc=fixture.kickoff_utc,
        )
        if matched:
            out.event_matched = True
            out.event_id = str(matched.get("id", "")) or None
            if out.event_id:
                odds_result = self.fetch_event_odds(sport_key, out.event_id)
                out.endpoint = odds_result.endpoint
                if odds_result.available and isinstance(odds_result.data, dict):
                    out.odds_api_called = True
                    out.credits_used = self.credits_per_odds_call
                    out.event = odds_result.data
                else:
                    out.error = odds_result.error or "event_odds_unavailable"
                    return out
        elif fallback_sport_odds:
            odds_result = self.fetch_sport_odds(sport_key)
            out.endpoint = odds_result.endpoint
            if odds_result.available and isinstance(odds_result.data, list):
                matched = self.match_event(
                    odds_result.data,
                    home_team=fixture.home_team,
                    away_team=fixture.away_team,
                    kickoff_utc=fixture.kickoff_utc,
                )
                if matched:
                    out.event_matched = True
                    out.event_id = str(matched.get("id", "")) or None
                    out.odds_api_called = True
                    out.credits_used = self.credits_per_odds_call
                    out.event = matched
                else:
                    out.error = "no_event_match"
                    return out
            else:
                out.error = odds_result.error or "sport_odds_unavailable"
                return out
        else:
            out.error = "no_event_match"
            return out

        if out.event:
            out.bookmaker_count = len(out.event.get("bookmakers") or [])
            out.consensus = build_market_consensus(
                out.event,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
            )
        return out


def build_market_consensus(
    event: dict[str, Any],
    *,
    home_team: str,
    away_team: str,
    primary_odds: Any | None = None,
) -> OddsApiConsensus:
    bookmakers = [b for b in (event.get("bookmakers") or []) if isinstance(b, dict)]
    h2h_home: list[float] = []
    h2h_draw: list[float] = []
    h2h_away: list[float] = []
    ou_over: list[float] = []
    ou_under: list[float] = []
    latest_ts: str | None = event.get("commence_time")

    for bm in bookmakers:
        ts = bm.get("last_update") or latest_ts
        if ts:
            latest_ts = str(ts)
        for market in bm.get("markets") or []:
            if not isinstance(market, dict):
                continue
            key = str(market.get("key", ""))
            outcomes = market.get("outcomes") or []
            if key == "h2h":
                probs: list[tuple[str, float]] = []
                for row in outcomes:
                    if not isinstance(row, dict):
                        continue
                    name = str(row.get("name", ""))
                    price = row.get("price")
                    if price is None:
                        continue
                    implied = decimal_to_implied(float(price))
                    if implied is None:
                        continue
                    if teams_match(name, home_team):
                        probs.append(("home", implied))
                    elif teams_match(name, away_team):
                        probs.append(("away", implied))
                    elif name.lower() in {"draw", "tie"}:
                        probs.append(("draw", implied))
                if probs:
                    norm = remove_overround([p for _, p in probs])
                    for (side, _), prob in zip(probs, norm):
                        if side == "home":
                            h2h_home.append(prob)
                        elif side == "away":
                            h2h_away.append(prob)
                        else:
                            h2h_draw.append(prob)
            elif key == "totals":
                over_prob = under_prob = None
                for row in outcomes:
                    if not isinstance(row, dict):
                        continue
                    point = row.get("point")
                    if point is not None and float(point) != 2.5:
                        continue
                    name = str(row.get("name", "")).lower()
                    price = row.get("price")
                    if price is None:
                        continue
                    implied = decimal_to_implied(float(price))
                    if implied is None:
                        continue
                    if "over" in name:
                        over_prob = implied
                    elif "under" in name:
                        under_prob = implied
                if over_prob is not None and under_prob is not None:
                    norm = remove_overround([over_prob, under_prob])
                    ou_over.append(norm[0])
                    ou_under.append(norm[1])

    def _avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    consensus = OddsApiConsensus(
        odds_api_bookmaker_count=len(bookmakers),
        odds_api_h2h_consensus={
            "home": _avg(h2h_home),
            "draw": _avg(h2h_draw),
            "away": _avg(h2h_away),
        },
        odds_api_ou25_consensus={
            "over_2_5": _avg(ou_over),
            "under_2_5": _avg(ou_under),
        },
        odds_api_market_timestamp=latest_ts,
    )
    consensus.cross_source_agreement, consensus.cross_source_note = _cross_source_agreement(
        consensus,
        primary_odds,
        home_team=home_team,
        away_team=away_team,
    )
    return consensus


def _cross_source_agreement(
    consensus: OddsApiConsensus,
    primary_odds: Any | None,
    *,
    home_team: str,
    away_team: str,
) -> tuple[float | None, str]:
    if not primary_odds or not getattr(primary_odds, "available", False):
        return None, "API-Football odds unavailable for comparison"
    h2h = consensus.odds_api_h2h_consensus
    if not any(v is not None for v in h2h.values()):
        return None, "The Odds API h2h consensus unavailable"

    primary_home = primary_away = primary_draw = None
    for bm in getattr(primary_odds, "bookmakers", None) or []:
        if not isinstance(bm, dict):
            continue
        for bet in bm.get("bets") or []:
            if str(bet.get("name", "")).lower() not in {"match winner", "1x2", "home/draw/away"}:
                continue
            for val in bet.get("values") or []:
                if not isinstance(val, dict):
                    continue
                label = str(val.get("value", ""))
                odd = val.get("odd")
                if odd is None:
                    continue
                implied = decimal_to_implied(float(odd))
                if implied is None:
                    continue
                if teams_match(label, home_team):
                    primary_home = implied
                elif teams_match(label, away_team):
                    primary_away = implied
                elif label.lower() == "draw":
                    primary_draw = implied

    pairs: list[tuple[float, float]] = []
    if h2h.get("home") is not None and primary_home is not None:
        pairs.append((h2h["home"], primary_home))
    if h2h.get("away") is not None and primary_away is not None:
        pairs.append((h2h["away"], primary_away))
    if h2h.get("draw") is not None and primary_draw is not None:
        pairs.append((h2h["draw"], primary_draw))
    if not pairs:
        return None, "Could not parse API-Football 1X2 for comparison"

    deltas = [abs(a - b) for a, b in pairs]
    agreement = round(max(0.0, 1.0 - (sum(deltas) / len(deltas)) * 2.0), 3)
    return agreement, f"Compared {len(pairs)} 1X2 leg(s) vs API-Football"

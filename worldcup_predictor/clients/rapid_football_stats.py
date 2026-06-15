"""
RapidAPI Football Stats — optional supplemental enrichment only.

Provider: Football Data API / football-stats-api-live-scores-xg-odds-player-data
Never replaces API-Sports. No mock data. Silent skip when disabled/unconfigured.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

from worldcup_predictor.config.settings import Settings

logger = logging.getLogger(__name__)

WORLD_CUP_COMPETITION_ID = "comp_6107"


@dataclass(frozen=True)
class RapidApiCallResult:
    endpoint: str
    loaded: bool
    response_count: int = 0
    error: str | None = None
    data: Any = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.loaded


@dataclass
class RapidEnrichmentBundle:
    """Normalized supplemental payload merged into MatchIntelligenceReport."""

    xg: dict[str, Any] | None = None
    npxg: dict[str, Any] | None = None
    player_statistics: list[dict[str, Any]] | None = None
    team_squad: dict[str, Any] | None = None
    prematch_odds: dict[str, Any] | None = None
    live_odds: dict[str, Any] | None = None
    historical_odds: dict[str, Any] | None = None
    live_scores: dict[str, Any] | None = None
    match_events: list[dict[str, Any]] | None = None
    match_statistics: dict[str, Any] | None = None
    rapid_match_id: str | None = None
    calls: list[RapidApiCallResult] = field(default_factory=list)

    @property
    def endpoints_called(self) -> int:
        return len(self.calls)

    @property
    def endpoints_loaded(self) -> int:
        return sum(1 for c in self.calls if c.loaded)

    def to_supplemental_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": "rapid_football_stats",
            "rapid_match_id": self.rapid_match_id,
            "endpoints_called": self.endpoints_called,
            "endpoints_loaded": self.endpoints_loaded,
        }
        if self.xg or self.npxg:
            payload["xg"] = self.xg or {}
            payload["npxg"] = self.npxg or {}
        if self.player_statistics:
            payload["player_statistics"] = self.player_statistics
        if self.team_squad:
            payload["team_squad"] = self.team_squad
        if self.prematch_odds:
            payload["prematch_odds"] = self.prematch_odds
        if self.live_odds:
            payload["live_odds"] = self.live_odds
        if self.historical_odds:
            payload["historical_odds"] = self.historical_odds
        if self.live_scores:
            payload["live_scores"] = self.live_scores
        if self.match_events:
            payload["match_events"] = self.match_events
        if self.match_statistics:
            payload["match_statistics"] = self.match_statistics
        return payload


class RapidFootballStatsClient:
    """RapidAPI supplemental football stats client."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.rapid_football_stats_base_url.rstrip("/")
        self._match_cache: dict[tuple[str, str, str | None], str | None] = {}

    @property
    def is_configured(self) -> bool:
        return self._settings.rapid_football_stats_configured

    def _headers(self) -> dict[str, str]:
        return {
            "x-rapidapi-key": self._settings.rapid_football_stats_key,
            "x-rapidapi-host": self._settings.rapid_football_stats_host,
            "Content-Type": "application/json",
        }

    def ping(self) -> RapidApiCallResult:
        """Light connectivity check — does not expose the API key."""
        if not self.is_configured:
            return RapidApiCallResult(
                endpoint="rapid/ping",
                loaded=False,
                error="not_configured",
            )
        return self._get("ping", "/matches", {"limit": 1})

    def resolve_match_id(
        self,
        *,
        home_team: str,
        away_team: str,
        kickoff_date: str | None = None,
    ) -> str | None:
        """Map API-Sports fixture teams to this provider's match id."""
        cache_key = (home_team, away_team, kickoff_date)
        if cache_key in self._match_cache:
            return self._match_cache[cache_key]

        home_key = _normalize_team_name(home_team)
        away_key = _normalize_team_name(away_team)

        param_sets: list[dict[str, Any]] = []
        if kickoff_date:
            param_sets.append(
                {"competition_id": WORLD_CUP_COMPETITION_ID, "date": kickoff_date, "limit": 100}
            )
        param_sets.append(
            {"competition_id": WORLD_CUP_COMPETITION_ID, "matchday": 1, "limit": 100}
        )

        for params in param_sets:
            result = self._get("resolve_match", "/matches", params)
            if result.error == "http_429":
                break
            if not result.loaded or not isinstance(result.data, list):
                continue
            match_id = _pick_match_id(
                result.data,
                home_key=home_key,
                away_key=away_key,
                kickoff_date=kickoff_date,
            )
            if match_id:
                self._match_cache[cache_key] = match_id
                return match_id

        self._match_cache[cache_key] = None
        return None

    def fetch_match_enrichment(
        self,
        *,
        fixture_id: int,
        home_team: str,
        away_team: str,
        kickoff_date: str | None = None,
    ) -> RapidEnrichmentBundle:
        if not self.is_configured:
            return RapidEnrichmentBundle()

        bundle = RapidEnrichmentBundle()
        rapid_match_id = self.resolve_match_id(
            home_team=home_team,
            away_team=away_team,
            kickoff_date=kickoff_date,
        )
        if not rapid_match_id:
            bundle.calls.append(
                RapidApiCallResult(
                    endpoint="rapid/resolve_match",
                    loaded=False,
                    error="match_not_found",
                )
            )
            return bundle

        bundle.rapid_match_id = rapid_match_id
        encoded_match_id = quote(rapid_match_id, safe="")

        detail = self._get("match_detail", f"/matches/{encoded_match_id}", {})
        bundle.calls.append(detail)
        match_data = detail.data if isinstance(detail.data, dict) else {}
        home_meta = match_data.get("home_team") if isinstance(match_data.get("home_team"), dict) else {}
        away_meta = match_data.get("away_team") if isinstance(match_data.get("away_team"), dict) else {}
        home_team_id = str(home_meta.get("id") or "")
        away_team_id = str(away_meta.get("id") or "")

        query_endpoints: list[tuple[str, str, dict[str, Any]]] = [
            ("match_xg", "/matches/xg", {"match_id": rapid_match_id}),
            ("match_statistics", "/matches/statistics", {"match_id": rapid_match_id}),
            ("match_events", "/matches/events", {"match_id": rapid_match_id}),
            ("odds_live", "/matches/live-odds", {"match_id": rapid_match_id}),
            ("odds_historical", "/matches/historical-odds", {"match_id": rapid_match_id}),
            ("live_scores", "/matches/live", {"match_id": rapid_match_id}),
        ]
        path_endpoints: list[tuple[str, str]] = [
            ("odds_prematch", f"/matches/{encoded_match_id}/odds"),
        ]

        for logical, path, params in query_endpoints:
            result = self._get(logical, path, params)
            bundle.calls.append(result)
            self._apply_call(bundle, logical, result)

        for logical, path in path_endpoints:
            result = self._get(logical, path, {})
            bundle.calls.append(result)
            self._apply_call(bundle, logical, result)

        squad: dict[str, Any] = {}
        for side, team_id in (("home", home_team_id), ("away", away_team_id)):
            if not team_id:
                continue
            encoded_team = quote(team_id, safe="")
            squad_result = self._get(
                "team_squad",
                f"/teams/{encoded_team}/players",
                {},
            )
            bundle.calls.append(squad_result)
            if squad_result.loaded:
                squad[side] = squad_result.data

        if squad:
            bundle.team_squad = squad

        if detail.loaded and match_data:
            xg_block = match_data.get("xg") or match_data.get("expected_goals")
            if isinstance(xg_block, dict):
                bundle.xg = xg_block.get("xg") or xg_block
                bundle.npxg = xg_block.get("npxg") or xg_block.get("npxG")

        return bundle

    def _apply_call(self, bundle: RapidEnrichmentBundle, logical: str, result: RapidApiCallResult) -> None:
        if not result.loaded:
            return
        normalized = self._normalize(logical, result.data)
        if normalized is None:
            return
        if logical == "match_xg" and isinstance(normalized, dict):
            bundle.xg = normalized.get("xg") or normalized
            bundle.npxg = normalized.get("npxg") or normalized.get("npxG")
        elif logical == "match_events" and isinstance(normalized, list):
            bundle.match_events = normalized
        elif logical == "player_statistics" and isinstance(normalized, list):
            bundle.player_statistics = normalized
        elif logical == "odds_prematch":
            bundle.prematch_odds = normalized if isinstance(normalized, dict) else {"bookmakers": normalized}
        elif logical == "odds_live":
            bundle.live_odds = normalized if isinstance(normalized, dict) else {"bookmakers": normalized}
        elif logical == "odds_historical":
            bundle.historical_odds = normalized if isinstance(normalized, dict) else {"bookmakers": normalized}
        elif logical == "live_scores":
            bundle.live_scores = normalized if isinstance(normalized, dict) else {"items": normalized}
        elif logical == "match_statistics":
            bundle.match_statistics = normalized if isinstance(normalized, dict) else {"items": normalized}

    def _get(
        self,
        logical: str,
        path: str,
        params: dict[str, Any],
    ) -> RapidApiCallResult:
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(timeout=25.0) as client:
                response = client.get(url, headers=self._headers(), params=params)
                if response.status_code == 404:
                    body = response.text.lower()
                    if "does not exist" in body:
                        return RapidApiCallResult(
                            endpoint=f"rapid/{logical}",
                            loaded=False,
                            error="not_found",
                        )
                if response.status_code >= 400:
                    return RapidApiCallResult(
                        endpoint=f"rapid/{logical}",
                        loaded=False,
                        error=f"http_{response.status_code}",
                    )
                payload = response.json()
            count, data = self._unwrap(payload)
            loaded = count > 0 or (isinstance(data, dict) and bool(data))
            return RapidApiCallResult(
                endpoint=f"rapid/{logical}",
                loaded=loaded,
                response_count=count,
                data=data,
            )
        except Exception as exc:
            logger.debug("RapidAPI %s failed: %s", logical, exc)
            return RapidApiCallResult(
                endpoint=f"rapid/{logical}",
                loaded=False,
                error=str(exc),
            )

    @staticmethod
    def _unwrap(payload: Any) -> tuple[int, Any]:
        if isinstance(payload, list):
            return len(payload), payload
        if isinstance(payload, dict):
            for key in ("data", "response", "results", "matches", "events", "players"):
                inner = payload.get(key)
                if isinstance(inner, list):
                    return len(inner), inner
                if isinstance(inner, dict) and inner:
                    return 1, inner
            if payload:
                return 1, payload
        return 0, None

    @staticmethod
    def _normalize(logical: str, data: Any) -> Any:
        if data is None:
            return None
        if logical == "match_xg" and isinstance(data, dict):
            return {
                "xg": data.get("xg") or data.get("expected_goals") or data.get("home_xg"),
                "npxg": data.get("npxg") or data.get("npxG") or data.get("non_penalty_xg"),
                "raw": data,
            }
        if logical == "odds_prematch" and isinstance(data, dict):
            return data
        return data


def _normalize_team_name(name: str) -> str:
    lowered = name.strip().lower()
    aliases = {
        "czech republic": "czechia",
        "korea republic": "south korea",
        "republic of korea": "south korea",
        "korea, republic of": "south korea",
        "usa": "united states",
        "u.s.a.": "united states",
    }
    return aliases.get(lowered, lowered)


def _pick_match_id(
    rows: list[Any],
    *,
    home_key: str,
    away_key: str,
    kickoff_date: str | None,
) -> str | None:
    candidates: list[tuple[int, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        home = row.get("home_team") or {}
        away = row.get("away_team") or {}
        if not isinstance(home, dict) or not isinstance(away, dict):
            continue
        row_home = _normalize_team_name(str(home.get("name") or ""))
        row_away = _normalize_team_name(str(away.get("name") or ""))
        if row_home != home_key or row_away != away_key:
            continue
        match_id = row.get("id")
        if not match_id:
            continue
        score = 0
        utc_date = str(row.get("utc_date") or "")
        if kickoff_date and utc_date.startswith(kickoff_date):
            score += 2
        candidates.append((score, str(match_id)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]

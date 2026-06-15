"""
Rapid Football XG Statistics — optional supplemental enrichment only.

Provider: football-xg-statistics.p.rapidapi.com
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


@dataclass(frozen=True)
class RapidXgCallResult:
    endpoint: str
    loaded: bool
    response_count: int = 0
    error: str | None = None
    data: Any = None


@dataclass
class RapidXgEnrichmentBundle:
    countries: list[dict[str, Any]] | None = None
    tournaments: list[dict[str, Any]] | None = None
    seasons: list[dict[str, Any]] | None = None
    fixtures: list[dict[str, Any]] | None = None
    fixture_detail: dict[str, Any] | None = None
    upcoming_odds: list[dict[str, Any]] | None = None
    xg: dict[str, Any] | None = None
    npxg: dict[str, Any] | None = None
    calls: list[RapidXgCallResult] = field(default_factory=list)

    @property
    def endpoints_called(self) -> int:
        return len(self.calls)

    @property
    def endpoints_loaded(self) -> int:
        return sum(1 for call in self.calls if call.loaded)

    def to_supplemental_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": "rapid_xg_statistics",
            "endpoints_called": self.endpoints_called,
            "endpoints_loaded": self.endpoints_loaded,
        }
        if self.countries:
            payload["countries"] = self.countries
        if self.tournaments:
            payload["tournaments"] = self.tournaments
        if self.seasons:
            payload["seasons"] = self.seasons
        if self.fixtures:
            payload["fixtures"] = self.fixtures
        if self.fixture_detail:
            payload["fixture_detail"] = self.fixture_detail
        if self.upcoming_odds:
            payload["upcoming_odds"] = self.upcoming_odds
        if self.xg or self.npxg:
            payload["xg"] = self.xg or {}
            payload["npxg"] = self.npxg or {}
        return payload


class RapidXgStatisticsClient:
    """RapidAPI xG statistics client — supplemental enrichment only."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.rapid_xg_base_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return self._settings.rapid_xg_configured

    def _headers(self) -> dict[str, str]:
        return {
            "x-rapidapi-key": self._settings.rapid_xg_key,
            "x-rapidapi-host": self._settings.rapid_xg_host,
            "Content-Type": "application/json",
        }

    def ping(self) -> RapidXgCallResult:
        if not self.is_configured:
            return RapidXgCallResult(endpoint="rapid_xg/ping", loaded=False, error="not_configured")
        return self._get("ping", "/countries/", {})

    def get_countries(self) -> RapidXgCallResult:
        return self._get("countries", "/countries/", {})

    def get_tournaments(self, country_id: int | str) -> RapidXgCallResult:
        cid = quote(str(country_id), safe="")
        return self._get("tournaments", f"/countries/{cid}/tournaments/", {})

    def get_seasons(self, tournament_id: int | str) -> RapidXgCallResult:
        tid = quote(str(tournament_id), safe="")
        return self._get("seasons", f"/tournaments/{tid}/seasons/", {})

    def get_fixtures_list(self, **params: Any) -> RapidXgCallResult:
        return self._get("fixtures", "/fixtures/list/", params)

    def get_fixture(self, fixture_id: int | str) -> RapidXgCallResult:
        fid = quote(str(fixture_id), safe="")
        return self._get("fixture_detail", f"/fixtures/{fid}/", {})

    def get_odds_upcoming(self) -> RapidXgCallResult:
        return self._get("odds_upcoming", "/odds/upcoming/", {})

    def fetch_match_enrichment(
        self,
        *,
        fixture_id: int,
        home_team: str,
        away_team: str,
        kickoff_date: str | None = None,
    ) -> RapidXgEnrichmentBundle:
        if not self.is_configured:
            return RapidXgEnrichmentBundle()

        bundle = RapidXgEnrichmentBundle()
        detail = self.get_fixture(fixture_id)
        bundle.calls.append(detail)
        if detail.loaded and isinstance(detail.data, dict):
            if not detail.data.get("error"):
                bundle.fixture_detail = detail.data
                xg_block = self._extract_xg(detail.data)
                if xg_block:
                    bundle.xg = xg_block.get("xg")
                    bundle.npxg = xg_block.get("npxg")

        odds = self.get_odds_upcoming()
        bundle.calls.append(odds)
        if odds.loaded and isinstance(odds.data, list):
            matched = self._match_odds_rows(odds.data, home_team, away_team, kickoff_date)
            if matched:
                bundle.upcoming_odds = matched

        if kickoff_date:
            list_result = self.get_fixtures_list(season_id=kickoff_date[:4])
            bundle.calls.append(list_result)
            if list_result.loaded and isinstance(list_result.data, list):
                bundle.fixtures = list_result.data[:20]

        return bundle

    def _get(self, logical: str, path: str, params: dict[str, Any]) -> RapidXgCallResult:
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(timeout=25.0, follow_redirects=True) as client:
                response = client.get(url, headers=self._headers(), params=params)
                if response.status_code >= 400:
                    return RapidXgCallResult(
                        endpoint=f"rapid_xg/{logical}",
                        loaded=False,
                        error=f"http_{response.status_code}",
                    )
                payload = response.json()
            if isinstance(payload, dict) and payload.get("error"):
                err = payload["error"]
                message = err.get("text") if isinstance(err, dict) else str(err)
                return RapidXgCallResult(
                    endpoint=f"rapid_xg/{logical}",
                    loaded=False,
                    error=message or "api_error",
                )
            count, data = self._unwrap(payload)
            loaded = count > 0 or (isinstance(data, dict) and bool(data))
            return RapidXgCallResult(
                endpoint=f"rapid_xg/{logical}",
                loaded=loaded,
                response_count=count,
                data=data,
            )
        except Exception as exc:
            logger.debug("Rapid XG %s failed: %s", logical, exc)
            return RapidXgCallResult(
                endpoint=f"rapid_xg/{logical}",
                loaded=False,
                error=str(exc),
            )

    @staticmethod
    def _unwrap(payload: Any) -> tuple[int, Any]:
        if isinstance(payload, list):
            return len(payload), payload
        if isinstance(payload, dict):
            for key in ("result", "data", "response", "results", "fixtures"):
                inner = payload.get(key)
                if isinstance(inner, list):
                    return len(inner), inner
                if isinstance(inner, dict) and inner:
                    return 1, inner
            if payload and "error" not in payload:
                return 1, payload
        return 0, None

    @staticmethod
    def _extract_xg(data: dict[str, Any]) -> dict[str, Any] | None:
        for key in ("xg", "expected_goals", "stats", "statistics"):
            block = data.get(key)
            if isinstance(block, dict):
                return {
                    "xg": block.get("xg") or block.get("home_xg"),
                    "npxg": block.get("npxg") or block.get("npxG"),
                    "raw": block,
                }
        home_xg = data.get("home_xg") or data.get("homeXg")
        away_xg = data.get("away_xg") or data.get("awayXg")
        if home_xg is not None or away_xg is not None:
            return {"xg": {"home": home_xg, "away": away_xg}, "npxg": None}
        return None

    @staticmethod
    def _match_odds_rows(
        rows: list[Any],
        home_team: str,
        away_team: str,
        kickoff_date: str | None,
    ) -> list[dict[str, Any]]:
        home_key = home_team.strip().lower()
        away_key = away_team.strip().lower()
        matched: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_home = str(row.get("home_team") or row.get("home") or "").lower()
            row_away = str(row.get("away_team") or row.get("away") or "").lower()
            if home_key in row_home or row_home in home_key:
                if away_key in row_away or row_away in away_key:
                    matched.append(row)
                    continue
            if kickoff_date and str(row.get("date", "")).startswith(kickoff_date):
                if home_key in row_home and away_key in row_away:
                    matched.append(row)
        return matched

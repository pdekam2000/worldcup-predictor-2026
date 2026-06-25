"""OddAlerts API client — Phase OA-1 research/audit only (not wired to production)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from worldcup_predictor.providers.base import ProviderCallResult, ProviderTier

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

DEFAULT_BASE_URL = "https://data.oddalerts.com/api"


class OddAlertsClient:
    """Minimal OddAlerts HTTP client for audit and future enrichment experiments."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 45.0,
    ) -> None:
        self._api_key = (api_key or os.getenv("ODDALERTS_API_KEY") or "").strip()
        self._base_url = (base_url or os.getenv("ODDALERTS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get(self, endpoint: str, *, params: dict[str, Any] | None = None) -> ProviderCallResult:
        if not self.is_configured:
            return ProviderCallResult(
                data=None,
                provider="api_sports",  # not in ProviderName union yet — audit only
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
                configured=False,
                error="ODDALERTS_API_KEY not configured",
            )
        clean = endpoint.lstrip("/")
        query = {"api_token": self._api_key, **(params or {})}
        url = f"{self._base_url}/{clean}"
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
                response = client.get(url, params=query, headers={"Accept": "application/json"})
            if response.status_code >= 400:
                return ProviderCallResult(
                    data=None,
                    provider="api_sports",
                    tier=ProviderTier.ENRICHMENT,
                    endpoint=clean,
                    error=f"http_{response.status_code}",
                    trace={"body": response.text[:500]},
                )
            ctype = (response.headers.get("content-type") or "").lower()
            if "json" not in ctype:
                return ProviderCallResult(
                    data={"raw_text": response.text[:2000]},
                    provider="api_sports",
                    tier=ProviderTier.ENRICHMENT,
                    endpoint=clean,
                    error="non_json_response",
                )
            payload = response.json()
            return ProviderCallResult(
                data=payload,
                provider="api_sports",
                tier=ProviderTier.ENRICHMENT,
                endpoint=clean,
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("OddAlerts request failed: %s %s", clean, exc)
            return ProviderCallResult(
                data=None,
                provider="api_sports",
                tier=ProviderTier.ENRICHMENT,
                endpoint=clean,
                error=str(exc),
            )

    def get_bookmakers(self) -> ProviderCallResult:
        return self._get("bookmakers")

    def get_competitions(self, *, page: int = 1, per_page: int = 250, search: str | None = None) -> ProviderCallResult:
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if search:
            params["search"] = search
        return self._get("competitions", params=params)

    def get_fixture(self, fixture_id: int, *, include: str | None = None) -> ProviderCallResult:
        params = {"include": include} if include else None
        return self._get(f"fixtures/{int(fixture_id)}", params=params)

    def get_fixtures_multiple(self, fixture_ids: list[int]) -> ProviderCallResult:
        if not fixture_ids:
            return self._get("fixtures/multiple")
        return self._get("fixtures/multiple", params={"ids": ",".join(str(int(i)) for i in fixture_ids)})

    def get_odds_history(self, fixture_id: int) -> ProviderCallResult:
        return self._get("odds/history", params={"id": int(fixture_id)})

    def get_odds_latest(self, *, since_minutes: int = 60, page: int = 1) -> ProviderCallResult:
        return self._get(
            "odds/latest",
            params={"since_minutes": min(1440, max(1, since_minutes)), "page": page, "per_page": 250},
        )

    def get_value_upcoming(self, *, page: int = 1, per_page: int = 250, market: str | None = None) -> ProviderCallResult:
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if market:
            params["market"] = market
        return self._get("value/upcoming", params=params)

    def get_trends(self, trend: str, *, duration: int = 86400, page: int = 1) -> ProviderCallResult:
        return self._get(f"trends/{trend}", params={"duration": duration, "page": page, "per_page": 250})

    def get_stats(self, *, stat_type: str, entity_id: int) -> ProviderCallResult:
        return self._get("stats", params={"type": stat_type, "id": int(entity_id)})

    def get_probability_fixture(self, fixture_id: int) -> ProviderCallResult:
        return self._get("probability", params={"type": "fixture", "id": int(fixture_id)})

    def get_predictions_fixture(self, fixture_id: int) -> ProviderCallResult:
        return self._get("predictions", params={"type": "fixture", "id": int(fixture_id)})

    def throttle(self, seconds: float = 0.15) -> None:
        time.sleep(seconds)

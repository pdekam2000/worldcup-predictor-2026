"""Optional external data providers — API-Sports remains primary."""

from worldcup_predictor.providers.base import (
    EnrichmentOutcome,
    ProviderCallResult,
    ProviderStatus,
    ProviderTier,
)
from worldcup_predictor.providers.enrichment_service import EnrichmentService
from worldcup_predictor.providers.registry import ProviderRegistry
from worldcup_predictor.providers.sportmonks_client import SportmonksClient
from worldcup_predictor.providers.the_odds_api_client import TheOddsApiClient
from worldcup_predictor.providers.weather_provider import WeatherProvider

__all__ = [
    "EnrichmentOutcome",
    "EnrichmentService",
    "ProviderCallResult",
    "ProviderRegistry",
    "ProviderStatus",
    "ProviderTier",
    "SportmonksClient",
    "TheOddsApiClient",
    "WeatherProvider",
]

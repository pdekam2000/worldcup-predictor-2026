"""Provider registry — priority: API-Sports primary, optional enrichment, no mock fallback."""

from __future__ import annotations

from worldcup_predictor.config.settings import Settings
from worldcup_predictor.providers.base import ProviderStatus, ProviderTier
from worldcup_predictor.clients.rapid_football_stats import RapidFootballStatsClient
from worldcup_predictor.clients.rapid_open_weather import RapidOpenWeatherClient
from worldcup_predictor.clients.rapid_xg_statistics import RapidXgStatisticsClient
from worldcup_predictor.providers.sportmonks_client import SportmonksClient
from worldcup_predictor.providers.the_odds_api_client import TheOddsApiClient
from worldcup_predictor.providers.weather_provider import WeatherProvider


class ProviderRegistry:
    """
    Central registry for optional external providers.

    Priority policy (documented, enforced by EnrichmentService):
      1. API-Sports (ApiFootballClient) — primary football data
      2. Sportmonks / RapidAPI — supplemental enrichment when primary fields are empty
      3. The Odds API — odds comparison when API-Sports odds missing
      4. WeatherAPI / OpenWeather — weather when fixture payload has none
      5. No mock fallback — missing optional keys simply skip enrichment
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.sportmonks = SportmonksClient(settings)
        self.the_odds_api = TheOddsApiClient(settings)
        self.weather = WeatherProvider(settings)
        self.rapid_football_stats = RapidFootballStatsClient(settings)
        self.rapid_xg_statistics = RapidXgStatisticsClient(settings)
        self.rapid_open_weather = RapidOpenWeatherClient(settings)

    @property
    def any_enrichment_configured(self) -> bool:
        return (
            self.sportmonks.is_configured
            or self.the_odds_api.is_configured
            or self.weather.is_configured
            or self.rapid_football_stats.is_configured
            or self.rapid_xg_statistics.is_configured
            or self.rapid_open_weather.is_configured
        )

    def status_report(self) -> list[ProviderStatus]:
        return [
            ProviderStatus(
                provider="api_sports",
                tier=ProviderTier.PRIMARY,
                configured=self._settings.api_football_configured,
                label="API-Sports (API-Football)",
                env_var="API_FOOTBALL_KEY",
                note="Required primary football provider.",
            ),
            ProviderStatus(
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                configured=self.sportmonks.is_configured,
                label="Sportmonks",
                env_var="SPORTMONKS_API_KEY",
                note="Optional backup/enrichment for fixtures, stats, squads.",
            ),
            ProviderStatus(
                provider="rapid_football_stats",
                tier=ProviderTier.ENRICHMENT,
                configured=self.rapid_football_stats.is_configured,
                label="RapidAPI Football Stats",
                env_var="RAPID_FOOTBALL_STATS_KEY",
                note="Optional xG, player stats, odds, live scores (requires RAPID_FOOTBALL_STATS_ENABLED=true).",
            ),
            ProviderStatus(
                provider="rapid_xg_statistics",
                tier=ProviderTier.ENRICHMENT,
                configured=self.rapid_xg_statistics.is_configured,
                label="Rapid Football XG Statistics",
                env_var="RAPID_XG_KEY",
                note="Optional xG, odds comparison, tournament mapping (requires RAPID_XG_ENABLED=true).",
            ),
            ProviderStatus(
                provider="rapid_open_weather",
                tier=ProviderTier.ENRICHMENT,
                configured=self.rapid_open_weather.is_configured,
                label="Rapid Open Weather",
                env_var="RAPID_OPEN_WEATHER_KEY",
                note="Optional weather backup when primary weather provider is missing (requires RAPID_OPEN_WEATHER_ENABLED=true).",
            ),
            ProviderStatus(
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                configured=self.the_odds_api.is_configured,
                label="The Odds API",
                env_var="THE_ODDS_API_KEY",
                note="Optional odds comparison when API-Sports odds are empty.",
            ),
            ProviderStatus(
                provider=self.weather.active_provider_name,
                tier=ProviderTier.ENRICHMENT,
                configured=self.weather.is_configured,
                label=f"Weather ({self.weather.active_provider_name})",
                env_var=self.weather.active_env_var,
                note="Optional venue weather enrichment.",
            ),
        ]

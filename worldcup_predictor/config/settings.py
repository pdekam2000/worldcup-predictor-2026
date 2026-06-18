from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Locale = Literal["en", "de", "fa", "sr", "bs", "hr"]
WeatherProviderKind = Literal["weatherapi", "openweather"]
AppEnv = Literal["local", "production"]


class Settings(BaseSettings):
    """Application configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_football_key: str = Field(default="", alias="API_FOOTBALL_KEY")
    api_football_base_url: str = Field(
        default="https://v3.football.api-sports.io",
        alias="API_FOOTBALL_BASE_URL",
    )

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    default_locale: Locale = Field(default="en", alias="DEFAULT_LOCALE")
    upcoming_fixture_limit: int = Field(default=5, alias="UPCOMING_FIXTURE_LIMIT")
    api_cache_dir: str = Field(default=".cache/api_football", alias="API_CACHE_DIR")
    api_cache_ttl_seconds: int = Field(default=3600, alias="API_CACHE_TTL_SECONDS")
    api_sync_mode: str = Field(default="fast", alias="API_SYNC_MODE")
    api_throttle_delay_seconds: float = Field(default=1.0, alias="API_THROTTLE_DELAY_SECONDS")
    api_throttle_warning_delay_seconds: float = Field(default=2.0, alias="API_THROTTLE_WARNING_DELAY_SECONDS")
    api_throttle_rate_limit_delay_seconds: float = Field(default=5.0, alias="API_THROTTLE_RATE_LIMIT_DELAY_SECONDS")

    # Database — PostgreSQL primary for SaaS; SQLite for intelligence (legacy/local)
    app_env: AppEnv = Field(default="local", alias="APP_ENV")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    sqlite_path: str = Field(default="data/football_intelligence.db", alias="SQLITE_PATH")
    database_fallback_enabled: bool = Field(default=True, alias="DATABASE_FALLBACK_ENABLED")

    # JWT auth (Phase 2)
    jwt_secret: str = Field(default="dev-only-change-in-production", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(default=10080, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")

    # Optional enrichment providers (not required — API-Sports remains primary)
    sportmonks_api_key: str = Field(default="", alias="SPORTMONKS_API_KEY")
    sportmonks_api_token: str = Field(default="", alias="SPORTMONKS_API_TOKEN")
    sportmonks_base_url: str = Field(
        default="https://api.sportmonks.com/v3/football",
        alias="SPORTMONKS_BASE_URL",
    )
    sportmonks_timeout_seconds: float = Field(default=20.0, alias="SPORTMONKS_TIMEOUT_SECONDS")
    the_odds_api_key: str = Field(default="", alias="THE_ODDS_API_KEY")
    the_odds_api_base_url: str = Field(
        default="https://api.the-odds-api.com/v4",
        alias="THE_ODDS_API_BASE_URL",
    )
    the_odds_api_sport: str = Field(
        default="soccer_fifa_world_cup",
        alias="THE_ODDS_API_SPORT",
    )
    the_odds_api_regions: str = Field(default="eu", alias="THE_ODDS_API_REGIONS")

    weather_provider: WeatherProviderKind = Field(default="weatherapi", alias="WEATHER_PROVIDER")
    weather_api_key: str = Field(default="", alias="WEATHER_API_KEY")
    openweather_api_key: str = Field(default="", alias="OPENWEATHER_API_KEY")

    # RapidAPI supplemental football stats (optional enrichment)
    rapid_football_stats_enabled: bool = Field(default=False, alias="RAPID_FOOTBALL_STATS_ENABLED")
    rapid_football_stats_key: str = Field(default="", alias="RAPID_FOOTBALL_STATS_KEY")
    rapid_football_stats_host: str = Field(
        default="football-stats-api-live-scores-xg-odds-player-data.p.rapidapi.com",
        alias="RAPID_FOOTBALL_STATS_HOST",
    )
    rapid_football_stats_base_url: str = Field(
        default="https://football-stats-api-live-scores-xg-odds-player-data.p.rapidapi.com",
        alias="RAPID_FOOTBALL_STATS_BASE_URL",
    )

    # RapidAPI xG statistics (optional enrichment)
    rapid_xg_enabled: bool = Field(default=False, alias="RAPID_XG_ENABLED")
    rapid_xg_key: str = Field(default="", alias="RAPID_XG_KEY")
    rapid_xg_host: str = Field(
        default="football-xg-statistics.p.rapidapi.com",
        alias="RAPID_XG_HOST",
    )
    rapid_xg_base_url: str = Field(
        default="https://football-xg-statistics.p.rapidapi.com",
        alias="RAPID_XG_BASE_URL",
    )

    # RapidAPI Open Weather backup (optional enrichment)
    rapid_open_weather_enabled: bool = Field(default=False, alias="RAPID_OPEN_WEATHER_ENABLED")
    rapid_open_weather_key: str = Field(default="", alias="RAPID_OPEN_WEATHER_KEY")
    rapid_open_weather_host: str = Field(
        default="open-weather13.p.rapidapi.com",
        alias="RAPID_OPEN_WEATHER_HOST",
    )
    rapid_open_weather_base_url: str = Field(
        default="https://open-weather13.p.rapidapi.com",
        alias="RAPID_OPEN_WEATHER_BASE_URL",
    )

    @property
    def api_football_configured(self) -> bool:
        return bool(self.api_football_key.strip())

    @property
    def sportmonks_effective_token(self) -> str:
        return (self.sportmonks_api_token or self.sportmonks_api_key).strip()

    @property
    def sportmonks_configured(self) -> bool:
        return bool(self.sportmonks_effective_token)

    @property
    def the_odds_api_configured(self) -> bool:
        return bool(self.the_odds_api_key.strip())

    @property
    def openweather_configured(self) -> bool:
        return bool(self.openweather_api_key.strip())

    @property
    def weather_provider_configured(self) -> bool:
        if self.weather_provider == "openweather":
            return self.openweather_configured or self.weather_configured
        return self.weather_configured

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key.strip())

    @property
    def weather_configured(self) -> bool:
        return bool(self.weather_api_key.strip())

    @property
    def effective_openweather_key(self) -> str:
        return self.openweather_api_key.strip() or self.weather_api_key.strip()

    @property
    def rapid_football_stats_configured(self) -> bool:
        return bool(self.rapid_football_stats_enabled and self.rapid_football_stats_key.strip())

    @property
    def rapid_xg_configured(self) -> bool:
        return bool(self.rapid_xg_enabled and self.rapid_xg_key.strip())

    @property
    def rapid_open_weather_configured(self) -> bool:
        return bool(self.rapid_open_weather_enabled and self.rapid_open_weather_key.strip())

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def postgres_configured(self) -> bool:
        return bool((self.database_url or "").strip())

    @property
    def postgres_required(self) -> bool:
        """Production and SaaS layers require PostgreSQL."""
        return self.is_production or self.postgres_configured

    @model_validator(mode="after")
    def _prefer_local_pgembed_url(self) -> "Settings":
        """Use pgembed URL file in local dev — port changes each embedded PG start."""
        if self.is_production:
            return self
        url_file = Path(__file__).resolve().parents[2] / "data" / "pgembed_dev" / "database.url"
        if not url_file.exists():
            return self
        file_url = url_file.read_text(encoding="utf-8").strip()
        if file_url:
            object.__setattr__(self, "database_url", file_url)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

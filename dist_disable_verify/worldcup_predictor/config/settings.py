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
    api_daily_live_limit: int = Field(default=7500, alias="API_DAILY_LIVE_LIMIT")
    fixtures_list_cache_ttl_seconds: int = Field(default=1800, alias="FIXTURES_LIST_CACHE_TTL_SECONDS")
    prediction_cache_dir: str = Field(default=".cache/predictions", alias="PREDICTION_CACHE_DIR")
    prediction_refresh_cooldown_seconds: int = Field(default=300, alias="PREDICTION_REFRESH_COOLDOWN_SECONDS")

    # Phase 12B — specialist lambda bridge (shadow parallel path; production unchanged)
    lambda_bridge_mode: Literal["off", "shadow", "limited", "full"] = Field(
        default="shadow",
        alias="LAMBDA_BRIDGE_MODE",
    )
    lambda_bridge_shadow_path: str = Field(
        default="data/shadow/lambda_bridge_shadow.jsonl",
        alias="LAMBDA_BRIDGE_SHADOW_PATH",
    )
    lambda_bridge_config_version: str = Field(
        default="12b-v1",
        alias="LAMBDA_BRIDGE_CONFIG_VERSION",
    )

    # Phase 21A — Rule A harmonization gate (shadow only; production unchanged)
    rule_a_gate_mode: Literal["off", "shadow"] = Field(
        default="shadow",
        alias="RULE_A_GATE_MODE",
    )
    rule_a_shadow_path: str = Field(
        default="data/shadow/rule_a_shadow.jsonl",
        alias="RULE_A_SHADOW_PATH",
    )

    # Phase 21A-LIVE — forward-only Rule A validation (no historical bootstrap)
    rule_a_live_mode: Literal["off", "shadow"] = Field(
        default="shadow",
        alias="RULE_A_LIVE_MODE",
    )
    rule_a_live_path: str = Field(
        default="data/shadow/rule_a_live_validation.jsonl",
        alias="RULE_A_LIVE_PATH",
    )

    # Phase 24A — expected lineup promotion (lineup_strength factor; weights unchanged)
    expected_lineup_promotion_mode: Literal["off", "shadow", "gated"] = Field(
        default="shadow",
        alias="EXPECTED_LINEUP_PROMOTION_MODE",
    )
    expected_lineup_promotion_shadow_path: str = Field(
        default="data/shadow/expected_lineup_promotion_shadow.jsonl",
        alias="EXPECTED_LINEUP_PROMOTION_SHADOW_PATH",
    )

    # Phase 24B — tournament context promotion (motivation_psychology factor; weights unchanged)
    tournament_context_promotion_mode: Literal["off", "shadow", "gated"] = Field(
        default="shadow",
        alias="TOURNAMENT_CONTEXT_PROMOTION_MODE",
    )
    tournament_context_promotion_shadow_path: str = Field(
        default="data/shadow/tournament_context_promotion_shadow.jsonl",
        alias="TOURNAMENT_CONTEXT_PROMOTION_SHADOW_PATH",
    )

    # Phase 24C — xG promotion (tactics_matchup factor; weights unchanged)
    xg_promotion_mode: Literal["off", "shadow", "gated"] = Field(
        default="shadow",
        alias="XG_PROMOTION_MODE",
    )
    xg_promotion_shadow_path: str = Field(
        default="data/shadow/xg_promotion_shadow.jsonl",
        alias="XG_PROMOTION_SHADOW_PATH",
    )

    # Phase 24C — Sportmonks prediction promotion (confidence/audit only)
    sportmonks_prediction_promotion_mode: Literal["off", "shadow", "gated"] = Field(
        default="shadow",
        alias="SPORTMONKS_PREDICTION_PROMOTION_MODE",
    )
    sportmonks_prediction_promotion_shadow_path: str = Field(
        default="data/shadow/sportmonks_prediction_promotion_shadow.jsonl",
        alias="SPORTMONKS_PREDICTION_PROMOTION_SHADOW_PATH",
    )

    # Phase 26 — real-world validation framework (capture only; promotions stay shadow)
    real_world_validation_mode: Literal["off", "shadow"] = Field(
        default="shadow",
        alias="REAL_WORLD_VALIDATION_MODE",
    )
    real_world_validation_path: str = Field(
        default="data/validation/real_world_validation.jsonl",
        alias="REAL_WORLD_VALIDATION_PATH",
    )
    real_world_validation_stats_path: str = Field(
        default="data/validation/promotion_contribution_stats.json",
        alias="REAL_WORLD_VALIDATION_STATS_PATH",
    )
    national_team_intelligence_enabled: bool = Field(
        default=True,
        alias="NATIONAL_TEAM_INTELLIGENCE_ENABLED",
    )
    worldcup_prediction_window_days: int = Field(
        default=3,
        alias="WORLDCUP_PREDICTION_WINDOW_DAYS",
    )
    worldcup_background_prediction_enabled: bool = Field(
        default=True,
        alias="WORLDCUP_BACKGROUND_PREDICTION_ENABLED",
    )

    # Database — PostgreSQL primary for SaaS; SQLite for intelligence (legacy/local)
    app_env: AppEnv = Field(default="local", alias="APP_ENV")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    sqlite_path: str = Field(default="data/football_intelligence.db", alias="SQLITE_PATH")
    database_fallback_enabled: bool = Field(default=True, alias="DATABASE_FALLBACK_ENABLED")

    # JWT auth (Phase 2)
    jwt_secret: str = Field(default="dev-only-change-in-production", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(default=10080, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")

    # Phase 37A — admin panel access gates (never expose to frontend)
    admin_access_key: str = Field(default="", alias="ADMIN_ACCESS_KEY")
    super_admin_access_key: str = Field(default="", alias="SUPER_ADMIN_ACCESS_KEY")
    admin_audit_log_path: str = Field(default="data/logs/admin_audit.jsonl", alias="ADMIN_AUDIT_LOG_PATH")
    auth_audit_log_path: str = Field(default="data/logs/auth_audit.jsonl", alias="AUTH_AUDIT_LOG_PATH")
    admin_gate_ttl_minutes: int = Field(default=60, alias="ADMIN_GATE_TTL_MINUTES")

    # Phase 38A — subscription contact admin (never expose admin email to users)
    admin_contact_email: str = Field(default="", alias="ADMIN_CONTACT_EMAIL")
    subscription_audit_log_path: str = Field(
        default="data/logs/subscription_audit.jsonl",
        alias="SUBSCRIPTION_AUDIT_LOG_PATH",
    )
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    email_verification_required: bool = Field(default=True, alias="EMAIL_VERIFICATION_REQUIRED")

    # Phase 39B-1 — Stripe SaaS billing (optional; missing env must not break startup)
    stripe_secret_key: str = Field(default="", alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field(default="", alias="STRIPE_WEBHOOK_SECRET")
    stripe_starter_price_id: str = Field(default="", alias="STRIPE_STARTER_PRICE_ID")
    stripe_pro_price_id: str = Field(default="", alias="STRIPE_PRO_PRICE_ID")
    stripe_success_url: str = Field(default="", alias="STRIPE_SUCCESS_URL")
    stripe_cancel_url: str = Field(default="", alias="STRIPE_CANCEL_URL")
    stripe_portal_return_url: str = Field(default="", alias="STRIPE_PORTAL_RETURN_URL")
    stripe_mode: str = Field(default="", alias="STRIPE_MODE")

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

    @property
    def stripe_secret_key_configured(self) -> bool:
        return bool(self.stripe_secret_key.strip())

    @property
    def stripe_webhook_secret_configured(self) -> bool:
        return bool(self.stripe_webhook_secret.strip())

    @property
    def stripe_starter_price_configured(self) -> bool:
        return bool(self.stripe_starter_price_id.strip())

    @property
    def stripe_pro_price_configured(self) -> bool:
        return bool(self.stripe_pro_price_id.strip())

    @property
    def stripe_success_url_configured(self) -> bool:
        return bool(self.stripe_success_url.strip())

    @property
    def stripe_cancel_url_configured(self) -> bool:
        return bool(self.stripe_cancel_url.strip())

    @property
    def stripe_portal_return_url_configured(self) -> bool:
        return bool(self.effective_stripe_portal_return_url.strip())

    @property
    def effective_stripe_portal_return_url(self) -> str:
        explicit = (self.stripe_portal_return_url or "").strip()
        if explicit:
            return explicit
        success = (self.stripe_success_url or "").strip()
        if success:
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(success)
            path = parsed.path.rstrip("/")
            if path.endswith("/success"):
                path = path[: -len("/success")]
            portal_path = f"{path}/subscription" if path else "/subscription"
            return urlunparse((parsed.scheme, parsed.netloc, portal_path, "", "", ""))
        return ""

    @property
    def stripe_mode_normalized(self) -> str:
        raw = (self.stripe_mode or "").strip().lower()
        if raw in ("test", "live"):
            return raw
        return "missing"

    def stripe_price_id_for_plan(self, plan: str) -> str:
        key = str(plan or "").strip().lower()
        if key == "starter":
            return self.stripe_starter_price_id.strip()
        if key == "pro":
            return self.stripe_pro_price_id.strip()
        return ""

    @property
    def stripe_billing_configured(self) -> bool:
        return (
            self.stripe_secret_key_configured
            and self.stripe_starter_price_configured
            and self.stripe_pro_price_configured
            and self.stripe_success_url_configured
            and self.stripe_cancel_url_configured
            and self.stripe_mode_normalized in ("test", "live")
        )

    @property
    def smtp_configured(self) -> bool:
        return bool(
            (self.smtp_host or "").strip()
            and (self.smtp_from or self.smtp_user or "").strip()
        )

    @property
    def admin_contact_email_configured(self) -> bool:
        return bool((self.admin_contact_email or "").strip())

    @property
    def email_operations_ready(self) -> bool:
        return self.smtp_configured and self.admin_contact_email_configured

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


from worldcup_predictor.config.env_loading import note_loaded_env_file, resolve_env_file


@lru_cache
def get_settings() -> Settings:
    env_path = resolve_env_file()
    note_loaded_env_file(env_path)
    if env_path is not None:
        return Settings(_env_file=str(env_path))
    return Settings()

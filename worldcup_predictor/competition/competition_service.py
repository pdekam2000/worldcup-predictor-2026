from __future__ import annotations

from worldcup_predictor.config.competitions import (
    COMPETITION_REGISTRY,
    CompetitionConfig,
    DEFAULT_COMPETITION_KEY,
    get_competition,
    list_competition_keys,
    normalize_competition_key,
)


class CompetitionService:
    """Competition registry access — multi-league expansion layer."""

    def get_competition(self, key: str | None = None) -> CompetitionConfig:
        return get_competition(key)

    def list_competitions(self) -> list[CompetitionConfig]:
        return [COMPETITION_REGISTRY[k] for k in list_competition_keys()]

    def is_worldcup_mode(self, key: str | None = None) -> bool:
        return normalize_competition_key(key) == DEFAULT_COMPETITION_KEY

    def get_supported_features(self, key: str | None = None) -> dict[str, bool | str]:
        comp = self.get_competition(key)
        return {
            "competition_key": comp.key,
            "competition_type": comp.compensation_type,
            "supports_groups": comp.supports_groups,
            "supports_table": comp.supports_table,
            "supports_knockout": comp.supports_knockout,
        }

    def resolve_league_id(self, key: str | None = None) -> int | None:
        comp = self.get_competition(key)
        if not comp.league_id_configured:
            return None
        return comp.league_id

    def get_default_season(self, key: str | None = None) -> int:
        comp = self.get_competition(key)
        if comp.default_seasons:
            return comp.default_seasons[-1]
        return comp.season

    def list_enabled_competitions(self) -> list[CompetitionConfig]:
        return [c for c in self.list_competitions() if c.enabled]

    def list_european_leagues(self) -> list[CompetitionConfig]:
        from worldcup_predictor.config.league_registry import list_enabled_european_leagues

        return list_enabled_european_leagues()

    def requires_league_setup(self, key: str | None = None) -> bool:
        return self.resolve_league_id(key) is None

    def setup_required_message(self, key: str | None = None) -> str:
        comp = self.get_competition(key)
        return (
            f"Setup required for {comp.display_name}: "
            f"api_football_league_id is not configured (placeholder 0). "
            f"{comp.notes}"
        )

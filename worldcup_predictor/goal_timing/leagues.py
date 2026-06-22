"""Phase 51C — allowed leagues for Elite Goal Timing (European focus)."""

from __future__ import annotations

from dataclasses import dataclass

from worldcup_predictor.config.competitions import COMPETITION_REGISTRY, CompetitionConfig, get_competition


@dataclass(frozen=True)
class GoalTimingLeagueSpec:
    key: str
    name: str
    api_football_league_id: int
    default_season: int


# Eredivisie + Liga Portugal are goal-timing scoped even if not in main registry.
_EXTRA_LEAGUES: dict[str, GoalTimingLeagueSpec] = {
    "eredivisie": GoalTimingLeagueSpec("eredivisie", "Eredivisie", 88, 2024),
    "liga_portugal": GoalTimingLeagueSpec("liga_portugal", "Liga Portugal", 94, 2024),
}

GOAL_TIMING_ALLOWED_LEAGUE_KEYS: tuple[str, ...] = (
    "premier_league",
    "la_liga",
    "bundesliga",
    "serie_a",
    "ligue_1",
    "eredivisie",
    "liga_portugal",
    "champions_league",
    "europa_league",
)


def resolve_goal_timing_league(competition_key: str) -> CompetitionConfig | GoalTimingLeagueSpec | None:
    key = str(competition_key or "").strip().lower()
    if key in _EXTRA_LEAGUES:
        return _EXTRA_LEAGUES[key]
    if key in COMPETITION_REGISTRY and key in GOAL_TIMING_ALLOWED_LEAGUE_KEYS:
        return get_competition(key)
    return None


def is_goal_timing_allowed_league(competition_key: str) -> bool:
    return resolve_goal_timing_league(competition_key) is not None


def is_goal_timing_prediction_league(competition_key: str) -> bool:
    """Phase 51D — leagues eligible for published goal-timing predictions."""
    from worldcup_predictor.goal_timing.config import GOAL_TIMING_PREDICTION_LEAGUE_KEYS

    key = str(competition_key or "").strip().lower()
    return key in GOAL_TIMING_PREDICTION_LEAGUE_KEYS


def list_goal_timing_league_keys() -> list[str]:
    return list(GOAL_TIMING_ALLOWED_LEAGUE_KEYS)


def api_football_league_id(competition_key: str) -> int | None:
    spec = resolve_goal_timing_league(competition_key)
    if spec is None:
        return None
    if isinstance(spec, CompetitionConfig):
        return spec.league_id
    return spec.api_football_league_id

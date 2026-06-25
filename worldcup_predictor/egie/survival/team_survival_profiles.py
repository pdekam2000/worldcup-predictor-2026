"""Per-team scoring and conceding timing profiles from survival data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.survival.config import TEAM_PROFILES_PATH
from worldcup_predictor.egie.survival.hazard_model import bucket_goal_probabilities
from worldcup_predictor.egie.survival.kaplan_meier import fit_kaplan_meier
from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES
from worldcup_predictor.goal_timing.data.stored_adapter import HistoricalMatchContext, StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.leagues import GOAL_TIMING_ALLOWED_LEAGUE_KEYS
from worldcup_predictor.goal_timing.minute_ranges import effective_minute, minute_to_range_key


def _match_observations(matches: list[HistoricalMatchContext]) -> list[tuple[float, int]]:
    obs: list[tuple[float, int]] = []
    for ctx in matches:
        minute = ctx.first_goal_minute
        if ctx.goal_events:
            first = ctx.goal_events[0]
            minute = effective_minute(first.minute, first.extra_minute)
        scoreless = (ctx.first_goal_minute is None) and not ctx.goal_events
        if scoreless:
            obs.append((90.0, 0))
        elif minute is not None:
            obs.append((float(minute), 1))
    return obs


def _profile_from_matches(matches: list[HistoricalMatchContext]) -> dict[str, Any]:
    obs = _match_observations(matches)
    km = fit_kaplan_meier(obs)
    bucket_probs = bucket_goal_probabilities(km["survival_curve"])
    hazard = {
        bucket: round(bucket_probs.get(bucket, 0.0), 4) for bucket in GOAL_TIMING_MINUTE_RANGES
    }
    return {
        "samples": len(matches),
        "km_n": km["n"],
        "goal_timing_distribution": hazard,
        "checkpoint_goal_probability": km["checkpoint_goal_probability"],
    }


class TeamSurvivalProfileStore:
    """Build and cache team-level home/away timing profiles."""

    def __init__(self, *, stored: StoredGoalTimingAdapter | None = None) -> None:
        self.stored = stored or StoredGoalTimingAdapter()

    def build_profiles(
        self,
        *,
        before_kickoff: str,
        competition_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        keys = competition_keys or list(GOAL_TIMING_ALLOWED_LEAGUE_KEYS)
        fixtures = self.stored.repo.list_finished_fixtures_before(
            before_kickoff=before_kickoff,
            competition_keys=keys,
            limit=800,
        )
        teams: set[str] = set()
        for fx in fixtures:
            teams.add(str(fx.get("home_team") or ""))
            teams.add(str(fx.get("away_team") or ""))
        teams.discard("")

        profiles: dict[str, Any] = {}
        for team in sorted(teams):
            all_history = self.stored.team_history_before(
                team, before_kickoff=before_kickoff, competition_keys=keys, limit=60
            )
            home_matches = [m for m in all_history if m.is_home_for_team]
            away_matches = [m for m in all_history if not m.is_home_for_team]
            profiles[team] = {
                "scoring_timing_profile": _profile_from_matches(all_history),
                "home_profile": _profile_from_matches(home_matches),
                "away_profile": _profile_from_matches(away_matches),
            }
        return profiles

    def save(self, profiles: dict[str, Any], path: Path | None = None) -> Path:
        path = path or TEAM_PROFILES_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(profiles, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def load(path: Path | None = None) -> dict[str, Any]:
        path = path or TEAM_PROFILES_PATH
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

"""Historical reliability priors for hybrid confidence (no leakage)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from worldcup_predictor.egie.confidence.config import RELIABILITY_SHRINKAGE_KAPPA


class ReliabilityPriorStore:
    """Rolling hit-rate priors from chronologically prior evaluated fixtures."""

    def __init__(self, *, kappa: float = RELIABILITY_SHRINKAGE_KAPPA) -> None:
        self.kappa = kappa
        self._team_hits: dict[str, list[int]] = defaultdict(list)
        self._team_total: dict[str, int] = defaultdict(int)
        self._league_range_hits: dict[str, list[int]] = defaultdict(list)
        self._league_total: dict[str, int] = defaultdict(int)
        self._global_team_hit = 0.5
        self._global_range_hit = 0.28

    def observe(
        self,
        *,
        home_team: str,
        away_team: str,
        competition_key: str,
        team_hit: int | None,
        range_hit: int,
    ) -> None:
        if team_hit is not None:
            for team in (home_team, away_team):
                self._team_hits[team].append(team_hit)
                self._team_total[team] += 1
        self._league_range_hits[competition_key].append(range_hit)
        self._league_total[competition_key] += 1

    def team_reliability(self, home_team: str, away_team: str) -> float:
        home_n = self._team_total.get(home_team, 0)
        away_n = self._team_total.get(away_team, 0)
        home_hits = sum(self._team_hits.get(home_team, []))
        away_hits = sum(self._team_hits.get(away_team, []))
        pooled_n = home_n + away_n
        pooled_hits = home_hits + away_hits
        if pooled_n <= 0:
            return self._global_team_hit
        raw = pooled_hits / pooled_n
        return round(
            (pooled_n * raw + self.kappa * self._global_team_hit) / (pooled_n + self.kappa),
            4,
        )

    def range_reliability(self, competition_key: str) -> float:
        n = self._league_total.get(competition_key, 0)
        hits = sum(self._league_range_hits.get(competition_key, []))
        if n <= 0:
            return self._global_range_hit
        raw = hits / n
        return round(
            (n * raw + self.kappa * self._global_range_hit) / (n + self.kappa),
            4,
        )

    def set_global_priors(self, *, team_hit: float, range_hit: float) -> None:
        self._global_team_hit = team_hit
        self._global_range_hit = range_hit

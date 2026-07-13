"""Lambda bias analysis for ECSE tail forensics."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LambdaBiasAccumulator:
    n: int = 0
    sum_lambda_home: float = 0.0
    sum_lambda_away: float = 0.0
    sum_actual_home: float = 0.0
    sum_actual_away: float = 0.0
    sum_lambda_total: float = 0.0
    sum_actual_total: float = 0.0
    sum_lambda_gap: float = 0.0
    sum_actual_gap: float = 0.0
    favourite_lambda_inflation: list[float] = field(default_factory=list)
    underdog_suppression: list[float] = field(default_factory=list)
    btts_contradictions: int = 0
    clean_sheet_overpredict: int = 0
    missed_high_tail: int = 0

    def add(
        self,
        *,
        lambda_home: float,
        lambda_away: float,
        actual_home: int,
        actual_away: int,
        odds_home: float,
        odds_away: float,
        market_btts_yes: float | None,
        model_btts: float,
        top5_hit: bool,
        score_bucket: str,
        actual_rank: int,
    ) -> None:
        self.n += 1
        self.sum_lambda_home += lambda_home
        self.sum_lambda_away += lambda_away
        self.sum_actual_home += actual_home
        self.sum_actual_away += actual_away
        lt = lambda_home + lambda_away
        at = actual_home + actual_away
        self.sum_lambda_total += lt
        self.sum_actual_total += at
        self.sum_lambda_gap += abs(lambda_home - lambda_away)
        self.sum_actual_gap += abs(actual_home - actual_away)

        fav_home = odds_home <= odds_away
        if fav_home:
            self.favourite_lambda_inflation.append(lambda_home - actual_home)
            self.underdog_suppression.append(lambda_away - actual_away)
        else:
            self.favourite_lambda_inflation.append(lambda_away - actual_away)
            self.underdog_suppression.append(lambda_home - actual_home)

        if market_btts_yes is not None and market_btts_yes > 0.52 and model_btts < 0.42:
            self.btts_contradictions += 1
        if actual_away == 0 and lambda_away > 0.9 and not top5_hit:
            self.clean_sheet_overpredict += 1
        if score_bucket == "HIGH_SCORE_TAIL" and actual_rank > 10:
            self.missed_high_tail += 1

    def summary(self) -> dict[str, Any]:
        n = self.n or 1
        return {
            "fixtures": self.n,
            "lambda_home_bias": round(self.sum_lambda_home / n - self.sum_actual_home / n, 4),
            "lambda_away_bias": round(self.sum_lambda_away / n - self.sum_actual_away / n, 4),
            "total_lambda_bias": round(self.sum_lambda_total / n - self.sum_actual_total / n, 4),
            "lambda_gap_bias": round(self.sum_lambda_gap / n - self.sum_actual_gap / n, 4),
            "favourite_lambda_inflation_mean": round(sum(self.favourite_lambda_inflation) / n, 4),
            "underdog_suppression_mean": round(sum(self.underdog_suppression) / n, 4),
            "btts_contradiction_cases": self.btts_contradictions,
            "clean_sheet_miss_with_high_lambda_away": self.clean_sheet_overpredict,
            "high_score_tail_outside_top10": self.missed_high_tail,
        }


class LeagueLambdaBias:
    def __init__(self) -> None:
        self.by_league: dict[str, LambdaBiasAccumulator] = defaultdict(LambdaBiasAccumulator)

    def add(self, league: str, **kwargs: Any) -> None:
        self.by_league[league].add(**kwargs)

    def report(self) -> dict[str, Any]:
        return {k: v.summary() for k, v in sorted(self.by_league.items(), key=lambda x: -x[1].n)[:20]}

"""Deterministic team strength engine V1 with hierarchical shrinkage."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from worldcup_predictor.research.football_strength_foundation.historical_match_service import (
    HistoricalMatchService,
)
from worldcup_predictor.research.lambda_team_strength.metrics import half_life_weight, shrink_to_prior


@dataclass
class TeamSideStrength:
    attack_global: float
    attack_home: float
    attack_away: float
    defense_global: float
    defense_home: float
    defense_away: float
    scoring_var: float
    conceding_var: float
    freq_score_2plus: float
    freq_score_3plus: float
    freq_concede_2plus: float
    freq_concede_3plus: float
    freq_clean_sheet: float
    freq_btts: float
    freq_over25: float
    freq_over35: float
    freq_over45: float
    scoring_trend: float
    defensive_trend: float
    n_total: int
    n_home: int
    n_away: int
    low_data: bool
    promoted_like: bool
    fallback_count: int
    quality_tier: str
    uncertainty: float


@dataclass
class MatchStrengthBundle:
    home: TeamSideStrength
    away: TeamSideStrength
    league_avg_home: float
    league_avg_away: float
    home_advantage: float
    league_environment: float
    explanation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "home": asdict(self.home),
            "away": asdict(self.away),
            "league_avg_home": self.league_avg_home,
            "league_avg_away": self.league_avg_away,
            "home_advantage": self.home_advantage,
            "league_environment": self.league_environment,
            "explanation": self.explanation,
        }


def _var(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def _trend(xs: list[float]) -> float:
    """Recent half minus older half (positive = scoring up)."""
    if len(xs) < 4:
        return 0.0
    mid = len(xs) // 2
    old = sum(xs[:mid]) / mid
    new = sum(xs[mid:]) / (len(xs) - mid)
    return new - old


class TeamStrengthEngine:
    def __init__(self, history: HistoricalMatchService, *, half_life_days: float = 90.0, prior_strength: float = 8.0):
        self.history = history
        self.half_life_days = half_life_days
        self.prior_strength = prior_strength

    def _side(
        self,
        team: str,
        cutoff: datetime,
        league: str,
        *,
        target_fixture_id: int | None = None,
        window: int = 40,
    ) -> TeamSideStrength:
        hq = self.history.matches_for_team(team, cutoff, window=window, target_fixture_id=target_fixture_id)
        matches = hq.matches
        key = hq.team_key
        ph = self.history.store.prior_home(league)
        pa = self.history.store.prior_away(league)
        g_prior = (ph + pa) / 2.0
        fallback = 0
        if not matches:
            fallback = 2
            return TeamSideStrength(
                attack_global=g_prior,
                attack_home=ph,
                attack_away=pa,
                defense_global=g_prior,
                defense_home=pa,
                defense_away=ph,
                scoring_var=0.0,
                conceding_var=0.0,
                freq_score_2plus=0.0,
                freq_score_3plus=0.0,
                freq_concede_2plus=0.0,
                freq_concede_3plus=0.0,
                freq_clean_sheet=0.0,
                freq_btts=0.0,
                freq_over25=0.0,
                freq_over35=0.0,
                freq_over45=0.0,
                scoring_trend=0.0,
                defensive_trend=0.0,
                n_total=0,
                n_home=0,
                n_away=0,
                low_data=True,
                promoted_like=True,
                fallback_count=fallback,
                quality_tier="league_prior",
                uncertainty=0.55,
            )

        wh_sc: list[tuple[float, float]] = []
        wa_sc: list[tuple[float, float]] = []
        wh_conc: list[tuple[float, float]] = []
        wa_conc: list[tuple[float, float]] = []
        scored: list[float] = []
        conceded: list[float] = []
        s2 = s3 = c2 = c3 = cs = btts = o25 = o35 = o45 = 0
        n_h = n_a = 0
        for m in matches:
            days = (cutoff - m.kickoff).total_seconds() / 86400.0
            w = half_life_weight(days, self.half_life_days)
            tot = m.home_goals + m.away_goals
            if m.home_team == key:
                n_h += 1
                gf, ga = m.home_goals, m.away_goals
                wh_sc.append((gf, w))
                wh_conc.append((ga, w))
            else:
                n_a += 1
                gf, ga = m.away_goals, m.home_goals
                wa_sc.append((gf, w))
                wa_conc.append((ga, w))
            scored.append(gf)
            conceded.append(ga)
            if gf >= 2:
                s2 += 1
            if gf >= 3:
                s3 += 1
            if ga >= 2:
                c2 += 1
            if ga >= 3:
                c3 += 1
            if ga == 0:
                cs += 1
            if gf > 0 and ga > 0:
                btts += 1
            if tot > 2.5:
                o25 += 1
            if tot > 3.5:
                o35 += 1
            if tot > 4.5:
                o45 += 1

        def wavg(pairs: list[tuple[float, float]], prior: float, n: int) -> float:
            if not pairs:
                fallback_local = 1
                return prior
            sw = sum(w for _, w in pairs)
            est = sum(v * w for v, w in pairs) / max(sw, 1e-9)
            # hierarchical: team estimate shrunk to league prior; do NOT force low-goal artificial prior
            return shrink_to_prior(est, prior, max(n, 1), self.prior_strength)

        # track fallbacks for empty home/away splits
        fb = 0
        if not wh_sc:
            fb += 1
        if not wa_sc:
            fb += 1
        att_h = wavg(wh_sc, ph, n_h)
        att_a = wavg(wa_sc, pa, n_a)
        def_h = wavg(wh_conc, pa, n_h)
        def_a = wavg(wa_conc, ph, n_a)
        att_g = shrink_to_prior(sum(scored) / len(scored), g_prior, len(scored), self.prior_strength)
        def_g = shrink_to_prior(sum(conceded) / len(conceded), g_prior, len(conceded), self.prior_strength)
        n = len(matches)
        unc = min(0.6, 0.08 + 0.35 / math.sqrt(max(n, 1)) + 0.04 * fb)
        tier = "high" if n >= 20 else "medium" if n >= 8 else "low"
        return TeamSideStrength(
            attack_global=att_g,
            attack_home=att_h,
            attack_away=att_a,
            defense_global=def_g,
            defense_home=def_h,
            defense_away=def_a,
            scoring_var=_var(scored),
            conceding_var=_var(conceded),
            freq_score_2plus=s2 / n,
            freq_score_3plus=s3 / n,
            freq_concede_2plus=c2 / n,
            freq_concede_3plus=c3 / n,
            freq_clean_sheet=cs / n,
            freq_btts=btts / n,
            freq_over25=o25 / n,
            freq_over35=o35 / n,
            freq_over45=o45 / n,
            scoring_trend=_trend(scored),
            defensive_trend=_trend(conceded),
            n_total=n,
            n_home=n_h,
            n_away=n_a,
            low_data=n < 8,
            promoted_like=n < 12,
            fallback_count=fb,
            quality_tier=tier,
            uncertainty=unc,
        )

    def build_match(
        self,
        home_team: str,
        away_team: str,
        cutoff: datetime,
        league: str,
        *,
        target_fixture_id: int | None = None,
    ) -> MatchStrengthBundle:
        home = self._side(home_team, cutoff, league, target_fixture_id=target_fixture_id)
        away = self._side(away_team, cutoff, league, target_fixture_id=target_fixture_id)
        ph = self.history.store.prior_home(league)
        pa = self.history.store.prior_away(league)
        ha = max(0.0, ph - pa)
        env = ph + pa
        return MatchStrengthBundle(
            home=home,
            away=away,
            league_avg_home=ph,
            league_avg_away=pa,
            home_advantage=ha,
            league_environment=env,
            explanation={
                "half_life_days": self.half_life_days,
                "prior_strength": self.prior_strength,
                "shrinkage": "team->league->global via sample-size weights",
                "low_goal_force": False,
            },
        )

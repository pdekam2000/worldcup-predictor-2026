"""OddsPrimaryScorelineEngine — shadow λ from market odds (primary) + xG (secondary)."""

from __future__ import annotations

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.prediction.odds_primary.models import OddsPrimaryResult

# Phase 16 calibrated weights (shadow simulation)
ODDS_WEIGHT = 0.70
XG_WEIGHT = 0.25
STATS_WEIGHT = 0.05
CONFIG_VERSION = "16-v1"


class OddsPrimaryScorelineEngine:
    """Parallel shadow engine — does not replace production scoreline path."""

    def __init__(
        self,
        *,
        odds_weight: float = ODDS_WEIGHT,
        xg_weight: float = XG_WEIGHT,
        stats_weight: float = STATS_WEIGHT,
        config_version: str = CONFIG_VERSION,
    ) -> None:
        self._odds_weight = odds_weight
        self._xg_weight = xg_weight
        self._stats_weight = stats_weight
        self._config_version = config_version

    @property
    def config_version(self) -> str:
        return self._config_version

    def compute(self, report: MatchIntelligenceReport) -> OddsPrimaryResult:
        notes: list[str] = []
        odds_pair = self._odds_lambda(report)
        odds_available = odds_pair is not None

        if not odds_available:
            from worldcup_predictor.prediction.scoreline_engine import _expected_goals_from_report

            lh, la = _expected_goals_from_report(report)
            return OddsPrimaryResult(
                lambda_home=lh,
                lambda_away=la,
                lambda_source="production_fallback_no_odds",
                odds_available=False,
                xg_available=False,
                used_production_fallback=True,
                notes=["No market odds — shadow mirrors production λ (excluded from primary comparison)."],
            )

        odds_h, odds_a = odds_pair
        xg_pair = self._xg_lambda(report)
        xg_available = xg_pair is not None
        stats_h, stats_a = self._stats_support_nudge(report)

        if xg_available:
            xg_h, xg_a = xg_pair
            lh = odds_h * self._odds_weight + xg_h * self._xg_weight + stats_h
            la = odds_a * self._odds_weight + xg_a * self._xg_weight + stats_a
            source = "odds_primary_xg_secondary"
            notes.append(f"Blend odds={self._odds_weight:.0%} xG={self._xg_weight:.0%} stats_nudge")
        else:
            lh = odds_h + stats_h
            la = odds_a + stats_a
            source = "odds_primary_only"
            notes.append("xG unavailable — odds-primary + stats nudge only")

        lh = max(0.55, min(round(lh, 4), 3.8))
        la = max(0.55, min(round(la, 4), 3.8))

        return OddsPrimaryResult(
            lambda_home=lh,
            lambda_away=la,
            lambda_source=source,
            odds_lambda_home=round(odds_h, 4),
            odds_lambda_away=round(odds_a, 4),
            xg_lambda_home=round(xg_pair[0], 4) if xg_pair else None,
            xg_lambda_away=round(xg_pair[1], 4) if xg_pair else None,
            stats_nudge_home=stats_h,
            stats_nudge_away=stats_a,
            odds_available=True,
            xg_available=xg_available,
            used_production_fallback=False,
            blend_weights={
                "odds": self._odds_weight if xg_available else 1.0,
                "xg": self._xg_weight if xg_available else 0.0,
                "stats": self._stats_weight,
            },
            notes=notes,
        )

    def _odds_lambda(self, report: MatchIntelligenceReport) -> tuple[float, float] | None:
        odds = report.odds
        if not odds or not odds.available or not odds.bookmakers:
            return None

        home_odd = draw_odd = away_odd = None
        for bookmaker in odds.bookmakers:
            for bet in bookmaker.get("bets", []):
                if bet.get("name") != "Match Winner":
                    continue
                for value in bet.get("values", []):
                    label = value.get("value", "")
                    try:
                        odd_val = float(value.get("odd", 0))
                    except (TypeError, ValueError):
                        continue
                    if label == "Home":
                        home_odd = odd_val
                    elif label == "Draw":
                        draw_odd = odd_val
                    elif label == "Away":
                        away_odd = odd_val

        if not all([home_odd, draw_odd, away_odd]):
            return None

        inv = [1 / home_odd, 1 / draw_odd, 1 / away_odd]
        total = sum(inv)
        hp, _, ap = [x / total for x in inv]

        total_goals = 2.55
        try:
            from worldcup_predictor.prediction.scoring_engine import ScoringEngine

            ou = ScoringEngine._extract_ou_market_probs(report)
            if ou and ou.get("over_2_5") is not None:
                over_p = float(ou["over_2_5"])
                total_goals = 2.5 + (over_p - 0.5) * 1.35
        except Exception:
            pass

        non_draw = hp + ap
        if non_draw <= 0:
            return None
        share_h = hp / non_draw
        lh = max(0.45, total_goals * share_h * 0.95)
        la = max(0.45, total_goals * (1 - share_h) * 0.95)
        return lh, la

    def _xg_lambda(self, report: MatchIntelligenceReport) -> tuple[float, float] | None:
        from worldcup_predictor.prediction.scoring_engine import ScoringEngine

        engine = ScoringEngine()
        xg_h, xg_a = engine._xg_goal_hints(report)
        if xg_h is None or xg_a is None:
            return None
        floor = 0.52
        return max(floor, float(xg_h)), max(floor, float(xg_a))

    def _stats_support_nudge(self, report: MatchIntelligenceReport) -> tuple[float, float]:
        """Small support-only nudge from form/H2H — not a primary signal."""
        from worldcup_predictor.prediction.scoring_engine import ScoringEngine

        engine = ScoringEngine()
        form_home = engine._form_points(report.home_team.form, report.home_team.team_id)
        form_away = engine._form_points(report.away_team.form, report.away_team.team_id)
        form_delta = form_home - form_away
        _, h2h_bias = engine._score_h2h(report.head_to_head, report.home_team.team_id)
        nudge = (form_delta * 0.02 + h2h_bias) * self._stats_weight
        return nudge, -nudge

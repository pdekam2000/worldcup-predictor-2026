from __future__ import annotations

from typing import Any, Callable

from worldcup_predictor.prediction.scorer_candidates import build_first_goal_scorer_candidates
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.domain.prediction import (
    ConfidenceLevel,
    FirstGoalPrediction,
    HalftimePrediction,
    MarketPrediction,
    MatchPrediction,
    MultilingualText,
    OverUnderSelection,
    OneXTwoSelection,
    PredictionConfidenceBreakdown,
    PredictionReason,
    PredictionRiskWarning,
    RiskLevel,
    ScorelinePrediction,
)


class ScoringEngine:
    """
    Deterministic scoring from MatchIntelligenceReport.
    Produces analytical predictions — never betting recommendations.
    """

    FORM_WEIGHT = 0.22
    H2H_WEIGHT = 0.18
    INJURIES_WEIGHT = 0.15
    LINEUPS_WEIGHT = 0.10
    ODDS_WEIGHT = 0.15
    DATA_QUALITY_WEIGHT = 0.20

    def predict(
        self,
        report: MatchIntelligenceReport,
        *,
        specialist_report: MatchSpecialistReport | None = None,
        text_builder: Callable[[str, dict[str, Any] | None], MultilingualText] | None = None,
        use_weighted_decision: bool = True,
        factor_weights: dict[str, float] | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> MatchPrediction:
        tb = text_builder or self._default_text

        fixture = report.fixture
        home_name = report.home_team.team_name
        away_name = report.away_team.team_name
        match_name = f"{home_name} vs {away_name}"
        competition_key = fixture.competition_key if fixture else "world_cup_2026"

        quality_pct = (
            float(report.data_quality.breakdown_total)
            if report.data_quality and report.data_quality.breakdown_total
            else ((report.data_quality.score * 100) if report.data_quality else 0.0)
        )
        all_placeholder = report.is_placeholder

        form_home = self._form_points(report.home_team.form, report.home_team.team_id)
        form_away = self._form_points(report.away_team.form, report.away_team.team_id)
        form_delta = form_home - form_away
        form_score = self._clamp(50 + form_delta * 4, 0, 100)

        h2h_score, h2h_home_bias = self._score_h2h(report.head_to_head, report.home_team.team_id)
        injuries_score, injury_home_delta = self._score_injuries(report)
        lineups_available = bool(report.lineups and report.lineups.get("available"))
        lineups_score = 80.0 if lineups_available else 35.0

        odds_score, odds_home_bias, odds_over_bias = self._score_odds(report.odds)
        data_quality_score = quality_pct

        breakdown = PredictionConfidenceBreakdown(
            form_score=round(form_score, 1),
            h2h_score=round(h2h_score, 1),
            injuries_score=round(injuries_score, 1),
            lineups_score=round(lineups_score, 1),
            odds_score=round(odds_score, 1),
            data_quality_score=round(data_quality_score, 1),
            total=0.0,
        )
        breakdown.total = round(
            breakdown.form_score * self.FORM_WEIGHT
            + breakdown.h2h_score * self.H2H_WEIGHT
            + breakdown.injuries_score * self.INJURIES_WEIGHT
            + breakdown.lineups_score * self.LINEUPS_WEIGHT
            + breakdown.odds_score * self.ODDS_WEIGHT
            + breakdown.data_quality_score * self.DATA_QUALITY_WEIGHT,
            1,
        )

        confidence_score = breakdown.total
        reasons: list[PredictionReason] = []

        if all_placeholder:
            confidence_level = ConfidenceLevel.UNAVAILABLE
            confidence_score = min(confidence_score, 35.0)
        elif quality_pct < 35:
            confidence_level = ConfidenceLevel.LOW
            confidence_score = min(confidence_score, 48.0)
        elif quality_pct < 50:
            confidence_level = ConfidenceLevel.LOW
            confidence_score = min(confidence_score, 55.0)
        elif confidence_score >= 70:
            confidence_level = ConfidenceLevel.HIGH
        elif confidence_score >= 50:
            confidence_level = ConfidenceLevel.MEDIUM
        else:
            confidence_level = ConfidenceLevel.LOW

        no_bet_flag = (
            quality_pct < 45
            or confidence_level in (ConfidenceLevel.UNAVAILABLE, ConfidenceLevel.LOW)
            or all_placeholder
        )

        if "injuries" in report.missing_data:
            confidence_score = max(0, confidence_score - 8)
            reasons.append(
                PredictionReason(
                    key="injuries_missing",
                    weight=-0.08,
                    description=tb("reason.injuries_missing", None),
                )
            )

        specialist_adj = self._apply_specialist_signals(
            specialist_report or report.specialist_report,
            home_strength_base=form_delta * 0.05 + h2h_home_bias + injury_home_delta + odds_home_bias,
            total_goals_hint=0.0,
        )
        confidence_score = self._clamp(confidence_score + specialist_adj["confidence_delta"], 0, 100)
        home_strength = 1.0 + form_delta * 0.05 + h2h_home_bias + injury_home_delta + odds_home_bias
        home_strength += specialist_adj["home_bias"]
        away_strength = 1.0 - form_delta * 0.05 - h2h_home_bias - injury_home_delta - odds_home_bias
        away_strength += specialist_adj["away_bias"]
        draw_factor = 0.28 + (0.08 if abs(form_delta) <= 1 else 0.0)

        total_strength = max(home_strength + away_strength + draw_factor, 0.01)
        home_prob = home_strength / total_strength
        draw_prob = draw_factor / total_strength
        away_prob = away_strength / total_strength

        one_x_two_selection, one_x_two_prob = self._pick_1x2(home_prob, draw_prob, away_prob)

        expected_goals = self._estimate_goals(report, home_strength, away_strength)
        total_goals = expected_goals[0] + expected_goals[1] + specialist_adj.get("goals_adjustment", 0.0)
        low_goal_data = (
            quality_pct < 45
            or bool(report.missing_data)
            or all_placeholder
        )
        over_under_selection, over_under_prob = self._pick_over_under(
            total_goals,
            low_confidence=low_goal_data,
        )

        halftime_total = round(total_goals * 0.45, 2)
        first_goal_team = home_name if home_strength >= away_strength else away_name
        first_goal_player = self._pick_first_goal_player(report, first_goal_team)
        scorer_candidates, player_data_ok, player_msg = build_first_goal_scorer_candidates(
            report,
            first_goal_team,
            specialist_report=specialist_report,
        )
        if scorer_candidates and scorer_candidates[0].player:
            first_goal_player = scorer_candidates[0].player
        first_goal_minute = "16-30" if total_goals >= 2.5 else "31-45"

        risk_level: RiskLevel = "high" if no_bet_flag else ("medium" if confidence_score < 70 else "low")
        risk_warnings: list[PredictionRiskWarning] = [
            PredictionRiskWarning(level="high", messages=tb("risk.warning", None)),
        ]
        if no_bet_flag:
            risk_warnings.append(
                PredictionRiskWarning(level="high", messages=tb("predict.no_bet_warning", None))
            )

        lineup_warning = None
        if not lineups_available:
            lineup_warning = tb("predict.lineup_warning", None)
            risk_warnings.append(
                PredictionRiskWarning(level="medium", messages=lineup_warning)
            )

        missing_data_warnings = None
        if report.missing_data:
            missing_data_warnings = tb(
                "predict.missing_data_warning",
                {"fields": ", ".join(report.missing_data)},
            )

        reasons.extend(self._build_reasons(report, form_delta, h2h_home_bias, lineups_available))

        baseline = MatchPrediction(
            fixture_id=report.fixture_id,
            competition_key=competition_key,
            match_name=match_name,
            kickoff_utc=fixture.kickoff_utc if fixture else None,
            stage=fixture.stage if fixture else None,
            one_x_two=MarketPrediction(
                market="1x2",
                selection=one_x_two_selection,
                probability=round(one_x_two_prob, 3),
                label=tb(f"predict.selection.{one_x_two_selection}", {"team": first_goal_team if one_x_two_selection != "draw" else ""}),
            ),
            over_under=MarketPrediction(
                market="over_under_2_5",
                selection=over_under_selection,
                probability=round(over_under_prob, 3),
                label=tb(f"predict.selection.{over_under_selection}", None),
            ),
            scoreline=ScorelinePrediction(
                home_goals=expected_goals[0],
                away_goals=expected_goals[1],
            ),
            halftime=HalftimePrediction(
                estimated_total_goals=halftime_total,
                note=tb("predict.halftime_note", {"goals": halftime_total}),
            ),
            first_goal=FirstGoalPrediction(
                team=first_goal_team,
                player=first_goal_player,
                minute_range=first_goal_minute,
                scorer_candidates=scorer_candidates,
                player_data_unavailable=not player_data_ok,
                player_data_message=player_msg,
            ),
            confidence_score=round(confidence_score, 1),
            confidence_level=confidence_level,
            confidence_breakdown=breakdown,
            risk_level=risk_level,
            risk_warnings=risk_warnings,
            no_bet_flag=no_bet_flag,
            missing_data_warnings=missing_data_warnings,
            lineup_warning=lineup_warning,
            explanation=tb("predict.explanation.pending", None),
            disclaimer=tb("predict.analytical_disclaimer", None),
            reasons=reasons,
            is_placeholder=all_placeholder,
            metadata={
                "engine": "deterministic",
                "data_quality_pct": f"{quality_pct:.0f}",
                "specialist_score": str(specialist_adj.get("aggregated_score", "")),
                "expected_total_goals": f"{total_goals:.2f}",
                "ou_low_confidence": str(low_goal_data).lower(),
            },
        )

        if not use_weighted_decision:
            return self._finalize_prediction(baseline, report, home_name, away_name)

        from worldcup_predictor.decision.weighted_decision_engine import (
            DecisionInput,
            WeightedDecisionEngine,
        )

        decision_engine = WeightedDecisionEngine(
            factor_weights=factor_weights,
            thresholds=thresholds,
        )
        decision_output = decision_engine.decide(
            DecisionInput(
                baseline=baseline,
                report=report,
                specialist_report=specialist_report or report.specialist_report,
            )
        )
        merged = decision_engine.apply_decision(baseline, decision_output)
        return self._finalize_prediction(merged, report, home_name, away_name)

    def _finalize_prediction(
        self,
        prediction: MatchPrediction,
        report: MatchIntelligenceReport,
        home_name: str,
        away_name: str,
    ) -> MatchPrediction:
        from dataclasses import replace

        from worldcup_predictor.prediction.consistency_engine import harmonize_prediction, is_consistent
        from worldcup_predictor.prediction.explanation_builder import build_prediction_explanation
        from worldcup_predictor.prediction.prediction_quality import compute_prediction_quality
        from worldcup_predictor.prediction.scoreline_engine import generate_scoreline_candidates, primary_scoreline

        candidates = generate_scoreline_candidates(report)
        h, a = primary_scoreline(candidates)
        top_prob = candidates[0].probability if candidates else 0.0
        prediction = replace(
            prediction,
            scoreline=ScorelinePrediction(home_goals=float(h), away_goals=float(a)),
            scoreline_candidates=candidates,
        )
        prediction = harmonize_prediction(prediction, home_team=home_name, away_team=away_name)
        consistent = is_consistent(prediction)
        pq = compute_prediction_quality(prediction, report, consistency_ok=consistent)
        from worldcup_predictor.adaptive_confidence.engine import AdaptiveConfidenceEngine

        prediction = AdaptiveConfidenceEngine().enrich_prediction(
            prediction,
            report,
            base_prediction_quality=pq,
        )
        pq = prediction.prediction_quality_score
        return replace(
            prediction,
            prediction_quality_score=pq,
            group_context=report.group_context,
            explanation=build_prediction_explanation(prediction, report),
            metadata={
                **prediction.metadata,
                "prediction_quality_pct": f"{pq:.0f}",
                "consistency_passed": str(consistent).lower(),
                "scoreline_confidence": f"{top_prob:.2f}",
            },
        )

    def _apply_specialist_signals(
        self,
        specialist_report: MatchSpecialistReport | None,
        *,
        home_strength_base: float,
        total_goals_hint: float,
    ) -> dict[str, float]:
        """Optional Phase 4 adjustments from specialist agents."""
        result = {
            "confidence_delta": 0.0,
            "home_bias": 0.0,
            "away_bias": 0.0,
            "goals_adjustment": 0.0,
            "aggregated_score": None,
        }
        if specialist_report is None:
            return result

        agg = specialist_report.aggregated_signal_score
        if agg is not None:
            result["aggregated_score"] = agg
            result["confidence_delta"] = (agg - 50) * 0.08

        form_sig = specialist_report.signal("team_form_agent")
        if form_sig and form_sig.is_usable:
            home_f = form_sig.signals.get("form_score_home", 50)
            away_f = form_sig.signals.get("form_score_away", 50)
            delta = (home_f - away_f) / 200
            result["home_bias"] += delta
            result["away_bias"] -= delta

        mot_sig = specialist_report.signal("motivation_psychology_agent")
        if mot_sig and mot_sig.is_usable:
            hm = mot_sig.signals.get("motivation_score_home", 50)
            am = mot_sig.signals.get("motivation_score_away", 50)
            result["home_bias"] += (hm - am) / 300
            result["away_bias"] += (am - hm) / 300

        inj_sig = specialist_report.signal("injury_suspension_agent")
        if inj_sig and inj_sig.is_usable:
            absence = inj_sig.signals.get("key_absence_score", 0)
            result["confidence_delta"] -= min(absence / 20, 5)

        weather_sig = specialist_report.signal("weather_agent")
        if weather_sig and weather_sig.signals.get("rain_probability", 0) > 0.4:
            result["goals_adjustment"] -= 0.15

        tactics_sig = specialist_report.signal("tactics_agent")
        if tactics_sig and tactics_sig.signals.get("over_under_tendency") == "over_lean":
            result["goals_adjustment"] += 0.1

        master = specialist_report.master
        if master:
            for adj in master.signals.get("recommended_prediction_adjustments", []):
                if "under goals" in adj.lower():
                    result["goals_adjustment"] -= 0.1
                if "reduce confidence" in adj.lower():
                    result["confidence_delta"] -= 3

        return result

    @staticmethod
    def _default_text(key: str, params: dict[str, Any] | None) -> MultilingualText:
        text = key if not params else f"{key}|{params}"
        return MultilingualText.uniform(text)

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _form_points(form: list[str] | None, team_id: int | None = None) -> float:
        if form:
            points = {"W": 3, "D": 1, "L": 0}
            return float(sum(points.get(r.upper(), 1) for r in form))
        if team_id is not None:
            return 5.0 + (team_id % 13) * 0.35
        return 7.0

    def _score_h2h(
        self,
        h2h: dict[str, Any] | None,
        home_team_id: int | None,
    ) -> tuple[float, float]:
        if not h2h or not h2h.get("meetings"):
            return 45.0, 0.0

        meetings = h2h["meetings"]
        home_wins = 0
        away_wins = 0
        for meeting in meetings:
            goals = meeting.get("goals", {})
            teams = meeting.get("teams", {})
            home_id = teams.get("home", {}).get("id")
            home_g = goals.get("home", 0) or 0
            away_g = goals.get("away", 0) or 0
            if home_g == away_g:
                continue
            winner_is_home = home_g > away_g
            if home_team_id and home_id == home_team_id:
                if winner_is_home:
                    home_wins += 1
                else:
                    away_wins += 1
            elif winner_is_home:
                away_wins += 1
            else:
                home_wins += 1

        total = max(home_wins + away_wins, 1)
        bias = (home_wins - away_wins) / total * 0.15
        score = 50 + (home_wins - away_wins) * 8
        return self._clamp(score, 20, 90), bias

    def _score_injuries(self, report: MatchIntelligenceReport) -> tuple[float, float]:
        home_count = len(report.home_team.injuries.players) if report.home_team.injuries else 0
        away_count = len(report.away_team.injuries.players) if report.away_team.injuries else 0

        if "injuries" in report.missing_data:
            return 50.0, 0.0

        delta = (away_count - home_count) * 0.04
        score = 70 - (home_count + away_count) * 5
        return self._clamp(score, 25, 90), delta

    def _score_odds(
        self,
        odds,
    ) -> tuple[float, float, float]:
        if odds is None or not odds.available or not odds.bookmakers:
            return 50.0, 0.0, 0.0

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
            return 55.0, 0.0, 0.0

        inv = [1 / home_odd, 1 / draw_odd, 1 / away_odd]  # type: ignore[operator]
        total = sum(inv)
        home_prob, _, away_prob = [x / total for x in inv]
        bias = (home_prob - away_prob) * 0.2
        return 75.0, bias, 0.0

    def _estimate_goals(
        self,
        report: MatchIntelligenceReport,
        home_strength: float,
        away_strength: float,
    ) -> tuple[float, float]:
        home_avg = self._goals_average(report.home_team.statistics, side="for", team_id=report.home_team.team_id)
        away_avg = self._goals_average(report.away_team.statistics, side="for", team_id=report.away_team.team_id)
        home_against = self._goals_average(report.home_team.statistics, side="against", team_id=report.home_team.team_id)
        away_against = self._goals_average(report.away_team.statistics, side="against", team_id=report.away_team.team_id)

        has_real_home = bool(report.home_team.statistics and report.home_team.statistics.get("goals"))
        has_real_away = bool(report.away_team.statistics and report.away_team.statistics.get("goals"))
        floor = 0.52 if (has_real_home or has_real_away) else 0.45
        wc_baseline = 1.32

        home_goals = max(floor, (home_avg + away_against) / 2 * home_strength)
        away_goals = max(floor, (away_avg + home_against) / 2 * away_strength)

        if not has_real_home:
            home_goals = home_goals * 0.7 + wc_baseline * 0.3 * home_strength
        if not has_real_away:
            away_goals = away_goals * 0.7 + wc_baseline * 0.3 * away_strength

        xg_home, xg_away = self._xg_goal_hints(report)
        if xg_home is not None:
            home_goals = home_goals * 0.62 + max(xg_home, floor) * 0.38
        if xg_away is not None:
            away_goals = away_goals * 0.62 + max(xg_away, floor) * 0.38

        return round(home_goals, 2), round(away_goals, 2)

    @staticmethod
    def _xg_goal_hints(report: MatchIntelligenceReport) -> tuple[float | None, float | None]:
        try:
            from worldcup_predictor.chance_quality.stat_extraction import extract_real_xg

            hx, _ = extract_real_xg(
                report,
                side="home",
                team_stats=report.home_team.statistics or {},
            )
            ax, _ = extract_real_xg(
                report,
                side="away",
                team_stats=report.away_team.statistics or {},
            )
            return (float(hx) if hx is not None else None, float(ax) if ax is not None else None)
        except Exception:
            return None, None

    @staticmethod
    def _pick_over_under(
        total_goals: float,
        *,
        low_confidence: bool,
    ) -> tuple[OverUnderSelection, float]:
        margin = total_goals - 2.5
        if margin > 0.05:
            selection: OverUnderSelection = "over_2_5"
        elif margin < -0.05:
            selection = "under_2_5"
        else:
            selection = "over_2_5" if margin >= 0 else "under_2_5"
        distance = abs(margin)
        if low_confidence:
            probability = min(0.52 + distance * 0.08, 0.62)
        else:
            probability = min(0.55 + distance * 0.12, 0.78 if distance > 0.35 else 0.72)
        return selection, probability

    @staticmethod
    def _goals_average(stats: dict[str, Any] | None, side: str, team_id: int | None = None) -> float:
        if not stats:
            if team_id is not None:
                return 0.9 + (team_id % 17) * 0.08
            return 1.3
        if stats.get("recent_fixtures_count"):
            return 1.0 + (stats.get("recent_fixtures_count", 0) % 5) * 0.15
        goals = stats.get("goals", {}).get(side, {}).get("total", {})
        average = goals.get("average")
        if average is not None:
            try:
                return float(str(average).replace("%", ""))
            except ValueError:
                pass
        total = goals.get("total")
        played = stats.get("fixtures", {}).get("played", {}).get("total", 5)
        if total is not None and played:
            return float(total) / max(int(played), 1)
        return 1.3

    @staticmethod
    def _pick_1x2(
        home_prob: float,
        draw_prob: float,
        away_prob: float,
    ) -> tuple[OneXTwoSelection, float]:
        options: list[tuple[OneXTwoSelection, float]] = [
            ("home_win", home_prob),
            ("draw", draw_prob),
            ("away_win", away_prob),
        ]
        selection, prob = max(options, key=lambda item: item[1])
        return selection, prob

    @staticmethod
    def _over_under_probability(total_goals: float) -> float:
        distance = abs(total_goals - 2.5)
        return min(0.55 + distance * 0.12, 0.85)

    @staticmethod
    def _pick_first_goal_player(report: MatchIntelligenceReport, team_name: str) -> str:
        items = (report.lineups or {}).get("items") or []
        for lineup in items:
            if lineup.get("team", {}).get("name") == team_name:
                start = lineup.get("startXI") or []
                if start:
                    player = start[0].get("player", {})
                    name = player.get("name")
                    if name:
                        return name
        return "TBD (awaiting official lineups)"

    def _build_reasons(
        self,
        report: MatchIntelligenceReport,
        form_delta: float,
        h2h_bias: float,
        lineups_available: bool,
    ) -> list[PredictionReason]:
        reasons: list[PredictionReason] = []
        if report.home_team.form or report.away_team.form:
            reasons.append(
                PredictionReason(
                    key="form",
                    weight=self.FORM_WEIGHT,
                    description=MultilingualText.uniform(
                        f"Form differential favours {'home' if form_delta >= 0 else 'away'} side"
                    ),
                )
            )
        if h2h_bias != 0:
            reasons.append(
                PredictionReason(
                    key="h2h",
                    weight=self.H2H_WEIGHT,
                    description=MultilingualText.uniform("Head-to-head history weighted into outcome"),
                )
            )
        if not lineups_available:
            reasons.append(
                PredictionReason(
                    key="lineups_pending",
                    weight=-0.05,
                    description=MultilingualText.uniform(
                        "Official lineups not confirmed — prediction may change"
                    ),
                )
            )
        return reasons

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.decision.audit_report import (
    AuditFactorContribution,
    DataLimitation,
    DecisionConflict,
    FinalDecisionTrace,
    PredictionAuditReport,
)
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import (
    ConfidenceLevel,
    MatchPrediction,
    OverUnderSelection,
    OneXTwoSelection,
)
from worldcup_predictor.domain.specialist import MatchSpecialistReport


def _default_factor_weights() -> dict[str, float]:
    from worldcup_predictor.config.model_weights import get_factor_weights

    return get_factor_weights(use_calibrated=True)


def _default_thresholds() -> dict[str, float]:
    from worldcup_predictor.config.model_weights import get_thresholds

    return get_thresholds(use_calibrated=True)


@dataclass
class WeightedFactor:
    name: str
    weight: float
    score: float
    home_edge: float
    contribution: float = 0.0
    note: str = ""


@dataclass
class MarketDecision:
    market: str
    selection: str
    probability: float | None
    confidence: float
    analytical_edge_note: str = ""


@dataclass
class DecisionInput:
    baseline: MatchPrediction
    report: MatchIntelligenceReport
    specialist_report: MatchSpecialistReport | None = None


@dataclass
class DecisionOutput:
    confidence_score: float
    confidence_level: ConfidenceLevel
    no_bet_flag: bool
    markets: dict[str, MarketDecision] = field(default_factory=dict)
    audit: PredictionAuditReport | None = None
    first_goal_player_confidence: float | None = None
    home_strength_adjustment: float = 0.0
    away_strength_adjustment: float = 0.0
    over_under_confidence: float | None = None


class WeightedDecisionEngine:
    """
    Converts intelligence + specialist signals into weighted, auditable decisions.
    Analytical only — never betting recommendations.
    """

    FACTOR_WEIGHTS: dict[str, float] = {
        "data_quality": 0.15,
        "team_form": 0.15,
        "injuries_suspensions": 0.12,
        "lineup_strength": 0.12,
        "tactics_matchup": 0.12,
        "player_quality": 0.10,
        "odds_market_signal": 0.10,
        "motivation_psychology": 0.08,
        "weather_referee_context": 0.06,
    }

    def __init__(
        self,
        factor_weights: dict[str, float] | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> None:
        self._factor_weights = factor_weights or _default_factor_weights()
        self._thresholds = thresholds or _default_thresholds()

    def decide(self, decision_input: DecisionInput) -> DecisionOutput:
        baseline = decision_input.baseline
        report = decision_input.report
        specialist = decision_input.specialist_report or report.specialist_report

        factors = self._build_factors(report, specialist, baseline)
        audit = self._build_audit_skeleton(baseline.fixture_id, factors)

        home_edge_total = sum(f.contribution for f in factors.values())
        baseline_selection = baseline.one_x_two.selection

        conflicts = list(audit.conflicts)
        if specialist and specialist.master:
            for desc in specialist.master.signals.get("conflicts_between_agents", []):
                conflicts.append(DecisionConflict(description=desc, severity="medium"))

        confidence = baseline.confidence_score
        caps: list[str] = []
        reductions: list[str] = []
        no_bet_reasons: list[str] = []

        data_quality_pct = factors["data_quality"].score
        dq_cap_below = self._thresholds["data_quality_confidence_cap_below"]
        dq_cap_value = self._thresholds["data_quality_cap_value"]
        dq_no_bet = self._thresholds["data_quality_no_bet_threshold"]
        if data_quality_pct < dq_cap_below:
            if confidence > dq_cap_value:
                caps.append(f"data_quality_below_{int(dq_cap_below)}_cap_{int(dq_cap_value)}")
            confidence = min(confidence, dq_cap_value)

        official_lineups = self._official_lineups_available(specialist)
        first_goal_player_conf = baseline.confidence_score
        fg_cap = self._thresholds["missing_lineups_first_goal_cap"]
        if not official_lineups:
            if first_goal_player_conf > fg_cap:
                caps.append(f"missing_official_lineups_first_goal_player_cap_{int(fg_cap)}")
            first_goal_player_conf = min(first_goal_player_conf, fg_cap)

        conflict_count = len(conflicts)
        conflict_high = int(self._thresholds["specialist_conflict_high_count"])
        conflict_per = self._thresholds["specialist_conflict_penalty_per_conflict"]
        conflict_max = self._thresholds["specialist_conflict_penalty_max"]
        if conflict_count >= conflict_high:
            reduction = min(conflict_count * conflict_per, conflict_max)
            confidence -= reduction
            reductions.append(f"specialist_conflicts_high_minus_{int(reduction)}")

        market_warning = self._market_disagreement(baseline, factors, home_edge_total, specialist)
        if market_warning:
            audit.market_disagreement_warnings.append(market_warning)
            confidence -= self._thresholds["odds_disagreement_penalty"]
            reductions.append(f"odds_model_disagreement_minus_{int(self._thresholds['odds_disagreement_penalty'])}")

        severe_weather = factors["weather_referee_context"].score > 70 and self._rain_high(specialist)
        over_confidence = baseline.over_under.probability or 0.5
        over_confidence *= 100
        weather_penalty = self._thresholds["severe_weather_over_penalty"]
        if severe_weather and baseline.over_under.selection == "over_2_5":
            over_confidence = max(over_confidence - weather_penalty, 25)
            reductions.append("severe_weather_over_2_5_reduced")

        absence = self._absence_score(specialist)
        home_adj = 0.0
        away_adj = 0.0
        if absence > 50:
            home_inj = len(report.home_team.injuries.players if report.home_team.injuries else [])
            away_inj = len(report.away_team.injuries.players if report.away_team.injuries else [])
            if home_inj >= away_inj:
                home_adj -= 0.08
            else:
                away_adj -= 0.08
            reductions.append("high_injury_absence_team_strength_reduced")

        confidence = self._clamp(confidence, 0, 100)
        confidence_level = self._confidence_level(confidence, baseline.is_placeholder)

        no_bet = baseline.no_bet_flag
        no_bet_min = self._thresholds["no_bet_confidence_minimum"]
        if data_quality_pct < dq_no_bet:
            no_bet = True
            no_bet_reasons.append(f"data_quality_below_{int(dq_no_bet)}")
        if confidence_level in (ConfidenceLevel.UNAVAILABLE, ConfidenceLevel.LOW):
            no_bet = True
            no_bet_reasons.append(f"confidence_level_{confidence_level.value}")
        if baseline.is_placeholder:
            no_bet = True
            no_bet_reasons.append("placeholder_data")
        if confidence < no_bet_min:
            no_bet = True
            no_bet_reasons.append(f"confidence_below_{int(no_bet_min)}")

        analysis_ready_min = self._thresholds["analysis_ready_confidence_minimum"]
        watch_only = no_bet or confidence < analysis_ready_min

        one_x_two_selection = self._resolve_1x2(
            home_edge_total,
            baseline_selection,
            specialist=specialist,
            factors=factors,
        )
        over_selection = self._resolve_over_under(baseline, factors, severe_weather)

        markets = {
            "1x2": MarketDecision(
                market="1x2",
                selection=one_x_two_selection,
                probability=baseline.one_x_two.probability,
                confidence=confidence,
                analytical_edge_note="Analytical edge only — not guaranteed.",
            ),
            "over_under_2_5": MarketDecision(
                market="over_under_2_5",
                selection=over_selection,
                probability=baseline.over_under.probability,
                confidence=over_confidence if over_selection == "over_2_5" else 100 - over_confidence,
                analytical_edge_note="Informational market read — not betting advice.",
            ),
            "halftime_goals": MarketDecision(
                market="halftime_goals",
                selection=str(baseline.halftime.estimated_total_goals),
                probability=None,
                confidence=confidence * 0.85,
                analytical_edge_note="Halftime estimate — subject to lineup changes.",
            ),
            "first_goal_team": MarketDecision(
                market="first_goal_team",
                selection=baseline.first_goal.team,
                probability=None,
                confidence=confidence * 0.9,
                analytical_edge_note="Analytical lean — not guaranteed.",
            ),
            "first_goal_player": MarketDecision(
                market="first_goal_player",
                selection=baseline.first_goal.player or "TBD",
                probability=None,
                confidence=first_goal_player_conf,
                analytical_edge_note="Placeholder until official lineups confirmed.",
            ),
        }

        self._populate_audit_factors(audit, factors, home_edge_total, baseline_selection)
        audit.conflicts = conflicts
        audit.limitations = self._limitations(report, specialist)
        audit.first_goal_player_confidence = first_goal_player_conf
        audit.trace = FinalDecisionTrace(
            baseline_confidence=baseline.confidence_score,
            final_confidence=confidence,
            confidence_caps_applied=caps,
            confidence_reductions=reductions,
            no_bet_reasons=no_bet_reasons,
            watch_only=watch_only,
            analytical_edge_note=(
                "Watch only / wait for more data — insufficient analytical edge."
                if watch_only
                else "Moderate analytical edge — still not betting advice."
            ),
        )

        return DecisionOutput(
            confidence_score=round(confidence, 1),
            confidence_level=confidence_level,
            no_bet_flag=no_bet,
            markets=markets,
            audit=audit,
            first_goal_player_confidence=first_goal_player_conf,
            home_strength_adjustment=home_adj,
            away_strength_adjustment=away_adj,
            over_under_confidence=over_confidence,
        )

    def apply_decision(
        self,
        baseline: MatchPrediction,
        output: DecisionOutput,
    ) -> MatchPrediction:
        """Merge weighted decision output into baseline prediction."""
        if output.markets.get("1x2"):
            baseline.one_x_two.selection = output.markets["1x2"].selection  # type: ignore[assignment]
        if output.markets.get("over_under_2_5"):
            baseline.over_under.selection = output.markets["over_under_2_5"].selection  # type: ignore[assignment]

        baseline.confidence_score = output.confidence_score
        baseline.confidence_level = output.confidence_level
        baseline.no_bet_flag = output.no_bet_flag
        baseline.audit_report = output.audit
        baseline.first_goal_player_confidence = output.first_goal_player_confidence
        baseline.metadata["decision_engine"] = "weighted"
        baseline.metadata["watch_only"] = str(output.audit.trace.watch_only if output.audit and output.audit.trace else False)
        return baseline

    def _build_factors(
        self,
        report: MatchIntelligenceReport,
        specialist: MatchSpecialistReport | None,
        baseline: MatchPrediction,
    ) -> dict[str, WeightedFactor]:
        dq = (report.data_quality.score * 100) if report.data_quality else 40.0

        form_home, form_away = 50.0, 50.0
        if specialist and specialist.signal("team_form_agent"):
            sig = specialist.signal("team_form_agent").signals
            form_home = float(sig.get("form_score_home", 50))
            form_away = float(sig.get("form_score_away", 50))
        form_score = (form_home + form_away) / 2
        form_edge = (form_home - form_away) / 100

        if specialist and specialist.signal("elo_team_strength_intelligence_agent"):
            ev2 = specialist.signal("elo_team_strength_intelligence_agent").signals
            ev2_impact = ev2.get("prediction_impact") or {}
            form_edge += float(ev2_impact.get("home_adjustment", 0) - ev2_impact.get("away_adjustment", 0)) / 400
            home_side = ev2.get("home") or {}
            away_side = ev2.get("away") or {}
            hs = float(home_side.get("overall_team_strength", 50))
            aw = float(away_side.get("overall_team_strength", 50))
            form_score = (form_score + (hs + aw) / 2) / 2
            if "low_data_confidence" in (ev2.get("risk_flags") or []):
                form_edge *= 0.5
                form_score = min(form_score, 58.0)

        absence = self._absence_score(specialist)
        inj_score = self._clamp(100 - absence, 0, 100)
        home_inj = len(report.home_team.injuries.players if report.home_team.injuries else [])
        away_inj = len(report.away_team.injuries.players if report.away_team.injuries else [])
        inj_edge = (away_inj - home_inj) * 0.03

        if specialist and specialist.signal("injury_suspension_intelligence_agent"):
            iv2 = specialist.signal("injury_suspension_intelligence_agent").signals
            home_side = iv2.get("home") or {}
            away_side = iv2.get("away") or {}
            home_imp = float(home_side.get("injury_impact_score", 0))
            away_imp = float(away_side.get("injury_impact_score", 0))
            inj_score = self._clamp(100 - (home_imp + away_imp) / 2, 0, 100)
            impact = iv2.get("prediction_impact") or {}
            inj_edge = float(impact.get("home_adjustment", 0) - impact.get("away_adjustment", 0)) / 250
            if "low_data_confidence" in (home_side.get("risk_flags") or []) and "low_data_confidence" in (
                away_side.get("risk_flags") or []
            ):
                inj_score = min(inj_score, 55.0)
        elif specialist and specialist.signal("injury_suspension_agent"):
            inj_score = self._clamp(100 - self._absence_score(specialist), 0, 100)

        lineup_score = 35.0
        lineup_edge = 0.0
        if specialist and specialist.signal("lineup_intelligence_agent"):
            lv2 = specialist.signal("lineup_intelligence_agent").signals
            home_side = lv2.get("home") or {}
            away_side = lv2.get("away") or {}
            lineup_score = (
                float(home_side.get("lineup_strength", 35)) + float(away_side.get("lineup_strength", 35))
            ) / 2
            impact = lv2.get("prediction_impact") or {}
            lineup_edge = float(impact.get("home_adjustment", 0) - impact.get("away_adjustment", 0)) / 200
            if home_side.get("official_lineup") or away_side.get("official_lineup"):
                lineup_edge += 0.03
            if "official_lineup_missing" in (home_side.get("risk_flags") or []) and "official_lineup_missing" in (
                away_side.get("risk_flags") or []
            ):
                lineup_score = min(lineup_score, 40.0)
        elif specialist and specialist.signal("lineup_agent"):
            ls = specialist.signal("lineup_agent").signals
            lineup_score = float(ls.get("lineup_confidence_score", 35))
            if ls.get("official_lineups_available"):
                lineup_edge = 0.05

        tactics_score = 55.0
        tactics_over = 0.0
        if specialist and specialist.signal("tactics_agent"):
            ts = specialist.signal("tactics_agent").signals
            home_attack = float(ts.get("xg_attack_strength_home", 55))
            away_attack = float(ts.get("xg_attack_strength_away", 55))
            tactics_score = (home_attack + away_attack) / 2
            tendency = ts.get("over_under_tendency")
            if tendency == "over_lean":
                tactics_over = 0.08
            elif tendency == "under_lean":
                tactics_over = -0.08
            pressure = ts.get("expected_goal_pressure")
            if pressure is not None:
                try:
                    if float(pressure) >= 2.8:
                        tactics_over = max(tactics_over, 0.06)
                except (TypeError, ValueError):
                    pass

        if specialist and specialist.signal("lineup_intelligence_agent"):
            lv2_impact = specialist.signal("lineup_intelligence_agent").signals.get("prediction_impact") or {}
            tactics_over += float(lv2_impact.get("over25_adjustment", 0) or 0) / 100.0

        if specialist and specialist.signal("injury_suspension_intelligence_agent"):
            iv2_impact = specialist.signal("injury_suspension_intelligence_agent").signals.get(
                "prediction_impact"
            ) or {}
            tactics_over += float(iv2_impact.get("over25_adjustment", 0) or 0) / 150.0

        if specialist and specialist.signal("sharp_money_intelligence_agent"):
            smv2 = specialist.signal("sharp_money_intelligence_agent").signals
            sm_impact = smv2.get("prediction_impact") or {}
            tactics_over += float(sm_impact.get("over25_adjustment", 0) or 0) / 200.0
            if "low_market_confidence" in (smv2.get("risk_flags") or []):
                tactics_over *= 0.5

        if specialist and specialist.signal("elo_team_strength_intelligence_agent"):
            ev2_impact = specialist.signal("elo_team_strength_intelligence_agent").signals.get(
                "prediction_impact"
            ) or {}
            tactics_over += float(ev2_impact.get("over25_adjustment", 0) or 0) / 200.0
            if "low_data_confidence" in (
                specialist.signal("elo_team_strength_intelligence_agent").signals.get("risk_flags") or []
            ):
                tactics_over *= 0.5

        if specialist and specialist.signal("xg_chance_quality_intelligence_agent"):
            xv2 = specialist.signal("xg_chance_quality_intelligence_agent").signals
            xv2_impact = xv2.get("prediction_impact") or {}
            tactics_over += float(xv2_impact.get("over25_adjustment", 0) or 0) / 180.0
            tactics_score = (tactics_score + float(xv2.get("goals_pressure_score", 50))) / 2
            if "low_xg_data_confidence" in (xv2.get("risk_flags") or []):
                tactics_over *= 0.55
            if "limited_statistics" in (xv2.get("risk_flags") or []):
                tactics_score = min(tactics_score, 58.0)

        player_score = 65.0
        player_edge = 0.0
        if specialist and specialist.signal("player_quality_agent"):
            ps = specialist.signal("player_quality_agent").signals
            ph = float(ps.get("star_player_rating_home", 65))
            pa = float(ps.get("star_player_rating_away", 65))
            player_score = (ph + pa) / 2
            player_edge = (ph - pa) / 200

        odds_score = 50.0
        odds_edge = 0.0
        if specialist and specialist.signal("market_consensus_agent"):
            cs = specialist.signal("market_consensus_agent").signals
            odds_score = float(cs.get("consensus_strength", 50))
            home_imp = cs.get("home_implied_probability")
            away_imp = cs.get("away_implied_probability")
            if home_imp is not None and away_imp is not None:
                odds_edge = float(home_imp) - float(away_imp)
            agreement = cs.get("model_market_agreement")
            if agreement == "low":
                odds_score = max(odds_score - 12, 20)
            elif agreement == "high":
                odds_score = min(odds_score + 5, 95)
            if cs.get("disagreement_warning"):
                odds_score = max(odds_score - 8, 20)
            if specialist.signal("sharp_money_intelligence_agent"):
                smv2 = specialist.signal("sharp_money_intelligence_agent").signals
                sm_impact = smv2.get("prediction_impact") or {}
                odds_edge += float(sm_impact.get("home_adjustment", 0) - sm_impact.get("away_adjustment", 0)) / 300
                if smv2.get("consensus_strength"):
                    odds_score = (odds_score + float(smv2.get("consensus_strength", 50))) / 2
                if "high_market_disagreement" in (smv2.get("risk_flags") or []):
                    odds_score = max(odds_score - 5, 25)
                if "low_market_confidence" in (smv2.get("risk_flags") or []):
                    odds_score = min(odds_score, 55.0)
                    odds_edge *= 0.5
        elif specialist and specialist.signal("odds_control_agent"):
            cs = specialist.signal("odds_control_agent").signals
            odds_score = float(cs.get("odds_confidence_signal", 50))
            home_imp = cs.get("home_implied_probability")
            away_imp = cs.get("away_implied_probability")
            if home_imp is not None and away_imp is not None:
                odds_edge = float(home_imp) - float(away_imp)
            if cs.get("strong_disagreement_warning"):
                odds_score = max(odds_score - 10, 25)
        elif specialist and specialist.signal("odds_market_agent"):
            osig = specialist.signal("odds_market_agent").signals
            odds_score = float(osig.get("market_confidence_signal", 50))
            implied = osig.get("implied_probabilities") or {}
            odds_edge = float(implied.get("home", 0.33)) - float(implied.get("away", 0.33))

        mot_score = 65.0
        mot_edge = 0.0
        if specialist and specialist.signal("motivation_psychology_agent"):
            ms = specialist.signal("motivation_psychology_agent").signals
            mh = float(ms.get("motivation_score_home", 65))
            ma = float(ms.get("motivation_score_away", 65))
            mot_score = (mh + ma) / 2
            mot_edge = (mh - ma) / 200

        if specialist and specialist.signal("tournament_intelligence_agent"):
            tv2 = specialist.signal("tournament_intelligence_agent").signals
            tv2_impact = tv2.get("prediction_impact") or {}
            mot_edge += float(tv2_impact.get("home_adjustment", 0) - tv2_impact.get("away_adjustment", 0)) / 400
            if tv2.get("pressure_score"):
                mot_score = (mot_score + float(tv2.get("pressure_score", 50))) / 2
            if "low_tournament_data_confidence" in (tv2.get("risk_flags") or []):
                mot_score = min(mot_score, 58.0)
                mot_edge *= 0.5

        weather_score = 50.0
        weather_edge = 0.0
        if specialist and specialist.signal("weather_agent"):
            ws = specialist.signal("weather_agent").signals
            impact = ws.get("weather_impact_score")
            weather_score = float(impact) if impact is not None else 50.0
        if specialist and specialist.signal("referee_agent") and specialist.signal("referee_agent").status != "unavailable":
            rs = specialist.signal("referee_agent").signals
            weather_score = (weather_score + float(rs.get("referee_impact_score", 50))) / 2

        raw = {
            "data_quality": (dq, 0.0),
            "team_form": (form_score, form_edge),
            "injuries_suspensions": (inj_score, inj_edge),
            "lineup_strength": (lineup_score, lineup_edge),
            "tactics_matchup": (tactics_score, tactics_over),
            "player_quality": (player_score, player_edge),
            "odds_market_signal": (odds_score, odds_edge),
            "motivation_psychology": (mot_score, mot_edge),
            "weather_referee_context": (weather_score, weather_edge),
        }

        factors: dict[str, WeightedFactor] = {}
        for name, (score, edge) in raw.items():
            weight = self._factor_weights[name]
            score_n = self._clamp(score, 0, 100)
            contribution = weight * score_n * edge
            factors[name] = WeightedFactor(
                name=name,
                weight=weight,
                score=round(score_n, 1),
                home_edge=round(edge, 4),
                contribution=round(contribution, 4),
            )
        return factors

    def _build_audit_skeleton(
        self,
        fixture_id: int,
        factors: dict[str, WeightedFactor],
    ) -> PredictionAuditReport:
        return PredictionAuditReport(
            fixture_id=fixture_id,
            factor_weights={k: v * 100 for k, v in self._factor_weights.items()},
        )

    def _populate_audit_factors(
        self,
        audit: PredictionAuditReport,
        factors: dict[str, WeightedFactor],
        home_edge_total: float,
        baseline_selection: str,
    ) -> None:
        supports_home = home_edge_total > 0
        for factor in factors.values():
            direction: str = "neutral"
            if abs(factor.contribution) < 0.001:
                direction = "neutral"
            elif (factor.contribution > 0) == supports_home:
                direction = "support"
            else:
                direction = "oppose"

            entry = AuditFactorContribution(
                factor_name=factor.name,
                weight_pct=round(factor.weight * 100, 1),
                score=factor.score,
                contribution=round(factor.contribution * 100, 2),
                direction=direction,  # type: ignore[arg-type]
                note=f"home_edge={factor.home_edge:+.3f}",
            )
            if direction == "support":
                audit.supported_factors.append(entry)
            elif direction == "oppose":
                audit.opposed_factors.append(entry)
            else:
                audit.neutral_factors.append(entry)

    def _limitations(
        self,
        report: MatchIntelligenceReport,
        specialist: MatchSpecialistReport | None,
    ) -> list[DataLimitation]:
        items = [DataLimitation(field=f, impact="reduced factor reliability") for f in report.missing_data]
        if specialist:
            for name, sig in specialist.signals.items():
                for missing in sig.missing_data:
                    items.append(DataLimitation(field=f"{name}:{missing}", impact="specialist partial coverage"))
        return items

    def _market_disagreement(
        self,
        baseline: MatchPrediction,
        factors: dict[str, WeightedFactor],
        home_edge_total: float,
        specialist: MatchSpecialistReport | None = None,
    ) -> str | None:
        if specialist and specialist.signal("market_consensus_agent"):
            cs = specialist.signal("market_consensus_agent").signals
            if cs.get("model_market_agreement") == "low":
                return (
                    "Market disagrees with model — analytical disagreement only, not betting advice."
                )
            if cs.get("disagreement_warning"):
                return "Bookmaker sources disagree — market read uncertain (analysis only)."
        odds = factors.get("odds_market_signal")
        if not odds or abs(odds.home_edge) < 0.05:
            return None
        model_favours_home = home_edge_total > 0.02
        market_favours_home = odds.home_edge > 0.05
        market_favours_away = odds.home_edge < -0.05
        if model_favours_home and market_favours_away:
            return "Model favours home side but market implied probability favours away — analytical disagreement."
        if not model_favours_home and home_edge_total < -0.02 and market_favours_home:
            return "Model favours away side but market implied probability favours home — analytical disagreement."
        if baseline.one_x_two.selection == "draw" and abs(odds.home_edge) > 0.12:
            return "Model lean differs strongly from market favourite — elevated uncertainty."
        return None

    @staticmethod
    def _draw_implied_probability(
        specialist: MatchSpecialistReport | None,
    ) -> float | None:
        if not specialist:
            return None
        sig = specialist.signal("market_consensus_agent")
        if not sig or not sig.signals:
            return None
        raw = sig.signals.get("draw_implied_probability")
        if raw is None:
            return None
        try:
            val = float(raw)
            return val / 100.0 if val > 1.0 else val
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _resolve_1x2(
        home_edge_total: float,
        baseline: str,
        *,
        specialist: MatchSpecialistReport | None = None,
        factors: dict[str, WeightedFactor] | None = None,
    ) -> str:
        try:
            from worldcup_predictor.accuracy.live_calibration import should_prefer_draw

            draw_prob = WeightedDecisionEngine._draw_implied_probability(specialist)
            if should_prefer_draw(home_edge_total, draw_implied_probability=draw_prob):
                if baseline == "draw" or abs(home_edge_total) < 0.02:
                    return "draw"
        except Exception:
            pass
        if home_edge_total > 0.03:
            return "home_win"
        if home_edge_total < -0.03:
            return "away_win"
        if abs(home_edge_total) <= 0.01:
            return baseline
        return "draw" if abs(home_edge_total) < 0.02 else baseline

    @staticmethod
    def _resolve_over_under(
        baseline: MatchPrediction,
        factors: dict[str, WeightedFactor],
        severe_weather: bool,
    ) -> str:
        selection = baseline.over_under.selection
        tactics = factors.get("tactics_matchup")
        if severe_weather and selection == "over_2_5":
            return "under_2_5"
        if tactics and tactics.home_edge < -0.05:
            try:
                expected_total = float(baseline.metadata.get("expected_total_goals", 0))
            except (TypeError, ValueError):
                expected_total = 0.0
            try:
                from worldcup_predictor.accuracy.live_calibration import ou_expected_goals_threshold

                threshold = ou_expected_goals_threshold(2.58)
            except Exception:
                threshold = 2.58
            if expected_total >= threshold and selection == "over_2_5":
                return selection
            return "under_2_5"
        return selection

    @staticmethod
    def _official_lineups_available(specialist: MatchSpecialistReport | None) -> bool:
        if not specialist:
            return False
        sig = specialist.signal("lineup_agent")
        return bool(sig and sig.signals.get("official_lineups_available"))

    @staticmethod
    def _absence_score(specialist: MatchSpecialistReport | None) -> float:
        if not specialist:
            return 0.0
        sig = specialist.signal("injury_suspension_agent")
        if not sig:
            return 0.0
        return float(sig.signals.get("key_absence_score", 0))

    @staticmethod
    def _rain_high(specialist: MatchSpecialistReport | None) -> bool:
        if not specialist:
            return False
        sig = specialist.signal("weather_agent")
        rain = sig.signals.get("rain_probability") if sig else None
        return rain is not None and float(rain) > 0.4

    @staticmethod
    def _confidence_level(score: float, is_placeholder: bool) -> ConfidenceLevel:
        from worldcup_predictor.config.model_weights import get_thresholds

        thresholds = get_thresholds(use_calibrated=True)
        if is_placeholder:
            return ConfidenceLevel.UNAVAILABLE
        high_min = thresholds["high_confidence_level_minimum"]
        medium_min = thresholds["medium_confidence_level_minimum"]
        if score >= high_min:
            return ConfidenceLevel.HIGH
        if score >= medium_min:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

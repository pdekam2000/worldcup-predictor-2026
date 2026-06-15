"""Prediction Explainability Engine — Phase 41 (read-only, no scoring changes)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.explainability.models import (
    AgentContribution,
    AgreementAnalysis,
    ConfidenceExplanation,
    ConflictAnalysis,
    DecisionTimelineStep,
    FinalReportV2,
    OutcomeExplanation,
    RiskAnalysis,
)
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport

_AGENT_ORDER: tuple[tuple[str, str], ...] = (
    ("team_form_agent", "Form"),
    ("elo_team_strength_intelligence_agent", "ELO & Strength"),
    ("xg_chance_quality_intelligence_agent", "xG & Chance Quality"),
    ("lineup_intelligence_agent", "Lineup Intelligence"),
    ("lineup_agent", "Lineup"),
    ("injury_suspension_intelligence_agent", "Injury Intelligence"),
    ("injury_suspension_agent", "Injuries"),
    ("sharp_money_intelligence_agent", "Sharp Money"),
    ("market_consensus_agent", "Market Consensus"),
    ("odds_movement_agent", "Odds Movement"),
    ("tactics_agent", "Tactics"),
    ("player_quality_agent", "Player Quality"),
    ("motivation_psychology_agent", "Motivation"),
    ("weather_agent", "Weather"),
    ("referee_agent", "Referee"),
)

_FACTOR_LABELS = {
    "team_form": "Team Form",
    "lineup_strength": "Lineup Strength",
    "injuries_suspensions": "Injuries & Suspensions",
    "odds_market_signal": "Market Odds",
    "tactics_matchup": "Tactics Matchup",
    "player_quality": "Player Quality",
    "motivation_psychology": "Motivation",
    "weather_referee_context": "Weather & Referee",
    "data_quality": "Data Quality",
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _agreement_band(score: float) -> str:
    if score < 20:
        return "Very Low"
    if score < 40:
        return "Low"
    if score < 60:
        return "Moderate"
    if score < 80:
        return "Strong"
    return "Very Strong"


def _risk_band(level: str | None, score: float) -> str:
    key = (level or "").lower()
    if key in {"very_high", "critical"} or score >= 80:
        return "Very High"
    if key == "high" or score >= 60:
        return "High"
    if key in {"medium", "moderate"} or score >= 35:
        return "Moderate"
    if key == "low" or score >= 15:
        return "Low"
    return "Very Low"


def _selection_lean(selection: str) -> str:
    if selection == "home_win":
        return "home"
    if selection == "away_win":
        return "away"
    if selection == "draw":
        return "draw"
    if selection == "over_2_5":
        return "over"
    if selection == "under_2_5":
        return "under"
    return "neutral"


def _impact_edge(signals: dict[str, Any]) -> float | None:
    impact = signals.get("prediction_impact") or {}
    if not impact:
        return None
    try:
        return float(impact.get("home_adjustment", 0) or 0) - float(impact.get("away_adjustment", 0) or 0)
    except (TypeError, ValueError):
        return None


def _agent_home_edge(agent_key: str, signals: dict[str, Any]) -> float | None:
    edge = _impact_edge(signals)
    if edge is not None and abs(edge) > 0.01:
        return edge

    if agent_key == "team_form_agent":
        h = float(signals.get("form_score_home", 50) or 50)
        a = float(signals.get("form_score_away", 50) or 50)
        return (h - a) / 50.0

    if agent_key == "elo_team_strength_intelligence_agent":
        edge = _impact_edge(signals)
        if edge is not None and abs(edge) > 0.01:
            return edge
        diff = signals.get("elo_difference")
        if diff is not None:
            return float(diff) / 200.0
        home = signals.get("home") or {}
        away = signals.get("away") or {}
        hs = float(home.get("overall_team_strength", 50) or 50)
        aw = float(away.get("overall_team_strength", 50) or 50)
        return (hs - aw) / 50.0

    if agent_key == "xg_chance_quality_intelligence_agent":
        edge = _impact_edge(signals)
        if edge is not None and abs(edge) > 0.01:
            return edge
        home_edge = signals.get("home_chance_edge")
        if home_edge is not None:
            return float(home_edge) / 50.0
        home = signals.get("home") or {}
        away = signals.get("away") or {}
        ha = float(home.get("attack_chance_quality", 50) or 50)
        aa = float(away.get("attack_chance_quality", 50) or 50)
        return (ha - aa) / 50.0

    if agent_key == "motivation_psychology_agent":
        h = float(signals.get("motivation_score_home", 50) or 50)
        a = float(signals.get("motivation_score_away", 50) or 50)
        return (h - a) / 50.0

    if agent_key == "market_consensus_agent":
        h = signals.get("home_implied_probability")
        a = signals.get("away_implied_probability")
        if h is not None and a is not None:
            return float(h) - float(a)

    if agent_key == "lineup_intelligence_agent":
        home = signals.get("home") or {}
        away = signals.get("away") or {}
        hs = float(home.get("lineup_strength", 50) or 50)
        aw = float(away.get("lineup_strength", 50) or 50)
        return (hs - aw) / 50.0

    if agent_key == "injury_suspension_intelligence_agent":
        home = signals.get("home") or {}
        away = signals.get("away") or {}
        hi = float(home.get("injury_impact_score", 0) or 0)
        ai = float(away.get("injury_impact_score", 0) or 0)
        return (ai - hi) / 50.0

    if agent_key == "sharp_money_intelligence_agent":
        edge = _impact_edge(signals)
        return edge if edge is not None else None

    if agent_key == "player_quality_agent":
        h = float(signals.get("star_player_rating_home", 50) or 50)
        a = float(signals.get("star_player_rating_away", 50) or 50)
        return (h - a) / 50.0

    if agent_key == "tactics_agent":
        tendency = str(signals.get("over_under_tendency") or "")
        if "home" in tendency.lower():
            return 0.3
        if "away" in tendency.lower():
            return -0.3
        return 0.0

    if agent_key == "odds_movement_agent":
        home_m = signals.get("home_movement")
        away_m = signals.get("away_movement")
        if home_m is not None and away_m is not None:
            return (float(away_m) - float(home_m)) / 20.0

    return None


def _ou_edge(agent_key: str, signals: dict[str, Any]) -> float | None:
    impact = signals.get("prediction_impact") or {}
    over = impact.get("over25_adjustment")
    under = impact.get("under25_adjustment")
    if over is not None or under is not None:
        return float(over or 0) - float(under or 0)
    if agent_key == "tactics_agent":
        t = str(signals.get("over_under_tendency") or "")
        if "over" in t.lower():
            return 0.5
        if "under" in t.lower():
            return -0.5
    if agent_key == "weather_agent" and float(signals.get("rain_probability", 0) or 0) > 0.4:
        return -0.4
    return None


def _aligns_with_selection(edge: float, lean: str) -> bool:
    if lean == "home":
        return edge > 0.05
    if lean == "away":
        return edge < -0.05
    if lean == "draw":
        return abs(edge) < 0.08
    return False


def _opposes_selection(edge: float, lean: str) -> bool:
    if lean == "home":
        return edge < -0.05
    if lean == "away":
        return edge > 0.05
    if lean == "draw":
        return abs(edge) >= 0.15
    return False


def _verdict_for_agent(label: str, edge: float | None, ou_edge: float | None, x2_lean: str, ou_lean: str) -> tuple[str, str]:
    if edge is None and ou_edge is None:
        return "Neutral", "neutral"
    primary = edge if edge is not None else 0.0
    if x2_lean == "home" and primary > 0.08:
        return f"{label} → Home positive", "home"
    if x2_lean == "away" and primary < -0.08:
        return f"{label} → Away positive", "away"
    if x2_lean == "draw" and abs(primary) < 0.1:
        return f"{label} → Draw balanced", "draw"
    if primary > 0.08:
        return f"{label} → Home lean", "home"
    if primary < -0.08:
        return f"{label} → Away lean", "away"
    if ou_edge is not None and ou_lean == "over" and ou_edge > 0.05:
        return f"{label} → Over lean", "over"
    if ou_edge is not None and ou_lean == "under" and ou_edge < -0.05:
        return f"{label} → Under lean", "under"
    return f"{label} → Neutral", "neutral"


def _collect_agent_rows(
    specialist: MatchSpecialistReport | None,
    x2_lean: str,
) -> list[tuple[str, str, float, str]]:
    rows: list[tuple[str, str, float, str]] = []
    if not specialist:
        return rows

    seen_labels: set[str] = set()
    for agent_key, label in _AGENT_ORDER:
        if label in seen_labels:
            continue
        sig = specialist.signal(agent_key)
        if not sig or not sig.signals:
            continue
        edge = _agent_home_edge(agent_key, sig.signals)
        ou_e = _ou_edge(agent_key, sig.signals)
        if edge is None and ou_e is None:
            continue
        raw = abs(edge or 0) * 10 + abs(ou_e or 0) * 5
        if raw < 0.5:
            raw = 1.0
        direction = "neutral"
        if edge is not None:
            if _aligns_with_selection(edge, x2_lean):
                direction = "positive"
            elif _opposes_selection(edge, x2_lean):
                direction = "negative"
        signed = raw if direction != "negative" else -raw
        if direction == "negative":
            signed = -raw
        elif direction == "positive":
            signed = raw
        else:
            signed = raw * 0.3
        rows.append((agent_key, label, signed, direction))
        seen_labels.add(label)

    return rows


def _normalize_contributions(rows: list[tuple[str, str, float, str]]) -> list[AgentContribution]:
    if not rows:
        return []
    total = sum(abs(r[2]) for r in rows) or 1.0
    out: list[AgentContribution] = []
    for key, label, signed, direction in rows:
        pct = round(abs(signed) / total * 100, 1)
        verdict = "Supports prediction" if signed > 0 else ("Opposes prediction" if signed < 0 else "Neutral influence")
        out.append(
            AgentContribution(
                agent_key=key,
                label=label,
                raw_score=round(signed, 1),
                influence_pct=pct,
                direction=direction if direction in {"positive", "negative", "neutral"} else "neutral",  # type: ignore[arg-type]
                verdict=verdict,
            )
        )
    out.sort(key=lambda c: abs(c.raw_score), reverse=True)
    return out


def _agreement_from_contributions(contributions: list[AgentContribution]) -> AgreementAnalysis:
    supporting = sum(1 for c in contributions if c.direction == "positive")
    opposing = sum(1 for c in contributions if c.direction == "negative")
    neutral = sum(1 for c in contributions if c.direction == "neutral")
    denom = supporting + opposing + max(neutral * 0.5, 0.5)
    score = round(_clamp((supporting / denom) * 100, 0, 100), 1)
    return AgreementAnalysis(
        agreement_score=score,
        agreement_band=_agreement_band(score),  # type: ignore[arg-type]
        supporting_agents=supporting,
        opposing_agents=opposing,
        neutral_agents=neutral,
    )


def _detect_conflicts(
    prediction: MatchPrediction,
    specialist: MatchSpecialistReport | None,
    report: MatchIntelligenceReport | None,
) -> ConflictAnalysis:
    conflicts: list[str] = []
    audit = prediction.audit_report
    if audit:
        for c in audit.conflicts:
            conflicts.append(c.description)
        for w in audit.market_disagreement_warnings:
            if w not in conflicts:
                conflicts.append(w)

    if specialist and specialist.master:
        for c in specialist.master.signals.get("conflicts_between_agents") or []:
            if c not in conflicts:
                conflicts.append(str(c))

    if specialist:
        lineup_v2 = specialist.signal("lineup_intelligence_agent")
        market = specialist.signal("market_consensus_agent") or specialist.signal("sharp_money_intelligence_agent")
        form = specialist.signal("team_form_agent")
        injury_v2 = specialist.signal("injury_suspension_intelligence_agent")

        if lineup_v2 and market and lineup_v2.signals and market.signals:
            le = _agent_home_edge("lineup_intelligence_agent", lineup_v2.signals)
            me = _agent_home_edge("market_consensus_agent", market.signals) or _agent_home_edge(
                "sharp_money_intelligence_agent", market.signals
            )
            if le is not None and me is not None and le * me < 0 and abs(le) > 0.1 and abs(me) > 0.05:
                conflicts.append("Lineup intelligence vs market consensus point in opposite directions.")

        if injury_v2 and market and injury_v2.signals and market.signals:
            ie = _agent_home_edge("injury_suspension_intelligence_agent", injury_v2.signals)
            me = _agent_home_edge("market_consensus_agent", market.signals)
            if ie is not None and me is not None and ie * me < 0 and abs(ie) > 0.08:
                conflicts.append("Injury impact assessment conflicts with market pricing direction.")

        if form and market and form.signals and market.signals:
            fe = _agent_home_edge("team_form_agent", form.signals)
            me = _agent_home_edge("market_consensus_agent", market.signals)
            if fe is not None and me is not None and fe * me < 0 and abs(fe) > 0.15 and abs(me) > 0.05:
                conflicts.append("Team form vs market odds conflict detected.")

    if report and report.missing_data:
        pass

    score = round(_clamp(len(conflicts) * 18, 0, 100), 1)
    return ConflictAnalysis(conflict_score=score, conflicts=conflicts[:12])


def _confidence_explanation(prediction: MatchPrediction, specialist: MatchSpecialistReport | None) -> ConfidenceExplanation:
    boosters: list[str] = []
    reducers: list[str] = []

    if specialist:
        lv2 = specialist.signal("lineup_intelligence_agent")
        if lv2 and lv2.signals:
            home = (lv2.signals.get("home") or {})
            away = (lv2.signals.get("away") or {})
            if home.get("official_lineup") or away.get("official_lineup"):
                boosters.append("Official lineup available")
            if "official_lineup_missing" in (home.get("risk_flags") or []) + (away.get("risk_flags") or []):
                reducers.append("Missing official lineup")

        iv2 = specialist.signal("injury_suspension_intelligence_agent")
        if iv2 and iv2.signals:
            ih = float((iv2.signals.get("home") or {}).get("injury_impact_score", 0) or 0)
            ia = float((iv2.signals.get("away") or {}).get("injury_impact_score", 0) or 0)
            if max(ih, ia) < 25:
                boosters.append("Low injury impact")
            elif max(ih, ia) >= 50:
                reducers.append("Elevated injury impact")

        mc = specialist.signal("market_consensus_agent")
        if mc and mc.signals:
            if mc.signals.get("model_market_agreement") == "high":
                boosters.append("Strong bookmaker agreement")
            if mc.signals.get("disagreement_warning") or mc.signals.get("model_market_agreement") == "low":
                reducers.append("Market disagreement")

        form = specialist.signal("team_form_agent")
        if form and form.signals:
            h = float(form.signals.get("form_score_home", 50) or 50)
            a = float(form.signals.get("form_score_away", 50) or 50)
            if abs(h - a) >= 12:
                boosters.append("Strong team form differential")

        sm = specialist.signal("sharp_money_intelligence_agent")
        if sm and sm.signals:
            if sm.signals.get("steam_move_detected"):
                reducers.append("Steam move detected in market")
            if "low_market_confidence" in (sm.signals.get("risk_flags") or []):
                reducers.append("Low market data confidence")

    bd = prediction.confidence_breakdown
    if bd and bd.data_quality_score >= 70:
        boosters.append("Good data quality coverage")
    elif bd and bd.data_quality_score < 45:
        reducers.append("Limited data quality")

    if prediction.no_bet_flag:
        reducers.append("Watch-only threshold — confidence capped")

    audit = prediction.audit_report
    if audit and audit.trace:
        for cap in audit.trace.confidence_caps_applied[:3]:
            reducers.append(f"Confidence cap: {cap.replace('_', ' ')}")
        for red in audit.trace.confidence_reductions[:2]:
            reducers.append(red)

    level = prediction.confidence_level.value if hasattr(prediction.confidence_level, "value") else str(prediction.confidence_level)
    return ConfidenceExplanation(
        score=prediction.confidence_score,
        level=level,
        boosters=boosters[:8],
        reducers=reducers[:8],
    )


def _risk_analysis(prediction: MatchPrediction, specialist: MatchSpecialistReport | None) -> RiskAnalysis:
    risks: list[str] = []
    risk_score = 20.0

    if prediction.no_bet_flag:
        risks.append("Watch-only / no-bet flag active")
        risk_score += 25

    for rw in prediction.risk_warnings or []:
        msgs = rw.messages.get("en") if rw.messages else None
        if msgs:
            risks.append(str(msgs)[:120])

    if specialist:
        for agent_key, label in (
            ("lineup_intelligence_agent", "Lineup"),
            ("injury_suspension_intelligence_agent", "Injury"),
            ("sharp_money_intelligence_agent", "Market"),
        ):
            sig = specialist.signal(agent_key)
            if not sig or not sig.signals:
                continue
            flags: list[str] = []
            if agent_key == "lineup_intelligence_agent":
                flags = (sig.signals.get("home") or {}).get("risk_flags") or []
                flags += (sig.signals.get("away") or {}).get("risk_flags") or []
            elif agent_key == "injury_suspension_intelligence_agent":
                flags = (sig.signals.get("home") or {}).get("risk_flags") or []
                flags += (sig.signals.get("away") or {}).get("risk_flags") or []
            else:
                flags = sig.signals.get("risk_flags") or []

            flag_labels = {
                "backup_goalkeeper": "Backup goalkeeper uncertainty",
                "key_player_missing": "Key player missing from lineup",
                "steam_move_detected": "Steam move detected",
                "low_data_confidence": "Injury data unavailable",
                "low_market_confidence": "Low market data confidence",
                "severe_injury_crisis": "Severe injury crisis",
                "reverse_line_movement": "Reverse line movement signal",
                "high_market_disagreement": "High market disagreement",
            }
            for f in flags:
                text = flag_labels.get(f, f.replace("_", " ").title())
                if text not in risks:
                    risks.append(text)
                risk_score += 8

    rl = prediction.risk_level.value if hasattr(prediction.risk_level, "value") else str(prediction.risk_level)
    return RiskAnalysis(
        risk_level=_risk_band(rl, risk_score),  # type: ignore[arg-type]
        top_risks=risks[:8] or ["No elevated risks flagged"],
    )


def _outcome_explanations(
    prediction: MatchPrediction,
    contributions: list[AgentContribution],
    specialist: MatchSpecialistReport | None,
    home_name: str,
    away_name: str,
) -> list[OutcomeExplanation]:
    explanations: list[OutcomeExplanation] = []
    x2 = prediction.one_x_two.selection
    ou = prediction.over_under.selection

    pos = [c.label for c in contributions if c.direction == "positive"][:4]
    neg = [c.label for c in contributions if c.direction == "negative"][:3]

    if x2 == "home_win":
        parts = [f"{home_name} selected due to combined home-leaning signals."]
        if pos:
            parts.append(f"Supported by: {', '.join(pos)}.")
        if neg:
            parts.append(f"Despite caution from: {', '.join(neg)}.")
        explanations.append(
            OutcomeExplanation("home_win", True, " ".join(parts), "strong" if len(pos) >= 2 else "moderate")
        )
    elif x2 == "away_win":
        parts = [f"{away_name} selected based on away-side strength signals."]
        if pos:
            parts.append(f"Supported by: {', '.join(pos)}.")
        explanations.append(
            OutcomeExplanation("away_win", True, " ".join(parts), "strong" if len(pos) >= 2 else "moderate")
        )
    elif x2 == "draw":
        explanations.append(
            OutcomeExplanation(
                "draw",
                True,
                "Draw lean — balanced strength with limited separation between teams.",
                "moderate",
            )
        )

    if ou == "over_2_5":
        ou_support = []
        if specialist:
            tac = specialist.signal("tactics_agent")
            if tac and "over" in str(tac.signals.get("over_under_tendency", "")).lower():
                ou_support.append("Tactics")
            sm = specialist.signal("sharp_money_intelligence_agent")
            if sm and float((sm.signals.get("prediction_impact") or {}).get("over25_adjustment", 0) or 0) > 0:
                ou_support.append("Sharp Money")
        text = "Over 2.5 lean from goal-expectation and attacking indicators."
        if ou_support:
            text += f" Supported by: {', '.join(ou_support)}."
        explanations.append(OutcomeExplanation("over_2_5", True, text, "moderate"))
    elif ou == "under_2_5":
        text = "Under 2.5 lean from conservative goal expectation and defensive context."
        explanations.append(OutcomeExplanation("under_2_5", True, text, "moderate"))

    return explanations


def _build_timeline(
    specialist: MatchSpecialistReport | None,
    x2_lean: str,
    ou_lean: str,
    final_x2_label: str,
) -> list[DecisionTimelineStep]:
    steps: list[DecisionTimelineStep] = []
    if not specialist:
        return steps

    for agent_key, label in _AGENT_ORDER:
        sig = specialist.signal(agent_key)
        if not sig or not sig.signals:
            continue
        edge = _agent_home_edge(agent_key, sig.signals)
        ou_e = _ou_edge(agent_key, sig.signals)
        verdict, lean = _verdict_for_agent(label, edge, ou_e, x2_lean, ou_lean)
        steps.append(DecisionTimelineStep(agent_label=label, verdict=verdict.split("→")[-1].strip(), lean=lean))  # type: ignore[arg-type]
        if len(steps) >= 8:
            break

    steps.append(
        DecisionTimelineStep(
            agent_label="Master Decision",
            verdict=final_x2_label,
            lean=x2_lean,  # type: ignore[arg-type]
        )
    )
    return steps


def _executive_summary(
    prediction: MatchPrediction,
    report: MatchIntelligenceReport | None,
    contributions: list[AgentContribution],
    agreement: AgreementAnalysis,
    conflicts: ConflictAnalysis,
    confidence: ConfidenceExplanation,
    risk: RiskAnalysis,
) -> str:
    home = report.home_team.team_name if report and report.home_team else "Home"
    away = report.away_team.team_name if report and report.away_team else "Away"
    x2 = prediction.one_x_two.selection.replace("_", " ").title()
    ou = prediction.over_under.selection.replace("_", " ").title()

    pos = [c.label for c in contributions if c.direction == "positive"][:3]
    sentences: list[str] = []

    if prediction.one_x_two.selection == "home_win":
        sentences.append(f"{home} receives analytical support from {', '.join(pos) if pos else 'multiple model factors'}.")
    elif prediction.one_x_two.selection == "away_win":
        sentences.append(f"{away} receives analytical support from {', '.join(pos) if pos else 'multiple model factors'}.")
    else:
        sentences.append(f"The model sees a balanced matchup between {home} and {away} with a draw lean.")

    if confidence.boosters:
        sentences.append(f"Confidence is supported by: {confidence.boosters[0].lower()}" + (
            f" and {confidence.boosters[1].lower()}" if len(confidence.boosters) > 1 else ""
        ) + ".")
    if confidence.reducers:
        sentences.append(f"Confidence is tempered by: {confidence.reducers[0].lower()}.")

    sentences.append(
        f"Agreement across agents is {agreement.agreement_band.lower()} ({agreement.agreement_score:.0f}/100); "
        f"goal market lean is {ou}."
    )
    if conflicts.conflicts:
        sentences.append(f"{len(conflicts.conflicts)} analytical conflict(s) noted — interpret with caution.")
    else:
        sentences.append(f"Overall risk is {risk.risk_level.lower()} with confidence at {prediction.confidence_score:.0f}/100.")

    fg_raw = (prediction.metadata or {}).get("first_goal_intelligence_v2")
    if fg_raw:
        try:
            import json

            fg = json.loads(fg_raw) if isinstance(fg_raw, str) else fg_raw
            team = fg.get("first_goal_team_display") or fg.get("first_goal_team", "—")
            band = fg.get("first_goal_minute_band", "—")
            fg_conf = fg.get("confidence", "—")
            sentences.append(
                f"First goal intelligence: {team} in minute band {band} (confidence {fg_conf}/100)."
            )
        except Exception:
            pass

    return " ".join(sentences[:6])


def _audit_factor_contributions(prediction: MatchPrediction) -> list[tuple[str, float, str]]:
    rows: list[tuple[str, float, str]] = []
    audit = prediction.audit_report
    if not audit:
        return rows
    for bucket in (audit.supported_factors, audit.opposed_factors, audit.neutral_factors):
        for f in bucket:
            label = _FACTOR_LABELS.get(f.factor_name, f.factor_name.replace("_", " ").title())
            direction = f.direction
            signed = f.contribution if direction != "oppose" else -abs(f.contribution)
            if direction == "neutral":
                signed = f.contribution * 0.3
            rows.append((label, signed, direction))
    return rows


def _safe_fallback(fixture_id: int = 0) -> FinalReportV2:
    return FinalReportV2(
        prediction={"fixture_id": fixture_id, "status": "unavailable"},
        confidence=ConfidenceExplanation(score=0, level="unavailable"),
        agreement=AgreementAnalysis(0, "Very Low", 0, 0, 0),  # type: ignore[arg-type]
        conflicts=ConflictAnalysis(0, []),
        risk_analysis=RiskAnalysis("Very High", ["Incomplete prediction data"]),
        agent_contributions=[],
        decision_timeline=[],
        outcome_explanations=[],
        top_positive_factors=[],
        top_negative_factors=[],
        executive_summary="Explainability report unavailable — safe fallback applied. Analysis only — not betting advice.",
    )


def build_prediction_explainability(
    prediction: MatchPrediction | None,
    report: MatchIntelligenceReport | None = None,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> FinalReportV2:
    """Build Final Report V2 from existing prediction outputs — read-only."""
    try:
        if prediction is None:
            return _safe_fallback()

        specialist = specialist_report
        if specialist is None and report is not None:
            specialist = report.specialist_report

        x2_lean = _selection_lean(prediction.one_x_two.selection)
        ou_lean = _selection_lean(prediction.over_under.selection)

        rows = _collect_agent_rows(specialist, x2_lean)
        if not rows and prediction.audit_report:
            for label, signed, direction in _audit_factor_contributions(prediction):
                dir_map = {"support": "positive", "oppose": "negative", "neutral": "neutral"}
                rows.append((label, label, signed, dir_map.get(direction, "neutral")))

        contributions = _normalize_contributions(rows)
        agreement = _agreement_from_contributions(contributions) if contributions else AgreementAnalysis(
            50.0, "Moderate", 0, 0, 0  # type: ignore[arg-type]
        )
        conflicts = _detect_conflicts(prediction, specialist, report)
        confidence = _confidence_explanation(prediction, specialist)
        risk = _risk_analysis(prediction, specialist)

        home_name = report.home_team.team_name if report and report.home_team else "Home"
        away_name = report.away_team.team_name if report and report.away_team else "Away"

        x2_label = {
            "home_win": f"{home_name} Win Lean",
            "away_win": f"{away_name} Win Lean",
            "draw": "Draw Lean",
        }.get(prediction.one_x_two.selection, "Selection Lean")

        timeline = _build_timeline(specialist, x2_lean, ou_lean, x2_label)
        outcomes = _outcome_explanations(prediction, contributions, specialist, home_name, away_name)

        top_pos = [c.label for c in contributions if c.raw_score > 0][:5]
        top_neg = [c.label for c in contributions if c.raw_score < 0][:5]

        pred_block = {
            "fixture_id": prediction.fixture_id,
            "match_name": prediction.match_name,
            "one_x_two": prediction.one_x_two.selection,
            "one_x_two_probability": prediction.one_x_two.probability,
            "over_under": prediction.over_under.selection,
            "over_under_probability": prediction.over_under.probability,
            "confidence_score": prediction.confidence_score,
            "risk_level": prediction.risk_level.value if hasattr(prediction.risk_level, "value") else str(prediction.risk_level),
            "no_bet_flag": prediction.no_bet_flag,
        }

        summary = _executive_summary(
            prediction, report, contributions, agreement, conflicts, confidence, risk
        )

        fusion_report = None
        try:
            from worldcup_predictor.fusion.final_decision_fusion_engine_v2 import (
                build_final_decision_fusion,
                load_fusion_from_prediction,
            )

            loaded = load_fusion_from_prediction(prediction)
            fusion_report = (
                loaded.to_dict()
                if loaded
                else build_final_decision_fusion(
                    prediction,
                    report=report,
                    specialist_report=specialist,
                ).to_dict()
            )
        except Exception:
            fusion_report = None

        api_sports_context = None
        try:
            from worldcup_predictor.integrations.api_sports_deep_data import build_api_sports_explainability_context

            api_sports_context = build_api_sports_explainability_context(report, prediction) or None
            if api_sports_context and api_sports_context.get("api_football_prediction", {}).get("available"):
                ref = api_sports_context["api_football_prediction"]
                summary += (
                    f" API-Football reference lean: {ref.get('api_one_x_two_lean')} "
                    f"(agreement {ref.get('agreement_pct')}%) — reference only."
                )
        except Exception:
            api_sports_context = None

        return FinalReportV2(
            prediction=pred_block,
            confidence=confidence,
            agreement=agreement,
            conflicts=conflicts,
            risk_analysis=risk,
            agent_contributions=contributions,
            decision_timeline=timeline,
            outcome_explanations=outcomes,
            top_positive_factors=top_pos,
            top_negative_factors=top_neg,
            executive_summary=summary + " Analysis only — not betting advice.",
            fusion_report=fusion_report,
            api_sports_context=api_sports_context,
        )
    except Exception:
        fid = prediction.fixture_id if prediction else 0
        return _safe_fallback(fid)

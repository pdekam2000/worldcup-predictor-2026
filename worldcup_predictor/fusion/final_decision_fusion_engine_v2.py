"""Final Decision Fusion Engine V2 — Phase 46 (additive, conservative caps)."""

from __future__ import annotations

import json
from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.fusion.models import (
    AgentSignalRow,
    FinalDecisionFusionReport,
    FusionConflict,
    QualityBand,
    SignalMatrix,
)
from worldcup_predictor.fusion.signal_diversity import (
    apply_correlation_dampening,
    classify_signals_for_explainability,
    compute_fusion_diversity_score,
)

_ADJUSTMENT_CAP = 10.0
_AGENT_SIGNAL_CAP = 100.0
_MAX_AGENT_SHARE = 0.18

_DOWNWEIGHT_FLAGS = frozenset(
    {
        "low_data_confidence",
        "low_market_confidence",
        "unreliable_history",
        "limited_statistics",
        "low_xg_data_confidence",
        "low_tournament_data_confidence",
        "official_lineup_missing",
        "low_fusion_confidence",
    }
)

_AGENT_ORDER: tuple[tuple[str, str, float], ...] = (
    ("lineup_intelligence_agent", "Lineup Intelligence", 1.0),
    ("injury_suspension_intelligence_agent", "Injury Intelligence", 1.0),
    ("sharp_money_intelligence_agent", "Sharp Money", 0.95),
    ("tournament_intelligence_agent", "Tournament", 0.75),
    ("elo_team_strength_intelligence_agent", "ELO & Strength", 0.9),
    ("xg_chance_quality_intelligence_agent", "xG & Chance Quality", 0.9),
    ("team_form_agent", "Form", 0.7),
    ("market_consensus_agent", "Market Consensus", 0.8),
    ("odds_movement_agent", "Odds Movement", 0.55),
    ("tactics_agent", "Tactics", 0.6),
    ("player_quality_agent", "Player Quality", 0.55),
    ("motivation_psychology_agent", "Motivation", 0.5),
    ("lineup_agent", "Lineup", 0.45),
    ("injury_suspension_agent", "Injuries", 0.45),
    ("weather_agent", "Weather", 0.35),
    ("referee_agent", "Referee", 0.3),
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _scale_adj(value: Any) -> float:
    try:
        return _clamp(float(value or 0) * 10.0, -_AGENT_SIGNAL_CAP, _AGENT_SIGNAL_CAP)
    except (TypeError, ValueError):
        return 0.0


def _lean_from_signals(home: float, away: float, draw: float, *, threshold: float = 8.0) -> str:
    if home - max(away, draw) >= threshold:
        return "home"
    if away - max(home, draw) >= threshold:
        return "away"
    if draw - max(home, away) >= threshold:
        return "draw"
    return "neutral"


def _ou_lean(over: float, under: float, *, threshold: float = 8.0) -> str:
    if over - under >= threshold:
        return "over"
    if under - over >= threshold:
        return "under"
    return "neutral"


def _quality_multiplier(agent_key: str, signals: dict[str, Any], report: MatchIntelligenceReport | None) -> float:
    mult = 1.0
    flags: list[str] = list(signals.get("risk_flags") or [])
    for side in ("home", "away"):
        side_flags = (signals.get(side) or {}).get("risk_flags") or []
        flags.extend(side_flags)

    for flag in flags:
        if flag in _DOWNWEIGHT_FLAGS:
            mult *= 0.55

    if agent_key in {"lineup_intelligence_agent", "lineup_agent"}:
        home = signals.get("home") or {}
        away = signals.get("away") or {}
        if not home.get("official_lineup") and not away.get("official_lineup"):
            if "official_lineup_missing" in (home.get("risk_flags") or []) + (away.get("risk_flags") or []):
                mult *= 0.5
    if agent_key in {"injury_suspension_intelligence_agent", "injury_suspension_agent"} and report:
        if "injuries" in (report.missing_data or []):
            mult *= 0.6
    if agent_key == "tournament_intelligence_agent":
        home = signals.get("home") or {}
        away = signals.get("away") or {}
        if home.get("qualification_status") == "unknown" and away.get("qualification_status") == "unknown":
            mult *= 0.75
    return round(_clamp(mult, 0.15, 1.0), 2)


def _signals_from_impact(signals: dict[str, Any]) -> tuple[float, float, float, float, float]:
    impact = signals.get("prediction_impact") or {}
    return (
        _scale_adj(impact.get("home_adjustment")),
        _scale_adj(impact.get("away_adjustment")),
        _scale_adj(impact.get("draw_adjustment")),
        _scale_adj(impact.get("over25_adjustment")),
        _scale_adj(impact.get("under25_adjustment")),
    )


def _signals_team_form(signals: dict[str, Any]) -> tuple[float, float, float, float, float]:
    h = float(signals.get("form_score_home", 50) or 50)
    a = float(signals.get("form_score_away", 50) or 50)
    home = _clamp((h - a) * 1.2, -80, 80)
    away = -home
    return home, away, 0.0, 0.0, 0.0


def _signals_market(signals: dict[str, Any]) -> tuple[float, float, float, float, float]:
    h = signals.get("home_implied_probability")
    a = signals.get("away_implied_probability")
    d = signals.get("draw_implied_probability")
    if h is None or a is None:
        implied = signals.get("implied_probabilities") or {}
        h = implied.get("home", 0.33)
        a = implied.get("away", 0.33)
        d = implied.get("draw", 0.34)
    try:
        hf, af = float(h), float(a)
        home = _clamp((hf - af) * 120, -80, 80)
        away = -home
        draw = _clamp((float(d or 0.33) - 0.33) * 80, -40, 40) if d is not None else 0.0
        return home, away, draw, 0.0, 0.0
    except (TypeError, ValueError):
        return 0.0, 0.0, 0.0, 0.0, 0.0


def _signals_tactics(signals: dict[str, Any]) -> tuple[float, float, float, float, float]:
    tendency = str(signals.get("over_under_tendency") or "")
    over = under = 0.0
    if "over" in tendency.lower():
        over = 35.0
    elif "under" in tendency.lower():
        under = 35.0
    pressure = signals.get("expected_goal_pressure")
    try:
        if float(pressure or 0) >= 2.8:
            over = max(over, 25.0)
        elif float(pressure or 0) <= 2.0:
            under = max(under, 20.0)
    except (TypeError, ValueError):
        pass
    return 0.0, 0.0, 0.0, over, under


def _signals_elo(signals: dict[str, Any]) -> tuple[float, float, float, float, float]:
    h, a, d, o, u = _signals_from_impact(signals)
    if abs(h) < 1 and abs(a) < 1:
        diff = signals.get("elo_difference")
        if diff is not None:
            edge = _clamp(float(diff) / 2.5, -80, 80)
            h, a = edge, -edge
    return h, a, d, o, u


def _signals_xg(signals: dict[str, Any]) -> tuple[float, float, float, float, float]:
    h, a, d, o, u = _signals_from_impact(signals)
    if abs(o) < 1 and abs(u) < 1:
        pressure = signals.get("goals_pressure_score")
        if pressure is not None:
            delta = _clamp((float(pressure) - 50) * 0.8, -40, 40)
            o, u = max(delta, 0), max(-delta, 0)
    if abs(h) < 1 and abs(a) < 1:
        edge = signals.get("home_chance_edge")
        if edge is not None:
            h, a = _clamp(float(edge), -80, 80), _clamp(-float(edge), -80, 80)
    return h, a, d, o, u


def _extract_agent_signals(
    agent_key: str,
    signals: dict[str, Any],
) -> tuple[float, float, float, float, float]:
    if signals.get("prediction_impact"):
        if agent_key == "elo_team_strength_intelligence_agent":
            return _signals_elo(signals)
        if agent_key == "xg_chance_quality_intelligence_agent":
            return _signals_xg(signals)
        return _signals_from_impact(signals)
    if agent_key == "team_form_agent":
        return _signals_team_form(signals)
    if agent_key in {"market_consensus_agent", "odds_market_agent", "sharp_money_intelligence_agent"}:
        return _signals_market(signals)
    if agent_key == "tactics_agent":
        return _signals_tactics(signals)
    if agent_key == "player_quality_agent":
        h = float(signals.get("star_player_rating_home", 50) or 50)
        a = float(signals.get("star_player_rating_away", 50) or 50)
        edge = _clamp((h - a) * 1.0, -60, 60)
        return edge, -edge, 0.0, 0.0, 0.0
    if agent_key == "motivation_psychology_agent":
        h = float(signals.get("motivation_score_home", 50) or 50)
        a = float(signals.get("motivation_score_away", 50) or 50)
        edge = _clamp((h - a) * 1.0, -60, 60)
        return edge, -edge, 0.0, 0.0, 0.0
    if agent_key == "lineup_intelligence_agent":
        home = signals.get("home") or {}
        away = signals.get("away") or {}
        hs = float(home.get("lineup_strength", 50) or 50)
        aw = float(away.get("lineup_strength", 50) or 50)
        edge = _clamp((hs - aw) * 1.0, -70, 70)
        return _signals_from_impact(signals) if any(_signals_from_impact(signals)) else (edge, -edge, 0.0, 0.0, 0.0)
    if agent_key == "injury_suspension_intelligence_agent":
        home = signals.get("home") or {}
        away = signals.get("away") or {}
        hi = float(home.get("injury_impact_score", 0) or 0)
        ai = float(away.get("injury_impact_score", 0) or 0)
        edge = _clamp((ai - hi) * 0.8, -70, 70)
        base = _signals_from_impact(signals)
        if any(base):
            return base
        return edge, -edge, 0.0, 0.0, 0.0
    return 0.0, 0.0, 0.0, 0.0, 0.0


def _baseline_block(prediction: MatchPrediction) -> dict[str, Any]:
    return {
        "fixture_id": prediction.fixture_id,
        "match_name": prediction.match_name,
        "one_x_two": prediction.one_x_two.selection,
        "one_x_two_probability": prediction.one_x_two.probability,
        "over_under": prediction.over_under.selection,
        "over_under_probability": prediction.over_under.probability,
        "confidence_score": prediction.confidence_score,
        "risk_level": prediction.risk_level,
        "no_bet_flag": prediction.no_bet_flag,
    }


def _detect_conflicts(
    rows: list[AgentSignalRow],
    baseline_1x2: str,
    baseline_ou: str,
    specialist: MatchSpecialistReport | None,
) -> list[FusionConflict]:
    conflicts: list[FusionConflict] = []
    by_key = {r.agent_key: r for r in rows}

    def _pair(a_key: str, b_key: str, label: str, severity: str = "medium") -> None:
        a, b = by_key.get(a_key), by_key.get(b_key)
        if not a or not b:
            return
        if a.lean_1x2 == "neutral" or b.lean_1x2 == "neutral":
            return
        if a.lean_1x2 != b.lean_1x2:
            conflicts.append(
                FusionConflict(
                    description=f"{label}: {a.label} leans {a.lean_1x2}, {b.label} leans {b.lean_1x2}.",
                    severity=severity,  # type: ignore[arg-type]
                    agents=[a_key, b_key],
                )
            )

    _pair("lineup_intelligence_agent", "lineup_agent", "Lineup V1 vs V2", "medium")
    _pair("injury_suspension_intelligence_agent", "injury_suspension_agent", "Injury V1 vs V2", "medium")
    _pair("team_form_agent", "elo_team_strength_intelligence_agent", "Form vs ELO", "medium")
    _pair("xg_chance_quality_intelligence_agent", "tactics_agent", "xG vs Tactics", "low")

    _pair("elo_team_strength_intelligence_agent", "sharp_money_intelligence_agent", "ELO vs Sharp Money", "high")
    _pair("elo_team_strength_intelligence_agent", "market_consensus_agent", "ELO vs Market", "medium")

    xg = by_key.get("xg_chance_quality_intelligence_agent")
    inj = by_key.get("injury_suspension_intelligence_agent")
    if xg and inj and xg.lean_ou == "over" and inj.lean_ou == "under":
        conflicts.append(
            FusionConflict(
                description="xG chance quality suggests over lean while injury context suggests caution on goals.",
                severity="medium",
                agents=["xg_chance_quality_intelligence_agent", "injury_suspension_intelligence_agent"],
            )
        )

    tour = by_key.get("tournament_intelligence_agent")
    lineup = by_key.get("lineup_intelligence_agent")
    if tour and lineup:
        tour_flags = (
            specialist.signal("tournament_intelligence_agent").signals.get("risk_flags") or []
            if specialist
            else []
        )
        if "high_rotation_risk" in tour_flags and lineup.lean_1x2 in {"home", "away"}:
            conflicts.append(
                FusionConflict(
                    description="Tournament rotation risk vs lineup strength edge — interpret cautiously.",
                    severity="medium",
                    agents=["tournament_intelligence_agent", "lineup_intelligence_agent"],
                )
            )

    if specialist and specialist.signal("sharp_money_intelligence_agent"):
        sm = specialist.signal("sharp_money_intelligence_agent").signals
        if sm.get("steam_move_detected") and baseline_1x2:
            mc = by_key.get("market_consensus_agent")
            if mc and mc.lean_1x2 != "neutral":
                conflicts.append(
                    FusionConflict(
                        description="Market steam move detected while model maintains analytical lean — monitor closely.",
                        severity="high",
                        agents=["sharp_money_intelligence_agent", "market_consensus_agent"],
                    )
                )

    if specialist and specialist.master:
        for desc in specialist.master.signals.get("conflicts_between_agents", [])[:5]:
            conflicts.append(FusionConflict(description=str(desc), severity="medium"))

    return conflicts


def _quality_band(score: float) -> QualityBand:
    if score >= 80:
        return "Very Strong"
    if score >= 65:
        return "Strong"
    if score >= 45:
        return "Moderate"
    return "Weak"


def _consensus_and_quality(
    rows: list[AgentSignalRow],
    baseline_1x2: str,
    baseline_ou: str,
    conflicts: list[FusionConflict],
    report: MatchIntelligenceReport | None,
) -> tuple[float, float]:
    if not rows:
        return 50.0, 45.0

    baseline_x2 = {"home_win": "home", "away_win": "away", "draw": "draw"}.get(baseline_1x2, "neutral")
    baseline_ou_lean = {"over_2_5": "over", "under_2_5": "under"}.get(baseline_ou, "neutral")

    aligned_x2 = sum(1 for r in rows if r.lean_1x2 == baseline_x2)
    aligned_ou = sum(1 for r in rows if r.lean_ou == baseline_ou_lean)
    active_x2 = sum(1 for r in rows if r.lean_1x2 != "neutral")
    active_ou = sum(1 for r in rows if r.lean_ou != "neutral")

    x2_ratio = aligned_x2 / max(active_x2, 1)
    ou_ratio = aligned_ou / max(active_ou, 1)
    avg_strength = sum(max(abs(r.home_signal), abs(r.away_signal), abs(r.over25_signal)) for r in rows) / len(rows)
    strength_factor = _clamp(avg_strength / 40.0, 0.3, 1.0)

    conflict_penalty = sum(12 if c.severity == "high" else 6 if c.severity == "medium" else 3 for c in conflicts)
    consensus = _clamp((x2_ratio * 55 + ou_ratio * 25 + 20) * strength_factor - conflict_penalty * 0.5, 0, 100)

    dq = (report.data_quality.score * 100) if report and report.data_quality else 50.0
    avg_quality = sum(r.quality_multiplier for r in rows) / len(rows)
    decision_quality = _clamp(consensus * 0.55 + dq * 0.25 + avg_quality * 20 - conflict_penalty * 0.35, 0, 100)
    return round(consensus, 1), round(decision_quality, 1)


def _aggregate_matrix(rows: list[AgentSignalRow]) -> SignalMatrix:
    if not rows:
        return SignalMatrix()

    rows, _mults = apply_correlation_dampening(rows)

    totals = {"home": 0.0, "away": 0.0, "draw": 0.0, "over": 0.0, "under": 0.0}
    weight_sum = 0.0
    for row in rows:
        effective = row.weight * row.quality_multiplier * row.correlation_multiplier
        capped = _MAX_AGENT_SHARE
        share = min(effective, capped)
        weight_sum += share
        totals["home"] += row.home_signal * share
        totals["away"] += row.away_signal * share
        totals["draw"] += row.draw_signal * share
        totals["over"] += row.over25_signal * share
        totals["under"] += row.under25_signal * share

    if weight_sum <= 0:
        return SignalMatrix(agents=rows)

    norm = 1.0 / weight_sum
    return SignalMatrix(
        home_signal=round(_clamp(totals["home"] * norm, -100, 100), 1),
        away_signal=round(_clamp(totals["away"] * norm, -100, 100), 1),
        draw_signal=round(_clamp(totals["draw"] * norm, -100, 100), 1),
        over25_signal=round(_clamp(totals["over"] * norm, -100, 100), 1),
        under25_signal=round(_clamp(totals["under"] * norm, -100, 100), 1),
        agents=rows,
    )


def _risk_flags(
    consensus: float,
    quality: float,
    conflicts: list[FusionConflict],
    report: MatchIntelligenceReport | None,
    specialist: MatchSpecialistReport | None,
) -> list[str]:
    flags: list[str] = []
    if consensus < 45:
        flags.append("low_fusion_confidence")
    if sum(1 for c in conflicts if c.severity == "high") >= 2:
        flags.append("severe_agent_conflict")
    elif len(conflicts) >= 3:
        flags.append("severe_agent_conflict")
    if report and report.data_quality and report.data_quality.score < 0.45:
        flags.append("poor_data_quality")
    if specialist and specialist.signal("market_consensus_agent"):
        if specialist.signal("market_consensus_agent").signals.get("model_market_agreement") == "low":
            flags.append("market_model_disagreement")
    if specialist and specialist.signal("lineup_intelligence_agent"):
        lv2 = specialist.signal("lineup_intelligence_agent").signals
        home = lv2.get("home") or {}
        away = lv2.get("away") or {}
        if "official_lineup_missing" in (home.get("risk_flags") or []) and "official_lineup_missing" in (
            away.get("risk_flags") or []
        ):
            flags.append("lineup_uncertainty")
    if report and "injuries" in (report.missing_data or []):
        flags.append("injury_uncertainty")
    return flags


def _confidence_adjustment(
    consensus: float,
    quality: float,
    conflicts: list[FusionConflict],
    flags: list[str],
    *,
    diversity_score: float = 50.0,
) -> float:
    adj = (consensus - 50.0) / 12.0 + (quality - 50.0) / 20.0
    adj -= sum(2.0 for c in conflicts if c.severity == "high")
    if "severe_agent_conflict" in flags:
        adj -= 2.5
    if "low_fusion_confidence" in flags:
        adj -= 1.5
    if "poor_data_quality" in flags:
        adj -= 2.0
    if diversity_score >= 72:
        adj += 1.0
    elif diversity_score < 40:
        adj -= 1.0
    return round(_clamp(adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 2)


def _conflict_resolution_summary(conflicts: list[FusionConflict], baseline_1x2: str, baseline_ou: str) -> str:
    if not conflicts:
        return "No major cross-agent conflicts — baseline weighted decision retained with fusion confidence overlay."
    high = [c for c in conflicts if c.severity == "high"]
    if high:
        return (
            f"{len(conflicts)} conflict(s) detected; {len(high)} high-severity. "
            f"Baseline {baseline_1x2}/{baseline_ou} retained — confidence downweighted conservatively."
        )
    return (
        f"{len(conflicts)} moderate conflict(s) noted — baseline {baseline_1x2}/{baseline_ou} retained "
        "with reduced fusion confidence weight."
    )


def build_final_decision_fusion(
    prediction: MatchPrediction | None,
    *,
    report: MatchIntelligenceReport | None = None,
    specialist_report: MatchSpecialistReport | None = None,
    explainability_report: dict[str, Any] | None = None,
) -> FinalDecisionFusionReport:
    """Build fusion report — never raises."""
    try:
        if prediction is None:
            return FinalDecisionFusionReport(
                final_summary="Fusion unavailable — no baseline prediction.",
                risk_flags=["low_fusion_confidence", "poor_data_quality"],
            )

        specialist = specialist_report
        if specialist is None and report is not None:
            specialist = report.specialist_report

        baseline = _baseline_block(prediction)
        rows: list[AgentSignalRow] = []

        for agent_key, label, base_weight in _AGENT_ORDER:
            if not specialist:
                continue
            sig = specialist.signal(agent_key)
            if not sig or not sig.signals:
                continue
            signals = sig.signals
            h, a, d, o, u = _extract_agent_signals(agent_key, signals)
            if not any((h, a, d, o, u)):
                continue
            qmult = _quality_multiplier(agent_key, signals, report)
            row = AgentSignalRow(
                agent_key=agent_key,
                label=label,
                home_signal=h * qmult,
                away_signal=a * qmult,
                draw_signal=d * qmult,
                over25_signal=o * qmult,
                under25_signal=u * qmult,
                weight=base_weight,
                quality_multiplier=qmult,
                lean_1x2=_lean_from_signals(h, a, d),
                lean_ou=_ou_lean(o, u),
            )
            rows.append(row)

        matrix = _aggregate_matrix(rows)
        conflicts = _detect_conflicts(
            rows,
            prediction.one_x_two.selection,
            prediction.over_under.selection,
            specialist,
        )
        baseline_x2 = {"home_win": "home", "away_win": "away", "draw": "draw"}.get(
            prediction.one_x_two.selection, "neutral"
        )
        diversity_detail = compute_fusion_diversity_score(rows, baseline_1x2_lean=baseline_x2)
        diversity_detail.update(
            classify_signals_for_explainability(rows, baseline_1x2_lean=baseline_x2)
        )
        consensus, quality = _consensus_and_quality(
            rows,
            prediction.one_x_two.selection,
            prediction.over_under.selection,
            conflicts,
            report,
        )
        band = _quality_band(quality)
        flags = _risk_flags(consensus, quality, conflicts, report, specialist)
        if diversity_detail.get("redundant_agents"):
            flags.append("correlated_signal_overlap")
        conf_adj = _confidence_adjustment(
            consensus,
            quality,
            conflicts,
            flags,
            diversity_score=float(diversity_detail.get("fusion_diversity_score", 50)),
        )
        resolution = _conflict_resolution_summary(
            conflicts, prediction.one_x_two.selection, prediction.over_under.selection
        )

        fused_conf = round(_clamp(prediction.confidence_score + conf_adj, 0, 100), 1)
        fusion_prediction = {
            **baseline,
            "one_x_two": baseline["one_x_two"],
            "over_under": baseline["over_under"],
            "confidence_score": fused_conf,
            "confidence_adjustment_applied": conf_adj,
            "consensus_strength": consensus,
            "decision_quality_band": band,
        }

        if explainability_report:
            agreement = explainability_report.get("agreement") or {}
            if agreement.get("agreement_score") is not None:
                try:
                    boost = (float(agreement["agreement_score"]) - 50) / 30.0
                    conf_adj = round(_clamp(conf_adj + boost, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 2)
                    fusion_prediction["confidence_score"] = round(
                        _clamp(prediction.confidence_score + conf_adj, 0, 100), 1
                    )
                except (TypeError, ValueError):
                    pass

        home = report.home_team.team_name if report and report.home_team else "Home"
        away = report.away_team.team_name if report and report.away_team else "Away"
        summary = (
            f"{home} vs {away}: fusion {band} quality ({quality:.0f}/100), "
            f"consensus {consensus:.0f}/100, diversity {diversity_detail.get('fusion_diversity_score', 50):.0f}/100, "
            f"{len(rows)} agents blended. "
            f"Baseline retained; confidence adjustment {conf_adj:+.1f}."
        )

        return FinalDecisionFusionReport(
            baseline_prediction=baseline,
            fusion_prediction=fusion_prediction,
            signal_matrix=matrix,
            consensus_strength=consensus,
            decision_quality_score=quality,
            decision_quality_band=band,
            conflicts=conflicts,
            conflict_resolution_summary=resolution,
            risk_flags=flags,
            confidence_adjustment=conf_adj,
            final_summary=summary,
            fusion_diversity_score=float(diversity_detail.get("fusion_diversity_score", 50)),
            independent_signal_count=int(diversity_detail.get("independent_count", 0)),
            correlated_signal_count=int(diversity_detail.get("correlated_count", 0)),
            signal_diversity=diversity_detail,
        )
    except Exception:
        return FinalDecisionFusionReport(
            baseline_prediction=_baseline_block(prediction) if prediction else {},
            final_summary="Fusion engine fallback — partial data only.",
            risk_flags=["low_fusion_confidence"],
        )


def load_fusion_from_prediction(prediction: MatchPrediction | None) -> FinalDecisionFusionReport | None:
    """Load persisted fusion report from prediction metadata."""
    if prediction is None:
        return None
    raw = prediction.metadata.get("fusion_report_v2")
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(data, dict):
            return None
        agents = []
        for row in (data.get("signal_matrix") or {}).get("agents") or []:
            if not isinstance(row, dict):
                continue
            agents.append(
                AgentSignalRow(
                    agent_key=str(row.get("agent_key", "")),
                    label=str(row.get("label", "")),
                    home_signal=float(row.get("home_signal", 0)),
                    away_signal=float(row.get("away_signal", 0)),
                    draw_signal=float(row.get("draw_signal", 0)),
                    over25_signal=float(row.get("over25_signal", 0)),
                    under25_signal=float(row.get("under25_signal", 0)),
                    weight=float(row.get("weight", 1)),
                    quality_multiplier=float(row.get("quality_multiplier", 1)),
                    lean_1x2=str(row.get("lean_1x2", "neutral")),
                    lean_ou=str(row.get("lean_ou", "neutral")),
                    correlation_multiplier=float(row.get("correlation_multiplier", 1)),
                )
            )
        matrix_data = data.get("signal_matrix") or {}
        matrix = SignalMatrix(
            home_signal=float(matrix_data.get("home_signal", 0)),
            away_signal=float(matrix_data.get("away_signal", 0)),
            draw_signal=float(matrix_data.get("draw_signal", 0)),
            over25_signal=float(matrix_data.get("over25_signal", 0)),
            under25_signal=float(matrix_data.get("under25_signal", 0)),
            agents=agents,
        )
        conflicts = [
            FusionConflict(**c) for c in data.get("conflicts") or [] if isinstance(c, dict)
        ]
        return FinalDecisionFusionReport(
            baseline_prediction=data.get("baseline_prediction") or {},
            fusion_prediction=data.get("fusion_prediction") or {},
            signal_matrix=matrix,
            consensus_strength=float(data.get("consensus_strength", 50)),
            decision_quality_score=float(data.get("decision_quality_score", 50)),
            decision_quality_band=data.get("decision_quality_band", "Moderate"),  # type: ignore[arg-type]
            conflicts=conflicts,
            conflict_resolution_summary=str(data.get("conflict_resolution_summary") or ""),
            risk_flags=list(data.get("risk_flags") or []),
            confidence_adjustment=float(data.get("confidence_adjustment", 0)),
            final_summary=str(data.get("final_summary") or ""),
            fusion_diversity_score=float(data.get("fusion_diversity_score", 50)),
            independent_signal_count=int(data.get("independent_signal_count", 0)),
            correlated_signal_count=int(data.get("correlated_signal_count", 0)),
            signal_diversity=dict(data.get("signal_diversity") or {}),
        )
    except Exception:
        return None

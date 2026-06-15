"""xG & Chance Quality Intelligence V2 — Phase 45."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.chance_quality.models import (
    ChanceQualityAdvantage,
    ChanceQualityPredictionImpact,
    ConversionLabel,
    TeamChanceQualitySide,
    XGChanceQualityResult,
)
from worldcup_predictor.chance_quality.stat_extraction import extract_real_xg, extract_team_shooting_profile
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport

_ADJUSTMENT_CAP = 10.0
_EDGE_THRESHOLD = 18.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _conversion_label(efficiency: float, *, has_denominator: bool) -> ConversionLabel:
    if not has_denominator:
        return "unknown"
    if efficiency >= 0.32:
        return "unsustainably_clinical"
    if efficiency >= 0.22:
        return "clinical"
    if efficiency >= 0.12:
        return "average"
    return "poor"


def _attack_chance_quality(
    profile: dict[str, float | None],
    *,
    xg_per_match: float | None,
    xg_available: bool,
    chance_creation_score: float | None = None,
) -> float:
    score = 35.0
    weights = 0.0

    shots = profile.get("shots_total")
    if shots is not None:
        score += _clamp(shots / 14.0, 0, 1) * 22
        weights += 1
    sot = profile.get("shots_on_target")
    if sot is not None:
        score += _clamp(sot / 5.5, 0, 1) * 20
        weights += 1
    big = profile.get("big_chances")
    if big is not None:
        score += _clamp(big / 2.5, 0, 1) * 18
        weights += 1
    inside = profile.get("inside_box_shots")
    if inside is not None:
        score += _clamp(inside / 8.0, 0, 1) * 10
        weights += 1
    goals = profile.get("goals")
    if goals is not None:
        score += _clamp(goals / 2.0, 0, 1) * 10
        weights += 1
    if xg_available and xg_per_match is not None:
        score += _clamp(xg_per_match / 2.2, 0, 1) * 25
        weights += 1
    if chance_creation_score is not None and chance_creation_score > 0:
        score += _clamp(chance_creation_score / 100.0, 0, 1) * 8
        weights += 1

    if weights == 0:
        return 50.0
    return round(_clamp(score, 0, 100), 1)


def _defensive_prevention(profile: dict[str, float | None]) -> float:
    score = 50.0
    ga = profile.get("goals_against_avg")
    if ga is not None:
        score += _clamp((2.0 - ga) / 2.0, -0.5, 1) * 30
    blocked = profile.get("blocked_shots")
    if blocked is not None:
        score += _clamp(blocked / 5.0, 0, 1) * 12
    saves = profile.get("goalkeeper_saves")
    if saves is not None:
        score += _clamp(saves / 4.5, 0, 1) * 10
    return round(_clamp(score, 0, 100), 1)


def _conversion_efficiency(profile: dict[str, float | None]) -> tuple[float, ConversionLabel]:
    goals = profile.get("goals")
    sot = profile.get("shots_on_target")
    shots = profile.get("shots_total")
    if goals is not None and sot is not None and sot > 0:
        eff = goals / sot
        return round(eff, 3), _conversion_label(eff, has_denominator=True)
    if goals is not None and shots is not None and shots > 0:
        eff = goals / shots
        return round(eff, 3), _conversion_label(eff, has_denominator=True)
    return 0.0, "unknown"


def _goals_pressure_score(home: TeamChanceQualitySide, away: TeamChanceQualitySide) -> float:
    attack_avg = (home.attack_chance_quality + away.attack_chance_quality) / 2
    prevention_avg = 100 - (home.defensive_chance_prevention + away.defensive_chance_prevention) / 2
    sot_sum = 0.0
    sot_n = 0
    for side in (home, away):
        if side.shots_on_target is not None:
            sot_sum += side.shots_on_target
            sot_n += 1
    sot_factor = _clamp(sot_sum / max(sot_n, 1) / 6.0, 0, 1) * 20 if sot_n else 0
    xg_factor = 0.0
    if home.xg_per_match is not None and away.xg_per_match is not None:
        xg_factor = _clamp((home.xg_per_match + away.xg_per_match) / 3.5, 0, 1) * 15
    raw = attack_avg * 0.45 + prevention_avg * 0.25 + sot_factor + xg_factor + 10
    return round(_clamp(raw, 0, 100), 1)


def _chance_edges(home: TeamChanceQualitySide, away: TeamChanceQualitySide) -> tuple[float, float]:
    attack_delta = home.attack_chance_quality - away.attack_chance_quality
    prevention_delta = home.defensive_chance_prevention - away.defensive_chance_prevention
    home_edge = _clamp(attack_delta * 0.7 + prevention_delta * 0.3, -100, 100)
    away_edge = _clamp(-home_edge, -100, 100)
    return round(home_edge, 1), round(away_edge, 1)


def _advantage(home: TeamChanceQualitySide, away: TeamChanceQualitySide, home_edge: float) -> ChanceQualityAdvantage:
    if home_edge >= _EDGE_THRESHOLD:
        return ChanceQualityAdvantage(
            side="home",
            reason=(
                f"Home leads chance quality ({home.attack_chance_quality:.0f} vs {away.attack_chance_quality:.0f} attack, "
                f"prevention {home.defensive_chance_prevention:.0f} vs {away.defensive_chance_prevention:.0f})."
            ),
        )
    if home_edge <= -_EDGE_THRESHOLD:
        return ChanceQualityAdvantage(
            side="away",
            reason=(
                f"Away leads chance quality ({away.attack_chance_quality:.0f} vs {home.attack_chance_quality:.0f} attack, "
                f"prevention {away.defensive_chance_prevention:.0f} vs {home.defensive_chance_prevention:.0f})."
            ),
        )
    return ChanceQualityAdvantage(
        side="balanced",
        reason="Chance creation and defensive prevention profiles are closely matched.",
    )


def _risk_flags(
    home: TeamChanceQualitySide,
    away: TeamChanceQualitySide,
    *,
    xg_available: bool,
    chance_quality_available: bool,
    is_placeholder: bool,
    goals_pressure: float,
) -> list[str]:
    flags: list[str] = []
    for side in (home, away):
        if side.attack_chance_quality >= 68:
            flags.append("high_chance_creation")
        if side.attack_chance_quality <= 32:
            flags.append("poor_chance_creation")
        if side.conversion_label == "clinical":
            flags.append("clinical_finishing")
        if side.conversion_label == "unsustainably_clinical":
            flags.append("unsustainable_finishing")
        if side.defensive_chance_prevention <= 35:
            flags.append("defensive_leak")
        if side.defensive_chance_prevention >= 68:
            flags.append("strong_defensive_prevention")

    if not xg_available:
        flags.append("low_xg_data_confidence")
    if not chance_quality_available or is_placeholder:
        flags.append("limited_statistics")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for flag in flags:
        if flag not in seen:
            seen.add(flag)
            unique.append(flag)

    if goals_pressure >= 72 and "high_chance_creation" not in unique:
        unique.append("high_chance_creation")
    if goals_pressure <= 28:
        unique.append("poor_chance_creation")
    return unique


def _prediction_impact(
    home: TeamChanceQualitySide,
    away: TeamChanceQualitySide,
    *,
    home_edge: float,
    advantage: ChanceQualityAdvantage,
    goals_pressure: float,
    risk_flags: list[str],
) -> ChanceQualityPredictionImpact:
    if "limited_statistics" in risk_flags and "low_xg_data_confidence" in risk_flags:
        return ChanceQualityPredictionImpact()

    home_adj = _clamp(home_edge / 35.0, -4.0, 4.0)
    away_adj = _clamp(-home_edge / 35.0, -4.0, 4.0)

    if advantage.side == "balanced":
        draw_adj = 1.5
    else:
        draw_adj = -1.0

    over_adj = _clamp((goals_pressure - 50) / 12.0, -4.0, 5.0)
    under_adj = _clamp(-over_adj * 0.65, -4.0, 4.0)

    if "defensive_leak" in risk_flags:
        over_adj += 1.0
    if "strong_defensive_prevention" in risk_flags and home.defensive_chance_prevention >= 68 and away.defensive_chance_prevention >= 68:
        over_adj -= 1.5
        under_adj += 1.0
    if "unsustainable_finishing" in risk_flags:
        over_adj -= 0.5
    if "clinical_finishing" in risk_flags:
        over_adj += 0.5

    if "low_xg_data_confidence" in risk_flags:
        over_adj *= 0.6
        home_adj *= 0.7
        away_adj *= 0.7

    return ChanceQualityPredictionImpact(
        home_adjustment=_clamp(home_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP),
        away_adjustment=_clamp(away_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP),
        draw_adjustment=_clamp(draw_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP),
        over25_adjustment=_clamp(over_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP),
        under25_adjustment=_clamp(under_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP),
    )


def _team_chance_creation(report: MatchIntelligenceReport, side: str) -> float | None:
    try:
        from worldcup_predictor.integrations.api_sports_deep_data import API_SPORTS_DEEP_KEY

        deep = (getattr(report, "supplemental_sources", None) or {}).get(API_SPORTS_DEEP_KEY) or {}
        block = (deep.get("chance_creation") or {}).get(side) or {}
        val = block.get("chance_creation_score")
        return float(val) if val is not None else None
    except Exception:
        return None


def _build_team_side(
    report: MatchIntelligenceReport,
    *,
    side: str,
    team_name: str,
    team_id: int | None,
    team_stats: dict[str, Any],
    xg_available: bool,
) -> TeamChanceQualitySide:
    profile = extract_team_shooting_profile(report, side=side, team_stats=team_stats)
    xg_val, _ = extract_real_xg(report, side=side, team_stats=team_stats)
    played = profile.get("matches_played")
    xg_per_match = None
    if xg_val is not None:
        if played and played > 1 and xg_val > played:
            xg_per_match = xg_val / played
        else:
            xg_per_match = xg_val

    cc_score = _team_chance_creation(report, side)
    attack = _attack_chance_quality(
        profile,
        xg_per_match=xg_per_match,
        xg_available=xg_available and xg_val is not None,
        chance_creation_score=cc_score,
    )
    prevention = _defensive_prevention(profile)
    efficiency, label = _conversion_efficiency(profile)

    return TeamChanceQualitySide(
        team_name=team_name,
        team_id=team_id,
        xg=xg_val,
        xg_per_match=xg_per_match,
        attack_chance_quality=attack,
        defensive_chance_prevention=prevention,
        conversion_efficiency=efficiency,
        conversion_label=label,
        shots_total=profile.get("shots_total"),
        shots_on_target=profile.get("shots_on_target"),
        big_chances=profile.get("big_chances"),
        goals=profile.get("goals"),
        blocked_shots=profile.get("blocked_shots"),
        goalkeeper_saves=profile.get("goalkeeper_saves"),
        inside_box_shots=profile.get("inside_box_shots"),
    )


def _has_chance_data(profile: dict[str, float | None]) -> bool:
    keys = ("shots_total", "shots_on_target", "big_chances", "goals", "blocked_shots", "inside_box_shots")
    return any(profile.get(k) is not None for k in keys)


def build_xg_chance_quality_intelligence(report: MatchIntelligenceReport | None) -> XGChanceQualityResult:
    """Build xG & chance quality intelligence — never raises."""
    fallback_home = TeamChanceQualitySide(team_name="Home")
    fallback_away = TeamChanceQualitySide(team_name="Away")
    if report is None:
        return XGChanceQualityResult(
            xg_available=False,
            chance_quality_available=False,
            data_mode="unavailable",
            home=fallback_home,
            away=fallback_away,
            chance_quality_advantage=ChanceQualityAdvantage(
                side="balanced",
                reason="No intelligence report — neutral chance quality assumed.",
            ),
            risk_flags=["low_xg_data_confidence", "limited_statistics"],
            summary="Chance quality unavailable — using neutral baseline.",
        )

    home_stats = report.home_team.statistics or {}
    away_stats = report.away_team.statistics or {}
    home_name = report.home_team.team_name or "Home"
    away_name = report.away_team.team_name or "Away"

    home_xg, _ = extract_real_xg(report, side="home", team_stats=home_stats)
    away_xg, _ = extract_real_xg(report, side="away", team_stats=away_stats)
    xg_available = home_xg is not None or away_xg is not None

    home_profile = extract_team_shooting_profile(report, side="home", team_stats=home_stats)
    away_profile = extract_team_shooting_profile(report, side="away", team_stats=away_stats)
    chance_quality_available = _has_chance_data(home_profile) or _has_chance_data(away_profile)

    if report.is_placeholder and not xg_available:
        chance_quality_available = False

    data_mode = "unavailable"
    if xg_available:
        data_mode = "xg"
    elif chance_quality_available:
        data_mode = "fallback"

    home = _build_team_side(
        report,
        side="home",
        team_name=home_name,
        team_id=report.home_team.team_id,
        team_stats=home_stats,
        xg_available=xg_available,
    )
    away = _build_team_side(
        report,
        side="away",
        team_name=away_name,
        team_id=report.away_team.team_id,
        team_stats=away_stats,
        xg_available=xg_available,
    )

    home_edge, away_edge = _chance_edges(home, away)
    advantage = _advantage(home, away, home_edge)
    goals_pressure = _goals_pressure_score(home, away)
    flags = _risk_flags(
        home,
        away,
        xg_available=xg_available,
        chance_quality_available=chance_quality_available,
        is_placeholder=report.is_placeholder,
        goals_pressure=goals_pressure,
    )
    impact = _prediction_impact(
        home,
        away,
        home_edge=home_edge,
        advantage=advantage,
        goals_pressure=goals_pressure,
        risk_flags=flags,
    )

    mode_label = {"xg": "xG-backed", "fallback": "shot-based fallback", "unavailable": "unavailable"}[data_mode]
    summary = (
        f"{home_name} vs {away_name} — {mode_label}. "
        f"Attack quality {home.attack_chance_quality:.0f}/{away.attack_chance_quality:.0f}, "
        f"goals pressure {goals_pressure:.0f}/100, advantage {advantage.side}."
    )

    return XGChanceQualityResult(
        xg_available=xg_available,
        chance_quality_available=chance_quality_available,
        data_mode=data_mode,
        home=home,
        away=away,
        home_chance_edge=home_edge,
        away_chance_edge=away_edge,
        goals_pressure_score=goals_pressure,
        chance_quality_advantage=advantage,
        risk_flags=flags,
        prediction_impact=impact,
        summary=summary,
    )

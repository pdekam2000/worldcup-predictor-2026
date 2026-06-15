"""ELO & Team Strength Intelligence V2 — Phase 44."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.strength.elo_engine import BASE_ELO, _HOME_ADVANTAGE_ELO, compute_elo_from_fixtures
from worldcup_predictor.strength.models import (
    EloTeamStrengthResult,
    FormWindowStats,
    MatchupAdvantage,
    StrengthPredictionImpact,
    TeamStrengthSide,
)

_ADJUSTMENT_CAP = 10.0
_ELO_GAP_LARGE = 120.0
_ELO_GAP_CLOSE = 35.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _empty_form() -> FormWindowStats:
    return FormWindowStats()


def _result_for_team(home_g: int, away_g: int, team_id: int, home_id: int | None, away_id: int | None) -> str | None:
    if team_id == home_id:
        if home_g > away_g:
            return "W"
        if home_g < away_g:
            return "L"
        return "D"
    if team_id == away_id:
        if away_g > home_g:
            return "W"
        if away_g < home_g:
            return "L"
        return "D"
    return None


def _collect_finished_matches(
    recent_fixtures: list[dict[str, Any]] | None,
    team_id: int | None,
) -> list[dict[str, Any]]:
    if not recent_fixtures or team_id is None:
        return []
    out: list[dict[str, Any]] = []
    for item in recent_fixtures:
        goals = item.get("goals") or {}
        teams = item.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        home_g = goals.get("home")
        away_g = goals.get("away")
        if home_g is None or away_g is None:
            continue
        try:
            home_g = int(home_g)
            away_g = int(away_g)
        except (TypeError, ValueError):
            continue
        home_id = home.get("id")
        away_id = away.get("id")
        result = _result_for_team(home_g, away_g, int(team_id), home_id, away_id)
        if result is None:
            continue
        gf = home_g if team_id == home_id else away_g
        ga = away_g if team_id == home_id else home_g
        out.append({"result": result, "gf": gf, "ga": ga})
    return out


def _form_window(matches: list[dict[str, Any]], window: int) -> FormWindowStats:
    slice_ = matches[:window]
    if not slice_:
        return _empty_form()
    wins = sum(1 for m in slice_ if m["result"] == "W")
    draws = sum(1 for m in slice_ if m["result"] == "D")
    losses = sum(1 for m in slice_ if m["result"] == "L")
    gf = sum(m["gf"] for m in slice_)
    ga = sum(m["ga"] for m in slice_)
    pts = wins * 3 + draws
    n = len(slice_)
    return FormWindowStats(
        matches=n,
        wins=wins,
        draws=draws,
        losses=losses,
        goals_for=gf,
        goals_against=ga,
        points_per_match=round(pts / n, 2),
        form_string="".join(m["result"] for m in slice_),
    )


def _strength_from_form(form: FormWindowStats) -> tuple[float, float, float]:
    if form.matches == 0:
        return 50.0, 50.0, 50.0
    gf_avg = form.goals_for / form.matches
    ga_avg = form.goals_against / form.matches
    attack = _clamp((gf_avg / 2.5) * 55 + 22, 0, 100)
    defense = _clamp((2.5 - ga_avg) / 2.5 * 55 + 22, 0, 100)
    ppg_factor = _clamp(form.points_per_match / 3.0 * 100, 0, 100)
    overall = _clamp(attack * 0.4 + defense * 0.35 + ppg_factor * 0.25, 0, 100)
    return round(attack, 1), round(defense, 1), round(overall, 1)


def _momentum(form5: FormWindowStats, form10: FormWindowStats) -> float:
    if form5.matches == 0 and form10.matches == 0:
        return 0.0
    ppg5 = form5.points_per_match if form5.matches else form10.points_per_match
    ppg10 = form10.points_per_match if form10.matches else ppg5
    if form10.matches >= 5 and form5.matches >= 3:
        delta = ppg5 - ppg10
        return round(_clamp(delta * 35.0, -100, 100), 1)
    if form5.matches >= 2:
        delta = ppg5 - 1.5
        return round(_clamp(delta * 25.0, -60, 60), 1)
    return 0.0


def _build_team_side(
    team_name: str,
    team_id: int | None,
    recent_fixtures: list[dict[str, Any]] | None,
    *,
    use_elo: bool,
) -> tuple[TeamStrengthSide, int]:
    matches = _collect_finished_matches(recent_fixtures, team_id)
    form5 = _form_window(matches, 5)
    form10 = _form_window(matches, 10)
    form20 = _form_window(matches, 20)
    attack, defense, overall = _strength_from_form(form10 if form10.matches else form5)
    momentum = _momentum(form5, form10)

    if use_elo and team_id is not None:
        elo, _ = compute_elo_from_fixtures(recent_fixtures, team_id)
    else:
        elo = BASE_ELO

    side = TeamStrengthSide(
        team_name=team_name,
        team_id=team_id,
        elo=elo,
        form_last_5=form5,
        form_last_10=form10,
        form_last_20=form20,
        attack_strength=attack,
        defense_strength=defense,
        overall_team_strength=overall,
        momentum_score=momentum,
    )
    return side, len(matches)


def _matchup_advantage(
    home: TeamStrengthSide,
    away: TeamStrengthSide,
    elo_difference: float,
) -> MatchupAdvantage:
    adjusted_diff = elo_difference
    if adjusted_diff >= _ELO_GAP_LARGE:
        reason = (
            f"Home has +{adjusted_diff:.0f} ELO advantage and "
            f"{'stronger' if home.attack_strength >= away.attack_strength else 'comparable'} attack profile."
        )
        return MatchupAdvantage(side="home", reason=reason)
    if adjusted_diff <= -_ELO_GAP_LARGE:
        reason = (
            f"Away has +{abs(adjusted_diff):.0f} ELO advantage and "
            f"{'stronger' if away.attack_strength >= home.attack_strength else 'comparable'} attack profile."
        )
        return MatchupAdvantage(side="away", reason=reason)
    if abs(adjusted_diff) <= _ELO_GAP_CLOSE:
        return MatchupAdvantage(
            side="balanced",
            reason=f"ELO gap is narrow ({adjusted_diff:+.0f}) — strength profiles closely matched.",
        )
    if adjusted_diff > 0:
        return MatchupAdvantage(
            side="home",
            reason=f"Home holds a moderate +{adjusted_diff:.0f} ELO edge with balanced underlying metrics.",
        )
    return MatchupAdvantage(
        side="away",
        reason=f"Away holds a moderate +{abs(adjusted_diff):.0f} ELO edge with balanced underlying metrics.",
    )


def _risk_flags(
    home: TeamStrengthSide,
    away: TeamStrengthSide,
    elo_difference: float,
    sample_home: int,
    sample_away: int,
    *,
    is_placeholder: bool,
    form_mismatch: bool,
) -> list[str]:
    flags: list[str] = []
    if abs(elo_difference) >= _ELO_GAP_LARGE:
        flags.append("large_elo_gap")
    if abs(elo_difference) <= _ELO_GAP_CLOSE:
        flags.append("close_strength_matchup")
    if form_mismatch:
        flags.append("form_mismatch")
    if home.defense_strength < 35 or away.defense_strength < 35:
        flags.append("defensive_weakness")
    if home.attack_strength >= 65 and home.attack_strength > away.attack_strength + 12:
        flags.append("attacking_advantage")
    elif away.attack_strength >= 65 and away.attack_strength > home.attack_strength + 12:
        flags.append("attacking_advantage")
    if home.momentum_score <= -25 or away.momentum_score <= -25:
        flags.append("recent_decline")
    if sample_home < 3 or sample_away < 3:
        flags.append("unreliable_history")
    if is_placeholder or sample_home < 2 or sample_away < 2:
        flags.append("low_data_confidence")
    return flags


def _prediction_impact(
    home: TeamStrengthSide,
    away: TeamStrengthSide,
    elo_difference: float,
    matchup: MatchupAdvantage,
    risk_flags: list[str],
) -> StrengthPredictionImpact:
    if "low_data_confidence" in risk_flags:
        return StrengthPredictionImpact()

    home_adj = _clamp(elo_difference / 80.0, -4.0, 4.0)
    away_adj = _clamp(-elo_difference / 80.0, -4.0, 4.0)

    if matchup.side == "balanced":
        draw_adj = 2.0
    elif abs(elo_difference) >= _ELO_GAP_LARGE:
        draw_adj = -2.5
    else:
        draw_adj = 0.5

    if "attacking_advantage" in risk_flags:
        if home.attack_strength > away.attack_strength:
            home_adj += 1.0
        else:
            away_adj += 1.0

    if "defensive_weakness" in risk_flags:
        over_adj = 1.5
        under_adj = -1.0
    else:
        avg_attack = (home.attack_strength + away.attack_strength) / 2
        over_adj = _clamp((avg_attack - 50) / 25.0, -2.0, 3.0)
        under_adj = -over_adj * 0.6

    if "form_mismatch" in risk_flags:
        if home.momentum_score > away.momentum_score + 15:
            home_adj += 1.0
        elif away.momentum_score > home.momentum_score + 15:
            away_adj += 1.0

    if "recent_decline" in risk_flags:
        if home.momentum_score <= -25:
            home_adj -= 1.0
        if away.momentum_score <= -25:
            away_adj -= 1.0

    if "close_strength_matchup" in risk_flags:
        home_adj *= 0.6
        away_adj *= 0.6

    return StrengthPredictionImpact(
        home_adjustment=_clamp(home_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP),
        away_adjustment=_clamp(away_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP),
        draw_adjustment=_clamp(draw_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP),
        over25_adjustment=_clamp(over_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP),
        under25_adjustment=_clamp(under_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP),
    )


def build_elo_team_strength_intelligence(report: MatchIntelligenceReport | None) -> EloTeamStrengthResult:
    """Build team strength intelligence — never raises."""
    fallback_home = TeamStrengthSide(team_name="Home")
    fallback_away = TeamStrengthSide(team_name="Away")
    if report is None:
        return EloTeamStrengthResult(
            home=fallback_home,
            away=fallback_away,
            home_elo=BASE_ELO,
            away_elo=BASE_ELO,
            elo_difference=0.0,
            matchup_advantage=MatchupAdvantage(
                side="balanced",
                reason="No intelligence report — neutral strength assumed.",
            ),
            risk_flags=["low_data_confidence", "unreliable_history"],
            summary="Team strength unavailable — using neutral baseline.",
            data_available=False,
        )

    home_name = getattr(report.home_team, "team_name", "Home") or "Home"
    away_name = getattr(report.away_team, "team_name", "Away") or "Away"
    home_id = report.home_team.team_id
    away_id = report.away_team.team_id
    use_elo = not report.is_placeholder and report.source != "placeholder"

    home_side, sample_home = _build_team_side(
        home_name,
        home_id,
        report.home_recent_fixtures,
        use_elo=use_elo,
    )
    away_side, sample_away = _build_team_side(
        away_name,
        away_id,
        report.away_recent_fixtures,
        use_elo=use_elo,
    )

    home_elo = home_side.elo
    away_elo = away_side.elo
    elo_difference = round(home_elo - away_elo + _HOME_ADVANTAGE_ELO, 1)

    form_mismatch = False
    if home_side.form_last_5.matches >= 3 and away_side.form_last_5.matches >= 3:
        ppg_gap = abs(home_side.form_last_5.points_per_match - away_side.form_last_5.points_per_match)
        elo_sign = 1 if elo_difference > 0 else -1 if elo_difference < 0 else 0
        form_sign = (
            1
            if home_side.form_last_5.points_per_match > away_side.form_last_5.points_per_match
            else -1
            if home_side.form_last_5.points_per_match < away_side.form_last_5.points_per_match
            else 0
        )
        form_mismatch = ppg_gap >= 1.0 and elo_sign != 0 and form_sign != 0 and elo_sign != form_sign

    matchup = _matchup_advantage(home_side, away_side, elo_difference)
    flags = _risk_flags(
        home_side,
        away_side,
        elo_difference,
        sample_home,
        sample_away,
        is_placeholder=report.is_placeholder,
        form_mismatch=form_mismatch,
    )
    impact = _prediction_impact(home_side, away_side, elo_difference, matchup, flags)

    data_available = sample_home >= 2 and sample_away >= 2 and use_elo
    summary = (
        f"{home_name} ELO {home_elo:.0f} vs {away_name} {away_elo:.0f} "
        f"(Δ {elo_difference:+.0f}, {matchup.side}). "
        f"Samples: {sample_home}/{sample_away} recent matches."
    )
    if not use_elo:
        summary += " Placeholder data — minimal strength weight applied."

    return EloTeamStrengthResult(
        home=home_side,
        away=away_side,
        home_elo=home_elo,
        away_elo=away_elo,
        elo_difference=elo_difference,
        matchup_advantage=matchup,
        risk_flags=flags,
        prediction_impact=impact,
        summary=summary,
        data_available=data_available,
        sample_size_home=sample_home,
        sample_size_away=sample_away,
    )

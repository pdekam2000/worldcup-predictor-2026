"""Tournament Intelligence V2 — World Cup, Nations League, EURO, Copa América context."""

from __future__ import annotations

import re
from typing import Any

from worldcup_predictor.tournament.models import (
    TeamTournamentSide,
    TournamentIntelligenceResult,
    TournamentPredictionImpact,
)

_ADJUSTMENT_CAP = 10.0

_TOURNAMENT_KEYWORDS = (
    "world cup",
    "nations league",
    "euro",
    "copa america",
    "copa américa",
    "afcon",
    "asian cup",
    "gold cup",
)

_KNOCKOUT_CONTEXTS = (
    ("third place", "Third Place Match"),
    ("3rd place", "Third Place Match"),
    ("final", "Final"),
    ("semi", "Semi Final"),
    ("quarter", "Quarter Final"),
    ("round of 16", "Round of 16"),
    ("last 16", "Round of 16"),
    ("8th finals", "Round of 16"),
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _classify_match_context(stage: str | None, round_name: str | None = None) -> str:
    combined = f"{stage or ''} {round_name or ''}".lower()
    if "third" in combined and "place" in combined:
        return "Third Place Match"
    if re.search(r"\bfinal\b", combined) and "semi" not in combined and "quarter" not in combined:
        if "3rd" not in combined and "third" not in combined:
            return "Final"
    for key, label in _KNOCKOUT_CONTEXTS:
        if key in combined and label != "Final":
            return label
    if "group" in combined or "matchday" in combined or re.search(r"group\s+[a-h]", combined):
        md = re.search(r"matchday\s*(\d+)", combined)
        if md:
            return f"Group Stage (Matchday {md.group(1)})"
        return "Group Stage"
    if "nations league" in combined:
        return "Nations League"
    if stage and stage != "TBD":
        return stage
    return "Unknown"


def _pressure_score(match_context: str) -> float:
    ctx = match_context.lower()
    if ctx == "final":
        return 96.0
    if "semi" in ctx:
        return 88.0
    if "quarter" in ctx:
        return 78.0
    if "round of 16" in ctx:
        return 68.0
    if "third place" in ctx:
        return 62.0
    if "matchday 3" in ctx or "matchday 3" in ctx.replace(" ", ""):
        return 55.0
    if "matchday 2" in ctx:
        return 45.0
    if "group stage" in ctx:
        return 38.0
    if "nations league" in ctx:
        return 50.0
    return 35.0


def _map_qualification_status(raw: str | None) -> str:
    key = (raw or "unknown").lower()
    mapping = {
        "likely_qualified": "already_qualified",
        "rotation_risk": "already_qualified",
        "must_win": "must_win",
        "eliminated": "already_eliminated",
        "draw_acceptable": "draw_acceptable",
        "goal_difference_critical": "goal_difference_critical",
    }
    return mapping.get(key, "unknown")


def _infer_draw_acceptable(
    status: str,
    rank: int | None,
    points: int | None,
    goal_diff: int | None,
) -> bool:
    if status in {"already_qualified", "draw_acceptable"}:
        return True
    if rank is not None and rank <= 2 and points is not None and points >= 4:
        return True
    if goal_diff is not None and rank == 3 and points is not None and points >= 3:
        return True
    return False


def _scenario_scores(
    status: str,
    rank: int | None,
    points: int | None,
    *,
    is_knockout: bool,
) -> tuple[float, float]:
    if is_knockout:
        return 50.0, 50.0
    if status == "already_qualified":
        return 88.0, 12.0
    if status == "already_eliminated":
        return 8.0, 92.0
    if status == "must_win":
        base = 35.0
        if rank == 3 and points is not None:
            base = 40.0 + min(points * 4, 12)
        return _clamp(base, 15, 55), _clamp(100 - base, 45, 85)
    if status == "draw_acceptable":
        return 65.0, 25.0
    if status == "goal_difference_critical":
        return 45.0, 55.0
    if rank == 1:
        return 72.0, 20.0
    if rank == 2:
        return 58.0, 30.0
    if rank == 3:
        return 42.0, 48.0
    if rank == 4:
        return 25.0, 65.0
    return 50.0, 50.0


def _motivation_boost(status: str, *, is_knockout: bool) -> float:
    if status == "must_win":
        return 8.0
    if status == "already_qualified":
        return -3.0
    if status == "already_eliminated":
        return -5.0
    if status == "draw_acceptable":
        return 2.0
    if status == "goal_difference_critical":
        return 5.0
    if is_knockout:
        return 4.0
    return 0.0


def _rotation_risk(
    home_status: str,
    away_status: str,
    match_context: str,
) -> str:
    ctx = match_context.lower()
    if "final" in ctx or "semi" in ctx or "quarter" in ctx or "round of 16" in ctx:
        return "Low"
    statuses = {home_status, away_status}
    if "already_qualified" in statuses:
        return "High"
    if home_status == "already_eliminated" and away_status == "already_eliminated":
        return "Medium"
    if "must_win" in statuses:
        return "Low"
    if "draw_acceptable" in statuses:
        return "Medium"
    return "Medium"


def _build_team_side(
    team_name: str,
    *,
    raw_status: str | None,
    rank: int | None,
    points: int | None,
    goal_diff: int | None,
    is_knockout: bool,
) -> TeamTournamentSide:
    status = _map_qualification_status(raw_status)
    if _infer_draw_acceptable(status, rank, points, goal_diff) and status == "unknown":
        status = "draw_acceptable"
    if goal_diff is not None and rank == 3 and status in {"must_win", "unknown"}:
        status = "goal_difference_critical"
    qual_prob, elim_risk = _scenario_scores(status, rank, points, is_knockout=is_knockout)
    return TeamTournamentSide(
        team_name=team_name,
        qualification_status=status,  # type: ignore[arg-type]
        qualification_probability=round(qual_prob, 1),
        elimination_risk=round(elim_risk, 1),
        motivation_boost=round(_motivation_boost(status, is_knockout=is_knockout), 1),
        rank=rank,
        points=points,
        goal_difference=goal_diff,
    )


def _build_risk_flags(
    home: TeamTournamentSide,
    away: TeamTournamentSide,
    rotation: str,
    match_context: str,
    data_available: bool,
) -> list[str]:
    flags: list[str] = []
    if home.qualification_status == "must_win" or away.qualification_status == "must_win":
        flags.append("must_win_match")
    if home.qualification_status == "goal_difference_critical" or away.qualification_status == "goal_difference_critical":
        flags.append("goal_difference_critical")
    if (
        home.qualification_status in {"must_win", "goal_difference_critical"}
        or away.qualification_status in {"must_win", "goal_difference_critical"}
    ) and "Group Stage" in match_context and "Matchday 3" in match_context:
        flags.append("qualification_decider")
    if home.elimination_risk >= 70 or away.elimination_risk >= 70:
        flags.append("elimination_risk_high")
    if home.qualification_status == "already_qualified":
        flags.append("already_qualified")
    if away.qualification_status == "already_qualified":
        flags.append("already_qualified")
    if home.qualification_status == "already_eliminated":
        flags.append("already_eliminated")
    if away.qualification_status == "already_eliminated":
        flags.append("already_eliminated")
    if rotation == "High":
        flags.append("high_rotation_risk")
    if match_context == "Final":
        flags.append("final_match_pressure")
    if not data_available:
        flags.append("low_tournament_data_confidence")
    return sorted(set(flags))


def _build_prediction_impact(
    home: TeamTournamentSide,
    away: TeamTournamentSide,
    match_context: str,
) -> TournamentPredictionImpact:
    impact = TournamentPredictionImpact()
    weight = 0.45

    impact.home_adjustment = round(
        _clamp(home.motivation_boost * weight, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 2
    )
    impact.away_adjustment = round(
        _clamp(away.motivation_boost * weight, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 2
    )

    if home.qualification_status == "draw_acceptable" or away.qualification_status == "draw_acceptable":
        impact.draw_adjustment = round(_clamp(2.5 * weight, 0, _ADJUSTMENT_CAP), 2)

    if "Final" in match_context or "Semi Final" in match_context:
        boost = 1.5 * weight
        if home.motivation_boost >= away.motivation_boost:
            impact.home_adjustment = round(_clamp(impact.home_adjustment + boost, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 2)
        else:
            impact.away_adjustment = round(_clamp(impact.away_adjustment + boost, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 2)

    return impact


def _competition_meta(report: Any) -> tuple[str, str]:
    fixture = getattr(report, "fixture", None)
    stage = getattr(fixture, "stage", None) or ""
    comp_key = getattr(fixture, "competition_key", None) or "unknown"
    comp_name = getattr(fixture, "competition_name", None) or str(comp_key).replace("_", " ").title()
    combined = f"{stage} {comp_name} {comp_key}".lower()
    if any(k in combined for k in _TOURNAMENT_KEYWORDS):
        if "nations league" in combined:
            return "tournament", "UEFA Nations League"
        if "copa" in combined:
            return "tournament", "Copa América"
        if "euro" in combined:
            return "tournament", "UEFA EURO"
        if "world cup" in combined or comp_key == "world_cup_2026":
            return "tournament", "FIFA World Cup"
        return "tournament", comp_name
    if "league" in combined and "nations" not in combined:
        return "league", comp_name
    if "friendly" in combined:
        return "friendly", comp_name
    return "unknown", comp_name


def _safe_fallback(report: Any | None = None) -> TournamentIntelligenceResult:
    home_name = getattr(getattr(report, "home_team", None), "team_name", "Home") if report else "Home"
    away_name = getattr(getattr(report, "away_team", None), "team_name", "Away") if report else "Away"
    empty = TeamTournamentSide(team_name=home_name)
    away = TeamTournamentSide(team_name=away_name)
    return TournamentIntelligenceResult(
        match_context="Unknown",
        competition_type="unknown",
        tournament_name="Unknown",
        home=empty,
        away=away,
        rotation_risk="Medium",
        pressure_score=35.0,
        risk_flags=["low_tournament_data_confidence"],
        summary="Tournament context unavailable — safe fallback applied. Analysis only — not betting advice.",
        data_available=False,
    )


def build_tournament_intelligence(
    report: Any,
    *,
    tournament_context: dict[str, Any] | None = None,
) -> TournamentIntelligenceResult:
    """Build Tournament Intelligence V2 from fixture, group context, and schedule data."""
    try:
        if report is None:
            return _safe_fallback()

        fixture = getattr(report, "fixture", None)
        home_name = getattr(getattr(report, "home_team", None), "team_name", "Home")
        away_name = getattr(getattr(report, "away_team", None), "team_name", "Away")
        stage = getattr(fixture, "stage", None) if fixture else None
        round_name = getattr(fixture, "round", None) if fixture else None

        tctx = tournament_context or {}
        group_ctx = getattr(report, "group_context", None) or {}

        match_context = _classify_match_context(stage, round_name or tctx.get("round"))
        is_knockout = match_context not in {"Group Stage", "Unknown"} and "Group Stage" not in match_context

        home_raw = str(
            tctx.get("home_qualification_status")
            or (group_ctx.get("home") or {}).get("description")
            or "unknown"
        ).lower()
        away_raw = str(
            tctx.get("away_qualification_status")
            or (group_ctx.get("away") or {}).get("description")
            or "unknown"
        ).lower()

        if "must" in home_raw:
            home_raw = "must_win"
        elif "qualif" in home_raw:
            home_raw = "likely_qualified"
        elif "elimin" in home_raw:
            home_raw = "eliminated"

        if "must" in away_raw:
            away_raw = "must_win"
        elif "qualif" in away_raw:
            away_raw = "likely_qualified"
        elif "elimin" in away_raw:
            away_raw = "eliminated"

        home_rank = (group_ctx.get("home") or {}).get("rank") or tctx.get("home_rank")
        away_rank = (group_ctx.get("away") or {}).get("rank") or tctx.get("away_rank")
        home_pts = (group_ctx.get("home") or {}).get("points") or tctx.get("home_points")
        away_pts = (group_ctx.get("away") or {}).get("points") or tctx.get("away_points")
        home_gd = (group_ctx.get("home") or {}).get("goal_diff") or tctx.get("home_goal_difference")
        away_gd = (group_ctx.get("away") or {}).get("goal_diff") or tctx.get("away_goal_difference")

        home = _build_team_side(
            home_name,
            raw_status=home_raw if home_raw != "unknown" else None,
            rank=int(home_rank) if home_rank is not None else None,
            points=int(home_pts) if home_pts is not None else None,
            goal_diff=int(home_gd) if home_gd is not None else None,
            is_knockout=is_knockout,
        )
        away = _build_team_side(
            away_name,
            raw_status=away_raw if away_raw != "unknown" else None,
            rank=int(away_rank) if away_rank is not None else None,
            points=int(away_pts) if away_pts is not None else None,
            goal_diff=int(away_gd) if away_gd is not None else None,
            is_knockout=is_knockout,
        )

        comp_type, tour_name = _competition_meta(report)
        rotation = _rotation_risk(home.qualification_status, away.qualification_status, match_context)
        pressure = _pressure_score(match_context)

        try:
            from worldcup_predictor.integrations.api_sports_deep_data import API_SPORTS_DEEP_KEY

            deep = (getattr(report, "supplemental_sources", None) or {}).get(API_SPORTS_DEEP_KEY) or {}
            squad_intel = deep.get("squad_intelligence") or {}
            if squad_intel.get("available"):
                for side_key, side_obj in (("home", home), ("away", away)):
                    side_data = squad_intel.get(side_key) or {}
                    age = side_data.get("squad_age_profile") or {}
                    depth = side_data.get("bench_depth") or {}
                    if age.get("available"):
                        exp = float(age.get("experience_score") or 50)
                        pressure += (exp - 50) * 0.04
                    if depth.get("rotation_risk") == "High":
                        rotation = "High"
                    elif depth.get("rotation_risk") == "Medium" and rotation == "Low":
                        rotation = "Medium"
                pressure = round(_clamp(pressure, 0, 100), 1)
        except Exception:
            pass

        data_available = bool(
            group_ctx.get("available")
            or tctx
            or (stage and stage != "TBD")
            or comp_type == "tournament"
        )

        flags = _build_risk_flags(home, away, rotation, match_context, data_available)
        impact = _build_prediction_impact(home, away, match_context)

        parts = [f"{match_context} — {tour_name}."]
        if home.qualification_status != "unknown":
            parts.append(f"{home_name}: {home.qualification_status.replace('_', ' ')}.")
        if away.qualification_status != "unknown":
            parts.append(f"{away_name}: {away.qualification_status.replace('_', ' ')}.")
        parts.append(f"Rotation risk {rotation}, pressure {pressure:.0f}/100.")
        summary = " ".join(parts) + " Analysis only — not betting advice."

        return TournamentIntelligenceResult(
            match_context=match_context,
            competition_type=comp_type,
            tournament_name=tour_name,
            home=home,
            away=away,
            rotation_risk=rotation,  # type: ignore[arg-type]
            pressure_score=round(pressure, 1),
            risk_flags=flags,
            prediction_impact=impact,
            summary=summary,
            data_available=data_available,
        )
    except Exception:
        return _safe_fallback(report)

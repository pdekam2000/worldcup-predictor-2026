"""Tournament context intelligence — standings, form, qualification (Phase 22E)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.intelligence.sportmonks_standings_service import lookup_team_standings
from worldcup_predictor.tournament.tournament_intelligence_engine import (
    _classify_match_context,
    _map_qualification_status,
    _motivation_boost,
    _pressure_score,
    _rotation_risk,
    _scenario_scores,
)

SPORTMONKS_TOURNAMENT_STANDINGS_KEY = "sportmonks_tournament_standings"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _form_score(form: list[str] | str | None) -> float:
    if not form:
        return 50.0
    if isinstance(form, str):
        tokens = [c.upper() for c in form if c.upper() in {"W", "D", "L"}]
    else:
        tokens = [str(x).upper() for x in form if str(x).upper() in {"W", "D", "L"}]
    if not tokens:
        return 50.0
    pts = {"W": 3, "D": 1, "L": 0}
    return round(sum(pts.get(t, 1) for t in tokens) / len(tokens) * 33.3, 1)


def _resolve_team_row(
    team_name: str,
    *,
    standings_context: dict[str, Any] | None,
    sportmonks_standings: dict[str, Any] | None,
    side_ctx: dict[str, Any] | None,
    tctx: dict[str, Any] | None,
    side: str,
) -> dict[str, Any]:
    """Merge API-Football standings (primary) with Sportmonks supplement."""
    row: dict[str, Any] = {
        "team_name": team_name,
        "group_position": None,
        "points": None,
        "goal_difference": None,
        "form": "",
        "qualification_status": "unknown",
        "source": "none",
    }

    if side_ctx and isinstance(side_ctx, dict):
        row["group_position"] = side_ctx.get("rank") or side_ctx.get("group_position")
        row["points"] = side_ctx.get("points")
        row["goal_difference"] = side_ctx.get("goal_diff") or side_ctx.get("goal_difference")
        row["source"] = "group_context"

    if standings_context and standings_context.get("available"):
        for block in standings_context.get("groups") or []:
            if not isinstance(block, dict):
                continue
            standings_groups = block.get("standings") or []
            for group_rows in standings_groups:
                if not isinstance(group_rows, list):
                    continue
                for standing in group_rows:
                    if not isinstance(standing, dict):
                        continue
                    team_block = standing.get("team") or {}
                    name = str(team_block.get("name") or "")
                    if name.lower() != team_name.lower() and team_name.lower() not in name.lower():
                        continue
                    row["group_position"] = standing.get("rank") or standing.get("position")
                    row["points"] = standing.get("points")
                    row["goal_difference"] = standing.get("goalsDiff")
                    row["form"] = standing.get("form") or row.get("form")
                    row["source"] = "api_football_standings"
                    break

    sm = lookup_team_standings(sportmonks_standings or {}, team_name)
    if sm:
        if row["group_position"] is None:
            row["group_position"] = sm.get("group_position")
        if row["points"] is None:
            row["points"] = sm.get("points")
        if row["goal_difference"] is None:
            row["goal_difference"] = sm.get("goal_difference")
        if not row.get("form"):
            row["form"] = sm.get("form") or ""
        row["source"] = (
            "api_football+sportmonks" if row["source"] == "api_football_standings" else "sportmonks"
        )

    if tctx:
        status_key = f"{side}_qualification_status"
        raw_status = str(tctx.get(status_key) or "unknown")
        row["qualification_status"] = _map_qualification_status(raw_status)
        if row["group_position"] is None:
            row["group_position"] = tctx.get(f"{side}_rank")
        if row["points"] is None:
            row["points"] = tctx.get(f"{side}_points")
        if row["goal_difference"] is None:
            row["goal_difference"] = tctx.get(f"{side}_goal_difference")

    return row


def _qualification_status_from_row(row: dict[str, Any], *, is_knockout: bool) -> str:
    status = str(row.get("qualification_status") or "unknown")
    if status != "unknown":
        return status
    rank = row.get("group_position")
    points = row.get("points")
    gd = row.get("goal_difference")
    try:
        rank_i = int(rank) if rank is not None else None
    except (TypeError, ValueError):
        rank_i = None
    try:
        pts_i = int(points) if points is not None else None
    except (TypeError, ValueError):
        pts_i = None
    try:
        gd_i = int(gd) if gd is not None else None
    except (TypeError, ValueError):
        gd_i = None

    if is_knockout:
        return "must_win"
    if rank_i is not None and rank_i <= 2 and pts_i is not None and pts_i >= 4:
        return "already_qualified"
    if rank_i == 4 and pts_i is not None and pts_i <= 1:
        return "already_eliminated"
    if rank_i == 3 and pts_i is not None and pts_i >= 3:
        return "goal_difference_critical"
    if rank_i == 3:
        return "must_win"
    if gd_i is not None and rank_i == 3:
        return "goal_difference_critical"
    return "unknown"


def _importance_label(match_context: str, home_status: str, away_status: str) -> str:
    ctx = match_context.lower()
    if "final" in ctx or "semi" in ctx:
        return "critical"
    if "must_win" in {home_status, away_status}:
        return "high"
    if "goal_difference_critical" in {home_status, away_status}:
        return "high"
    if "matchday 3" in ctx:
        return "high"
    if "group stage" in ctx:
        return "medium"
    return "standard"


def _compare_with_motivation(
    *,
    motivation_home: float,
    motivation_away: float,
    context_home: float,
    context_away: float,
    must_win_flag: bool,
    mot_must_win: bool,
) -> dict[str, Any]:
    diffs = [
        abs(motivation_home - context_home),
        abs(motivation_away - context_away),
    ]
    avg_diff = sum(diffs) / len(diffs)
    disagreement = round(_clamp(avg_diff / 25.0, 0, 1), 3)
    agreement = round((1.0 - disagreement) * 100.0, 1)
    supports = disagreement < 0.35 and (must_win_flag == mot_must_win or not must_win_flag)
    return {
        "agreement_score": agreement,
        "disagreement_score": disagreement,
        "context_supports_internal": supports,
        "available": True,
    }


@dataclass
class TournamentContextIntelligenceResult:
    group_position_home: int | None = None
    group_position_away: int | None = None
    points_home: int | None = None
    points_away: int | None = None
    goal_difference_home: int | None = None
    goal_difference_away: int | None = None
    qualification_status_home: str = "unknown"
    qualification_status_away: str = "unknown"
    qualification_probability_home: float = 50.0
    qualification_probability_away: float = 50.0
    elimination_risk_home: float = 50.0
    elimination_risk_away: float = 50.0
    must_win_flag: bool = False
    pressure_rating: float = 35.0
    motivation_score_home: float = 50.0
    motivation_score_away: float = 50.0
    recent_form_score_home: float = 50.0
    recent_form_score_away: float = 50.0
    tournament_importance: str = "standard"
    rotation_risk: str = "Medium"
    group_context_strength: float = 0.0
    expected_conservatism: str = "balanced"
    expected_aggression: str = "balanced"
    draw_acceptability: bool = False
    likely_rotation_behavior: str = "standard_rotation"
    agreement_score: float = 50.0
    disagreement_score: float = 0.0
    context_supports_internal: bool = False
    match_context: str = "Unknown"
    data_sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    version: str = "22e"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_tournament_context_intelligence(
    report: MatchIntelligenceReport,
    *,
    tournament_context: dict[str, Any] | None = None,
    sportmonks_standings: dict[str, Any] | None = None,
    specialist_signals: dict[str, Any] | None = None,
) -> TournamentContextIntelligenceResult:
    """Build tournament context benchmark — trace only, no WDE changes."""
    specialist_signals = specialist_signals or {}
    home_name = report.home_team.team_name
    away_name = report.away_team.team_name
    fixture = report.fixture
    stage = getattr(fixture, "stage", None) if fixture else None
    round_name = getattr(fixture, "round", None) if fixture else None
    tctx = tournament_context or {}

    match_context = _classify_match_context(stage, round_name or tctx.get("round"))
    is_knockout = "Group Stage" not in match_context and match_context not in {"Unknown", "Group Stage"}

    group_ctx = getattr(report, "group_context", None) or {}
    standings_context = report.standings_context

    home_row = _resolve_team_row(
        home_name,
        standings_context=standings_context,
        sportmonks_standings=sportmonks_standings,
        side_ctx=group_ctx.get("home") if isinstance(group_ctx, dict) else None,
        tctx=tctx,
        side="home",
    )
    away_row = _resolve_team_row(
        away_name,
        standings_context=standings_context,
        sportmonks_standings=sportmonks_standings,
        side_ctx=group_ctx.get("away") if isinstance(group_ctx, dict) else None,
        tctx=tctx,
        side="away",
    )

    home_status = _qualification_status_from_row(home_row, is_knockout=is_knockout)
    away_status = _qualification_status_from_row(away_row, is_knockout=is_knockout)

    def _int_or_none(val: Any) -> int | None:
        try:
            return int(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    home_rank = _int_or_none(home_row.get("group_position"))
    away_rank = _int_or_none(away_row.get("group_position"))
    home_pts = _int_or_none(home_row.get("points"))
    away_pts = _int_or_none(away_row.get("points"))
    home_gd = _int_or_none(home_row.get("goal_difference"))
    away_gd = _int_or_none(away_row.get("goal_difference"))

    home_qual, home_elim = _scenario_scores(home_status, home_rank, home_pts, is_knockout=is_knockout)
    away_qual, away_elim = _scenario_scores(away_status, away_rank, away_pts, is_knockout=is_knockout)

    home_form_list = report.home_team.form
    away_form_list = report.away_team.form
    if not home_form_list and home_row.get("form"):
        home_form_list = list(str(home_row["form"]))
    if not away_form_list and away_row.get("form"):
        away_form_list = list(str(away_row["form"]))

    form_home = _form_score(home_form_list)
    form_away = _form_score(away_form_list)

    team_form_sig = specialist_signals.get("team_form_agent")
    if team_form_sig is not None and getattr(team_form_sig, "is_usable", False):
        block = team_form_sig.signals if hasattr(team_form_sig, "signals") else team_form_sig
        form_home = float(block.get("form_score_home") or form_home)
        form_away = float(block.get("form_score_away") or form_away)

    pressure = _pressure_score(match_context)
    rotation = _rotation_risk(home_status, away_status, match_context)
    importance = _importance_label(match_context, home_status, away_status)

    mot_home = 50.0 + _motivation_boost(home_status, is_knockout=is_knockout) * 3
    mot_away = 50.0 + _motivation_boost(away_status, is_knockout=is_knockout) * 3
    mot_home = _clamp(mot_home + (form_home - 50) * 0.15, 0, 100)
    mot_away = _clamp(mot_away + (form_away - 50) * 0.15, 0, 100)

    must_win = home_status == "must_win" or away_status == "must_win"
    draw_ok = home_status == "draw_acceptable" or away_status == "draw_acceptable" or (
        home_status == "already_qualified" and away_status == "already_qualified"
    )

    if draw_ok or (home_status == "already_qualified" or away_status == "already_qualified"):
        conservatism = "high"
    elif must_win:
        conservatism = "low"
    else:
        conservatism = "balanced"

    if must_win or is_knockout:
        aggression = "high"
    elif home_status == "already_eliminated" and away_status == "already_eliminated":
        aggression = "low"
    else:
        aggression = "medium"

    rotation_behavior = "heavy_rotation" if rotation == "High" else (
        "minimal_rotation" if rotation == "Low" else "standard_rotation"
    )

    sources: list[str] = []
    if standings_context and standings_context.get("available"):
        sources.append("api_football_standings")
    if sportmonks_standings and sportmonks_standings.get("available"):
        sources.append("sportmonks_standings")
    if tctx:
        sources.append("schedule_context")
    if report.home_team.statistics or report.away_team.statistics:
        sources.append("team_season_statistics")
    if home_form_list or away_form_list:
        sources.append("recent_form")

    strength = round(min(100.0, len(sources) * 18.0 + (10 if group_ctx.get("available") else 0)), 1)

    comparison = {"agreement_score": 50.0, "disagreement_score": 0.0, "context_supports_internal": False, "available": False}
    mot_sig = specialist_signals.get("motivation_psychology_agent")
    if mot_sig is not None and getattr(mot_sig, "is_usable", True):
        block = mot_sig.signals if hasattr(mot_sig, "signals") else mot_sig
        mot_h = float(block.get("motivation_score_home") or 50)
        mot_a = float(block.get("motivation_score_away") or 50)
        mot_must = (
            str(block.get("home_qualification_status") or "") == "must_win"
            or str(block.get("away_qualification_status") or "") == "must_win"
        )
        comparison = _compare_with_motivation(
            motivation_home=mot_h,
            motivation_away=mot_a,
            context_home=mot_home,
            context_away=mot_away,
            must_win_flag=must_win,
            mot_must_win=mot_must,
        )

    notes: list[str] = []
    if not sources:
        notes.append("Limited tournament context — standings/form unavailable.")
    if sportmonks_standings and sportmonks_standings.get("available"):
        notes.append("Sportmonks standings used as supplemental group table.")
    if must_win:
        notes.append("Must-win tournament context detected — trace only.")
    if comparison.get("available") and not comparison.get("context_supports_internal"):
        notes.append("Tournament context diverges from motivation agent — review benchmark.")

    return TournamentContextIntelligenceResult(
        group_position_home=home_rank,
        group_position_away=away_rank,
        points_home=home_pts,
        points_away=away_pts,
        goal_difference_home=home_gd,
        goal_difference_away=away_gd,
        qualification_status_home=home_status,
        qualification_status_away=away_status,
        qualification_probability_home=home_qual,
        qualification_probability_away=away_qual,
        elimination_risk_home=home_elim,
        elimination_risk_away=away_elim,
        must_win_flag=must_win,
        pressure_rating=round(pressure, 1),
        motivation_score_home=round(mot_home, 1),
        motivation_score_away=round(mot_away, 1),
        recent_form_score_home=round(form_home, 1),
        recent_form_score_away=round(form_away, 1),
        tournament_importance=importance,
        rotation_risk=rotation,
        group_context_strength=strength,
        expected_conservatism=conservatism,
        expected_aggression=aggression,
        draw_acceptability=draw_ok,
        likely_rotation_behavior=rotation_behavior,
        agreement_score=comparison.get("agreement_score", 50.0),
        disagreement_score=comparison.get("disagreement_score", 0.0),
        context_supports_internal=bool(comparison.get("context_supports_internal")),
        match_context=match_context,
        data_sources=sources,
        notes=notes,
    )

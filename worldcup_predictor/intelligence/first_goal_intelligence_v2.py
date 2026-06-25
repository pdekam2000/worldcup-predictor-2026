"""First Goal Intelligence V2 — additive informational module (no 1X2/O-U impact)."""

from __future__ import annotations

import json
from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.intelligence.first_goal_models import (
    FirstGoalIntelligenceV2Result,
    FirstGoalScorerCandidateV2,
    FirstGoalTeamSide,
    MinuteBand,
)
from worldcup_predictor.prediction.scorer_candidates import build_first_goal_scorer_candidates

_MINUTE_BANDS: tuple[MinuteBand, ...] = (
    "0-15",
    "16-30",
    "31-45",
    "46-60",
    "61-75",
    "76-90",
    "no_goal",
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _team_side(team_name: str, home: str, away: str) -> FirstGoalTeamSide:
    if not team_name or team_name.lower() in {"unknown", "tbd"}:
        return "unknown"
    if team_name.lower() == home.lower():
        return "home"
    if team_name.lower() == away.lower():
        return "away"
    return "unknown"


def _form_points(form: list[str] | None) -> float:
    if not form:
        return 3.0
    points = {"W": 3, "D": 1, "L": 0}
    return float(sum(points.get(str(r).upper(), 1) for r in form))


def _attack_score(report: MatchIntelligenceReport, side: str) -> float:
    home_fp = _form_points(report.home_team.form)
    away_fp = _form_points(report.away_team.form)
    base = home_fp if side == "home" else away_fp
    score = 40.0 + base * 6.0
    if side == "home" and home_fp > away_fp:
        score += 8
    elif side == "away" and away_fp > home_fp:
        score += 8
    stats = report.home_team.statistics if side == "home" else report.away_team.statistics
    if isinstance(stats, dict):
        goals = stats.get("goals") or {}
        if isinstance(goals, dict):
            for_block = goals.get("for") or {}
            if isinstance(for_block, dict):
                total = for_block.get("total")
                if isinstance(total, dict):
                    total = total.get("total") or total.get("all")
                if total is not None:
                    try:
                        score += _clamp(float(total) / 10.0, 0, 1) * 15
                    except (TypeError, ValueError):
                        pass
    return round(_clamp(score, 0, 100), 1)


def _has_xg_data(report: MatchIntelligenceReport) -> bool:
    try:
        from worldcup_predictor.chance_quality.stat_extraction import extract_real_xg, extract_team_shooting_profile

        for side in ("home", "away"):
            profile = extract_team_shooting_profile(report, side=side)
            val, _ = extract_real_xg(report, side=side, team_stats=profile)
            if val is not None:
                return True
    except Exception as exc:
        from worldcup_predictor.providers.safe_enrichment_logger import log_enrichment_failure

        log_enrichment_failure(
            "worldcup_predictor.intelligence.first_goal_intelligence_v2",
            exc,
            fixture_id=getattr(report, "fixture_id", None),
            layer="xg_probe",
        )
    return False


def _expected_total_goals(report: MatchIntelligenceReport, prediction: MatchPrediction | None) -> float:
    if prediction and prediction.scoreline:
        return max(0.0, prediction.scoreline.home_goals + prediction.scoreline.away_goals)
    home_g = _attack_score(report, "home")
    away_g = _attack_score(report, "away")
    return round((home_g + away_g) / 50.0 * 1.2, 2)


def _pick_minute_band(total_goals: float, *, no_goal_likely: bool) -> MinuteBand:
    if no_goal_likely or total_goals < 0.85:
        return "no_goal"
    if total_goals >= 3.2:
        return "0-15" if total_goals >= 3.8 else "16-30"
    if total_goals >= 2.6:
        return "16-30"
    if total_goals >= 2.0:
        return "31-45"
    if total_goals >= 1.4:
        return "46-60"
    return "61-75"


def _resolve_team_lean(
    report: MatchIntelligenceReport,
    prediction: MatchPrediction | None,
) -> tuple[FirstGoalTeamSide, str, list[str]]:
    home = report.home_team.team_name
    away = report.away_team.team_name
    reasoning: list[str] = []
    home_score = _attack_score(report, "home")
    away_score = _attack_score(report, "away")
    total_goals = _expected_total_goals(report, prediction)

    if total_goals < 0.85:
        reasoning.append("Low expected goals lean toward no first goal (0-0 or delayed scoring).")
        return "no_goal", "No goal expected", reasoning

    baseline_team = None
    if prediction and prediction.first_goal and prediction.first_goal.team:
        baseline_team = prediction.first_goal.team
        side = _team_side(baseline_team, home, away)
        if side != "unknown":
            reasoning.append(f"Baseline scoring engine lean: {baseline_team}.")
            return side, baseline_team, reasoning

    if abs(home_score - away_score) < 4:
        reasoning.append("Balanced attacking profiles — slight home lean on tie-break.")
        return "home", home, reasoning
    if home_score >= away_score:
        reasoning.append(f"Home attack index {home_score:.0f} vs away {away_score:.0f}.")
        return "home", home, reasoning
    reasoning.append(f"Away attack index {away_score:.0f} vs home {home_score:.0f}.")
    return "away", away, reasoning


def build_first_goal_intelligence_v2(
    report: MatchIntelligenceReport,
    *,
    prediction: MatchPrediction | None = None,
    specialist_report: MatchSpecialistReport | None = None,
) -> FirstGoalIntelligenceV2Result:
    """Build first-goal intelligence from real data only — never invents player names."""
    home = report.home_team.team_name
    away = report.away_team.team_name
    lineups = bool(report.lineups and (report.lineups.get("items") or []))
    injuries_missing = "injuries" in (report.missing_data or [])
    odds_ok = bool(report.odds and report.odds.available)
    xg_ok = _has_xg_data(report)

    team_side, team_display, reasoning = _resolve_team_lean(report, prediction)
    total_goals = _expected_total_goals(report, prediction)
    no_goal_likely = team_side == "no_goal"
    minute_band = _pick_minute_band(total_goals, no_goal_likely=no_goal_likely)

    fg_team_name = team_display if team_side in {"home", "away"} else home
    if team_side == "away":
        fg_team_name = away
    elif team_side == "no_goal":
        fg_team_name = home if _attack_score(report, "home") >= _attack_score(report, "away") else away

    candidates_raw, player_ok, player_msg = build_first_goal_scorer_candidates(
        report,
        fg_team_name,
        specialist_report=specialist_report or report.specialist_report,
    )
    scorers = [
        FirstGoalScorerCandidateV2(
            player=c.player,
            team=c.team,
            score=c.score,
            reason=c.reason,
            data_source=c.data_source,
            position=c.position or "",
        )
        for c in candidates_raw
    ]

    risk_flags: list[str] = []
    if not lineups:
        risk_flags.append("Official lineups not confirmed")
    if injuries_missing:
        risk_flags.append("Injury data incomplete")
    if not player_ok:
        risk_flags.append("Player scorer data unavailable")
    if not odds_ok:
        risk_flags.append("Bookmaker goal markets unavailable")
    if report.is_placeholder:
        risk_flags.append("Placeholder/demo fixture data")

    confidence = 35.0
    if lineups:
        confidence += 18
    if player_ok and scorers:
        confidence += 22
    if odds_ok:
        confidence += 10
    if xg_ok:
        confidence += 12
    if prediction:
        confidence += 8
    confidence = _clamp(confidence, 15, 92)
    if not player_ok:
        confidence = min(confidence, 45)

    data_availability = {
        "lineups": lineups,
        "player_stats": player_ok,
        "odds_markets": odds_ok,
        "xg_data": xg_ok,
        "injuries": not injuries_missing,
    }
    deep = (getattr(report, "supplemental_sources", None) or {}).get("api_sports_deep") or {}
    if deep.get("top_scorers"):
        data_availability["top_scorers"] = True
        reasoning.append("Tournament top-scorer data available from API-Sports.")
    if deep.get("fixture_players"):
        data_availability["fixture_players"] = True
        reasoning.append("Fixture player statistics available from API-Sports.")
    fp_rows = deep.get("fixture_players") or []
    if any(isinstance(r, dict) and r.get("player_rating") is not None for r in fp_rows):
        data_availability["player_ratings"] = True
    if any(isinstance(r, dict) and int(r.get("assists") or 0) > 0 for r in (deep.get("top_scorers") or []) + fp_rows):
        data_availability["assists"] = True
    if any(isinstance(r, dict) and int(r.get("key_passes") or 0) > 0 for r in fp_rows):
        data_availability["key_passes"] = True
    if deep.get("squad_intelligence", {}).get("available"):
        data_availability["bench_depth"] = True
        data_availability["squad_age"] = True
    data_available = any(data_availability.values())

    reasoning.append(f"Expected total goals ~{total_goals:.1f} → minute band {minute_band}.")
    if scorers:
        reasoning.append(f"Top scorer candidate: {scorers[0].player} ({scorers[0].data_source}).")
    elif player_msg:
        reasoning.append(player_msg)

    summary = (
        f"First goal lean: {team_display} · band {minute_band} · "
        f"confidence {confidence:.0f}/100"
    )
    if not player_ok:
        summary = (
            "Player-level scorer data unavailable; team/minute estimate only. "
            f"Lean: {team_display} · band {minute_band} · confidence {confidence:.0f}/100."
        )

    return FirstGoalIntelligenceV2Result(
        fixture_id=report.fixture_id,
        first_goal_team=team_side,
        first_goal_team_display=team_display,
        likely_first_goal_scorers=scorers,
        first_goal_minute_band=minute_band,
        confidence=confidence,
        risk_flags=risk_flags,
        reasoning=reasoning,
        data_availability=data_availability,
        data_available=data_available,
        player_data_unavailable=not player_ok,
        player_data_message=player_msg if not player_ok else None,
        summary=summary,
    )


def load_first_goal_v2_from_prediction(prediction: MatchPrediction) -> FirstGoalIntelligenceV2Result | None:
    raw = (prediction.metadata or {}).get("first_goal_intelligence_v2")
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        raw_scorers = data.get("likely_first_goal_scorers") or data.get("likely_scorers") or []
        scorers: list[FirstGoalScorerCandidateV2] = []
        for row in raw_scorers:
            if not isinstance(row, dict):
                continue
            player = row.get("player") or row.get("player_name") or ""
            scorers.append(
                FirstGoalScorerCandidateV2(
                    player=str(player),
                    team=str(row.get("team") or ""),
                    score=float(row.get("score") or row.get("confidence") or 0),
                    reason=str(row.get("reason") or ""),
                    data_source=str(row.get("data_source") or "stored"),
                    position=str(row.get("position") or ""),
                )
            )
        return FirstGoalIntelligenceV2Result(
            fixture_id=int(data.get("fixture_id") or prediction.fixture_id),
            first_goal_team=data.get("first_goal_team") or "unknown",
            first_goal_team_display=str(data.get("first_goal_team_display") or "Unknown"),
            likely_first_goal_scorers=scorers,
            first_goal_minute_band=data.get("first_goal_minute_band") or "31-45",
            confidence=float(data.get("confidence") or 0),
            risk_flags=list(data.get("risk_flags") or []),
            reasoning=list(data.get("reasoning") or []),
            data_availability=dict(data.get("data_availability") or {}),
            data_available=bool(data.get("data_available", any((data.get("data_availability") or {}).values()))),
            player_data_unavailable=bool(data.get("player_data_unavailable")),
            player_data_message=data.get("player_data_message"),
            summary=str(data.get("summary") or ""),
            disclaimer=str(data.get("disclaimer") or FirstGoalIntelligenceV2Result.disclaimer),
        )
    except Exception:
        return None


def attach_first_goal_v2_to_prediction(
    prediction: MatchPrediction,
    report: MatchIntelligenceReport | None,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> FirstGoalIntelligenceV2Result | None:
    if report is None:
        return None
    try:
        result = build_first_goal_intelligence_v2(
            report,
            prediction=prediction,
            specialist_report=specialist_report,
        )
        prediction.metadata = dict(prediction.metadata or {})
        prediction.metadata["first_goal_intelligence_v2"] = json.dumps(result.to_dict(), ensure_ascii=False)
        return result
    except Exception:
        return None

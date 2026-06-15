"""Structured prediction explanations."""

from __future__ import annotations

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction, MultilingualText


def build_prediction_explanation(
    prediction: MatchPrediction,
    report: MatchIntelligenceReport,
) -> MultilingualText:
    lines: list[str] = []

    x2 = prediction.one_x_two.selection
    if x2 == "home_win":
        lines.append(f"Home team ({report.home_team.team_name}) favored on form, H2H, and strength signals.")
    elif x2 == "away_win":
        lines.append(f"Away team ({report.away_team.team_name}) favored on comparative signals.")
    else:
        lines.append("Draw lean — balanced strength with limited separation.")

    ou = prediction.over_under.selection
    if ou == "over_2_5":
        lines.append("Over 2.5 lean from expected goals and attacking indicators.")
    else:
        lines.append("Under 2.5 lean from conservative goal expectation.")

    if prediction.scoreline:
        lines.append(f"Primary scoreline: {prediction.scoreline.label}.")
    if prediction.scoreline_candidates:
        cand_text = ", ".join(
            f"{c.label} ({c.probability:.0%})" for c in prediction.scoreline_candidates[:3]
        )
        lines.append(f"Top scorelines: {cand_text}.")

    if report.missing_data:
        lines.append("Missing data: " + ", ".join(report.missing_data[:8]) + ".")

    if prediction.no_bet_flag:
        lines.append("Confidence capped — watch-only until critical inputs improve.")

    if prediction.consistency_notes:
        lines.append(prediction.consistency_notes[0])

    if report.group_context and report.group_context.get("available"):
        gh = report.group_context.get("home") or {}
        ga = report.group_context.get("away") or {}
        if gh.get("group") or ga.get("group"):
            lines.append(
                f"Group context: {report.home_team.team_name} "
                f"({gh.get('group', '—')} P{gh.get('points', '—')}) vs "
                f"{report.away_team.team_name} ({ga.get('group', '—')} P{ga.get('points', '—')})."
            )

    text = " ".join(lines)
    return MultilingualText.uniform(text)

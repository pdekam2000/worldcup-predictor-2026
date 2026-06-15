"""Harmonize 1X2, O/U, scoreline, halftime, and first-goal outputs."""

from __future__ import annotations

from dataclasses import replace

from worldcup_predictor.domain.prediction import (
    FirstGoalPrediction,
    HalftimePrediction,
    MatchPrediction,
    OverUnderSelection,
    OneXTwoSelection,
    ScorelinePrediction,
)


def _result_from_scoreline(home: int, away: int) -> OneXTwoSelection:
    if home > away:
        return "home_win"
    if home < away:
        return "away_win"
    return "draw"


def _ou_from_total(total: int) -> OverUnderSelection:
    return "over_2_5" if total > 2 else "under_2_5"


def harmonize_prediction(
    prediction: MatchPrediction,
    *,
    home_team: str,
    away_team: str,
) -> MatchPrediction:
    notes: list[str] = []
    home = round(prediction.scoreline.home_goals) if prediction.scoreline else 1
    away = round(prediction.scoreline.away_goals) if prediction.scoreline else 1
    home = max(0, min(home, 9))
    away = max(0, min(away, 9))
    total = home + away

    implied_1x2 = _result_from_scoreline(home, away)
    implied_ou = _ou_from_total(total)

    if prediction.one_x_two.selection != implied_1x2:
        notes.append(
            f"Adjusted 1X2 from {prediction.one_x_two.selection} to {implied_1x2} "
            f"to match scoreline {home}-{away}."
        )
    if prediction.over_under.selection != implied_ou:
        notes.append(
            f"Adjusted O/U from {prediction.over_under.selection} to {implied_ou} "
            f"for scoreline total {total}."
        )

    if implied_1x2 == "home_win":
        fg_team = home_team
    elif implied_1x2 == "away_win":
        fg_team = away_team
    else:
        fg_team = home_team if home >= away else away_team

    if prediction.first_goal.team not in (home_team, away_team):
        notes.append(f"Adjusted first-goal team to {fg_team}.")
    elif prediction.first_goal.team != fg_team and total > 0:
        notes.append(f"Aligned first-goal team with scoreline lean: {fg_team}.")

    ht_total = prediction.halftime.estimated_total_goals
    max_ht = max(0.5, total * 0.55)
    ht_note = prediction.halftime.note
    if ht_total > max_ht:
        notes.append(f"Reduced halftime estimate from {ht_total:.2f} to {max_ht:.2f} (≤ full-time total).")
        ht_total = round(max_ht, 2)
        if ht_note:
            ht_note = replace(
                ht_note,
                en=f"Estimated first-half total goals: {ht_total:.2f} (not guaranteed)",
                de=f"Estimated first-half total goals: {ht_total:.2f} (not guaranteed)",
                fa=f"Estimated first-half total goals: {ht_total:.2f} (not guaranteed)",
            )

    if not notes:
        notes.append("All markets consistent with primary scoreline.")

    return replace(
        prediction,
        scoreline=ScorelinePrediction(home_goals=float(home), away_goals=float(away)),
        one_x_two=replace(
            prediction.one_x_two,
            selection=implied_1x2,
        ),
        over_under=replace(
            prediction.over_under,
            selection=implied_ou,
        ),
        halftime=replace(
            prediction.halftime,
            estimated_total_goals=ht_total,
            note=ht_note,
        ),
        first_goal=replace(
            prediction.first_goal,
            team=fg_team,
        ),
        consistency_notes=notes,
        metadata={
            **prediction.metadata,
            "consistency_checked": "true",
            "consistency_fixes": str(len([n for n in notes if n.startswith("Adjusted")])),
        },
    )


def is_consistent(prediction: MatchPrediction) -> bool:
    if prediction.scoreline is None:
        return False
    home = round(prediction.scoreline.home_goals)
    away = round(prediction.scoreline.away_goals)
    total = home + away
    return (
        prediction.one_x_two.selection == _result_from_scoreline(home, away)
        and prediction.over_under.selection == _ou_from_total(total)
    )

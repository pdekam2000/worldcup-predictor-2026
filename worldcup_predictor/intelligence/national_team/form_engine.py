"""National team form engine — international match weighting (Phase 32B)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from worldcup_predictor.intelligence.national_team._shared import (
    clamp,
    competition_weight,
    goals_from_fixture,
    match_recency_index,
    parse_kickoff,
    safe_list,
    team_side_in_fixture,
    venue_bucket,
)


@dataclass
class TeamFormMetrics:
    team_id: int | None
    team_name: str
    matches_used: int = 0
    last5: dict[str, Any] = field(default_factory=dict)
    last10: dict[str, Any] = field(default_factory=dict)
    home: dict[str, Any] = field(default_factory=dict)
    away: dict[str, Any] = field(default_factory=dict)
    neutral: dict[str, Any] = field(default_factory=dict)
    explanation: list[str] = field(default_factory=list)


def _aggregate_window(
    fixtures: list[dict[str, Any]],
    team_id: int,
    *,
    window: int | None = None,
    venue_filter: str | None = None,
) -> dict[str, Any]:
    rows = fixtures[:window] if window else fixtures
    scored = conceded = wins = clean = btts = over25 = 0.0
    weight_sum = 0.0
    used = 0
    for idx, item in enumerate(rows):
        if venue_filter and venue_bucket(item, team_id) != venue_filter:
            continue
        side = team_side_in_fixture(item, team_id)
        if side is None:
            continue
        home_g, away_g = goals_from_fixture(item)
        if home_g is None or away_g is None:
            continue
        gf = home_g if side == "home" else away_g
        ga = away_g if side == "home" else home_g
        league = item.get("league") or {}
        comp_w = competition_weight(league)
        recency_w = match_recency_index(idx, len(rows))
        w = comp_w * recency_w
        weight_sum += w
        used += 1
        scored += gf * w
        conceded += ga * w
        if gf > ga:
            wins += w
        if ga == 0:
            clean += w
        if gf > 0 and ga > 0:
            btts += w
        if gf + ga > 2:
            over25 += w
    if weight_sum <= 0:
        return {
            "matches": 0,
            "goals_scored_avg": None,
            "goals_conceded_avg": None,
            "win_pct": None,
            "clean_sheet_pct": None,
            "btts_pct": None,
            "over_2_5_pct": None,
        }
    return {
        "matches": used,
        "goals_scored_avg": round(scored / weight_sum, 2),
        "goals_conceded_avg": round(conceded / weight_sum, 2),
        "win_pct": round(wins / weight_sum * 100, 1),
        "clean_sheet_pct": round(clean / weight_sum * 100, 1),
        "btts_pct": round(btts / weight_sum * 100, 1),
        "over_2_5_pct": round(over25 / weight_sum * 100, 1),
    }


def _score_from_metrics(metrics: dict[str, Any]) -> float:
    if not metrics.get("matches"):
        return 50.0
    win_pct = float(metrics.get("win_pct") or 50)
    gf = float(metrics.get("goals_scored_avg") or 1.2)
    ga = float(metrics.get("goals_conceded_avg") or 1.2)
    attack = clamp(gf / 2.0 * 35, 0, 35)
    defense = clamp((2.2 - ga) / 2.2 * 25, 0, 25)
    form = clamp(win_pct * 0.4, 0, 40)
    return round(clamp(attack + defense + form, 20, 95), 1)


def build_team_form_metrics(
    *,
    team_id: int | None,
    team_name: str,
    recent_fixtures: list[dict[str, Any]] | None,
) -> TeamFormMetrics:
    fixtures = safe_list(recent_fixtures)
    if team_id is None or not fixtures:
        return TeamFormMetrics(
            team_id=team_id,
            team_name=team_name,
            explanation=["Insufficient recent international fixtures — neutral form assumed."],
        )

    last5 = _aggregate_window(fixtures, team_id, window=5)
    last10 = _aggregate_window(fixtures, team_id, window=10)
    home = _aggregate_window(fixtures, team_id, window=10, venue_filter="home")
    away = _aggregate_window(fixtures, team_id, window=10, venue_filter="away")
    neutral = _aggregate_window(fixtures, team_id, window=10, venue_filter="neutral")

    notes: list[str] = []
    if last10.get("matches"):
        notes.append(
            f"Last {last10['matches']} weighted matches: win {last10.get('win_pct')}%, "
            f"GF {last10.get('goals_scored_avg')} GA {last10.get('goals_conceded_avg')}."
        )
    else:
        notes.append("No completed recent fixtures parsed.")

    return TeamFormMetrics(
        team_id=team_id,
        team_name=team_name,
        matches_used=int(last10.get("matches") or 0),
        last5=last5,
        last10=last10,
        home=home,
        away=away,
        neutral=neutral,
        explanation=notes,
    )


def national_form_score(
    *,
    home_metrics: TeamFormMetrics,
    away_metrics: TeamFormMetrics,
) -> tuple[float, dict[str, Any]]:
    home_score = _score_from_metrics(home_metrics.last10)
    away_score = _score_from_metrics(away_metrics.last10)
    combined = (home_score + away_score) / 2
    delta = home_score - away_score
    # Confidence-oriented score: stronger side differentiation lifts confidence modestly
    score = clamp(50 + abs(delta) * 0.35 + (combined - 50) * 0.55, 25, 92)
    if home_metrics.matches_used == 0 and away_metrics.matches_used == 0:
        score = 50.0
    detail = {
        "home_form_score": home_score,
        "away_form_score": away_score,
        "combined_form_score": round(combined, 1),
        "form_differential": round(delta, 1),
        "home": asdict(home_metrics),
        "away": asdict(away_metrics),
        "explanation": home_metrics.explanation + away_metrics.explanation,
    }
    return round(score, 1), detail

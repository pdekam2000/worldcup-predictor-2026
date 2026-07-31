"""Uncovered Top-N mass after Exact3 + Main Coverage (read-only vs ECSE matrix)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.insurance.schemas import (
    UncoveredMassReport,
    UncoveredScore,
)
from worldcup_predictor.research.bet_coverage_optimizer.models import CoverageRecommendation, ScoreEntry
from worldcup_predictor.research.exact_score_coverage_advisor.score_features import score_features


def _parse_score(score: str) -> tuple[int, int] | None:
    parts = str(score).replace(" ", "").split("-")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def primary_covered_score_set(rec: CoverageRecommendation) -> set[str]:
    covered: set[str] = {e.score for e in rec.selected_exact_scores}
    if rec.selected_coverage_market is not None:
        covered.update(str(s) for s in (rec.selected_coverage_market.covered_scores or []))
    return covered


def compute_uncovered_mass(rec: CoverageRecommendation) -> UncoveredMassReport:
    """
    Derive uncovered Top-N outcomes vs Exact1–3 + Main Coverage.
    Uses recommendation top_n_scores_list probabilities (ECSE/consensus matrix already built).
    Does not alter the matrix.
    """
    top_entries: list[ScoreEntry] = list(rec.top_n_scores_list)
    top_map = {s.score: float(s.probability or 0.0) for s in top_entries}
    top_n_mass = round(sum(top_map.values()), 8)
    exacts = [e.score for e in rec.selected_exact_scores]
    cov_scores = list((rec.selected_coverage_market.covered_scores if rec.selected_coverage_market else []) or [])
    cov_key = rec.selected_coverage_market.market_key if rec.selected_coverage_market else None
    primary = primary_covered_score_set(rec)
    covered_mass = round(sum(top_map[s] for s in primary if s in top_map), 8)
    uncovered_rows: list[UncoveredScore] = []
    for s in top_entries:
        if s.score in primary:
            continue
        uncovered_rows.append(UncoveredScore(score=s.score, probability=float(s.probability or 0.0)))
    uncovered_mass = round(sum(u.probability for u in uncovered_rows), 8)
    ratio = round(covered_mass / top_n_mass, 8) if top_n_mass > 0 else 0.0

    direction = {"home_win": 0.0, "draw": 0.0, "away_win": 0.0}
    profiles = {
        "btts_yes": 0.0,
        "btts_no": 0.0,
        "over_2_5": 0.0,
        "under_2_5": 0.0,
        "over_3_5": 0.0,
        "under_3_5": 0.0,
        "clean_sheet_home": 0.0,
        "clean_sheet_away": 0.0,
        "winning_margin_1": 0.0,
        "winning_margin_2": 0.0,
        "winning_margin_3_plus": 0.0,
        "home_goals_ge_2": 0.0,
        "away_goals_ge_2": 0.0,
    }
    for u in uncovered_rows:
        feats = score_features(u.score)
        if not feats:
            continue
        p = float(u.probability)
        if feats["result"] == "HOME":
            direction["home_win"] += p
        elif feats["result"] == "DRAW":
            direction["draw"] += p
        else:
            direction["away_win"] += p
        if feats["btts"]:
            profiles["btts_yes"] += p
        else:
            profiles["btts_no"] += p
        if feats["over_2_5"]:
            profiles["over_2_5"] += p
        else:
            profiles["under_2_5"] += p
        if feats["over_3_5"]:
            profiles["over_3_5"] += p
        else:
            profiles["under_3_5"] += p
        if feats["away_goals"] == 0:
            profiles["clean_sheet_home"] += p
        if feats["home_goals"] == 0:
            profiles["clean_sheet_away"] += p
        gd = int(feats["abs_goal_difference"])
        if feats["result"] != "DRAW":
            if gd == 1:
                profiles["winning_margin_1"] += p
            elif gd == 2:
                profiles["winning_margin_2"] += p
            elif gd >= 3:
                profiles["winning_margin_3_plus"] += p
        if feats["home_goals"] >= 2:
            profiles["home_goals_ge_2"] += p
        if feats["away_goals"] >= 2:
            profiles["away_goals_ge_2"] += p

    direction = {k: round(v, 8) for k, v in direction.items()}
    profiles = {k: round(v, 8) for k, v in profiles.items()}

    return UncoveredMassReport(
        fixture_id=int(rec.fixture_id),
        top_n=int(rec.top_n),
        top_n_scores=[s.score for s in top_entries],
        top_n_probability_mass=top_n_mass,
        primary_exact_scores=exacts,
        primary_coverage_market_key=cov_key,
        primary_coverage_scores=cov_scores,
        primary_covered_scores=sorted(primary),
        primary_covered_probability_mass=covered_mass,
        primary_uncovered_scores=uncovered_rows,
        primary_uncovered_probability_mass=uncovered_mass,
        primary_coverage_ratio=ratio,
        uncovered_result_direction=direction,
        uncovered_goal_profiles=profiles,
    )


def uncovered_as_target_pairs(report: UncoveredMassReport) -> list[tuple[str, float]]:
    return [(u.score, float(u.probability)) for u in report.primary_uncovered_scores]

"""PHASE GT-1 — Goal timing split predictor (research only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.goal_timing_split.features import (
    DEFAULT_EARLY_SHARE,
    _p00_from_distribution,
)

PHASE = "GT-1"
MODEL_VERSION = "GT-1-v1"
PROB_SUM_TOLERANCE = 0.02
SIDE_EDGE_MIN = 0.05
WINDOW_EDGE_MIN = 0.03


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _normalize_outcomes(raw: dict[str, float]) -> dict[str, float]:
    total = sum(raw.values())
    if total <= 0:
        uniform = 1.0 / len(raw)
        return {k: round(uniform, 6) for k in raw}
    return {k: round(v / total, 6) for k, v in raw.items()}


def _blend(a: float, b: float, weight_b: float) -> float:
    w = _clamp01(weight_b)
    return a * (1.0 - w) + b * w


def predict_goal_timing_split(ctx: dict[str, Any]) -> dict[str, Any]:
    """
    Estimate five-way outcome:
    home 0-30, away 0-30, home 31+, away 31+, no goal.
    """
    if not ctx.get("has_sufficient_data"):
        return _insufficient_result(ctx)

    lambda_home = float(ctx["lambda_home"] or 0)
    lambda_away = float(ctx["lambda_away"] or 0)
    if lambda_home <= 0 or lambda_away <= 0:
        return _insufficient_result(ctx)

    p_no_goal = _p00_from_distribution(lambda_home, lambda_away)
    p_any_goal = 1.0 - p_no_goal

    total_lambda = lambda_home + lambda_away
    share_home = lambda_home / total_lambda
    share_away = lambda_away / total_lambda

    odds = ctx.get("odds_signals") or {}
    home_imp = odds.get("ft_home_implied")
    away_imp = odds.get("ft_away_implied")
    if home_imp and away_imp:
        imp_total = home_imp + away_imp
        if imp_total > 0:
            share_home = _blend(share_home, home_imp / imp_total, 0.22)
            share_away = _blend(share_away, away_imp / imp_total, 0.22)

    ou_over_15 = odds.get("ou_over_15_implied")
    ou_under_15 = odds.get("ou_under_15_implied")
    if ou_over_15 and ou_under_15:
        over_share = ou_over_15 / (ou_over_15 + ou_under_15)
        p_any_goal = _blend(p_any_goal, over_share, 0.18)
        p_no_goal = 1.0 - p_any_goal

    btts_yes = odds.get("btts_yes_implied")
    if btts_yes:
        p_any_goal = _blend(p_any_goal, min(0.92, btts_yes * 1.15), 0.10)
        p_no_goal = 1.0 - p_any_goal

    early_share = float(ctx.get("early_share") or DEFAULT_EARLY_SHARE)
    ou_over_25 = odds.get("ou_over_25_implied")
    if ou_over_25 and ou_over_25 > 0.5:
        early_share = _blend(early_share, min(0.52, early_share + 0.04), 0.35)

    p_home_first = p_any_goal * share_home
    p_away_first = p_any_goal * share_away

    outcomes = _normalize_outcomes(
        {
            "p_home_0_30": p_home_first * early_share,
            "p_away_0_30": p_away_first * early_share,
            "p_home_31_plus": p_home_first * (1.0 - early_share),
            "p_away_31_plus": p_away_first * (1.0 - early_share),
            "p_no_goal": p_no_goal,
        }
    )

    side, window, tier = _recommend(outcomes, float(ctx.get("data_quality_score") or 0))
    raw_features = {
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "lambda_source": ctx.get("lambda_source"),
        "early_share": early_share,
        "early_share_source": ctx.get("early_share_source"),
        "odds_signals": odds,
        "snapshot_present": ctx.get("snapshot_present"),
        "registry_fixture_id": ctx.get("registry_fixture_id"),
        "disclaimer": "probabilistic_research_only_not_guaranteed",
    }

    return {
        "fixture_id": ctx["fixture_id"],
        "match_name": f"{ctx['home_team']} vs {ctx['away_team']}",
        "kickoff_utc": ctx.get("kickoff_utc"),
        "home_team": ctx["home_team"],
        "away_team": ctx["away_team"],
        **outcomes,
        "recommended_side": side,
        "recommended_window": window,
        "confidence_tier": tier,
        "data_quality_score": ctx.get("data_quality_score"),
        "raw_features": raw_features,
        "model_version": MODEL_VERSION,
        "status": "ok",
    }


def _insufficient_result(ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": ctx.get("fixture_id"),
        "match_name": f"{ctx.get('home_team')} vs {ctx.get('away_team')}",
        "kickoff_utc": ctx.get("kickoff_utc"),
        "home_team": ctx.get("home_team"),
        "away_team": ctx.get("away_team"),
        "p_home_0_30": None,
        "p_away_0_30": None,
        "p_home_31_plus": None,
        "p_away_31_plus": None,
        "p_no_goal": None,
        "recommended_side": "INSUFFICIENT_DATA",
        "recommended_window": "INSUFFICIENT_DATA",
        "confidence_tier": "INSUFFICIENT_DATA",
        "data_quality_score": ctx.get("data_quality_score"),
        "raw_features": {
            "reason": "missing_lambda_and_odds",
            "lambda_source": ctx.get("lambda_source"),
            "snapshot_present": ctx.get("snapshot_present"),
            "odds_row_present": ctx.get("odds_row_present"),
        },
        "model_version": MODEL_VERSION,
        "status": "insufficient_data",
    }


def _recommend(
    outcomes: dict[str, float],
    data_quality: float,
) -> tuple[str, str, str]:
    p_h = outcomes["p_home_0_30"] + outcomes["p_home_31_plus"]
    p_a = outcomes["p_away_0_30"] + outcomes["p_away_31_plus"]
    p_n = outcomes["p_no_goal"]

    ranked = sorted(
        [("home", p_h), ("away", p_a), ("no_goal", p_n)],
        key=lambda x: -x[1],
    )
    top_side, top_p = ranked[0]
    second_p = ranked[1][1]

    if top_side == "no_goal" and top_p > 0.38:
        side = "no_clear_edge"
        window = "no_clear_edge"
    elif top_p - second_p < SIDE_EDGE_MIN:
        side = "no_clear_edge"
        window = "no_clear_edge"
    else:
        side = top_side if top_side != "no_goal" else "no_clear_edge"
        if side == "home":
            w_early = outcomes["p_home_0_30"]
            w_late = outcomes["p_home_31_plus"]
        elif side == "away":
            w_early = outcomes["p_away_0_30"]
            w_late = outcomes["p_away_31_plus"]
        else:
            w_early = w_late = 0.0
        if side in {"home", "away"}:
            if abs(w_early - w_late) < WINDOW_EDGE_MIN:
                window = "no_clear_edge"
            else:
                window = "0_30" if w_early > w_late else "31_plus"
        else:
            window = "no_clear_edge"

    if data_quality >= 0.60 and top_p - second_p >= 0.10:
        tier = "A"
    elif data_quality >= 0.40 and top_p - second_p >= 0.06:
        tier = "B"
    elif data_quality >= 0.25:
        tier = "C"
    else:
        tier = "C"

    if side == "no_clear_edge" and tier == "A":
        tier = "B"

    return side, window, tier


def probability_sum(outcomes: dict[str, float | None]) -> float | None:
    keys = ("p_home_0_30", "p_away_0_30", "p_home_31_plus", "p_away_31_plus", "p_no_goal")
    vals = [outcomes.get(k) for k in keys]
    if any(v is None for v in vals):
        return None
    return float(sum(vals))

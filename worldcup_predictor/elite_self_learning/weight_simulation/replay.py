"""Fusion replay engine with configurable weights."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from worldcup_predictor.elite_self_learning.simulation import (
    _load_team_goalscorer_proxy,
    _tier_from_margin,
)
from worldcup_predictor.elite_self_learning.post_match_eval import reality_from_fixture_row

EXPANDED_PATH = Path("artifacts/phase54f6_expanded_dataset/expanded_egie_dataset.parquet")


def build_contributions(row: Any, gs_proxy: dict[int, dict[str, float]]) -> tuple[list[dict[str, Any]], float, str]:
    """Return component contributions, confidence, tier for a fixture row."""
    sm_id = int(row.sportmonks_fixture_id)
    proxy = gs_proxy.get(sm_id, {})
    home_rate = float(row.home_goal_rate_proxy or 0)
    away_rate = float(row.away_goal_rate_proxy or 0)

    egie_pick = "home" if home_rate >= away_rate else "away"
    gs_home = proxy.get("home", home_rate)
    gs_away = proxy.get("away", away_rate)
    gs_pick = "home" if gs_home >= gs_away else "away"
    odds_pick = "home" if home_rate > away_rate else "away"
    mbi_pick = odds_pick
    lineup_pick = gs_pick
    fgt_v2_pick = gs_pick if proxy else egie_pick

    margin = float(proxy.get("margin", abs(home_rate - away_rate)))
    tier = _tier_from_margin(margin)
    confidence = round(0.45 + min(0.4, margin), 4)

    contributions = [
        {"component_id": "first_goal_team_v2", "prediction": fgt_v2_pick, "confidence": confidence},
        {"component_id": "egie_historical_baseline", "prediction": egie_pick, "confidence": 0.5},
        {"component_id": "goalscorer_intelligence", "prediction": gs_pick, "confidence": 0.55 + min(0.2, margin)},
        {"component_id": "odds_intelligence", "prediction": odds_pick, "confidence": 0.48},
        {"component_id": "market_behavior_intelligence", "prediction": mbi_pick, "confidence": 0.45},
        {"component_id": "lineup_intelligence", "prediction": lineup_pick, "confidence": 0.52},
    ]
    return contributions, confidence, tier


def fuse_pick(
    contributions: list[dict[str, Any]],
    weights: dict[str, float],
    *,
    market_id: str = "first_goal_team",
) -> tuple[str, float, dict[str, float]]:
    """Weighted vote fusion; return pick, win-share confidence, vote breakdown."""
    votes: dict[str, float] = {}
    conf_weighted: dict[str, float] = {}
    for c in contributions:
        cid = c["component_id"]
        pred = c.get("prediction")
        if pred is None:
            continue
        w = float(weights.get(cid, 0.0))
        if w <= 0:
            continue
        key = str(pred)
        votes[key] = votes.get(key, 0.0) + w
        conf_weighted[key] = conf_weighted.get(key, 0.0) + w * float(c.get("confidence") or 0.5)

    if not votes:
        return "home", 0.5, {}

    total = sum(votes.values())
    pick = max(votes, key=votes.get)
    win_share = votes[pick] / total if total else 0.5
    # Blend vote share with confidence of winning side
    conf = conf_weighted.get(pick, win_share) / votes[pick] if votes[pick] else win_share
    prob = round(0.6 * win_share + 0.4 * conf, 4)
    return pick, prob, {k: round(v / total, 4) for k, v in votes.items()}


def load_fixture_rows(*, sort_temporal: bool = True) -> list[Any]:
    import pandas as pd

    if not EXPANDED_PATH.is_file():
        return []
    df = pd.read_parquet(EXPANDED_PATH)
    if sort_temporal and "kickoff_utc" in df.columns:
        df = df.sort_values("kickoff_utc")
    return list(df.itertuples(index=False))


def replay_fixture(
    row: Any,
    gs_proxy: dict[int, dict[str, float]],
    old_weights: dict[str, float],
    new_weights: dict[str, float],
    *,
    market_id: str = "first_goal_team",
) -> dict[str, Any]:
    reality = reality_from_fixture_row(row)
    real = reality.get(market_id)
    contributions, _, tier = build_contributions(row, gs_proxy)

    old_pick, old_prob, _ = fuse_pick(contributions, old_weights, market_id=market_id)
    new_pick, new_prob, _ = fuse_pick(contributions, new_weights, market_id=market_id)

    old_hit = 1 if str(old_pick) == str(real) else 0
    new_hit = 1 if str(new_pick) == str(real) else 0

    return {
        "fixture_id": int(row.fixture_id),
        "league_id": int(row.league_id) if getattr(row, "league_id", None) is not None else None,
        "reality": real,
        "tier": tier,
        "old_pick": old_pick,
        "new_pick": new_pick,
        "old_prob": old_prob,
        "new_prob": new_prob,
        "old_hit": old_hit,
        "new_hit": new_hit,
        "pick_changed": old_pick != new_pick,
    }


def load_gs_proxy() -> dict[int, dict[str, float]]:
    return _load_team_goalscorer_proxy()

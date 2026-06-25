"""Shadow replay — simulate post-match learning on historical fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.elite_self_learning.adaptive_weights import DEFAULT_WEIGHTS
from worldcup_predictor.elite_self_learning.component_attribution import attribute_components
from worldcup_predictor.elite_self_learning.post_match_eval import evaluate_post_match, reality_from_fixture_row

EXPANDED_PATH = Path("artifacts/phase54f6_expanded_dataset/expanded_egie_dataset.parquet")
GOALSCORER_PATH = Path("artifacts/phase54q_goalscorer_generalization/goalscorer_dataset_v3.parquet")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tier_from_margin(margin: float) -> str:
    if margin >= 0.25:
        return "A"
    if margin >= 0.15:
        return "B"
    if margin >= 0.08:
        return "C"
    return "D"


def _load_team_goalscorer_proxy() -> dict[int, dict[str, float]]:
    if not GOALSCORER_PATH.is_file():
        return {}
    gs = pd.read_parquet(
        GOALSCORER_PATH,
        columns=["sportmonks_fixture_id", "team_id", "goals_per_90", "starter_probability"],
    )
    gs = gs[gs["starter_probability"] > 0.3]
    top = (
        gs.groupby(["sportmonks_fixture_id", "team_id"])["goals_per_90"]
        .max()
        .reset_index()
    )
    out: dict[int, dict[str, float]] = {}
    for fid, grp in top.groupby("sportmonks_fixture_id"):
        rows = grp.sort_values("goals_per_90", ascending=False)
        if len(rows) < 2:
            continue
        home_strength = float(rows.iloc[0]["goals_per_90"])
        away_strength = float(rows.iloc[1]["goals_per_90"])
        out[int(fid)] = {"home": home_strength, "away": away_strength, "margin": abs(home_strength - away_strength)}
    return out


def _simulate_component_contributions(row: Any, gs_proxy: dict[int, dict[str, float]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    sm_id = int(row.sportmonks_fixture_id)
    reality_fgt = str(row.label_first_goal_team)
    proxy = gs_proxy.get(sm_id, {})
    home_rate = float(row.home_goal_rate_proxy or 0)
    away_rate = float(row.away_goal_rate_proxy or 0)

    # Component picks (shadow proxies mirroring 57A validated stack)
    egie_pick = "home" if home_rate >= away_rate else "away"
    gs_home = proxy.get("home", home_rate)
    gs_away = proxy.get("away", away_rate)
    gs_pick = "home" if gs_home >= gs_away else "away"
    odds_pick = "home" if float(row.home_goal_rate_proxy or 0) > float(row.away_goal_rate_proxy or 0) else "away"
    mbi_pick = odds_pick  # MBI shadow follows odds direction in replay
    lineup_pick = gs_pick  # lineup gates goalscorer
    fgt_v2_pick = gs_pick if proxy else egie_pick

    margin = proxy.get("margin", abs(home_rate - away_rate))
    tier = _tier_from_margin(margin)
    confidence = round(0.45 + min(0.4, margin), 4)

    weights = DEFAULT_WEIGHTS["first_goal_team"]
    contributions = [
        {"component_id": "first_goal_team_v2", "prediction": fgt_v2_pick, "weight": weights["first_goal_team_v2"], "confidence": confidence},
        {"component_id": "egie_historical_baseline", "prediction": egie_pick, "weight": weights["egie_historical_baseline"], "confidence": 0.5},
        {"component_id": "goalscorer_intelligence", "prediction": gs_pick, "weight": weights["goalscorer_intelligence"], "confidence": 0.55 + min(0.2, margin)},
        {"component_id": "odds_intelligence", "prediction": odds_pick, "weight": weights["odds_intelligence"], "confidence": 0.48},
        {"component_id": "market_behavior_intelligence", "prediction": mbi_pick, "weight": weights["market_behavior_intelligence"], "confidence": 0.45},
        {"component_id": "lineup_intelligence", "prediction": lineup_pick, "weight": weights["lineup_intelligence"], "confidence": 0.52},
        {"component_id": "hybrid_confidence_engine", "prediction": None, "weight": 0.0, "confidence": confidence},
    ]

    # Fusion pick: weighted vote
    votes: dict[str, float] = {}
    for c in contributions:
        if c["prediction"] is None:
            continue
        votes[str(c["prediction"])] = votes.get(str(c["prediction"]), 0) + float(c["weight"])

    fusion_pick = max(votes, key=votes.get) if votes else egie_pick

    shadow_markets = {
        "first_goal_team": {"prediction": fusion_pick, "confidence": confidence, "tier": tier},
        "team_to_score_first": {"prediction": fusion_pick, "confidence": confidence, "tier": tier},
    }
    return shadow_markets, contributions


def run_shadow_replay(*, limit: int | None = None) -> list[dict[str, Any]]:
    """Replay post-match evaluation on expanded EGIE dataset (shadow proxies)."""
    if not EXPANDED_PATH.is_file():
        return []

    df = pd.read_parquet(EXPANDED_PATH)
    if limit:
        df = df.head(limit)
    gs_proxy = _load_team_goalscorer_proxy()
    evaluations: list[dict[str, Any]] = []

    for row in df.itertuples(index=False):
        reality = reality_from_fixture_row(row)
        shadow_markets, contributions = _simulate_component_contributions(row, gs_proxy)
        markets = evaluate_post_match(
            fixture_id=int(row.fixture_id),
            sportmonks_fixture_id=int(row.sportmonks_fixture_id),
            league_id=int(row.league_id) if pd.notna(row.league_id) else None,
            competition_key=str(row.competition_key) if pd.notna(row.competition_key) else None,
            kickoff_utc=str(row.kickoff_utc) if pd.notna(row.kickoff_utc) else None,
            evaluated_at=_utc_now(),
            shadow_markets=shadow_markets,
            reality=reality,
        )
        attributions = attribute_components(
            market_id="first_goal_team",
            reality=reality["first_goal_team"],
            contributions=contributions,
        )
        fusion_correct = any(m.outcome == "correct" for m in markets)
        record = {
            "fixture_id": int(row.fixture_id),
            "sportmonks_fixture_id": int(row.sportmonks_fixture_id),
            "league_id": int(row.league_id) if pd.notna(row.league_id) else None,
            "competition_key": str(row.competition_key) if pd.notna(row.competition_key) else None,
            "kickoff_utc": str(row.kickoff_utc) if pd.notna(row.kickoff_utc) else None,
            "evaluated_at": _utc_now(),
            "markets": [m.to_dict() for m in markets],
            "attributions": [a.to_dict() for a in attributions],
            "fusion_correct": fusion_correct,
            "meta": {"replay": "shadow_proxy", "phase": "58A"},
        }
        evaluations.append(record)
    return evaluations

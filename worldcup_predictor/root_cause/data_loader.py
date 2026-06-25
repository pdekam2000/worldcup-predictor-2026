"""Load 58C shadow evaluations and historical replay fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.elite_self_learning.adaptive_weights import DEFAULT_WEIGHTS
from worldcup_predictor.elite_self_learning.post_match_eval import reality_from_fixture_row
from worldcup_predictor.root_cause.config import EVALUATIONS_PATH, EXPANDED_PATH, GOALSCORER_PATH


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def load_live_evaluations(path: Path | None = None) -> list[dict[str, Any]]:
    rows = load_jsonl(path or EVALUATIONS_PATH)
    return [r for r in rows if str(r.get("outcome") or "") in ("correct", "incorrect", "partial")]


def load_fixture_meta_lookup() -> dict[int, dict[str, Any]]:
    if not EXPANDED_PATH.is_file():
        return {}
    df = pd.read_parquet(
        EXPANDED_PATH,
        columns=[
            "fixture_id",
            "league_id",
            "season_id",
            "competition_key",
            "data_quality_score",
            "home_recent_xg",
            "away_recent_xg",
            "home_goal_rate_proxy",
            "away_goal_rate_proxy",
            "home_team",
            "away_team",
        ],
    )
    lookup: dict[int, dict[str, Any]] = {}
    for row in df.itertuples(index=False):
        lookup[int(row.fixture_id)] = {
            "league_id": int(row.league_id) if pd.notna(row.league_id) else None,
            "season_id": int(row.season_id) if pd.notna(row.season_id) else None,
            "competition_key": str(row.competition_key) if pd.notna(row.competition_key) else None,
            "data_quality_score": float(row.data_quality_score) if pd.notna(row.data_quality_score) else None,
            "home_recent_xg": float(row.home_recent_xg) if pd.notna(row.home_recent_xg) else None,
            "away_recent_xg": float(row.away_recent_xg) if pd.notna(row.away_recent_xg) else None,
            "home_goal_rate_proxy": float(row.home_goal_rate_proxy) if pd.notna(row.home_goal_rate_proxy) else None,
            "away_goal_rate_proxy": float(row.away_goal_rate_proxy) if pd.notna(row.away_goal_rate_proxy) else None,
            "home_team": str(row.home_team) if pd.notna(row.home_team) else None,
            "away_team": str(row.away_team) if pd.notna(row.away_team) else None,
        }
    return lookup


def _load_team_goalscorer_proxy() -> dict[int, dict[str, float]]:
    if not GOALSCORER_PATH.is_file():
        return {}
    gs = pd.read_parquet(
        GOALSCORER_PATH,
        columns=["sportmonks_fixture_id", "team_id", "goals_per_90", "starter_probability"],
    )
    gs = gs[gs["starter_probability"] > 0.3]
    top = gs.groupby(["sportmonks_fixture_id", "team_id"])["goals_per_90"].max().reset_index()
    out: dict[int, dict[str, float]] = {}
    for fid, grp in top.groupby("sportmonks_fixture_id"):
        rows = grp.sort_values("goals_per_90", ascending=False)
        if len(rows) < 2:
            continue
        home_strength = float(rows.iloc[0]["goals_per_90"])
        away_strength = float(rows.iloc[1]["goals_per_90"])
        out[int(fid)] = {"home": home_strength, "away": away_strength, "margin": abs(home_strength - away_strength)}
    return out


def _tier_from_margin(margin: float) -> str:
    if margin >= 0.25:
        return "A"
    if margin >= 0.15:
        return "B"
    if margin >= 0.08:
        return "C"
    return "D"


def _simulate_fgt_row(row: Any, gs_proxy: dict[int, dict[str, float]]) -> dict[str, Any] | None:
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
        {"component_id": "lineup_intelligence", "prediction": lineup_pick, "weight": weights["lineup_intelligence"], "confidence": 0.52 if proxy else 0.42},
    ]

    votes: dict[str, float] = {}
    for c in contributions:
        if c["prediction"] is None:
            continue
        votes[str(c["prediction"])] = votes.get(str(c["prediction"]), 0) + float(c["weight"])
    fusion_pick = max(votes, key=votes.get) if votes else egie_pick

    reality = reality_from_fixture_row(row)
    real_fgt = reality["first_goal_team"]
    outcome = "correct" if str(fusion_pick).lower() == str(real_fgt).lower() else "incorrect"

    return {
        "fixture_id": int(row.fixture_id),
        "market_id": "first_goal_team",
        "prediction": fusion_pick,
        "reality": real_fgt,
        "confidence": confidence,
        "tier": tier,
        "outcome": outcome,
        "component_contributions": contributions,
        "source": "historical_replay",
        "meta": {"replay": "expanded_egie", "phase": "58D"},
    }


def build_historical_replay_evaluations(*, limit: int | None = None) -> list[dict[str, Any]]:
    if not EXPANDED_PATH.is_file():
        return []
    df = pd.read_parquet(EXPANDED_PATH)
    if limit:
        df = df.head(limit)
    gs_proxy = _load_team_goalscorer_proxy()
    rows: list[dict[str, Any]] = []
    for row in df.itertuples(index=False):
        ev = _simulate_fgt_row(row, gs_proxy)
        if ev:
            rows.append(ev)
    return rows


def build_analysis_dataset(*, historical_limit: int | None = None) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]], dict[str, int]]:
    live = load_live_evaluations()
    historical = build_historical_replay_evaluations(limit=historical_limit)
    lookup = load_fixture_meta_lookup()
    stats = {
        "live_paired": len(live),
        "historical_replay": len(historical),
        "pending_shadow": len(load_jsonl(EVALUATIONS_PATH)) - len(live),
    }
    combined = live + historical
    return combined, lookup, stats

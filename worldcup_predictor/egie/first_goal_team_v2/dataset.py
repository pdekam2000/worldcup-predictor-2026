"""Build first_goal_team_dataset_v2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.egie.uefa_club.first_goal_market_audit import parse_first_goal_markets
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache

EXPANDED_DATASET = Path("artifacts/phase54f6_expanded_dataset/expanded_egie_dataset.parquet")
GOALSCORER_V3 = Path("artifacts/phase54q_goalscorer_generalization/goalscorer_dataset_v3.parquet")
ML1_DATASET = Path("artifacts/ml1_unified_dataset.parquet")

_CACHE_ROOT = Path("data/egie/uefa_club/raw")


def _aggregate_goalscorer_intel(gs: pd.DataFrame) -> pd.DataFrame:
    """Fixture-level goalscorer intelligence from player rows."""
    rows: list[dict[str, Any]] = []
    for fid, grp in gs.groupby("sportmonks_fixture_id"):
        home_id = int(grp["home_team_id"].iloc[0]) if "home_team_id" in grp.columns and grp["home_team_id"].notna().any() else None
        if home_id is None:
            teams = grp["team_id"].unique()
            if len(teams) < 2:
                continue
            home_id, away_id = int(teams[0]), int(teams[1])
        else:
            away_id = int(grp.loc[grp["team_id"] != home_id, "team_id"].iloc[0]) if len(grp["team_id"].unique()) > 1 else home_id

        def _team_feats(tid: int, prefix: str) -> dict[str, float]:
            t = grp[grp["team_id"] == tid]
            if t.empty:
                return {
                    f"{prefix}_top_goals_per_90": 0.0,
                    f"{prefix}_top_xg_per_90": 0.0,
                    f"{prefix}_top_recent_form": 0.0,
                }
            return {
                f"{prefix}_top_goals_per_90": float(t["goals_per_90"].max()),
                f"{prefix}_top_xg_per_90": float(t["xg_per_90"].max()),
                f"{prefix}_top_recent_form": float(t["recent_form_score"].max()),
            }

        home_feats = _team_feats(home_id, "home")
        away_feats = _team_feats(away_id, "away")
        gap = home_feats["home_top_goals_per_90"] - away_feats["away_top_goals_per_90"]
        rows.append(
            {
                "sportmonks_fixture_id": int(fid),
                **home_feats,
                **away_feats,
                "goalscorer_intel_gap": round(gap, 4),
            }
        )
    return pd.DataFrame(rows)


def _aggregate_lineups(gs: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for fid, grp in gs.groupby("sportmonks_fixture_id"):
        rec: dict[str, Any] = {"sportmonks_fixture_id": int(fid)}
        for side, tid in _home_away_team_ids(grp):
            t = grp[grp["team_id"] == tid]
            prefix = "home" if side == "home" else "away"
            starters = t[t.get("lineup_status", pd.Series()) == "starter"] if "lineup_status" in t.columns else t[t.get("starter", False) == True]  # noqa: E712
            rec[f"{prefix}_starter_count"] = int(len(starters))
            rec[f"{prefix}_avg_starter_probability"] = float(t["starter_probability"].mean()) if len(t) else 0.0
            rec[f"{prefix}_lineup_quality"] = float(t["lineup_quality_score"].mean()) if "lineup_quality_score" in t.columns and len(t) else 0.0
        rows.append(rec)
    return pd.DataFrame(rows)


def _home_away_team_ids(grp: pd.DataFrame) -> list[tuple[str, int]]:
    if "home_team_id" in grp.columns and grp["home_team_id"].notna().any():
        home_id = int(grp["home_team_id"].dropna().iloc[0])
        away_ids = grp.loc[grp["team_id"] != home_id, "team_id"].unique()
        away_id = int(away_ids[0]) if len(away_ids) else home_id
        return [("home", home_id), ("away", away_id)]
    teams = sorted(int(t) for t in grp["team_id"].unique())
    if len(teams) < 2:
        return [("home", teams[0]), ("away", teams[0])]
    return [("home", teams[0]), ("away", teams[1])]


def _load_fts_odds(fixture_ids: list[int]) -> pd.DataFrame:
    settings = get_settings()
    rows: list[dict[str, Any]] = []
    for fid in fixture_ids:
        cache = load_cache(cache_path(settings, int(fid)))
        if not cache:
            path = _CACHE_ROOT / f"{fid}.json"
            if path.is_file():
                try:
                    blob = json.loads(path.read_text(encoding="utf-8"))
                    cache = blob
                except (json.JSONDecodeError, OSError):
                    cache = None
        if not cache:
            rows.append({"sportmonks_fixture_id": int(fid)})
            continue
        deep = parse_first_goal_markets(cache.get("payload") or cache)
        rows.append(
            {
                "sportmonks_fixture_id": int(fid),
                "fts_implied_home": deep.get("fts_consensus_implied_home") or deep.get("consensus_implied_home"),
                "fts_implied_away": deep.get("fts_consensus_implied_away") or deep.get("consensus_implied_away"),
                "mw_implied_home": deep.get("consensus_implied_home"),
                "mw_implied_away": deep.get("consensus_implied_away"),
                "mw_implied_draw": deep.get("consensus_implied_draw"),
                "odds_movement_home": deep.get("odds_movement_home"),
                "odds_movement_away": deep.get("odds_movement_away"),
            }
        )
    return pd.DataFrame(rows)


def temporal_split(df: pd.DataFrame, train_frac: float = 0.7, val_frac: float = 0.15) -> pd.DataFrame:
    out = df.copy()
    date_col = "kickoff_utc" if "kickoff_utc" in out.columns else "date"
    out = out.sort_values(date_col).reset_index(drop=True)
    n = len(out)
    if n == 0:
        out["split"] = []
        return out
    train_end = max(1, int(n * train_frac))
    val_end = max(train_end + 1, int(n * (train_frac + val_frac)))
    splits = ["train"] * train_end + ["val"] * (val_end - train_end) + ["test"] * (n - val_end)
    out["split"] = splits[:n]
    return out


def build_dataset_v2() -> tuple[pd.DataFrame, dict[str, Any]]:
    if not EXPANDED_DATASET.is_file():
        raise FileNotFoundError(f"Missing expanded dataset: {EXPANDED_DATASET}")

    base = pd.read_parquet(EXPANDED_DATASET)
    base = base[base["label_first_goal_team"].isin(["home", "away"])].copy()
    base["target_home_first_goal"] = (base["label_first_goal_team"] == "home").astype(int)

    gs = pd.read_parquet(GOALSCORER_V3) if GOALSCORER_V3.is_file() else pd.DataFrame()
    if not gs.empty and "home_team_id" not in gs.columns:
        eg_home = base[["sportmonks_fixture_id", "home_team_id", "away_team_id"]].drop_duplicates()
        gs = gs.merge(eg_home, on="sportmonks_fixture_id", how="left")

    if not gs.empty:
        gs_intel = _aggregate_goalscorer_intel(gs)
        lineup = _aggregate_lineups(gs)
        base = base.merge(gs_intel, on="sportmonks_fixture_id", how="left")
        base = base.merge(lineup, on="sportmonks_fixture_id", how="left")
    else:
        gs_intel = lineup = pd.DataFrame()

    fts = _load_fts_odds(base["sportmonks_fixture_id"].astype(int).tolist())
    base = base.merge(fts, on="sportmonks_fixture_id", how="left")

    if ML1_DATASET.is_file():
        ml1 = pd.read_parquet(ML1_DATASET)
        ml_cols = [c for c in ml1.columns if c.startswith("sm_") and "implied" in c]
        if ml_cols and "fixture_id" in base.columns:
            merge_cols = ["fixture_id"] + ml_cols[:6]
            avail = [c for c in merge_cols if c in ml1.columns]
            if avail:
                base = base.merge(ml1[avail].drop_duplicates("fixture_id"), on="fixture_id", how="left", suffixes=("", "_ml1"))

    base = temporal_split(base)

    meta = {
        "status": "ok",
        "rows": len(base),
        "fixtures": int(base["sportmonks_fixture_id"].nunique()),
        "sources": {
            "expanded_egie": str(EXPANDED_DATASET),
            "goalscorer_v3": str(GOALSCORER_V3) if GOALSCORER_V3.is_file() else None,
            "goalscorer_fixtures_merged": int(gs_intel["sportmonks_fixture_id"].nunique()) if not gs_intel.empty else 0,
            "fts_odds_non_null": int(base["fts_implied_home"].notna().sum()) if "fts_implied_home" in base.columns else 0,
        },
        "label_balance": base["target_home_first_goal"].mean() if len(base) else 0.5,
    }
    return base, meta

"""Build team-level context features for goalscorer dataset v4."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_intelligence.team_context.models import TEAM_CONTEXT_COLUMNS

_CACHE_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
    Path("data/feature_store/sportmonks_pressure/raw"),
)

_ELO_K = 20.0
_ELO_BASE = 1500.0


def _load_fixture_meta() -> dict[int, dict[str, Any]]:
    """Cache-first home/away map and final scores per fixture."""
    meta: dict[int, dict[str, Any]] = {}
    for root in _CACHE_ROOTS:
        if not root.is_dir():
            continue
        for path in root.glob("*.json"):
            try:
                fid = int(path.stem)
            except ValueError:
                continue
            if fid in meta:
                continue
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            data = (blob.get("payload") or {}).get("data")
            if not isinstance(data, dict):
                continue
            home_id = away_id = None
            for p in data.get("participants") or []:
                if not isinstance(p, dict):
                    continue
                loc = str((p.get("meta") or {}).get("location") or "").lower()
                tid = int(p.get("id") or 0)
                if loc == "home":
                    home_id = tid
                elif loc == "away":
                    away_id = tid
            scores: dict[int, int] = {}
            for sc in data.get("scores") or []:
                if not isinstance(sc, dict):
                    continue
                if str(sc.get("description") or "").upper() != "CURRENT":
                    continue
                pid = int(sc.get("participant_id") or 0)
                goals = int((sc.get("score") or {}).get("goals") or 0)
                scores[pid] = goals
            meta[fid] = {
                "home_team_id": home_id,
                "away_team_id": away_id,
                "home_goals": scores.get(home_id or -1, 0) if home_id else 0,
                "away_goals": scores.get(away_id or -1, 0) if away_id else 0,
            }
    return meta


def _build_team_match_table(df: pd.DataFrame, fixture_meta: dict[int, dict[str, Any]]) -> pd.DataFrame:
    """One row per team per fixture with goals/xg and home flag."""
    agg = (
        df.groupby(["sportmonks_fixture_id", "team_id", "league_id", "season_id", "match_date"], dropna=False)
        .agg(
            goals_for=("match_goals", lambda s: int(pd.to_numeric(s, errors="coerce").fillna(0).sum())),
            xg_for=("match_xg", lambda s: float(pd.to_numeric(s, errors="coerce").fillna(0).sum())),
        )
        .reset_index()
    )
    fixture_teams = df.groupby("sportmonks_fixture_id")["team_id"].apply(lambda s: list(s.unique())).to_dict()
    goals_against: list[int] = []
    xg_against: list[float] = []
    is_home: list[int] = []
    for _, row in agg.iterrows():
        fid = int(row["sportmonks_fixture_id"])
        tid = int(row["team_id"])
        teams = fixture_teams.get(fid, [])
        opp = next((t for t in teams if int(t) != tid), None)
        if opp is not None:
            opp_rows = agg[(agg["sportmonks_fixture_id"] == fid) & (agg["team_id"] == opp)]
            ga = int(opp_rows.iloc[0]["goals_for"]) if len(opp_rows) else 0
            xga = float(opp_rows.iloc[0]["xg_for"]) if len(opp_rows) else 0.0
        else:
            fm = fixture_meta.get(fid, {})
            if fm.get("home_team_id") == tid:
                ga = int(fm.get("away_goals") or 0)
            elif fm.get("away_team_id") == tid:
                ga = int(fm.get("home_goals") or 0)
            else:
                ga = 0
            xga = 0.0
        goals_against.append(ga)
        xg_against.append(xga)
        fm = fixture_meta.get(fid, {})
        home = 1 if fm.get("home_team_id") == tid else (0 if fm.get("away_team_id") == tid else 0)
        is_home.append(home)
    agg["goals_against"] = goals_against
    agg["xg_against"] = xg_against
    agg["is_home"] = is_home
    agg["match_date"] = pd.to_datetime(agg["match_date"], errors="coerce")
    return agg.sort_values(["team_id", "match_date", "sportmonks_fixture_id"]).reset_index(drop=True)


def _match_points(row: pd.Series) -> float:
    gf = int(row.get("goals_for") or 0)
    ga = int(row.get("goals_against") or 0)
    if gf > ga:
        return 3.0
    if gf == ga:
        return 1.0
    return 0.0


def _update_elo(elo: float, goals_for: int, goals_against: int) -> float:
    if goals_for > goals_against:
        score = 1.0
    elif goals_for == goals_against:
        score = 0.5
    else:
        score = 0.0
    expected = 1.0 / (1.0 + 10 ** ((_ELO_BASE - elo) / 400.0))
    return elo + _ELO_K * (score - expected)


def _compute_rolling_team_features(team_matches: pd.DataFrame) -> pd.DataFrame:
    """Leakage-safe rolling team stats keyed by fixture+team."""
    rows: list[dict[str, Any]] = []
    for team_id, grp in team_matches.groupby("team_id"):
        g = grp.sort_values(["match_date", "sportmonks_fixture_id"]).reset_index(drop=True)
        elo = _ELO_BASE
        season_points: dict[int, float] = {}
        for i, row in g.iterrows():
            hist = g.iloc[:i]
            w5 = hist.tail(5)
            w3 = hist.tail(3)
            home_hist = hist[hist["is_home"] == 1].tail(5)
            away_hist = hist[hist["is_home"] == 0].tail(5)

            attack = float(w5["goals_for"].mean()) if len(w5) else 0.0
            defense_weak = float(w5["goals_against"].mean()) if len(w5) else 0.0
            recent_gs = float(w3["goals_for"].mean()) if len(w3) else 0.0
            recent_gc = float(w3["goals_against"].mean()) if len(w3) else 0.0
            roll_xg = float(w5["xg_for"].mean()) if len(w5) and w5["xg_for"].notna().any() else attack
            roll_xga = float(w5["xg_against"].mean()) if len(w5) and w5["xg_against"].notna().any() else defense_weak
            home_atk = float(home_hist["goals_for"].mean()) if len(home_hist) else attack
            away_atk = float(away_hist["goals_for"].mean()) if len(away_hist) else attack

            sid = int(row["season_id"]) if pd.notna(row["season_id"]) else 0
            pts = season_points.get(sid, 0.0)
            league_pos = 0.5
            if sid and len(hist):
                season_hist = hist[hist["season_id"] == sid]
                if len(season_hist):
                    team_pts = season_hist.assign(pts=season_hist.apply(_match_points, axis=1))["pts"].sum()
                    league_pos = max(0.01, 1.0 - (team_pts / max(1.0, len(season_hist) * 3)))

            rows.append(
                {
                    "sportmonks_fixture_id": int(row["sportmonks_fixture_id"]),
                    "team_id": int(team_id),
                    "team_attack_strength": round(attack, 4),
                    "team_defensive_weakness": round(defense_weak, 4),
                    "team_recent_goals_scored": round(recent_gs, 4),
                    "team_recent_goals_conceded": round(recent_gc, 4),
                    "team_rolling_xg": round(roll_xg, 4),
                    "team_rolling_xga": round(roll_xga, 4),
                    "team_league_position": round(league_pos, 4),
                    "team_elo_strength": round(elo, 2),
                    "team_home_attack": round(home_atk, 4),
                    "team_away_attack": round(away_atk, 4),
                    "is_home": int(row["is_home"]),
                }
            )
            gf, ga = int(row["goals_for"]), int(row["goals_against"])
            elo = _update_elo(elo, gf, ga)
            season_points[sid] = pts + _match_points(row)

    out = pd.DataFrame(rows)
    fixture_pairs = team_matches.groupby("sportmonks_fixture_id")["team_id"].apply(list).to_dict()
    fav, dog = [], []
    for _, row in out.iterrows():
        fid = int(row["sportmonks_fixture_id"])
        tid = int(row["team_id"])
        teams = fixture_pairs.get(fid, [])
        opp = next((t for t in teams if int(t) != tid), None)
        if opp is None:
            fav.append(0)
            dog.append(0)
            continue
        opp_rows = out[(out["sportmonks_fixture_id"] == fid) & (out["team_id"] == opp)]
        opp_elo = float(opp_rows.iloc[0]["team_elo_strength"]) if len(opp_rows) else _ELO_BASE
        my_elo = float(row["team_elo_strength"])
        fav.append(1 if my_elo >= opp_elo else 0)
        dog.append(1 if my_elo < opp_elo else 0)
    out["is_favorite"] = fav
    out["is_underdog"] = dog
    return out


def _attacking_share(df: pd.DataFrame) -> pd.Series:
    weights = (
        pd.to_numeric(df.get("xg_per_90"), errors="coerce").fillna(0)
        * pd.to_numeric(df.get("starter_probability"), errors="coerce").fillna(0)
    )
    tmp = df[["sportmonks_fixture_id", "team_id"]].copy()
    tmp["_w"] = weights.values
    denom = tmp.groupby(["sportmonks_fixture_id", "team_id"], observed=True)["_w"].transform("sum")
    return (tmp["_w"] / denom.replace(0, pd.NA)).fillna(0.0).round(4)


def enrich_team_context(df: pd.DataFrame) -> pd.DataFrame:
    """Attach team context columns to player-fixture rows."""
    fixture_meta = _load_fixture_meta()
    team_matches = _build_team_match_table(df, fixture_meta)
    team_feats = _compute_rolling_team_features(team_matches)

    out = df.merge(team_feats, on=["sportmonks_fixture_id", "team_id"], how="left")
    out["team_attacking_share"] = _attacking_share(out)

    for col in TEAM_CONTEXT_COLUMNS:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    return out

"""Leakage-safe baselines for Phase 3B experiments."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from worldcup_predictor.challenger.phase3b.distributions import goals_to_markets


def league_avg_predict(train_rows: list[dict], row: dict, *, family: str = "independent_poisson") -> dict[str, Any]:
    comp = row["competition_key"]
    same = [r for r in train_rows if r["competition_key"] == comp] or train_rows
    ah = sum(r["home_goals"] for r in same) / len(same)
    aa = sum(r["away_goals"] for r in same) / len(same)
    return goals_to_markets(ah, aa, family=family)


def fit_team_strength(train_rows: list[dict], *, min_games: int = 3) -> dict[str, Any]:
    """Attack/defence multipliers relative to league averages (train only)."""
    by_comp: dict[str, list[dict]] = defaultdict(list)
    for r in train_rows:
        by_comp[r["competition_key"]].append(r)

    league_means: dict[str, dict[str, float]] = {}
    for comp, rows in by_comp.items():
        league_means[comp] = {
            "home": sum(r["home_goals"] for r in rows) / len(rows),
            "away": sum(r["away_goals"] for r in rows) / len(rows),
        }

    # team_id -> scored/conceded lists split by venue
    scored: dict[tuple[str, int], list[float]] = defaultdict(list)
    conceded: dict[tuple[str, int], list[float]] = defaultdict(list)
    for r in train_rows:
        comp = r["competition_key"]
        hid = int(r.get("home_team_id") or (r.get("features") or {}).get("home_team_id") or 0)
        aid = int(r.get("away_team_id") or (r.get("features") or {}).get("away_team_id") or 0)
        if hid:
            scored[(comp, hid)].append(float(r["home_goals"]))
            conceded[(comp, hid)].append(float(r["away_goals"]))
        if aid:
            scored[(comp, aid)].append(float(r["away_goals"]))
            conceded[(comp, aid)].append(float(r["home_goals"]))

    att: dict[tuple[str, int], float] = {}
    deff: dict[tuple[str, int], float] = {}
    for key, vals in scored.items():
        comp = key[0]
        mean_g = (league_means[comp]["home"] + league_means[comp]["away"]) / 2.0
        if len(vals) >= min_games and mean_g > 0:
            att[key] = (sum(vals) / len(vals)) / mean_g
        else:
            att[key] = 1.0
    for key, vals in conceded.items():
        comp = key[0]
        mean_g = (league_means[comp]["home"] + league_means[comp]["away"]) / 2.0
        if len(vals) >= min_games and mean_g > 0:
            deff[key] = (sum(vals) / len(vals)) / mean_g
        else:
            deff[key] = 1.0

    return {"league_means": league_means, "attack": att, "defence": deff, "min_games": min_games}


def team_strength_predict(strength: dict[str, Any], row: dict, *, family: str = "independent_poisson") -> dict[str, Any]:
    comp = row["competition_key"]
    means = strength["league_means"].get(comp) or {"home": 1.4, "away": 1.2}
    hid = int(row.get("home_team_id") or (row.get("features") or {}).get("home_team_id") or 0)
    aid = int(row.get("away_team_id") or (row.get("features") or {}).get("away_team_id") or 0)
    ah = float(strength["attack"].get((comp, hid), 1.0))
    dh = float(strength["defence"].get((comp, hid), 1.0))
    aa = float(strength["attack"].get((comp, aid), 1.0))
    da = float(strength["defence"].get((comp, aid), 1.0))
    lam_h = means["home"] * ah * da
    lam_a = means["away"] * aa * dh
    return goals_to_markets(lam_h, lam_a, family=family)

"""Leakage-safe attack/defence strength fitting for TSBP."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from worldcup_predictor.challenger.tsbp.constants import MIN_TEAM_GAMES


def fit_strength_from_conn(
    conn,
    competition_keys: list[str],
    *,
    before_kickoff: str | None = None,
    min_games: int = MIN_TEAM_GAMES,
) -> dict[str, Any]:
    """
    Fit team attack/defence using only fixtures with kickoff < before_kickoff (if set)
    and status FT (regulation-oriented). AET/PEN excluded for parameter stability.
    """
    ph = ",".join("?" for _ in competition_keys)
    params: list[Any] = list(competition_keys)
    time_clause = ""
    if before_kickoff:
        time_clause = " AND f.kickoff_utc < ? "
        params.append(before_kickoff[:19].replace("Z", ""))
    rows = conn.execute(
        f"""
        SELECT f.fixture_id, f.competition_key, f.home_team_id, f.away_team_id,
               r.home_goals, r.away_goals, f.kickoff_utc
        FROM fixtures f
        JOIN fixture_results r ON r.fixture_id = f.fixture_id
        WHERE f.is_placeholder=0 AND f.status='FT'
          AND r.home_goals IS NOT NULL AND r.away_goals IS NOT NULL
          AND f.competition_key IN ({ph})
          {time_clause}
        ORDER BY f.kickoff_utc ASC
        """,
        params,
    ).fetchall()

    by_comp: dict[str, list] = defaultdict(list)
    for r in rows:
        by_comp[str(r["competition_key"])].append(r)

    league_means: dict[str, dict[str, float]] = {}
    for comp, rs in by_comp.items():
        league_means[comp] = {
            "home": sum(float(x["home_goals"]) for x in rs) / len(rs),
            "away": sum(float(x["away_goals"]) for x in rs) / len(rs),
            "n": float(len(rs)),
        }

    scored: dict[tuple[str, int], list[float]] = defaultdict(list)
    conceded: dict[tuple[str, int], list[float]] = defaultdict(list)
    for r in rows:
        comp = str(r["competition_key"])
        hid = int(r["home_team_id"] or 0)
        aid = int(r["away_team_id"] or 0)
        if hid:
            scored[(comp, hid)].append(float(r["home_goals"]))
            conceded[(comp, hid)].append(float(r["away_goals"]))
        if aid:
            scored[(comp, aid)].append(float(r["away_goals"]))
            conceded[(comp, aid)].append(float(r["home_goals"]))

    attack: dict[str, float] = {}
    defence: dict[str, float] = {}
    games: dict[str, int] = {}
    for key, vals in scored.items():
        comp, tid = key
        mean_g = (league_means[comp]["home"] + league_means[comp]["away"]) / 2.0
        sk = f"{comp}:{tid}"
        games[sk] = len(vals)
        if len(vals) >= min_games and mean_g > 0:
            attack[sk] = (sum(vals) / len(vals)) / mean_g
        else:
            attack[sk] = 1.0
    for key, vals in conceded.items():
        comp, tid = key
        mean_g = (league_means[comp]["home"] + league_means[comp]["away"]) / 2.0
        sk = f"{comp}:{tid}"
        if len(vals) >= min_games and mean_g > 0:
            defence[sk] = (sum(vals) / len(vals)) / mean_g
        else:
            defence[sk] = 1.0

    payload = {
        "league_means": league_means,
        "attack": attack,
        "defence": defence,
        "games": games,
        "min_games": min_games,
        "n_fixtures": len(rows),
        "before_kickoff": before_kickoff,
        "competitions": competition_keys,
        "method": {
            "attack": "mean_goals_scored / league_mean_goals",
            "defence": "mean_goals_conceded / league_mean_goals",
            "home_advantage": "league_avg_home_goals - league_avg_away_goals",
            "time_decay": "none_equal_weight_expanding",
            "league_normalization": "per_competition",
            "parameter_estimation": "closed_form_relative_rates",
            "status_filter": "FT_only",
        },
    }
    raw = json.dumps(
        {"n": len(rows), "comps": competition_keys, "before": before_kickoff, "min_games": min_games},
        sort_keys=True,
    )
    payload["artifact_hash"] = hashlib.sha256(raw.encode()).hexdigest()
    return payload


def predict_lambdas(
    strength: dict[str, Any],
    *,
    competition_key: str,
    home_team_id: int,
    away_team_id: int,
) -> dict[str, Any]:
    means = strength.get("league_means", {}).get(competition_key) or {"home": 1.4, "away": 1.2, "n": 0}
    ah = float(strength.get("attack", {}).get(f"{competition_key}:{home_team_id}", 1.0))
    dh = float(strength.get("defence", {}).get(f"{competition_key}:{home_team_id}", 1.0))
    aa = float(strength.get("attack", {}).get(f"{competition_key}:{away_team_id}", 1.0))
    da = float(strength.get("defence", {}).get(f"{competition_key}:{away_team_id}", 1.0))
    lam_h = float(means["home"]) * ah * da
    lam_a = float(means["away"]) * aa * dh
    home_adv = float(means["home"]) - float(means["away"])
    return {
        "lam_h": lam_h,
        "lam_a": lam_a,
        "home_attack": ah,
        "away_attack": aa,
        "home_defence": dh,
        "away_defence": da,
        "league_baseline": {"home": means["home"], "away": means["away"], "n": means.get("n")},
        "home_advantage": home_adv,
        "home_games": strength.get("games", {}).get(f"{competition_key}:{home_team_id}", 0),
        "away_games": strength.get("games", {}).get(f"{competition_key}:{away_team_id}", 0),
    }

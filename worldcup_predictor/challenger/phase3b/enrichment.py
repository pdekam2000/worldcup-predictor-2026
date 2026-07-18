"""Chronological feature enrichment for GBGM-v2 (no post-match leakage)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def enrich_rows_chronological(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Walk fixtures in kickoff order and attach expanding Elo + attack/defence
    using ONLY prior matches. Mutates a shallow copy of each row's features.
    """
    ordered = sorted(rows, key=lambda r: (str(r.get("kickoff_utc") or ""), int(r["fixture_id"])))
    elo: dict[tuple[str, int], float] = defaultdict(lambda: 1500.0)
    gf: dict[tuple[str, int], list[float]] = defaultdict(list)
    ga: dict[tuple[str, int], list[float]] = defaultdict(list)
    games: dict[tuple[str, int], int] = defaultdict(int)
    out = []

    for r in ordered:
        comp = r["competition_key"]
        hid = int(r.get("home_team_id") or (r.get("features") or {}).get("home_team_id") or 0)
        aid = int(r.get("away_team_id") or (r.get("features") or {}).get("away_team_id") or 0)
        feats = dict(r.get("features") or {})

        # Relative form vs league averages already in snapshot
        lg_h = float(feats.get("league_avg_home_goals") or 1.4)
        lg_a = float(feats.get("league_avg_away_goals") or 1.2)
        hgf = feats.get("home_goals_for_avg_l5")
        hga = feats.get("home_goals_against_avg_l5")
        agf = feats.get("away_goals_for_avg_l5")
        aga = feats.get("away_goals_against_avg_l5")
        feats["home_att_rel_l5"] = (float(hgf) / lg_h) if hgf is not None and lg_h else None
        feats["home_def_rel_l5"] = (float(hga) / lg_a) if hga is not None and lg_a else None
        feats["away_att_rel_l5"] = (float(agf) / lg_a) if agf is not None and lg_a else None
        feats["away_def_rel_l5"] = (float(aga) / lg_h) if aga is not None and lg_h else None

        # Expanding team strength (prior only)
        def _att(team: int) -> float:
            vals = gf[(comp, team)]
            if len(vals) < 3:
                return 1.0
            mean_g = (lg_h + lg_a) / 2.0
            return (sum(vals) / len(vals)) / mean_g if mean_g else 1.0

        def _deff(team: int) -> float:
            vals = ga[(comp, team)]
            if len(vals) < 3:
                return 1.0
            mean_g = (lg_h + lg_a) / 2.0
            return (sum(vals) / len(vals)) / mean_g if mean_g else 1.0

        feats["home_att_expanding"] = _att(hid) if hid else 1.0
        feats["home_def_expanding"] = _deff(hid) if hid else 1.0
        feats["away_att_expanding"] = _att(aid) if aid else 1.0
        feats["away_def_expanding"] = _deff(aid) if aid else 1.0
        feats["elo_home"] = elo[(comp, hid)] if hid else 1500.0
        feats["elo_away"] = elo[(comp, aid)] if aid else 1500.0
        feats["elo_diff"] = feats["elo_home"] - feats["elo_away"]
        feats["home_games_prior"] = games[(comp, hid)] if hid else 0
        feats["away_games_prior"] = games[(comp, aid)] if aid else 0
        feats["coverage_score"] = min(
            float(feats.get("home_l5_sample") or 0),
            float(feats.get("away_l5_sample") or 0),
            5.0,
        ) / 5.0
        # League one-hots (safe categorical)
        for ck in ("premier_league", "bundesliga", "champions_league", "world_cup_2026"):
            feats[f"comp__{ck}"] = 1.0 if comp == ck else 0.0
        # is_home was incorrectly constant=1 in v1 snapshot; keep flag for audit
        feats["is_home_constant_bug"] = 1.0 if float(feats.get("is_home") or 0) == 1.0 else 0.0
        feats["is_home"] = 1.0  # still home-row encoding; both sides already encoded via home_/away_ feats

        # Opponent-adjusted expected goals proxy (prematch)
        feats["lambda_proxy_home"] = lg_h * feats["home_att_expanding"] * feats["away_def_expanding"]
        feats["lambda_proxy_away"] = lg_a * feats["away_att_expanding"] * feats["home_def_expanding"]

        missing_rate = sum(
            1
            for k in (
                "home_goals_for_avg_l5",
                "home_goals_against_avg_l5",
                "away_goals_for_avg_l5",
                "away_goals_against_avg_l5",
            )
            if feats.get(k) is None
        ) / 4.0
        feats["form_missing_rate"] = missing_rate
        if missing_rate <= 0.0:
            feats["coverage_bucket"] = "HIGH_COVERAGE"
        elif missing_rate <= 0.5:
            feats["coverage_bucket"] = "MEDIUM_COVERAGE"
        else:
            feats["coverage_bucket"] = "LOW_COVERAGE"

        nr = dict(r)
        nr["features"] = feats
        nr["home_team_id"] = hid
        nr["away_team_id"] = aid
        out.append(nr)

        # Update state AFTER prediction features are fixed
        hg, ag = float(r["home_goals"]), float(r["away_goals"])
        if hid:
            gf[(comp, hid)].append(hg)
            ga[(comp, hid)].append(ag)
            games[(comp, hid)] += 1
        if aid:
            gf[(comp, aid)].append(ag)
            ga[(comp, aid)].append(hg)
            games[(comp, aid)] += 1
        # Elo update
        if hid and aid:
            eh, ea = elo[(comp, hid)], elo[(comp, aid)]
            exp_h = 1.0 / (1.0 + 10 ** ((ea - eh) / 400.0))
            if hg > ag:
                score_h = 1.0
            elif hg < ag:
                score_h = 0.0
            else:
                score_h = 0.5
            k = 20.0
            elo[(comp, hid)] = eh + k * (score_h - exp_h)
            elo[(comp, aid)] = ea + k * ((1.0 - score_h) - (1.0 - exp_h))

    # restore original chronological order of input if needed — return kickoff order
    return out


V2_FEATURE_COLS_NM = [
    "home_goals_for_avg_l5",
    "home_goals_against_avg_l5",
    "away_goals_for_avg_l5",
    "away_goals_against_avg_l5",
    "league_avg_home_goals",
    "league_avg_away_goals",
    "home_l5_sample",
    "away_l5_sample",
    "league_sample_before_cutoff",
    "home_att_rel_l5",
    "home_def_rel_l5",
    "away_att_rel_l5",
    "away_def_rel_l5",
    "home_att_expanding",
    "home_def_expanding",
    "away_att_expanding",
    "away_def_expanding",
    "elo_home",
    "elo_away",
    "elo_diff",
    "home_games_prior",
    "away_games_prior",
    "coverage_score",
    "form_missing_rate",
    "lambda_proxy_home",
    "lambda_proxy_away",
    "comp__premier_league",
    "comp__bundesliga",
    "comp__champions_league",
    "comp__world_cup_2026",
]

V2_FEATURE_COLS_MC = V2_FEATURE_COLS_NM + [
    "implied_home",
    "implied_draw",
    "implied_away",
    "bookmaker_count",
    "market_odds_usable",
]

V1_FEATURE_COLS_NM = [
    "home_goals_for_avg_l5",
    "home_goals_against_avg_l5",
    "away_goals_for_avg_l5",
    "away_goals_against_avg_l5",
    "league_avg_home_goals",
    "league_avg_away_goals",
    "is_home",
    "home_l5_sample",
    "away_l5_sample",
    "league_sample_before_cutoff",
]

V1_FEATURE_COLS_MC = V1_FEATURE_COLS_NM + [
    "implied_home",
    "implied_draw",
    "implied_away",
    "bookmaker_count",
    "market_odds_usable",
]

"""PHASE GT-1 — Feature loading from ECSE live, odds, EGIE priors."""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

from worldcup_predictor.research.ecse_live.prediction_builder import build_odds_feature_row
from worldcup_predictor.research.ecse_live.store import get_snapshot
from worldcup_predictor.research.ecse_match_display import _load_lambda, resolve_registry_fixture_id
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution

PHASE = "GT-1"

DEFAULT_EARLY_SHARE = 0.43


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (name,)
        ).fetchone()
    )


def _implied(odd: float | None) -> float | None:
    if odd is None or odd <= 1.0:
        return None
    return 1.0 / float(odd)


def _poisson_p00(lambda_home: float, lambda_away: float) -> float:
    return math.exp(-max(lambda_home + lambda_away, 1e-9))


def _p00_from_distribution(lambda_home: float, lambda_away: float) -> float:
    dist = generate_score_distribution(lambda_home, lambda_away)
    for row in dist:
        if int(row.get("home_goals", -1)) == 0 and int(row.get("away_goals", -1)) == 0:
            return float(row.get("probability") or 0.0)
    return _poisson_p00(lambda_home, lambda_away)


def _early_share_from_ranges(range_probs: dict[str, float]) -> float | None:
    if not range_probs:
        return None
    early = float(range_probs.get("0-15") or 0) + float(range_probs.get("16-30") or 0)
    late = sum(
        float(range_probs.get(k) or 0)
        for k in ("31-45+", "46-60", "61-75", "76-90+")
    )
    total = early + late
    if total <= 0:
        return None
    return early / total


def _league_early_share_from_history(conn: sqlite3.Connection, competition_key: str) -> float | None:
    if not _table_exists(conn, "fixture_goal_events"):
        return None
    try:
        rows = conn.execute(
            """
            SELECT minute FROM fixture_goal_events
            WHERE competition_key = ? AND minute IS NOT NULL AND minute > 0
            ORDER BY id DESC
            LIMIT 400
            """,
            (competition_key,),
        ).fetchall()
    except sqlite3.OperationalError:
        return None
    if len(rows) < 30:
        return None
    early = sum(1 for r in rows if int(r["minute"]) <= 30)
    return early / len(rows)


def _egie_range_prior(conn: sqlite3.Connection, fixture_id: int) -> dict[str, float] | None:
    """Read EGIE/goal_timing range probs from SQLite shadow if present."""
    if not _table_exists(conn, "goal_timing_prediction_shadow"):
        return None
    try:
        row = conn.execute(
            """
            SELECT range_probs_json FROM goal_timing_prediction_shadow
            WHERE fixture_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (int(fixture_id),),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row or not row["range_probs_json"]:
        return None
    try:
        data = json.loads(row["range_probs_json"])
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(data, dict):
        return {str(k): float(v) for k, v in data.items() if v is not None}
    return None


def load_fixture_context(
    conn: sqlite3.Connection,
    fixture_id: int,
    *,
    home_team: str | None = None,
    away_team: str | None = None,
) -> dict[str, Any]:
    """Assemble all inputs for goal-timing split prediction."""
    snapshot = get_snapshot(conn, fixture_id)
    fx = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, competition_key
        FROM fixtures WHERE fixture_id = ?
        """,
        (int(fixture_id),),
    ).fetchone()

    home = home_team or (snapshot or {}).get("home_team") or (dict(fx)["home_team"] if fx else "")
    away = away_team or (snapshot or {}).get("away_team") or (dict(fx)["away_team"] if fx else "")
    kickoff = (snapshot or {}).get("kickoff_utc") or (dict(fx)["kickoff_utc"] if fx else None)
    competition_key = (snapshot or {}).get("competition_key") or (
        dict(fx)["competition_key"] if fx else "world_cup_2026"
    )

    resolved = resolve_registry_fixture_id(conn, fixture_id)
    registry_id = resolved.get("registry_fixture_id")

    lambda_home: float | None = None
    lambda_away: float | None = None
    lambda_source = "missing"
    data_quality = 0.0

    if snapshot:
        lambda_home = float(snapshot.get("lambda_home") or 0) or None
        lambda_away = float(snapshot.get("lambda_away") or 0) or None
        data_quality = float(snapshot.get("data_quality_score") or 0)
        lambda_source = "ecse_live_snapshot"

    if (lambda_home is None or lambda_away is None) and registry_id is not None:
        lambdas = _load_lambda(conn, registry_id)
        if lambdas:
            lambda_home = float(lambdas["lambda_home"])
            lambda_away = float(lambdas["lambda_away"])
            data_quality = max(data_quality, float(lambdas["data_quality_score"]))
            lambda_source = "ecse_lambda_features"

    odds_row = build_odds_feature_row(conn, fixture_id)
    if lambda_home is None or lambda_away is None:
        if odds_row:
            from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas

            feat = extract_lambdas(odds_row)
            if feat:
                lambda_home = float(feat["lambda_home"])
                lambda_away = float(feat["lambda_away"])
                data_quality = max(data_quality, float(feat.get("data_quality_score") or 0.35))
                lambda_source = "odds_extracted_lambda"

    early_share = DEFAULT_EARLY_SHARE
    early_source = "default_prior"
    egie_ranges = _egie_range_prior(conn, fixture_id)
    if egie_ranges:
        es = _early_share_from_ranges(egie_ranges)
        if es is not None:
            early_share = es
            early_source = "egie_range_prior"
    else:
        hist = _league_early_share_from_history(conn, competition_key)
        if hist is not None:
            early_share = hist
            early_source = "historical_goal_events"

    odds_signals: dict[str, float | None] = {}
    if odds_row:
        odds_signals = {
            "ft_home_implied": _implied(odds_row.get("ft_home_closing")),
            "ft_draw_implied": _implied(odds_row.get("ft_draw_closing")),
            "ft_away_implied": _implied(odds_row.get("ft_away_closing")),
            "ou_over_15_implied": _implied(odds_row.get("ou_over_15_closing")),
            "ou_under_15_implied": _implied(odds_row.get("ou_under_15_closing")),
            "ou_over_25_implied": _implied(odds_row.get("ou_over_25_closing")),
            "ou_under_25_implied": _implied(odds_row.get("ou_under_25_closing")),
            "btts_yes_implied": _implied(odds_row.get("btts_yes_closing")),
            "btts_no_implied": _implied(odds_row.get("btts_no_closing")),
        }

    has_lambda = lambda_home is not None and lambda_away is not None and lambda_home > 0 and lambda_away > 0
    has_odds = any(v is not None for v in odds_signals.values())
    sufficient = has_lambda or (has_odds and odds_signals.get("ft_home_implied") is not None)

    return {
        "fixture_id": int(fixture_id),
        "home_team": home,
        "away_team": away,
        "kickoff_utc": kickoff,
        "competition_key": competition_key,
        "registry_fixture_id": registry_id,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "lambda_source": lambda_source,
        "data_quality_score": round(data_quality, 4),
        "early_share": early_share,
        "early_share_source": early_source,
        "odds_signals": odds_signals,
        "has_sufficient_data": sufficient,
        "snapshot_present": snapshot is not None,
        "odds_row_present": odds_row is not None,
    }

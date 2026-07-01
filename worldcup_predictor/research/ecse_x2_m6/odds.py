"""PHASE ECSE-X2-M6 — Odds / home_prob extraction for live fixtures."""

from __future__ import annotations

import sqlite3
from typing import Any

from worldcup_predictor.research.ecse_live.prediction_builder import build_odds_feature_row
from worldcup_predictor.research.ecse_x2_m2.prob_features import build_prob_map


def _coverage_from_prediction(prediction: dict[str, Any]) -> int:
    raw = prediction.get("raw_features") or {}
    cov = raw.get("coverage")
    if isinstance(cov, dict):
        return int(cov.get("feature_coverage_count") or cov.get("count") or 0)
    if isinstance(cov, (int, float)):
        return int(cov)
    odds_row = raw.get("odds_row") or {}
    n = sum(1 for k, v in odds_row.items() if v is not None and str(k).endswith("_closing"))
    return max(n, 1 if odds_row.get("ft_home_closing") else 0)


def resolve_odds_snapshot_id(conn: sqlite3.Connection, fixture_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM odds_snapshots WHERE fixture_id = ? ORDER BY id DESC LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    return int(row["id"]) if row else None


def build_probs_for_fixture(
    conn: sqlite3.Connection,
    fixture_id: int,
    prediction: dict[str, Any] | None = None,
) -> tuple[dict[str, float | None], int, int | None]:
    """Return (probs, coverage, odds_snapshot_id)."""
    prediction = prediction or {}
    raw = prediction.get("raw_features") or {}
    odds_row = dict(raw.get("odds_row") or {})
    if not odds_row.get("ft_home_closing"):
        fetched = build_odds_feature_row(conn, fixture_id)
        if fetched:
            odds_row = fetched
    if not odds_row:
        return {}, 0, resolve_odds_snapshot_id(conn, fixture_id)

    probs = build_prob_map(odds_row)
    coverage = _coverage_from_prediction(prediction) or max(
        1, sum(1 for v in odds_row.values() if v is not None)
    )
    snap_id = resolve_odds_snapshot_id(conn, fixture_id)
    return probs, coverage, snap_id

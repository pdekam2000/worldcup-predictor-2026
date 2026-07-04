"""Load ECSE candidate pools and resolve actual-score rank — read-only."""

from __future__ import annotations

import sqlite3
from typing import Any

from worldcup_predictor.research.ecse_match_display import resolve_registry_fixture_id
from worldcup_predictor.research.ecse_rerank.features import parse_top10


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return row is not None


def load_snapshot_top10(raw: Any) -> list[dict[str, Any]]:
    return sorted(parse_top10(raw), key=lambda x: x.get("rank", 99))


def load_distribution_ranks(
    conn: sqlite3.Connection,
    registry_fixture_id: int | None,
    *,
    limit: int = 65,
) -> list[dict[str, Any]]:
    if registry_fixture_id is None or not _table_exists(conn, "ecse_score_distributions"):
        return []
    rows = conn.execute(
        """
        SELECT scoreline, probability, rank, home_goals, away_goals, lambda_home, lambda_away
        FROM ecse_score_distributions
        WHERE registry_fixture_id = ?
        ORDER BY rank
        LIMIT ?
        """,
        (registry_fixture_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def find_rank(actual: str | None, ranked_lines: list[str]) -> int | None:
    if not actual or not ranked_lines:
        return None
    norm = str(actual).replace(":", "-")
    try:
        return ranked_lines.index(norm) + 1
    except ValueError:
        return None


def find_rank_in_distribution(actual: str | None, dist_rows: list[dict[str, Any]]) -> int | None:
    if not actual:
        return None
    norm = str(actual).replace(":", "-")
    for row in dist_rows:
        if row.get("scoreline") == norm:
            return int(row.get("rank") or 0) or None
    return None


def build_coverage_record(
    *,
    actual: str | None,
    snapshot_top10: list[dict[str, Any]],
    dist_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    snap_lines = [c["scoreline"] for c in snapshot_top10]
    dist_lines = [r["scoreline"] for r in dist_rows]
    full_lines = dist_lines if dist_lines else snap_lines

    rank_snap = find_rank(actual, snap_lines)
    rank_dist = find_rank_in_distribution(actual, dist_rows) if dist_rows else rank_snap
    rank_full = rank_dist or find_rank(actual, full_lines)

    top5_snap = snap_lines[:5]
    top10_snap = snap_lines[:10]

    dist_top20_lines = [r["scoreline"] for r in dist_rows if int(r.get("rank") or 99) <= 20]

    lambdas = {}
    if dist_rows:
        lambdas = {
            "lambda_home": dist_rows[0].get("lambda_home"),
            "lambda_away": dist_rows[0].get("lambda_away"),
        }

    return {
        "snapshot_top5": top5_snap,
        "snapshot_top10": top10_snap,
        "distribution_top20": dist_top20_lines,
        "distribution_full_count": len(dist_rows),
        "rank_in_snapshot": rank_snap,
        "rank_in_distribution": rank_dist,
        "rank_effective": rank_full,
        "in_top3_snapshot": actual in snap_lines[:3] if actual else False,
        "in_top5_snapshot": actual in top5_snap if actual else False,
        "in_top10_snapshot": actual in top10_snap if actual else False,
        "in_top20_distribution": actual in dist_top20_lines if actual and dist_top20_lines else None,
        "in_full_distribution": rank_full is not None,
        "lambdas": lambdas,
    }

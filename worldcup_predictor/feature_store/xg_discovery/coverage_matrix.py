"""Build XG_COVERAGE_MATRIX from discovery season rows."""

from __future__ import annotations

from typing import Any


def build_coverage_matrix(season_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matrix: list[dict[str, Any]] = []
    for row in season_rows:
        total = int(row.get("total_fixtures") or 0)
        with_xg = int(row.get("fixtures_with_xg") or 0)
        sampled = int(row.get("fixtures_sampled") or 0)
        sample_with = int(row.get("sample_with_xg") or 0)
        matrix.append(
            {
                "league": row.get("league_name") or row.get("league_key"),
                "league_id": row.get("league_id"),
                "season": row.get("season_name") or row.get("season_id"),
                "season_id": row.get("season_id"),
                "fixtures": total,
                "fixtures_sampled": sampled,
                "fixtures_with_xg": with_xg,
                "sample_with_xg": sample_with,
                "sample_coverage_pct": round(100.0 * sample_with / sampled, 2) if sampled else None,
                "coverage_pct": round(100.0 * with_xg / total, 2) if total else None,
                "team_xg": int(row.get("team_xg_count") or 0),
                "player_xg": int(row.get("player_xg_count") or 0),
                "xgot": int(row.get("xgot_count") or 0),
                "unknown": int(row.get("unknown_metric_count") or 0),
                "estimation_method": row.get("estimation_method", "sample_extrapolation"),
            }
        )
    return matrix

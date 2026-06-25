"""Build PRESSURE_COVERAGE_MATRIX from season audit rows."""

from __future__ import annotations

from typing import Any


def build_pressure_coverage_matrix(season_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matrix: list[dict[str, Any]] = []
    for row in season_rows:
        total = int(row.get("total_fixtures") or 0)
        with_p = int(row.get("fixtures_with_pressure") or 0)
        sampled = int(row.get("fixtures_sampled") or 0)
        sample_with = int(row.get("sample_with_pressure") or 0)
        matrix.append(
            {
                "league": row.get("league_name") or row.get("league_key"),
                "league_id": row.get("league_id"),
                "season": row.get("season_name") or row.get("season_id"),
                "season_id": row.get("season_id"),
                "fixtures": total,
                "fixtures_sampled": sampled,
                "fixtures_with_pressure": with_p,
                "sample_with_pressure": sample_with,
                "coverage_pct": round(100.0 * with_p / total, 2) if total else None,
                "sample_coverage_pct": round(100.0 * sample_with / sampled, 2) if sampled else None,
                "minute_level": row.get("minute_level", False),
                "live_capable": row.get("live_capable", False),
                "historical_capable": row.get("historical_capable", False),
                "quality_score": row.get("quality_score"),
                "avg_minutes_covered": row.get("avg_minutes_covered"),
                "avg_rows_per_fixture": row.get("avg_rows_per_fixture"),
                "estimation_method": row.get("estimation_method", "sample_extrapolation"),
            }
        )
    return matrix

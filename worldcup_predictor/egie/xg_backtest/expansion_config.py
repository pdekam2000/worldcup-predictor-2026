"""Season/league discovery for Phase 54F-6 expanded xG dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Priority leagues with proven xG (Phase 54F-3 matrix)
PRIORITY_LEAGUES: dict[int, str] = {
    732: "world_cup",
    2: "champions_league",
    5: "europa_league",
    2286: "conference_league",
}

INVESTIGATE_LEAGUES: dict[int, str] = {
    1326: "euro_championship",
    1538: "nations_league",
    1325: "euro_qualification",
}

COVERAGE_MATRIX_PATH = Path("artifacts/phase54f3_xg_discovery/XG_COVERAGE_MATRIX.json")

# Backfill targets: (league_id, season_label, season_id)
EXPANSION_TARGETS: list[tuple[int, str, int]] = [
    (732, "2026", 26618),
    (2, "2024/2025", 23619),
    (2, "2025/2026", 25580),
    (5, "2024/2025", 23620),
    (5, "2025/2026", 25582),
    (2286, "2025/2026", 25581),
]


def load_coverage_matrix(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or COVERAGE_MATRIX_PATH
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def eligible_seasons(
    *,
    min_coverage_pct: float = 30.0,
    max_coverage_pct_skip: float = 10.0,
    include_investigate: bool = True,
) -> list[dict[str, Any]]:
    """
    Return league-season rows with coverage >= min_coverage_pct.

    Rows with coverage < max_coverage_pct_skip are excluded unless league is priority.
    """
    rows = load_coverage_matrix()
    out: list[dict[str, Any]] = []
    allowed_leagues = set(PRIORITY_LEAGUES) | (set(INVESTIGATE_LEAGUES) if include_investigate else set())

    for row in rows:
        lid = int(row.get("league_id") or 0)
        if lid not in allowed_leagues:
            continue
        cov = row.get("coverage_pct")
        if cov is None:
            continue
        pct = float(cov)
        if pct < min_coverage_pct:
            if pct >= max_coverage_pct_skip and lid in INVESTIGATE_LEAGUES:
                row = {**row, "included": False, "skip_reason": f"coverage_{pct}_below_{min_coverage_pct}"}
                out.append(row)
            continue
        sid = int(row.get("season_id") or 0)
        season_name = str(row.get("season") or "")
        if sid <= 0:
            continue
        # Recent years only (2024+)
        year_tokens = [int(p) for p in season_name.replace("/", " ").split() if p.isdigit()]
        if year_tokens and max(year_tokens) < 2024 and lid != 732:
            continue
        out.append(
            {
                **row,
                "included": True,
                "competition_key": PRIORITY_LEAGUES.get(lid) or INVESTIGATE_LEAGUES.get(lid, f"league_{lid}"),
            }
        )
    return out


def expansion_backfill_targets() -> list[dict[str, Any]]:
    """Canonical backfill jobs for Phase 54F-6."""
    targets: list[dict[str, Any]] = []
    for league_id, season_label, season_id in EXPANSION_TARGETS:
        targets.append(
            {
                "league_id": league_id,
                "season_label": season_label,
                "season_id": season_id,
                "competition_key": PRIORITY_LEAGUES[league_id],
                "max_calls": 350,
                "max_pages": 25,
            }
        )
    return targets

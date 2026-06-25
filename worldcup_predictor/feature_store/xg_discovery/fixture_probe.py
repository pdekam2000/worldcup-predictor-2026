"""Probe Sportmonks fixture payloads for xG metrics (read-only audit)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from worldcup_predictor.feature_store.xg_discovery.xg_fixture_parser import classify_metric_key
from worldcup_predictor.providers.sportmonks_xg_extraction import (
    _expected_rows_from_fixture,
    _type_id_from_row,
    parse_sportmonks_xg_match,
)

_XG_TYPE_IDS = frozenset({5304, 5305, 7939, 7940, 7941, 7942, 7943, 7944, 7945, 9684, 9685, 9686, 9687})


def _rows_from_block(block: Any) -> list[dict[str, Any]]:
    if isinstance(block, dict):
        nested = block.get("expected") or block.get("data")
        if isinstance(nested, list):
            return [r for r in nested if isinstance(r, dict)]
    elif isinstance(block, list):
        return [r for r in block if isinstance(r, dict)]
    return []


def probe_fixture_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Classify xG-related metrics present in a fixture payload."""
    counts: Counter[str] = Counter()
    unknown: Counter[str] = Counter()
    has_xgfixture = any(raw.get(k) is not None for k in ("xGFixture", "xgfixture"))
    has_statistics = bool(raw.get("statistics"))
    has_lineup_xg = any(
        isinstance(lu, dict) and (lu.get("xGLineup") or lu.get("xgLineup"))
        for lu in (raw.get("lineups") or [])
    )

    for row in _expected_rows_from_fixture(raw):
        metric = classify_metric_key(row)
        tid = _type_id_from_row(row)
        if metric:
            counts[metric] += 1
        elif tid in _XG_TYPE_IDS:
            unknown[f"type_{tid}"] += 1
        elif tid is not None:
            unknown[f"non_xg_type_{tid}"] += 1

    for lu in raw.get("lineups") or []:
        if not isinstance(lu, dict):
            continue
        for row in lu.get("xGLineup") or lu.get("xgLineup") or []:
            if not isinstance(row, dict):
                continue
            metric = classify_metric_key(row)
            if metric == "xg":
                counts["player_xg"] += 1
            elif metric == "xgot":
                counts["player_xgot"] += 1
            elif metric:
                counts[f"player_{metric}"] += 1

    parsed = parse_sportmonks_xg_match(raw)
    team = parsed.get("team") or {}
    team_xg = team.get("home_xg") is not None or team.get("away_xg") is not None
    team_xgot = team.get("home_xgot") is not None or team.get("away_xgot") is not None

    has_team_xg = team_xg or counts.get("xg", 0) > 0
    has_any_xg = has_team_xg or counts.get("player_xg", 0) > 0 or counts.get("xgot", 0) > 0

    return {
        "has_xgfixture_block": has_xgfixture,
        "has_statistics": has_statistics,
        "has_lineup_xg": has_lineup_xg,
        "has_team_xg": bool(has_team_xg),
        "has_team_xgot": bool(team_xgot or counts.get("xgot", 0) > 0),
        "has_player_xg": counts.get("player_xg", 0) > 0,
        "has_any_xg": bool(has_any_xg),
        "metric_counts": dict(counts),
        "unknown_type_counts": dict(unknown),
        "parse_source": team.get("source"),
        "expected_row_count": len(_expected_rows_from_fixture(raw)),
    }

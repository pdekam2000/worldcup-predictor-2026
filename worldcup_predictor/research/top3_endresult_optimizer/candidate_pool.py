"""Build candidate pool from ECSE + WDE signal lines — read-only."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.top3_endresult_optimizer.features import (
    match_archetype,
    winner_side,
)

SIGNAL_LINES: dict[str, list[str]] = {
    "favorite_btts_yes": ["2-1", "3-1", "3-2", "1-1"],
    "favorite_under_btts_no": ["1-0", "2-0", "3-0", "0-0"],
    "favorite_over_btts_yes": ["2-1", "3-1", "3-2", "2-2"],
    "favorite_over_btts_no": ["2-0", "3-0", "4-0", "3-1"],
    "draw_risk": ["1-1", "2-2", "0-0", "1-0", "0-1"],
    "underdog_away": ["0-1", "1-2", "0-2", "1-1"],
    "balanced": ["1-0", "1-1", "2-1", "0-1"],
}


def _rank_map(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for c in candidates:
        line = c["scoreline"]
        if line not in out or c.get("rank", 99) < out[line].get("rank", 99):
            out[line] = dict(c)
    return out


def build_candidate_pool(
    *,
    top10: list[dict[str, Any]],
    top5_lines: list[str] | None = None,
    wde: dict[str, Any],
) -> dict[str, Any]:
    """Merge ECSE ranked candidates with optional WDE signal lines."""
    ecse_sorted = sorted(top10, key=lambda x: x.get("rank", 99))
    ecse_map = _rank_map(ecse_sorted)
    top5 = top5_lines or [c["scoreline"] for c in ecse_sorted[:5]]

    archetype = match_archetype(wde)
    signal = list(SIGNAL_LINES.get(archetype, SIGNAL_LINES["balanced"]))

    # Filter signal lines to preserve winner direction when WDE pick is clear
    pick = wde.get("pick_1x2")
    if pick in ("home_win", "away_win"):
        filtered = [ln for ln in signal if winner_side(ln) == pick or winner_side(ln) == "draw"]
        if filtered:
            signal = filtered
    elif pick == "draw":
        signal = [ln for ln in signal if winner_side(ln) == "draw"] or signal

    pool_lines: list[str] = []
    for ln in [c["scoreline"] for c in ecse_sorted]:
        if ln not in pool_lines:
            pool_lines.append(ln)
    for ln in signal:
        if ln not in pool_lines:
            pool_lines.append(ln)

    pool: list[dict[str, Any]] = []
    for i, ln in enumerate(pool_lines):
        base = ecse_map.get(ln)
        if base:
            pool.append(base)
        else:
            pool.append(
                {
                    "scoreline": ln,
                    "probability": 0.01,
                    "rank": 50 + i,
                    "source": "wde_signal",
                }
            )

    return {
        "top10": ecse_sorted,
        "top5": top5,
        "pool": pool,
        "ecse_map": ecse_map,
        "signal_lines": signal,
        "archetype": archetype,
    }

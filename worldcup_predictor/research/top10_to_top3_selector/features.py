"""Per-candidate feature rows from ECSE Top10 — read-only."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_rerank.features import (
    is_btts,
    is_clean_sheet,
    parse_scoreline,
    total_goals,
    winner_side,
)
from worldcup_predictor.research.top3_endresult_optimizer.features import draw_risk_score

PHASE = "TOP10-TO-TOP3-SELECTOR-1"

TAIL_INJECTION_LINES = ("3-2", "2-3", "4-1", "1-4", "4-2", "2-4")


def _norm_btts(val: str | None) -> str | None:
    if not val:
        return None
    v = str(val).lower().replace("btts_", "")
    return v if v in ("yes", "no") else None


def _norm_ou(val: str | None) -> str | None:
    if not val:
        return None
    v = str(val).lower()
    if "over" in v:
        return "over_2_5"
    if "under" in v:
        return "under_2_5"
    return v


def _winner_label(line: str) -> str:
    side = winner_side(line)
    if side == "home_win":
        return "home"
    if side == "away_win":
        return "away"
    return "draw"


def _alignment(actual: str, predicted: str | None) -> str | None:
    if predicted is None:
        return None
    return "yes" if actual == predicted else "no"


def build_candidate_features(
    *,
    fixture_id: int,
    match: str,
    top10: list[dict[str, Any]],
    wde: dict[str, Any],
    knockout: bool,
    odds_freshness: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    pick = wde.get("pick_1x2")
    btts_pick = _norm_btts(wde.get("pick_btts"))
    ou_pick = _norm_ou(wde.get("pick_ou25"))
    draw_risk = draw_risk_score(wde)
    freshness = odds_freshness or {}
    top_prob = max((float(c.get("probability") or 0) for c in top10), default=0.01) or 0.01

    rows: list[dict[str, Any]] = []
    for c in sorted(top10, key=lambda x: x.get("rank", 99)):
        line = c["scoreline"]
        parsed = parse_scoreline(line)
        tg = total_goals(line) or 0
        gd = abs(parsed[0] - parsed[1]) if parsed else 0
        side = winner_side(line)
        prob = float(c.get("probability") or 0)
        rank = int(c.get("rank") or 0)

        rows.append(
            {
                "fixture_id": fixture_id,
                "match": match,
                "scoreline": line,
                "original_ecse_rank": rank,
                "total_goals": tg,
                "goal_difference": gd,
                "winner_direction": _winner_label(line),
                "btts": "yes" if is_btts(line) else "no",
                "over_25": "yes" if tg > 2 else "no",
                "clean_sheet": "yes" if is_clean_sheet(line) else "no",
                "favorite_direction_match": _alignment(
                    side, pick if pick in ("home_win", "away_win", "draw") else None
                ),
                "wde_1x2_alignment": _alignment(side, pick),
                "wde_btts_alignment": _alignment("yes" if is_btts(line) else "no", btts_pick),
                "wde_ou25_alignment": _alignment("over_2_5" if tg > 2 else "under_2_5", ou_pick),
                "draw_risk_alignment": "yes" if draw_risk >= 0.35 and side == "draw" else "no",
                "knockout": knockout,
                "odds_freshness_status": freshness.get("freshness_flag"),
                "candidate_probability": round(prob, 6),
                "candidate_rank_probability_decay": round(prob / top_prob, 4) if top_prob else 0,
                "injected_tail_candidate": False,
            }
        )
    return rows


def inject_tail_candidates(
    candidates: list[dict[str, Any]],
    wde: dict[str, Any],
    *,
    fixture_id: int,
    match: str,
    knockout: bool,
    odds_freshness: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Shadow-only tail injection when WDE Over+BTTS and lines missing."""
    btts = _norm_btts(wde.get("pick_btts"))
    ou = _norm_ou(wde.get("pick_ou25"))
    pick = wde.get("pick_1x2")
    if btts != "yes" or ou != "over_2_5":
        return list(candidates)

    existing = {r["scoreline"] for r in candidates}
    out = list(candidates)
    rank_base = 100
    for i, line in enumerate(TAIL_INJECTION_LINES):
        if line in existing:
            continue
        side = winner_side(line)
        if pick in ("home_win", "away_win") and side not in (pick, "draw"):
            continue
        parsed = parse_scoreline(line)
        tg = total_goals(line) or 0
        out.append(
            {
                "fixture_id": fixture_id,
                "match": match,
                "scoreline": line,
                "original_ecse_rank": rank_base + i,
                "total_goals": tg,
                "goal_difference": abs(parsed[0] - parsed[1]) if parsed else 0,
                "winner_direction": _winner_label(line),
                "btts": "yes",
                "over_25": "yes",
                "clean_sheet": "no",
                "favorite_direction_match": _alignment(side, pick),
                "wde_1x2_alignment": _alignment(side, pick),
                "wde_btts_alignment": "yes",
                "wde_ou25_alignment": "yes",
                "draw_risk_alignment": "no",
                "knockout": knockout,
                "odds_freshness_status": (odds_freshness or {}).get("freshness_flag"),
                "candidate_probability": 0.005,
                "candidate_rank_probability_decay": 0.01,
                "injected_tail_candidate": True,
            }
        )
    return out

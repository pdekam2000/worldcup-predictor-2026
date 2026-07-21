"""ECSE direction derivation and goal-pattern helpers."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.forward_evaluation.context import scoreline_side
from worldcup_predictor.research.wde_ecse_conflict.detect import market_implied_direction
from worldcup_predictor.research.wde_vs_ecse_forensics.directions import (
    majority_direction,
    mass_winner,
    norm_dir,
    prob01,
)


def ranks_from_ecse(ecse: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not ecse:
        return []
    ranks: list[dict[str, Any]] = []
    for i in range(1, 6):
        t = ecse.get(f"top{i}")
        if isinstance(t, dict) and t.get("score"):
            ranks.append(
                {
                    "rank": i,
                    "score": str(t.get("score")),
                    "probability": t.get("probability"),
                    "direction": scoreline_side(str(t.get("score"))),
                }
            )
        elif isinstance(t, str) and t:
            ranks.append({"rank": i, "score": t, "probability": None, "direction": scoreline_side(t)})
    if len(ranks) < 5:
        for i, sc in enumerate(ecse.get("scores") or [], start=1):
            if i > 5:
                break
            if not any(r.get("score") == str(sc) for r in ranks):
                ranks.append({"rank": i, "score": str(sc), "probability": None, "direction": scoreline_side(str(sc))})
    return ranks[:5]


def derive_directions(
    *,
    wde: dict[str, Any] | None,
    ecse: dict[str, Any] | None,
    odds_home: Any,
    odds_draw: Any,
    odds_away: Any,
) -> dict[str, Any]:
    ranks = ranks_from_ecse(ecse)
    maj3 = majority_direction(ranks, 3)
    maj5 = majority_direction(ranks, 5)
    top1 = ranks[0] if ranks else {}
    top1_dir = norm_dir(top1.get("direction")) or scoreline_side(str(top1.get("score") or ""))
    wde_dir = norm_dir((wde or {}).get("decision"))
    ft_dir = norm_dir((wde or {}).get("ft_marginal"))
    market = market_implied_direction(odds_home, odds_draw, odds_away)

    votes = maj5.get("votes_by_direction") or {}
    mass = maj5.get("mass_by_direction") or {}
    total_votes = sum(int(v) for v in votes.values()) or 0
    top_vote = max(votes.values()) if votes else 0
    dominance = round(top_vote / total_votes, 6) if total_votes else None

    label5 = maj5.get("label")
    if label5 == "direction_tie" or maj5.get("tied"):
        top5_maj = None
        top5_label = "ECSE_DIRECTION_TIE"
    else:
        top5_maj = maj5.get("majority")
        top5_label = top5_maj

    label3 = maj3.get("label")
    if label3 == "direction_tie" or maj3.get("tied"):
        top3_maj = None
        top3_label = "ECSE_DIRECTION_TIE"
    else:
        top3_maj = maj3.get("majority")
        top3_label = top3_maj

    return {
        "wde_decision": wde_dir,
        "ft_marginal": ft_dir,
        "market_direction": market,
        "ecse_top1_direction": top1_dir,
        "ecse_top3_majority": top3_maj,
        "ecse_top3_majority_label": top3_label,
        "ecse_top5_majority": top5_maj,
        "ecse_top5_majority_label": top5_label,
        "top3_mass_by_direction": maj3.get("mass_by_direction"),
        "top5_mass_by_direction": mass,
        "top5_votes_by_direction": votes,
        "directional_dominance_ratio": dominance,
        "direction_mass_winner": mass_winner(mass),
        "ranks": ranks,
        "ecse_direction_tie": top5_label == "ECSE_DIRECTION_TIE",
    }


def goal_alignment(ecse: dict[str, Any] | None, btts: dict[str, Any] | None, ou25: dict[str, Any] | None) -> dict[str, Any]:
    ranks = ranks_from_ecse(ecse)
    scores = [str(r.get("score") or "") for r in ranks]
    clean = 0
    both = 0
    overs = 0
    unders = 0
    for sc in scores:
        if "-" not in sc:
            continue
        try:
            h, a = [int(x) for x in sc.split("-", 1)]
        except ValueError:
            continue
        if h == 0 or a == 0:
            clean += 1
        if h > 0 and a > 0:
            both += 1
        if h + a >= 3:
            overs += 1
        else:
            unders += 1
    btts_pred = str((btts or {}).get("prediction") or "").lower()
    ou_pred = str((ou25 or {}).get("preferred_side") or "").lower()
    return {
        "btts_prediction": btts_pred or None,
        "ou25_prediction": ou_pred or None,
        "top5_clean_sheet_count": clean,
        "top5_btts_count": both,
        "top5_over25_count": overs,
        "top5_under25_count": unders,
        "ou_consistent_with_top5": (
            (ou_pred.startswith("over") and overs >= 3)
            or (ou_pred.startswith("under") and unders >= 3)
            if ou_pred
            else None
        ),
        "btts_consistent_with_top5": (
            (btts_pred in {"yes", "btts_yes"} and both >= 3)
            or (btts_pred in {"no", "btts_no"} and clean >= 3)
            if btts_pred
            else None
        ),
    }

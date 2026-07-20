"""Snapshot-to-snapshot stability comparison (pure)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_timing_experiment.hashing import as_float, as_prob


def _scores(payload: dict[str, Any]) -> list[str]:
    ecse = payload.get("ecse") or {}
    scores = ecse.get("scores") or []
    out = [str(s) for s in scores if s]
    if len(out) >= 5:
        return out[:5]
    for i in range(1, 6):
        t = ecse.get(f"top{i}") or {}
        sc = t.get("score") if isinstance(t, dict) else None
        if sc and str(sc) not in out:
            out.append(str(sc))
    return out[:5]


def _rank_map(payload: dict[str, Any]) -> dict[str, int]:
    return {sc: i + 1 for i, sc in enumerate(_scores(payload))}


def _prob_map(payload: dict[str, Any]) -> dict[str, float | None]:
    ecse = payload.get("ecse") or {}
    out: dict[str, float | None] = {}
    for i in range(1, 6):
        t = ecse.get(f"top{i}") or {}
        if isinstance(t, dict) and t.get("score"):
            out[str(t["score"])] = as_prob(t.get("probability"))
    return out


def _norm_side(v: Any) -> str:
    s = str(v or "").lower().strip()
    if s in {"1", "home", "home_win", "h"}:
        return "home_win"
    if s in {"x", "draw", "d"}:
        return "draw"
    if s in {"2", "away", "away_win", "a"}:
        return "away_win"
    return s


def _implied_probs(h: float | None, d: float | None, a: float | None) -> dict[str, float | None]:
    if None in (h, d, a) or min(h or 0, d or 0, a or 0) <= 1:
        return {"home": None, "draw": None, "away": None, "overround": None}
    raw = {"home": 1.0 / h, "draw": 1.0 / d, "away": 1.0 / a}  # type: ignore[operator]
    s = sum(raw.values())
    return {
        "home": round(raw["home"] / s, 6),
        "draw": round(raw["draw"] / s, 6),
        "away": round(raw["away"] / s, 6),
        "overround": round(s, 6),
    }


def compare_snapshots(
    from_payload: dict[str, Any],
    to_payload: dict[str, Any],
    *,
    from_class: str,
    to_class: str,
) -> dict[str, Any]:
    """Compare two research snapshot payloads; never mutates production."""
    a_scores = _scores(from_payload)
    b_scores = _scores(to_payload)
    a_set, b_set = set(a_scores), set(b_scores)
    overlap = a_set & b_set
    union = a_set | b_set
    jaccard = (len(overlap) / len(union)) if union else None

    a_wde = _norm_side((from_payload.get("wde") or {}).get("decision"))
    b_wde = _norm_side((to_payload.get("wde") or {}).get("decision"))
    a_ft = _norm_side((from_payload.get("wde") or {}).get("ft_marginal"))
    b_ft = _norm_side((to_payload.get("wde") or {}).get("ft_marginal"))
    a_top1 = a_scores[0] if a_scores else None
    b_top1 = b_scores[0] if b_scores else None

    a_rm, b_rm = _rank_map(from_payload), _rank_map(to_payload)
    rank_moves = []
    changed_positions = 0
    for sc in sorted(overlap):
        ra, rb = a_rm[sc], b_rm[sc]
        if ra != rb:
            changed_positions += 1
        rank_moves.append({"score": sc, "from_rank": ra, "to_rank": rb, "delta": rb - ra})

    a_ecse, b_ecse = from_payload.get("ecse") or {}, to_payload.get("ecse") or {}
    a_mass3, b_mass3 = as_float(a_ecse.get("top3_mass")), as_float(b_ecse.get("top3_mass"))
    a_mass5, b_mass5 = as_float(a_ecse.get("top5_mass")), as_float(b_ecse.get("top5_mass"))
    a_ent, b_ent = as_float(a_ecse.get("entropy")), as_float(b_ecse.get("entropy"))

    a_odds = from_payload.get("odds") or {}
    b_odds = to_payload.get("odds") or {}
    ah, ad, aa = as_float(a_odds.get("home")), as_float(a_odds.get("draw")), as_float(a_odds.get("away"))
    bh, bd, ba = as_float(b_odds.get("home")), as_float(b_odds.get("draw")), as_float(b_odds.get("away"))
    odds_move = {
        "home": None if ah is None or bh is None else round(bh - ah, 4),
        "draw": None if ad is None or bd is None else round(bd - ad, 4),
        "away": None if aa is None or ba is None else round(ba - aa, 4),
    }
    abs_moves = [abs(v) for v in odds_move.values() if v is not None]
    max_abs_odds = max(abs_moves) if abs_moves else None
    a_imp = _implied_probs(ah, ad, aa)
    b_imp = _implied_probs(bh, bd, ba)
    imp_move = {
        k: None
        if a_imp.get(k) is None or b_imp.get(k) is None
        else round(float(b_imp[k]) - float(a_imp[k]), 6)  # type: ignore[arg-type]
        for k in ("home", "draw", "away")
    }

    wde_changed = bool(a_wde and b_wde and a_wde != b_wde)
    top1_changed = str(a_top1 or "") != str(b_top1 or "")
    set_same = a_set == b_set and len(a_set) == 5
    order_same = a_scores == b_scores and len(a_scores) == 5
    mass5_delta = (
        round(b_mass5 - a_mass5, 6) if a_mass5 is not None and b_mass5 is not None else None
    )

    labels: list[str] = []
    if wde_changed:
        labels.append("WDE_CHANGED")
    if top1_changed:
        labels.append("TOP1_CHANGED")
    if order_same and not wde_changed:
        labels.append("FULLY_STABLE")
    elif set_same and not order_same and not top1_changed:
        labels.append("SET_STABLE_RANK_REORDERED")
    elif (not set_same) and (not top1_changed) and a_top1 and b_top1:
        labels.append("BOUNDARY_CHANGED")

    major = (
        wde_changed
        or top1_changed
        or (jaccard is not None and jaccard < 0.6)  # <3/5 overlap
        or (mass5_delta is not None and abs(mass5_delta) >= 0.05)
    )
    if major:
        labels.append("MAJOR_MODEL_MOVEMENT")

    if "FULLY_STABLE" in labels:
        primary = "FULLY_STABLE"
    elif "WDE_CHANGED" in labels:
        primary = "WDE_CHANGED"
    elif "TOP1_CHANGED" in labels:
        primary = "TOP1_CHANGED"
    elif "BOUNDARY_CHANGED" in labels:
        primary = "BOUNDARY_CHANGED"
    elif "SET_STABLE_RANK_REORDERED" in labels:
        primary = "SET_STABLE_RANK_REORDERED"
    elif "MAJOR_MODEL_MOVEMENT" in labels:
        primary = "MAJOR_MODEL_MOVEMENT"
    else:
        primary = "SET_STABLE_RANK_REORDERED" if set_same else "BOUNDARY_CHANGED"

    return {
        "from_class": from_class,
        "to_class": to_class,
        "wde_same": a_wde == b_wde if a_wde and b_wde else None,
        "wde_changed": wde_changed,
        "ft_marginal_same": a_ft == b_ft if a_ft and b_ft else None,
        "ft_marginal_changed": bool(a_ft and b_ft and a_ft != b_ft),
        "top1_same": not top1_changed,
        "top1_changed": top1_changed,
        "from_top1": a_top1,
        "to_top1": b_top1,
        "from_top5": a_scores,
        "to_top5": b_scores,
        "top5_set_overlap": len(overlap),
        "top5_jaccard": None if jaccard is None else round(jaccard, 6),
        "rank_movement": rank_moves,
        "changed_rank_positions": changed_positions,
        "scores_added": sorted(b_set - a_set),
        "scores_removed": sorted(a_set - b_set),
        "top3_mass_delta": (
            round(b_mass3 - a_mass3, 6) if a_mass3 is not None and b_mass3 is not None else None
        ),
        "top5_mass_delta": mass5_delta,
        "entropy_delta": (
            round(b_ent - a_ent, 6) if a_ent is not None and b_ent is not None else None
        ),
        "consensus_from": from_payload.get("consensus"),
        "consensus_to": to_payload.get("consensus"),
        "consensus_changed": from_payload.get("consensus") != to_payload.get("consensus"),
        "no_bet_from": from_payload.get("no_bet"),
        "no_bet_to": to_payload.get("no_bet"),
        "no_bet_changed": from_payload.get("no_bet") != to_payload.get("no_bet"),
        "odds_movement": odds_move,
        "max_abs_odds_movement": max_abs_odds,
        "implied_probability_from": a_imp,
        "implied_probability_to": b_imp,
        "implied_probability_movement": imp_move,
        "primary_stability_label": primary,
        "labels": labels,
        "research_only": True,
        "canonical": False,
        "final_decision_authority": False,
    }

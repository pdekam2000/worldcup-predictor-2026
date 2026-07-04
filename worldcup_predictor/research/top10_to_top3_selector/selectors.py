"""Top10→Top3 selection strategies — shadow only, exactly 3 picks."""

from __future__ import annotations

from typing import Any, Callable

from worldcup_predictor.research.ecse_rerank.features import is_btts, is_clean_sheet, total_goals, winner_side
from worldcup_predictor.research.top3_endresult_optimizer.features import draw_risk_score

StrategyFn = Callable[[list[dict[str, Any]], dict[str, Any]], list[str]]


def _pick(lines: list[str], n: int = 3) -> list[str]:
    out: list[str] = []
    for ln in lines:
        if ln not in out:
            out.append(ln)
        if len(out) >= n:
            break
    return out[:n]


def _rank_score(row: dict[str, Any]) -> float:
    rank = int(row.get("original_ecse_rank") or 99)
    if row.get("injected_tail_candidate"):
        return 0.5
    return max(0.0, 11 - rank)


def _market_score(row: dict[str, Any], wde: dict[str, Any], *, stale_penalty: float = 0.0) -> float:
    s = _rank_score(row) * 0.35
    if row.get("wde_1x2_alignment") == "yes":
        s += 2.5
    elif row.get("wde_1x2_alignment") == "no":
        s -= 1.5
    if row.get("wde_btts_alignment") == "yes":
        s += 2.0
    elif row.get("wde_btts_alignment") == "no":
        s -= 0.8
    if row.get("wde_ou25_alignment") == "yes":
        s += 1.8
    elif row.get("wde_ou25_alignment") == "no":
        s -= 0.6
    if row.get("draw_risk_alignment") == "yes":
        s += 1.2
    s += float(row.get("candidate_rank_probability_decay") or 0) * 2.0
    s -= stale_penalty
    return s


def _sorted_by_score(rows: list[dict[str, Any]], wde: dict[str, Any], *, stale_penalty: float = 0.0) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: -_market_score(r, wde, stale_penalty=stale_penalty))


def strategy_a_raw_top3(candidates: list[dict[str, Any]], wde: dict[str, Any]) -> list[str]:
    ecse = [r for r in candidates if not r.get("injected_tail_candidate")]
    ecse.sort(key=lambda r: r.get("original_ecse_rank", 99))
    return _pick([r["scoreline"] for r in ecse], 3)


def strategy_b_market_aligned(candidates: list[dict[str, Any]], wde: dict[str, Any]) -> list[str]:
    stale = 0.4 if any(r.get("odds_freshness_status") == "STALE_ODDS" for r in candidates) else 0.0
    ranked = _sorted_by_score(candidates, wde, stale_penalty=stale)
    selected: list[str] = []
    clean_count = 0
    for r in ranked:
        line = r["scoreline"]
        if line in selected:
            continue
        if r.get("clean_sheet") == "yes":
            if clean_count >= 1:
                continue
            clean_count += 1
        selected.append(line)
        if len(selected) >= 3:
            break
    return _pick(selected + [r["scoreline"] for r in ranked], 3)


def strategy_c_portfolio(candidates: list[dict[str, Any]], wde: dict[str, Any]) -> list[str]:
    pick = wde.get("pick_1x2")
    ranked = _sorted_by_score(candidates, wde)
    selected: list[str] = []

    for r in ranked:
        if pick and winner_side(r["scoreline"]) == pick and r["scoreline"] not in selected:
            selected.append(r["scoreline"])
            break

    for r in ranked:
        if r.get("wde_btts_alignment") == "yes" or r.get("wde_ou25_alignment") == "yes":
            if r["scoreline"] not in selected:
                selected.append(r["scoreline"])
                break

    if draw_risk_score(wde) >= 0.35:
        for r in ranked:
            if winner_side(r["scoreline"]) == "draw" and r["scoreline"] not in selected:
                selected.append(r["scoreline"])
                break

    for r in ranked:
        if len(selected) >= 3:
            break
        if r["scoreline"] not in selected:
            selected.append(r["scoreline"])
    return _pick(selected, 3)


def strategy_d_anti_clean_sheet(candidates: list[dict[str, Any]], wde: dict[str, Any]) -> list[str]:
    base = strategy_a_raw_top3(candidates, wde)
    btts = str(wde.get("pick_btts") or "").lower().replace("btts_", "")
    ou = str(wde.get("pick_ou25") or "").lower()
    ecse = sorted(
        [r for r in candidates if not r.get("injected_tail_candidate")],
        key=lambda r: r.get("original_ecse_rank", 99),
    )
    ranks_4_10 = [r for r in ecse if int(r.get("original_ecse_rank") or 99) >= 4]

    clean_in_base = sum(1 for ln in base if is_clean_sheet(ln))
    if clean_in_base < 2:
        return base
    boost_btts = btts == "yes" or btts not in ("yes", "no")
    boost_over = "over" in ou or not ou

    out = [ln for ln in base if not is_clean_sheet(ln)]
    if not any(is_clean_sheet(ln) for ln in base):
        out = list(base)
    else:
        for ln in base:
            if is_clean_sheet(ln) and not any(is_clean_sheet(x) for x in out):
                out.insert(0, ln)
                break
        if len(out) < 3:
            out = list(base[:1]) + [ln for ln in base[1:] if ln not in out]

    if boost_btts:
        for r in ranks_4_10:
            if is_btts(r["scoreline"]) and r["scoreline"] not in out:
                out = (out[:2] + [r["scoreline"]]) if len(out) >= 2 else out + [r["scoreline"]]
                break

    if boost_over:
        for r in ranks_4_10:
            if (total_goals(r["scoreline"]) or 0) >= 3 and r["scoreline"] not in out:
                if len(out) >= 3:
                    out[2] = r["scoreline"]
                else:
                    out.append(r["scoreline"])
                break

    if not any(winner_side(ln) == "draw" for ln in out):
        for r in ranks_4_10:
            if winner_side(r["scoreline"]) == "draw" and r["scoreline"] not in out:
                if len(out) >= 3:
                    out[2] = r["scoreline"]
                else:
                    out.append(r["scoreline"])
                break
    return _pick(out, 3)


def strategy_e_rank7_rescue(candidates: list[dict[str, Any]], wde: dict[str, Any]) -> list[str]:
    base = strategy_a_raw_top3(candidates, wde)
    ecse = sorted(
        [r for r in candidates if not r.get("injected_tail_candidate")],
        key=lambda r: r.get("original_ecse_rank", 99),
    )
    mid = [r for r in ecse if 4 <= int(r.get("original_ecse_rank") or 99) <= 10]
    pick = wde.get("pick_1x2")
    out = list(base)

    if not any(winner_side(ln) == "draw" for ln in out):
        draw_cands = [r for r in mid if winner_side(r["scoreline"]) == "draw"]
        if draw_cands:
            best = min(draw_cands, key=lambda r: r.get("original_ecse_rank", 99))
            idx = next((i for i, ln in enumerate(out) if is_clean_sheet(ln)), len(out) - 1)
            out[idx] = best["scoreline"]

    clean_count = sum(1 for ln in out if is_clean_sheet(ln))
    if clean_count >= 2:
        btts_cands = [r for r in mid if is_btts(r["scoreline"])]
        if pick in ("home_win", "away_win"):
            btts_cands = [r for r in btts_cands if winner_side(r["scoreline"]) in (pick, "draw")]
        if btts_cands:
            preferred = sorted(
                btts_cands,
                key=lambda r: (
                    r["scoreline"] not in {"2-1", "3-1", "1-1", "2-2", "1-2", "2-3"},
                    r.get("original_ecse_rank", 99),
                ),
            )
            line = preferred[0]["scoreline"]
            if line not in out:
                idx = next((i for i, ln in enumerate(out) if is_clean_sheet(ln) and i > 0), len(out) - 1)
                out[idx] = line

    return _pick(out, 3)


def strategy_f_hybrid(candidates: list[dict[str, Any]], wde: dict[str, Any]) -> list[str]:
    b = strategy_b_market_aligned(candidates, wde)
    d = strategy_d_anti_clean_sheet(candidates, wde)
    e = strategy_e_rank7_rescue(candidates, wde)
    merged: list[str] = []
    for ln in e + d + b:
        if ln not in merged:
            merged.append(ln)
        if len(merged) >= 3:
            break
    return _pick(merged, 3)


def strategy_f_hybrid_with_tail(candidates: list[dict[str, Any]], wde: dict[str, Any]) -> list[str]:
    return strategy_f_hybrid(candidates, wde)


STRATEGIES: dict[str, dict[str, Any]] = {
    "A_raw_top3": {"fn": strategy_a_raw_top3, "label": "Raw ECSE Top3 (ranks 1-3)"},
    "B_market_aligned": {"fn": strategy_b_market_aligned, "label": "Market-aligned Top3"},
    "C_portfolio_coverage": {"fn": strategy_c_portfolio, "label": "Portfolio coverage Top3"},
    "D_anti_clean_sheet": {"fn": strategy_d_anti_clean_sheet, "label": "Anti clean-sheet bias"},
    "E_rank7_rescue": {"fn": strategy_e_rank7_rescue, "label": "Rank 6-10 rescue"},
    "F_hybrid_best": {"fn": strategy_f_hybrid, "label": "Hybrid best"},
    "F_hybrid_tail_injection": {"fn": strategy_f_hybrid_with_tail, "label": "Hybrid + shadow tail injection pool"},
}


def select_top3(strategy_id: str, candidates: list[dict[str, Any]], wde: dict[str, Any]) -> list[str]:
    spec = STRATEGIES[strategy_id]
    lines = spec["fn"](candidates, wde)
    ecse_fallback = [r["scoreline"] for r in sorted(candidates, key=lambda r: r.get("original_ecse_rank", 99))]
    if len(lines) < 3:
        lines = _pick(lines + ecse_fallback, 3)
    if len(lines) != 3:
        raise ValueError(f"Strategy {strategy_id} returned {len(lines)} lines")
    return lines

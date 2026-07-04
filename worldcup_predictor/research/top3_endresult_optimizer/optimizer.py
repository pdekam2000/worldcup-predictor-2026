"""Shadow Top3 portfolio selection strategies — exactly 3 candidates per fixture."""

from __future__ import annotations

from typing import Any, Callable

from worldcup_predictor.research.top3_endresult_optimizer.features import (
    draw_risk_score,
    is_btts,
    is_clean_sheet,
    match_archetype,
    total_goals,
    winner_side,
)

StrategyFn = Callable[[dict[str, Any], dict[str, Any]], list[str]]

ARCHETYPE_LINES: dict[str, list[str]] = {
    "favorite_under_btts_no": ["1-0", "2-0", "3-0"],
    "favorite_over_btts_yes": ["2-1", "3-1", "3-2"],
    "favorite_over_btts_no": ["2-0", "3-0", "4-0"],
    "draw_risk": ["1-1", "2-2", "1-0"],
    "underdog_away": ["0-1", "1-2", "0-2"],
    "favorite_btts_yes": ["2-1", "3-1", "3-2"],
    "balanced": ["1-1", "2-1", "1-0"],
}


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


def _pick_exact(lines: list[str], n: int = 3, *, fallback: list[str] | None = None) -> list[str]:
    out: list[str] = []
    for ln in lines:
        if ln not in out:
            out.append(ln)
        if len(out) >= n:
            break
    if len(out) < n and fallback:
        for ln in fallback:
            if ln not in out:
                out.append(ln)
            if len(out) >= n:
                break
    return out[:n]


def _score_consistency(line: str, wde: dict[str, Any]) -> float:
    score = 0.0
    pick = wde.get("pick_1x2")
    btts = _norm_btts(wde.get("pick_btts"))
    ou = _norm_ou(wde.get("pick_ou25"))
    side = winner_side(line)
    tg = total_goals(line) or 0

    if pick and side:
        if side == pick:
            score += 3.0
        elif pick != "draw" and side == "draw":
            score += 0.5 if draw_risk_score(wde) >= 0.35 else -1.0
        else:
            score -= 2.0

    if btts == "yes":
        score += 2.0 if is_btts(line) else -1.5
    elif btts == "no":
        score += 1.5 if is_clean_sheet(line) else -0.5

    if ou == "over_2_5":
        score += 2.0 if tg >= 3 else -1.0
    elif ou == "under_2_5":
        score += 1.5 if tg <= 2 else -1.0

    return score


def _ecse_prob_bonus(line: str, pool: dict[str, Any]) -> float:
    ecse_map = pool.get("ecse_map") or {}
    row = ecse_map.get(line)
    if not row:
        return 0.0
    rank = int(row.get("rank") or 99)
    prob = float(row.get("probability") or 0)
    return max(0, (11 - rank) * 0.15) + prob * 2.0


def _select_from_pool(
    pool_lines: list[str],
    wde: dict[str, Any],
    pool: dict[str, Any],
    *,
    n: int = 3,
) -> list[str]:
    ranked = sorted(
        pool_lines,
        key=lambda ln: (_score_consistency(ln, wde) + _ecse_prob_bonus(ln, pool)),
        reverse=True,
    )
    return _pick_exact(ranked, n)


def strategy_0_baseline(pool: dict[str, Any], wde: dict[str, Any]) -> list[str]:
    """Raw ECSE Top 3."""
    top10 = pool.get("top10") or []
    return _pick_exact([c["scoreline"] for c in sorted(top10, key=lambda x: x.get("rank", 99))], 3)


def strategy_1_top5_consistency(pool: dict[str, Any], wde: dict[str, Any]) -> list[str]:
    """Best 3 from ECSE Top5 by WDE market consistency."""
    top5 = pool.get("top5") or []
    return _select_from_pool(top5, wde, pool, n=3)


def strategy_2_top10_diversity(pool: dict[str, Any], wde: dict[str, Any]) -> list[str]:
    """Portfolio diversity from Top10 with scenario constraints."""
    btts = _norm_btts(wde.get("pick_btts"))
    ou = _norm_ou(wde.get("pick_ou25"))
    pick = wde.get("pick_1x2")
    top10_lines = [c["scoreline"] for c in pool.get("top10") or []]

    selected: list[str] = []
    # Anchor: best consistency from top5
    for ln in strategy_1_top5_consistency(pool, wde):
        if ln not in selected:
            selected.append(ln)

    def add_first(predicate, source: list[str]) -> None:
        if len(selected) >= 3:
            return
        for ln in source:
            if ln in selected:
                continue
            if predicate(ln) and (not pick or winner_side(ln) in (pick, "draw", None)):
                selected.append(ln)
                return

    if btts == "no" or ou == "under_2_5":
        add_first(lambda ln: is_clean_sheet(ln) or (total_goals(ln) or 0) <= 2, top10_lines)
    if btts == "yes":
        add_first(is_btts, top10_lines)
    if ou == "over_2_5":
        add_first(lambda ln: (total_goals(ln) or 0) >= 3, top10_lines)
    if draw_risk_score(wde) >= 0.35:
        add_first(lambda ln: winner_side(ln) == "draw", top10_lines)

    for ln in _select_from_pool(top10_lines, wde, pool):
        if len(selected) >= 3:
            break
        if ln not in selected:
            selected.append(ln)
    return _pick_exact(selected, 3)


def strategy_3_archetype(pool: dict[str, Any], wde: dict[str, Any]) -> list[str]:
    """Archetype portfolio lines filtered by winner direction."""
    arch = match_archetype(wde)
    lines = list(ARCHETYPE_LINES.get(arch, ARCHETYPE_LINES["balanced"]))
    pick = wde.get("pick_1x2")
    if pick == "away_win":
        lines = ["0-1", "1-2", "0-2"]
    elif pick == "home_win":
        lines = [ln for ln in lines if winner_side(ln) in ("home_win", "draw")] or lines
    elif pick == "draw":
        lines = [ln for ln in lines if winner_side(ln) == "draw"] or ["1-1", "2-2", "0-0"]
    # Prefer lines that exist in ECSE pool
    ecse_lines = {c["scoreline"] for c in pool.get("top10") or []}
    ecse_first = [ln for ln in lines if ln in ecse_lines]
    fallback = [c["scoreline"] for c in pool.get("top10") or []]
    merged = _pick_exact(ecse_first + lines, 3, fallback=fallback)
    return merged


def strategy_4_hybrid(pool: dict[str, Any], wde: dict[str, Any]) -> list[str]:
    """Start ECSE Top3, hedge duplicates with scenario replacements."""
    base = strategy_0_baseline(pool, wde)
    btts = _norm_btts(wde.get("pick_btts"))
    ou = _norm_ou(wde.get("pick_ou25"))
    top10_lines = [c["scoreline"] for c in pool.get("top10") or []]
    replacements: list[tuple[str, str]] = []

    clean_count = sum(1 for ln in base if is_clean_sheet(ln))
    if btts == "yes" and clean_count >= 2:
        replacements.append(("1-0", "2-1"))
        replacements.append(("2-0", "3-1"))
    if ou == "over_2_5" and all((total_goals(ln) or 0) <= 2 for ln in base):
        replacements.append(("1-0", "3-1"))
        replacements.append(("2-0", "3-0"))
    if draw_risk_score(wde) >= 0.4 and not any(winner_side(ln) == "draw" for ln in base):
        replacements.append((base[-1], "1-1"))

    out = list(base)
    for old, new in replacements:
        if old in out and new not in out:
            idx = out.index(old)
            if new in top10_lines or _score_consistency(new, wde) >= 0:
                out[idx] = new
        if len(set(out)) < 3:
            break

    if len(out) < 3:
        for ln in strategy_1_top5_consistency(pool, wde):
            if ln not in out:
                out.append(ln)
    return _pick_exact(out, 3)


def strategy_5_conservative(pool: dict[str, Any], wde: dict[str, Any]) -> list[str]:
    """One winner-direction, one BTTS/Over aligned, one hedge."""
    pick = wde.get("pick_1x2")
    btts = _norm_btts(wde.get("pick_btts"))
    ou = _norm_ou(wde.get("pick_ou25"))
    top10 = pool.get("top10") or []
    top10_lines = [c["scoreline"] for c in top10]

    winner_cands = [ln for ln in top10_lines if pick and winner_side(ln) == pick]
    btts_cands = [ln for ln in top10_lines if btts == "yes" and is_btts(ln)]
    over_cands = [ln for ln in top10_lines if ou == "over_2_5" and (total_goals(ln) or 0) >= 3]
    hedge_cands = [ln for ln in top10_lines if winner_side(ln) == "draw" or (total_goals(ln) or 0) >= 3]

    selected: list[str] = []
    if winner_cands:
        selected.append(winner_cands[0])
    if btts == "yes" and btts_cands:
        for ln in btts_cands:
            if ln not in selected:
                selected.append(ln)
                break
    elif ou == "over_2_5" and over_cands:
        for ln in over_cands:
            if ln not in selected:
                selected.append(ln)
                break
    for ln in hedge_cands + top10_lines:
        if len(selected) >= 3:
            break
        if ln not in selected:
            selected.append(ln)
    return _pick_exact(selected or strategy_0_baseline(pool, wde), 3)


STRATEGIES: dict[str, dict[str, Any]] = {
    "S0_baseline_raw_top3": {"fn": strategy_0_baseline, "label": "Baseline: ECSE raw Top3"},
    "S1_top5_market_consistency": {"fn": strategy_1_top5_consistency, "label": "Top5 best-3 by WDE consistency"},
    "S2_top10_portfolio_diversity": {"fn": strategy_2_top10_diversity, "label": "Top10 portfolio diversity"},
    "S3_archetype_portfolio": {"fn": strategy_3_archetype, "label": "Archetype portfolio"},
    "S4_hybrid_hedge": {"fn": strategy_4_hybrid, "label": "Hybrid hedge from Top3"},
    "S5_conservative_coverage": {"fn": strategy_5_conservative, "label": "Conservative high-coverage"},
}


def optimize_top3(strategy_id: str, pool: dict[str, Any], wde: dict[str, Any]) -> list[str]:
    spec = STRATEGIES.get(strategy_id)
    if not spec:
        raise ValueError(f"Unknown strategy: {strategy_id}")
    lines = spec["fn"](pool, wde)
    if len(lines) < 3:
        pad = strategy_0_baseline(pool, wde)
        lines = _pick_exact(lines + pad, 3)
    if len(lines) != 3:
        raise ValueError(f"Strategy {strategy_id} returned {len(lines)} candidates, expected 3")
    return lines

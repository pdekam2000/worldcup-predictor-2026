"""PHASE ECSE-X3-A — Score mapping and composite challenger methods."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.research.ecse_x3.constants import (
    CONSERVATIVE_MIN_FAMILIES,
    DRAW_UNDER_SCORELINES,
    H_BOOST,
    HOME_WIN_SCORELINES,
    I_BOOST,
    J2_G_SLOPE_STRENGTH,
    SEGMENT_H_MULT,
    SEGMENT_I_MULT,
    TOP_N_SHADOW,
    ZZ2_BOOST,
    ZZ2_TARGET,
    BTTS_HIGH_MIN,
    DRAW_HIGH_MIN,
    UNDER_HIGH_MIN,
)
from worldcup_predictor.research.ecse_x3.signals import CompositeSignals, compute_composite_signals, signals_finite
from worldcup_predictor.research.ecse_x2_m4.segment import classify_match_state


def _top_n_rows(dist: list[dict[str, Any]], n: int = TOP_N_SHADOW) -> list[dict[str, Any]]:
    return [
        {
            "scoreline": r["scoreline"],
            "probability": round(float(r["probability"]), 8),
            "rank": int(r["rank"]),
        }
        for r in sorted(dist, key=lambda x: int(x["rank"]))[:n]
    ]


def _renormalize(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = sum(float(r["probability"]) for r in pool)
    if total <= 0:
        return pool
    for row in pool:
        row["probability"] = round(float(row["probability"]) / total, 10)
    pool.sort(key=lambda r: (-float(r["probability"]), str(r["scoreline"])))
    for i, row in enumerate(pool, start=1):
        row["rank"] = i
    return pool


def _boost_scorelines(
    baseline: list[dict[str, Any]],
    *,
    targets: frozenset[str],
    weight: float,
    top_n: int = TOP_N_SHADOW,
) -> list[dict[str, Any]]:
    pool = [dict(r) for r in sorted(baseline, key=lambda x: int(x["rank"]))[:top_n]]
    if not pool or weight <= 1.0:
        return _top_n_rows(baseline, top_n)
    for row in pool:
        if str(row["scoreline"]) in targets:
            row["probability"] = float(row["probability"]) * weight
    return _top_n_rows(_renormalize(pool), top_n)


def _continuous_adjust(
    baseline: list[dict[str, Any]],
    *,
    sig: CompositeSignals,
    top_n: int = TOP_N_SHADOW,
) -> list[dict[str, Any]]:
    pool = [dict(r) for r in sorted(baseline, key=lambda x: int(x["rank"]))[:top_n]]
    if not pool:
        return _top_n_rows(baseline, top_n)

    j2 = sig.J2 or 1.0
    g = sig.G or 0.0
    slope = sig.ou_slope or 1.0
    # Higher J2 / G / slope nudge toward higher-scoring home-win patterns in pool
    for row in pool:
        sl = str(row["scoreline"])
        try:
            h, a = sl.split("-")
            hg, ag = int(h), int(a)
        except (ValueError, AttributeError):
            continue
        goal_sum = hg + ag
        home_edge = hg - ag
        score_key = (
            J2_G_SLOPE_STRENGTH * (j2 - 1.0)
            + J2_G_SLOPE_STRENGTH * min(g, 2.0)
            + J2_G_SLOPE_STRENGTH * (slope - 1.0)
            + 0.02 * goal_sum
            + 0.03 * max(home_edge, 0)
        )
        row["probability"] = float(row["probability"]) * max(0.85, 1.0 + score_key)
    return _top_n_rows(_renormalize(pool), top_n)


def _apply_hi(sig: CompositeSignals, baseline: list[dict[str, Any]], *, h_mult: float = 1.0, i_mult: float = 1.0) -> list[dict[str, Any]]:
    pool = [dict(r) for r in sorted(baseline, key=lambda x: int(x["rank"]))[:TOP_N_SHADOW]]
    if not pool:
        return _top_n_rows(baseline, TOP_N_SHADOW)

    h_weight = H_BOOST * h_mult if sig.H is not None and sig.H >= 0.40 else 1.0
    i_weight = I_BOOST * i_mult if sig.I is not None and sig.I >= 0.35 else 1.0

    for row in pool:
        sl = str(row["scoreline"])
        if sl in HOME_WIN_SCORELINES and h_weight > 1.0:
            row["probability"] = float(row["probability"]) * h_weight
        if sl in DRAW_UNDER_SCORELINES and i_weight > 1.0:
            row["probability"] = float(row["probability"]) * i_weight
    return _top_n_rows(_renormalize(pool), TOP_N_SHADOW)


def _apply_zz2(sig: CompositeSignals, baseline: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pool = [dict(r) for r in sorted(baseline, key=lambda x: int(x["rank"]))[:TOP_N_SHADOW]]
    meta: dict[str, Any] = {"zz2_fired": bool(sig.zz2_flag), "zz2_in_pool": False, "zz2_would_help_research": False}
    if not pool or not sig.zz2_flag:
        return _top_n_rows(baseline, TOP_N_SHADOW), meta

    in_pool = any(str(r["scoreline"]) == ZZ2_TARGET for r in pool)
    meta["zz2_in_pool"] = in_pool
    if in_pool:
        for row in pool:
            if str(row["scoreline"]) == ZZ2_TARGET:
                row["probability"] = float(row["probability"]) * ZZ2_BOOST
        return _top_n_rows(_renormalize(pool), TOP_N_SHADOW), meta
    meta["zz2_not_in_pool"] = True
    return _top_n_rows(baseline, TOP_N_SHADOW), meta


def _rank_movements(baseline: list[dict[str, Any]], adjusted: list[dict[str, Any]]) -> dict[str, int]:
    base_rank = {str(r["scoreline"]): int(r["rank"]) for r in baseline}
    out: dict[str, int] = {}
    for row in adjusted:
        sl = str(row["scoreline"])
        if sl in base_rank:
            out[sl] = base_rank[sl] - int(row["rank"])
    return out


def score_all_methods(
    *,
    dist_rows: list[dict[str, Any]],
    probs: dict[str, float | None],
    raw_row: dict[str, Any] | None = None,
    top_n: int = TOP_N_SHADOW,
) -> dict[str, Any]:
    baseline = [dict(r) for r in dist_rows]
    baseline_top = _top_n_rows(baseline, top_n)
    sig = compute_composite_signals(probs, raw_row=raw_row)
    signals_ok = signals_finite(sig)

    outputs: dict[str, list[dict[str, Any]]] = {"champion": baseline_top}
    zz2_meta: dict[str, Any] = {}

    if not signals_ok:
        for key in ("hi_only", "zz2_only", "j2_g_slope", "composite_full", "conservative_composite", "segment_aware"):
            outputs[key] = baseline_top
        return {
            "signals": sig.to_dict(),
            "signals_ok": False,
            "outputs": outputs,
            "rank_movements": {},
            "zz2_meta": zz2_meta,
            "home_prob": probs.get("ft_home"),
            "match_state": classify_match_state(probs),
        }

    outputs["hi_only"] = _apply_hi(sig, baseline)
    zz2_top, zz2_meta = _apply_zz2(sig, baseline)
    outputs["zz2_only"] = zz2_top
    outputs["j2_g_slope"] = _continuous_adjust(baseline, sig=sig, top_n=top_n)

    # Full composite: HI + ZZ2 + continuous
    comp = _apply_hi(sig, baseline)
    comp_pool = [dict(r) for r in comp]
    if sig.zz2_flag and any(str(r["scoreline"]) == ZZ2_TARGET for r in comp_pool):
        for row in comp_pool:
            if str(row["scoreline"]) == ZZ2_TARGET:
                row["probability"] = float(row["probability"]) * ZZ2_BOOST
        comp_pool = _renormalize(comp_pool)
    outputs["composite_full"] = _continuous_adjust(comp_pool, sig=sig, top_n=top_n)

    if sig.signal_families_available >= CONSERVATIVE_MIN_FAMILIES:
        outputs["conservative_composite"] = outputs["composite_full"]
    else:
        outputs["conservative_composite"] = baseline_top

    # Segment-aware
    state = classify_match_state(probs)
    pd = sig.pd or 0.0
    pu = sig.p_u25 or 0.0
    seg_pool = baseline
    h_mult = SEGMENT_H_MULT if state == "home_favorite" else 1.0
    i_mult = SEGMENT_I_MULT if (pd >= DRAW_HIGH_MIN or pu >= UNDER_HIGH_MIN) else 1.0
    seg_hi = _apply_hi(sig, seg_pool, h_mult=h_mult, i_mult=i_mult)
    if sig.zz2_flag and (sig.p_btts or 0) >= BTTS_HIGH_MIN and (sig.p_u25 or 0) >= UNDER_HIGH_MIN:
        seg_zz2, _ = _apply_zz2(sig, seg_hi)
        seg_pool = seg_zz2
    else:
        seg_pool = seg_hi
    outputs["segment_aware"] = _continuous_adjust(seg_pool, sig=sig, top_n=top_n)

    movements = {
        m: _rank_movements(baseline_top, outputs[m])
        for m in outputs
        if m != "champion"
    }

    return {
        "signals": sig.to_dict(),
        "signals_ok": True,
        "outputs": outputs,
        "rank_movements": movements,
        "zz2_meta": zz2_meta,
        "home_prob": probs.get("ft_home"),
        "match_state": classify_match_state(probs),
    }


def apply_j2_g_slope_shadow(
    baseline_top10: list[dict[str, Any]],
    probs: dict[str, float | None],
    *,
    raw_row: dict[str, Any] | None = None,
    top_n: int = TOP_N_SHADOW,
) -> dict[str, Any]:
    """PHASE ECSE-X3-B — j2_g_slope shadow shortlist (never overrides baseline)."""
    from worldcup_predictor.research.ecse_x3_b.constants import REQUIRED_PROB_KEYS

    baseline = [dict(r) for r in baseline_top10]
    baseline_top = _top_n_rows(baseline, top_n)
    missing = [k for k in REQUIRED_PROB_KEYS if probs.get(k) is None]
    if missing:
        return {
            "x3_status": "unavailable",
            "rejection_reason": "missing_odds_fields",
            "missing_fields": missing,
            "baseline_top10": baseline_top,
            "x3_top10": baseline_top,
            "public_prediction_changed": False,
        }

    sig = compute_composite_signals(probs, raw_row=raw_row)
    if not signals_finite(sig) or sig.J2 is None or sig.G is None or sig.ou_slope is None:
        return {
            "x3_status": "rejected",
            "rejection_reason": "invalid_j2_g_slope_signals",
            "missing_fields": sig.missing_fields,
            "signals": sig.to_dict(),
            "baseline_top10": baseline_top,
            "x3_top10": baseline_top,
            "public_prediction_changed": False,
        }

    x3_top = _continuous_adjust(baseline, sig=sig, top_n=top_n)
    return {
        "x3_status": "available",
        "rejection_reason": None,
        "missing_fields": sig.missing_fields,
        "signals": sig.to_dict(),
        "j2": sig.J2,
        "g": sig.G,
        "ou_slope": sig.ou_slope,
        "baseline_top10": baseline_top,
        "x3_top10": x3_top,
        "rank_movements": _rank_movements(baseline_top, x3_top),
        "public_prediction_changed": False,
    }


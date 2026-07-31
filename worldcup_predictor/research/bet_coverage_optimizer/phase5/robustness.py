"""Robustness / stress tests for incomplete markets (research-only)."""

from __future__ import annotations

import copy
import random
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.phase5.historical_validation import (
    run_historical_validation,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase5.layer_builder import (
    select_main_and_insurance,
)


def _degrade_candidates(cands: list[dict[str, Any]], *, mode: str, rng: random.Random) -> list[dict[str, Any]]:
    cands = copy.deepcopy(cands)
    if mode == "missing_half_markets":
        rng.shuffle(cands)
        return cands[: max(1, len(cands) // 2)]
    if mode == "missing_odds":
        for c in cands:
            if rng.random() < 0.4:
                c["odds"] = None
                c["eligible"] = False
                c.setdefault("rejection_reasons", []).append("STRESS_MISSING_ODDS")
        return cands
    if mode == "incomplete_market_set":
        keep_families = {"btts", "over_under"}
        return [c for c in cands if c.get("market_type") in keep_families] or cands[:1]
    return cands


def run_robustness_tests(fixtures: list[dict[str, Any]], *, seed: int = 42) -> dict[str, Any]:
    rng = random.Random(seed)
    # Subsample for speed
    sample = fixtures[: min(400, len(fixtures))]

    scenarios = {
        "baseline": sample,
        "extreme_favorites": [f for f in sample if f.get("odds_home") and float(f["odds_home"]) <= 1.55],
        "balanced_matches": [
            f
            for f in sample
            if f.get("odds_home") and 1.90 <= float(f["odds_home"]) <= 2.40
        ],
        "high_scoring": [f for f in sample if float(f.get("lambda_total") or 0) >= 3.2],
        "low_scoring": [f for f in sample if 0 < float(f.get("lambda_total") or 0) <= 2.2],
    }

    # Synthetic degraded copies for missing markets/odds
    degraded_modes = ("missing_half_markets", "missing_odds", "incomplete_market_set")
    for mode in degraded_modes:
        rows = []
        for fx in sample[:200]:
            cands = list(fx.get("all_candidates") or [])
            if not cands:
                rows.append(fx)
                continue
            top_pairs = [(x["score"], float(x["probability"])) for x in (fx.get("top_n_scores") or [])]
            exact3 = list(fx.get("exact3") or [])
            degraded = _degrade_candidates(cands, mode=mode, rng=rng)
            layers = select_main_and_insurance(degraded, top_n_pairs=top_pairs, exact3=exact3)
            neo = dict(fx)
            neo["main_coverage_scores"] = list(layers.get("main_coverage_scores") or [])
            neo["insurance_scores"] = list(layers.get("insurance_scores") or [])
            neo["main_market_label"] = (layers.get("main_coverage") or {}).get("market_label")
            neo["insurance_market_label"] = (layers.get("insurance") or {}).get("market_label")
            neo["graceful"] = bool(layers.get("main_coverage")) or bool(exact3)
            rows.append(neo)
        scenarios[mode] = rows

    results = {}
    for name, rows in scenarios.items():
        if not rows:
            results[name] = {"n": 0, "skipped": True}
            continue
        hv = run_historical_validation(rows)
        graceful = sum(1 for r in rows if r.get("graceful", True))
        results[name] = {
            "n": len(rows),
            "coverage_main": hv["strategies"]["exact3_main"]["coverage_rate"],
            "coverage_main_insurance": hv["strategies"]["exact3_main_insurance"]["coverage_rate"],
            "insurance_still_helps": hv["main_plus_insurance_outperforms_main"],
            "graceful_degradation_rate": round(graceful / len(rows), 8),
            "complete_failure_reduced": hv["complete_coupon_failure"]["insurance_reduces_complete_failure"],
        }

    robust = all(
        results.get(m, {}).get("graceful_degradation_rate", 0) >= 0.95
        for m in degraded_modes
        if results.get(m, {}).get("n", 0) > 0
    )
    return {
        "research_only": True,
        "scenarios": results,
        "robust_to_incomplete_markets": robust,
        "seed": seed,
    }

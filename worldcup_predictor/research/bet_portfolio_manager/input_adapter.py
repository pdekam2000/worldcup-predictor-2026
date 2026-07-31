"""Normalize read-only BCO / freeze fixture rows into portfolio inputs."""

from __future__ import annotations

from typing import Any


def normalize_fixture(raw: dict[str, Any]) -> dict[str, Any]:
    """Map heterogeneous research fixture payloads into a stable schema (read-only)."""
    top = list(raw.get("top_n_scores") or [])
    top5_mass = 0.0
    if top:
        top5_mass = sum(float(x.get("probability") or 0.0) for x in top[:5] if isinstance(x, dict))

    confidence = float(
        raw.get("confidence")
        or raw.get("wde_confidence")
        or raw.get("top5_mass")
        or top5_mass
        or 0.0
    )
    entropy = float(raw.get("entropy") or 0.0)
    coverage = float(raw.get("coverage_ratio_with_insurance") or raw.get("coverage_ratio_primary") or 0.0)
    residual = float(raw.get("residual_mass") or max(0.0, 1.0 - coverage))
    ins_mass = float(raw.get("incremental_uncovered_mass") or 0.0)
    odds_home = raw.get("odds_home")
    try:
        odds_home_f = float(odds_home) if odds_home is not None else None
    except (TypeError, ValueError):
        odds_home_f = None

    # Odds balance: closer to 2.0–2.5 preferred for research slate diversity
    if odds_home_f and odds_home_f > 1.0:
        balance = max(0.0, 1.0 - abs(odds_home_f - 2.2) / 2.2)
    else:
        balance = 0.4

    league = str(raw.get("league") or raw.get("competition") or "unknown")
    markets = set()
    if raw.get("main_market_family"):
        markets.add(str(raw["main_market_family"]))
    if raw.get("insurance_market_family"):
        markets.add(str(raw["insurance_market_family"]))
    if raw.get("main_market_label"):
        markets.add(str(raw["main_market_label"]))
    if raw.get("insurance_market_label"):
        markets.add(str(raw["insurance_market_label"]))

    return {
        "fixture_id": int(raw.get("fixture_id") or 0),
        "match_name": str(raw.get("match_name") or raw.get("fixture_id") or ""),
        "league": league,
        "kickoff": str(raw.get("kickoff") or "")[:10],
        "confidence": confidence,
        "entropy": entropy,
        "top5_mass": float(raw.get("top5_mass") or top5_mass),
        "coverage_mass": coverage,
        "residual_risk": residual,
        "insurance_contribution": ins_mass,
        "odds_home": odds_home_f,
        "odds_balance": round(balance, 6),
        "market_tags": sorted(markets),
        "insurance_market_label": raw.get("insurance_market_label"),
        "main_market_label": raw.get("main_market_label"),
        "insurance_odds": raw.get("insurance_odds") or raw.get("main_odds"),
        "actual_score": raw.get("actual_score"),
        "exact3": list(raw.get("exact3") or []),
        "main_coverage_scores": list(raw.get("main_coverage_scores") or []),
        "insurance_scores": list(raw.get("insurance_scores") or []),
        "hit_main": None,
        "hit_insurance": None,
        "source": raw.get("source"),
        "raw_ref": None,  # never mutate caller
    }


def attach_outcomes(fx: dict[str, Any]) -> dict[str, Any]:
    out = dict(fx)
    actual = str(fx.get("actual_score") or "").replace(" ", "")
    if not actual:
        return out
    main = set(str(s).replace(" ", "") for s in (fx.get("exact3") or []) + (fx.get("main_coverage_scores") or []))
    ins = set(main) | set(str(s).replace(" ", "") for s in (fx.get("insurance_scores") or []))
    out["hit_main"] = actual in main
    out["hit_insurance"] = actual in ins
    return out

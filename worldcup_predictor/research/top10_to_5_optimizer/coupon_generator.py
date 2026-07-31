"""Three-fixture coupon generator — 125 universe research-only; optimized caps."""

from __future__ import annotations

import itertools
from typing import Any


def generate_coupon_universe(
    fixture_selections: list[dict[str, Any]],
    *,
    ticket_cap: int = 25,
) -> dict[str, Any]:
    """
    fixture_selections: list of 3 fixtures, each with exactly 5 selection dicts
      [{selection_id, label, decimal_odds?, modeled_probability?}, ...]
    """
    if len(fixture_selections) != 3:
        return {
            "error": "requires_exactly_three_fixtures",
            "research_only": True,
            "auto_generate_125_disabled_for_execution": True,
        }

    legs = []
    for fx in fixture_selections:
        sels = list(fx.get("selections") or [])[:5]
        while len(sels) < 5:
            sels.append({"selection_id": f"pad_{len(sels)}", "label": "UNAVAILABLE", "decimal_odds": None, "modeled_probability": 0.0})
        legs.append(sels)

    universe = []
    for combo in itertools.product(*legs):
        probs = [float(x.get("modeled_probability") or 0.0) for x in combo]
        odds = [x.get("decimal_odds") for x in combo]
        priced = all(o is not None and float(o) > 1.0 for o in odds)
        joint_p = 1.0
        for p in probs:
            joint_p *= max(0.0, p)
        combined_odds = None
        if priced:
            combined_odds = 1.0
            for o in odds:
                combined_odds *= float(o)
        ev = (joint_p * combined_odds - 1.0) if priced and combined_odds is not None else None
        labels = [str(x.get("label") or x.get("selection_id")) for x in combo]
        universe.append(
            {
                "legs": labels,
                "selection_ids": [str(x.get("selection_id")) for x in combo],
                "joint_modeled_probability": round(joint_p, 12),
                "combined_odds": round(combined_odds, 8) if combined_odds is not None else None,
                "expected_value": round(ev, 8) if ev is not None else None,
                "priced": priced,
                "insurance_dependence": sum(1 for x in combo if "market" in str(x.get("selection_id") or "")),
                "worst_leg_risk": round(1.0 - min(probs) if probs else 1.0, 8),
            }
        )

    # Deduplicate by selection_ids
    seen = set()
    unique = []
    for t in universe:
        key = tuple(t["selection_ids"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(t)

    def coupon_score(t: dict[str, Any]) -> tuple:
        return (
            -float(t.get("joint_modeled_probability") or 0),
            -(float(t["expected_value"]) if t.get("expected_value") is not None else -999),
            -(float(t["combined_odds"]) if t.get("combined_odds") is not None else 0),
            float(t.get("worst_leg_risk") or 0),
            tuple(t["selection_ids"]),
        )

    unique.sort(key=coupon_score)
    for i, t in enumerate(unique, start=1):
        t["rank"] = i
        t["coupon_score"] = round(float(t.get("joint_modeled_probability") or 0) * 1000, 8)
        t["coupon_score_is_probability"] = False

    cap = int(ticket_cap)
    optimized = unique[:cap]
    freqs: dict[str, int] = {}
    for t in optimized:
        for lab in t["legs"]:
            freqs[lab] = freqs.get(lab, 0) + 1

    priced_n = sum(1 for t in optimized if t.get("priced"))
    odds_vals = [float(t["combined_odds"]) for t in optimized if t.get("combined_odds") is not None]

    return {
        "research_only": True,
        "not_deployed": True,
        "auto_execute_125": False,
        "universe_125_count": len(unique),
        "universe_125": unique if len(unique) <= 125 else unique[:125],
        "optimized_ticket_cap": cap,
        "optimized_tickets": optimized,
        "ticket_count": len(optimized),
        "priced_ticket_count": priced_n,
        "unpriced_ticket_count": len(optimized) - priced_n,
        "min_combined_odds": min(odds_vals) if odds_vals else None,
        "max_combined_odds": max(odds_vals) if odds_vals else None,
        "expected_coupon_value": (
            round(sum(float(t["expected_value"]) for t in optimized if t.get("expected_value") is not None), 8)
            if priced_n == len(optimized) and optimized
            else None
        ),
        "monetary_ev_claimed": False if priced_n < len(optimized) else True,
        "probability_mass_utility": round(sum(float(t.get("joint_modeled_probability") or 0) for t in optimized), 8),
        "selection_frequency": freqs,
        "scenario_survival": {
            "note": "research ranking only — no live coupon execution",
            "unique_tickets": len(unique),
            "duplicates_removed": len(universe) - len(unique),
        },
    }

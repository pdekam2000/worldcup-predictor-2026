"""Similarity overlay on Portfolio Manager — research-only.

May only adjust exposure / action class. Must not alter football predictions,
selections markets, or freezes.
"""

from __future__ import annotations

from typing import Any


def apply_similarity_overlay(
    *,
    base_action: str,
    base_exposure: float,
    base_selected_fixture_ids: list[int],
    similarity_recommendation: str,
    ood_level: str,
    overlay_cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    Overlay actions:
      SIMILARITY_SUPPORTS | SIMILARITY_NEUTRAL | SIMILARITY_REDUCE | SIMILARITY_SKIP_OOD
    """
    selected = list(base_selected_fixture_ids)
    action = base_action
    exposure = float(base_exposure)
    mult = 1.0
    overlay_action = "SIMILARITY_NEUTRAL"

    supports = float(overlay_cfg.get("supports_capital_multiplier", 1.15))
    reduce = float(overlay_cfg.get("reduce_capital_multiplier", 0.55))
    micro = float(overlay_cfg.get("watch_micro_allocation", 0.10))
    max_up = float(overlay_cfg.get("max_exposure_uplift", 1.25))
    max_down = float(overlay_cfg.get("max_exposure_reduction", 0.40))
    skip_ood = bool(overlay_cfg.get("skip_on_strong_ood", True))

    if ood_level == "strongly_out_of_distribution" and skip_ood:
        overlay_action = "SIMILARITY_SKIP_OOD"
        action = "HARD_SKIP"
        exposure = 0.0
        mult = 0.0
        selected = []
    elif similarity_recommendation == "HOSTILE_SIMILARITY":
        overlay_action = "SIMILARITY_REDUCE"
        mult = max(max_down, reduce)
        if action in {"BET", "SMALL_BET"}:
            action = "WATCH_NO_CAPITAL" if mult < 0.5 else "SMALL_BET"
            if action == "WATCH_NO_CAPITAL":
                exposure = 0.0
                selected = []
            else:
                exposure = float(base_exposure) * mult
        elif action == "WATCH_POSITIVE":
            exposure = float(base_exposure) * mult
    elif similarity_recommendation == "FAVORABLE_SIMILARITY":
        overlay_action = "SIMILARITY_SUPPORTS"
        mult = min(max_up, supports)
        if action == "WATCH_NO_CAPITAL":
            # convert to micro-allocation without inventing new selections beyond first eligible id
            action = "WATCH_POSITIVE"
            exposure = micro * max(1.0, float(base_exposure) or 1.0)
            # keep selections unchanged if empty — still no prediction change
            if not selected and base_selected_fixture_ids:
                selected = list(base_selected_fixture_ids)[:1]
        elif action in {"SMALL_BET", "BET", "WATCH_POSITIVE"}:
            exposure = float(base_exposure) * mult if base_exposure > 0 else exposure
    elif similarity_recommendation in {"MODERATELY_FAVORABLE", "NEUTRAL", "UNCERTAIN_LOW_SAMPLE", "OUT_OF_DISTRIBUTION"}:
        if similarity_recommendation == "OUT_OF_DISTRIBUTION":
            overlay_action = "SIMILARITY_REDUCE"
            mult = max(max_down, reduce)
            exposure = float(base_exposure) * mult
        else:
            overlay_action = "SIMILARITY_NEUTRAL"
            mult = 1.0

    return {
        "research_only": True,
        "overlay_action": overlay_action,
        "action": action,
        "exposure_units": round(float(exposure), 6),
        "capital_multiplier": round(float(mult), 6),
        "selected_fixture_ids": selected,
        "predictions_unchanged": True,
        "selections_markets_unchanged": True,
        "freezes_unchanged": True,
        "base_action": base_action,
        "base_exposure": base_exposure,
        "similarity_recommendation": similarity_recommendation,
        "ood_level": ood_level,
    }

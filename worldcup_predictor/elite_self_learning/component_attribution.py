"""Part B — component contribution attribution."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.elite_self_learning.models import ATTRIBUTION_COMPONENTS, ComponentAttribution


def _pick_matches(prediction: Any, reality: Any) -> bool | None:
    if prediction is None or reality is None:
        return None
    if isinstance(prediction, list):
        return str(reality) in [str(p) for p in prediction]
    return str(prediction).lower() == str(reality).lower()


def attribute_components(
    *,
    market_id: str,
    reality: Any,
    contributions: list[dict[str, Any]],
) -> list[ComponentAttribution]:
    """Determine which component helped, hurt, or was neutral for a market."""
    rows: list[ComponentAttribution] = []
    for block in contributions:
        cid = str(block.get("component_id") or "")
        if cid not in ATTRIBUTION_COMPONENTS and cid != "first_goal_team_v2":
            continue
        pred = block.get("prediction")
        weight = float(block.get("weight") or 0.0)
        conf = float(block.get("confidence") or 0.5)
        match = _pick_matches(pred, reality)
        helped = match is True
        hurt = match is False and pred is not None
        neutral = match is None or (not helped and not hurt)
        rows.append(
            ComponentAttribution(
                component_id=cid,
                prediction=pred,
                weight_used=round(weight, 4),
                confidence=round(conf, 4),
                helped=helped,
                hurt=hurt,
                neutral=neutral,
            )
        )
    return rows


def summarize_attribution(attributions: list[ComponentAttribution]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for a in attributions:
        entry = summary.setdefault(a.component_id, {"helped": 0, "hurt": 0, "neutral": 0})
        if a.helped:
            entry["helped"] += 1
        elif a.hurt:
            entry["hurt"] += 1
        else:
            entry["neutral"] += 1
    return summary

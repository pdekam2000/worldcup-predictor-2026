"""Canonical vs Exact V2 agreement classifications (research-only; never routes)."""

from __future__ import annotations

from typing import Any

MODELS_AGREE = "MODELS_AGREE"
MODELS_PARTIAL_AGREEMENT = "MODELS_PARTIAL_AGREEMENT"
MODELS_CONFLICT = "MODELS_CONFLICT"
EXACT_V2_HIGH_GOAL_SHIFT = "EXACT_V2_HIGH_GOAL_SHIFT"
CANONICAL_HIGHER_CONFIDENCE = "CANONICAL_HIGHER_CONFIDENCE"
SHADOW_HIGHER_CONCENTRATION = "SHADOW_HIGHER_CONCENTRATION"
RESEARCH_ONLY_NO_BET = "RESEARCH_ONLY_NO_BET"

_ALL = (
    MODELS_AGREE,
    MODELS_PARTIAL_AGREEMENT,
    MODELS_CONFLICT,
    EXACT_V2_HIGH_GOAL_SHIFT,
    CANONICAL_HIGHER_CONFIDENCE,
    SHADOW_HIGHER_CONCENTRATION,
    RESEARCH_ONLY_NO_BET,
)


def _side_from_score(score: str | None) -> str | None:
    if not score or "-" not in str(score):
        return None
    try:
        h, a = str(score).split("-", 1)
        hi, ai = int(h.strip()), int(a.strip())
    except Exception:
        return None
    if hi > ai:
        return "HOME"
    if ai > hi:
        return "AWAY"
    return "DRAW"


def classify_model_agreement(
    *,
    canonical_top1: str | None,
    exact_top1: str | None,
    top3_overlap: int,
    top5_overlap: int,
    canonical_confidence: float | None,
    canonical_top5_mass: float | None,
    exact_top5_mass: float | None,
    canonical_total_lambda: float | None,
    exact_total_lambda: float | None,
    high_score_tail_diff: float | None,
    no_bet: bool | None,
) -> dict[str, Any]:
    """Return primary classification + tag list. Does not alter routing."""
    tags: list[str] = []
    if no_bet:
        tags.append(RESEARCH_ONLY_NO_BET)

    c_side = _side_from_score(canonical_top1)
    e_side = _side_from_score(exact_top1)
    same_top1 = bool(canonical_top1 and exact_top1 and str(canonical_top1) == str(exact_top1))

    if same_top1 and c_side and e_side and c_side == e_side:
        primary_score = MODELS_AGREE
    elif c_side and e_side and c_side != e_side:
        primary_score = MODELS_CONFLICT
    elif top3_overlap >= 1 or top5_overlap >= 2:
        primary_score = MODELS_PARTIAL_AGREEMENT
    elif canonical_top1 and exact_top1:
        primary_score = MODELS_PARTIAL_AGREEMENT
    else:
        primary_score = MODELS_PARTIAL_AGREEMENT

    tags.append(primary_score)

    if high_score_tail_diff is not None and abs(float(high_score_tail_diff)) >= 0.05:
        tags.append(EXACT_V2_HIGH_GOAL_SHIFT)
    elif (
        canonical_total_lambda is not None
        and exact_total_lambda is not None
        and (float(exact_total_lambda) - float(canonical_total_lambda)) >= 0.45
    ):
        tags.append(EXACT_V2_HIGH_GOAL_SHIFT)

    if canonical_confidence is not None and exact_top5_mass is not None:
        # confidence is often 0-100; top5 mass 0-1
        conf = float(canonical_confidence)
        conf_norm = conf / 100.0 if conf > 1.5 else conf
        if conf_norm > float(exact_top5_mass) + 0.05:
            tags.append(CANONICAL_HIGHER_CONFIDENCE)

    if (
        canonical_top5_mass is not None
        and exact_top5_mass is not None
        and float(exact_top5_mass) > float(canonical_top5_mass) + 0.03
    ):
        tags.append(SHADOW_HIGHER_CONCENTRATION)

    # Prefer research-only no_bet as primary when present; else conflict > high-goal > partial > agree
    priority = [
        RESEARCH_ONLY_NO_BET,
        MODELS_CONFLICT,
        EXACT_V2_HIGH_GOAL_SHIFT,
        MODELS_PARTIAL_AGREEMENT,
        SHADOW_HIGHER_CONCENTRATION,
        CANONICAL_HIGHER_CONFIDENCE,
        MODELS_AGREE,
    ]
    primary = next((p for p in priority if p in tags), primary_score)
    # Deduplicate preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for t in tags:
        if t not in seen and t in _ALL:
            seen.add(t)
            ordered.append(t)
    return {
        "agreement_classification": primary,
        "agreement_tags": ordered,
        "research_only": True,
        "does_not_alter_canonical_routing": True,
    }

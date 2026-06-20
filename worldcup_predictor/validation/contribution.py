"""Phase 26 — signal contribution assessment."""

from __future__ import annotations

from worldcup_predictor.validation.models import (
    PromotionContributionStats,
    PromotionTrackSnapshot,
    RealWorldValidationRecord,
    SignalUsefulness,
)


def assess_promotion_contribution(
    promo: PromotionTrackSnapshot,
    *,
    correct: bool | None,
) -> SignalUsefulness:
    if not promo.signal_available or correct is None:
        return "unknown"
    if abs(promo.delta) < 0.01 and promo.promotion_key != "24c_sportmonks":
        return "neutral"
    if promo.promotion_key == "24c_sportmonks":
        if promo.delta < -2 and correct:
            return "harmful"
        if promo.disagreement and promo.disagreement >= 0.35 and not correct:
            return "helped"
        return "neutral"
    if promo.delta > 0 and correct:
        return "helped"
    if promo.delta > 0 and not correct:
        return "harmful"
    if promo.delta < 0 and not correct:
        return "helped"
    if promo.delta < 0 and correct:
        return "harmful"
    return "neutral"


def assess_signal_usefulness(record: RealWorldValidationRecord) -> dict[str, str]:
    usefulness: dict[str, str] = {}
    for promo in record.promotions:
        usefulness[promo.promotion_key] = assess_promotion_contribution(
            promo, correct=record.one_x_two_correct
        )
    return usefulness


def update_contribution_stats(
    _stats: dict[str, PromotionContributionStats] | None,
    records: list[RealWorldValidationRecord],
) -> dict[str, PromotionContributionStats]:
    keys = ("24a_lineup", "24b_context", "24c_xg", "24c_sportmonks")
    out: dict[str, PromotionContributionStats] = {
        key: PromotionContributionStats(promotion_key=key) for key in keys
    }
    deltas: dict[str, list[float]] = {key: [] for key in keys}
    disagreements: dict[str, list[float]] = {key: [] for key in keys}
    avail: dict[str, int] = {key: 0 for key in keys}

    for record in records:
        if not record.settled:
            continue
        for promo in record.promotions:
            block = out[promo.promotion_key]
            block.total += 1
            verdict = record.signal_usefulness.get(promo.promotion_key, "unknown")
            if verdict == "helped":
                block.helped += 1
            elif verdict == "harmful":
                block.harmful += 1
            elif verdict == "neutral":
                block.neutral += 1
            else:
                block.unknown += 1
            if promo.signal_available:
                avail[promo.promotion_key] += 1
            deltas[promo.promotion_key].append(promo.delta)
            if promo.disagreement is not None:
                disagreements[promo.promotion_key].append(promo.disagreement)

    for key in keys:
        block = out[key]
        if block.total:
            block.signal_available_rate = round(avail[key] / block.total, 4)
            block.avg_delta = round(sum(deltas[key]) / len(deltas[key]), 4)
            if disagreements[key]:
                block.avg_disagreement = round(sum(disagreements[key]) / len(disagreements[key]), 4)
    return out

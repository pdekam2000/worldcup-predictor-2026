"""Statistical promotion policy — never auto-replaces canonical."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.challenger.constants import FORWARD_THRESHOLDS, PROMOTION_DECISIONS
from worldcup_predictor.challenger.schemas import content_hash


def review_promotion(
    *,
    model_id: str,
    model_version: str,
    forward_completed_n: int,
    holdout_improved: bool | None,
    backtest_passed: bool,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """
    Maximum allowed approval: ENSEMBLE_RESEARCH_APPROVED.
    Never returns CHALLENGER_REPLACES_CANONICAL.
    """
    if not backtest_passed:
        decision = "CHALLENGER_REJECTED"
    elif forward_completed_n < FORWARD_THRESHOLDS["promotion_quality"]:
        decision = "CHALLENGER_MORE_DATA_REQUIRED"
    elif holdout_improved is False:
        decision = "CHALLENGER_RETRAIN_REQUIRED"
    elif holdout_improved is True and forward_completed_n >= FORWARD_THRESHOLDS["promotion_quality"]:
        # Still cannot replace canonical; only allow ensemble research if evidence says so
        if evidence.get("approve_ensemble_research") is True:
            decision = "ENSEMBLE_RESEARCH_APPROVED"
        elif evidence.get("domain_limited") is True:
            decision = "CHALLENGER_DOMAIN_LIMITED_RESEARCH_APPROVED"
        else:
            decision = "CHALLENGER_MORE_DATA_REQUIRED"
    else:
        decision = "CHALLENGER_MORE_DATA_REQUIRED"

    assert decision in PROMOTION_DECISIONS
    assert decision != "CHALLENGER_REPLACES_CANONICAL"
    payload = {
        "model_id": model_id,
        "model_version": model_version,
        "decision": decision,
        "forward_completed_n": forward_completed_n,
        "holdout_improved": holdout_improved,
        "backtest_passed": backtest_passed,
        "max_allowed": "ENSEMBLE_RESEARCH_APPROVED",
        "canonical_replacement_allowed": False,
        "evidence": evidence,
    }
    payload["evidence_hash"] = content_hash(payload)
    return payload

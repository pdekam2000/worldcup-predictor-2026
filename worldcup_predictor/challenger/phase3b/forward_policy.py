"""Forward shadow policy after Phase 3B gates."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.challenger.constants import (
    CHALLENGER_FINAL_DECISION_AUTHORITY,
    CHALLENGER_IS_SHADOW,
    CHALLENGER_PUBLIC_VISIBLE,
)


def decide_forward_policy(selection: dict[str, Any], *, domain_limited: bool = False) -> dict[str, Any]:
    """
    Pause new GBGM-1 forward generation if still below league baseline.
    Never deletes historical Challenger freezes. Canonical unaffected.
    """
    beats_league = bool(selection.get("beats_league_baseline_holdout"))
    beats_gbgm1 = bool(selection.get("beats_gbgm_v1_holdout"))
    if beats_league and beats_gbgm1:
        # Global holdout beat of league baseline → IMPROVED; domain flag is informational only
        status = "GBGM_IMPROVED_CHALLENGER_READY"
        return {
            "forward_active": True,
            "reason": "PHASE3B_GATES_PASSED",
            "activate_candidate": selection.get("chosen_by_validation"),
            "preserve_gbgm1_history": True,
            "pause_gbgm1_new_generation": True,
            "status": status,
            "domain_limited_signal": domain_limited,
            "is_shadow": CHALLENGER_IS_SHADOW,
            "public_visible": CHALLENGER_PUBLIC_VISIBLE,
            "final_decision_authority": CHALLENGER_FINAL_DECISION_AUTHORITY,
        }
    if domain_limited and beats_gbgm1 and not beats_league:
        return {
            "forward_active": True,
            "reason": "DOMAIN_SPECIFIC_GATES_PASSED",
            "activate_candidate": selection.get("chosen_by_validation"),
            "preserve_gbgm1_history": True,
            "pause_gbgm1_new_generation": True,
            "status": "GBGM_DOMAIN_LIMITED_CHALLENGER_READY",
            "note": "Global model still below league baseline; shadow only in improving domains",
            "is_shadow": True,
            "public_visible": False,
            "final_decision_authority": False,
        }
    return {
        "forward_active": False,
        "reason": "MODEL_BELOW_BASELINE",
        "preserve_gbgm1_history": True,
        "pause_gbgm1_new_generation": True,
        "status": "GBGM_REDESIGN_REQUIRED",
        "is_shadow": CHALLENGER_IS_SHADOW,
        "public_visible": CHALLENGER_PUBLIC_VISIBLE,
        "final_decision_authority": CHALLENGER_FINAL_DECISION_AUTHORITY,
        "note": "Do not accumulate 250 forward fixtures for a clearly inferior model",
    }

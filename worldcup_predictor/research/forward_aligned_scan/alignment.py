"""Alignment tier classification and research-only scoring."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.forward_aligned_scan.constants import (
    TIER_A,
    TIER_B,
    TIER_REJECTED,
    TIER_S,
    TOP5_MASS_TIER_S_MIN,
)
from worldcup_predictor.research.forward_aligned_scan.directions import norm_dir


SCORE_FORMULA = """
Research-only alignment score (0–100), does not alter canonical outputs:

Positive:
  +25 WDE = ECSE Top5 majority
  +15 WDE = ECSE Top3 majority
  +12 WDE = ECSE Top1 direction
  +12 WDE = FT marginal
  +8  WDE = market direction
  +10 consensus == HIGH_AGREEMENT
  +10 Top5 Mass >= 0.70
  +8  Top5 Mass 0.60–0.699
  +6  Top5 Mass 0.52–0.599
  +3  Top5 Mass 0.45–0.519
  +5  stable Top5 across snapshots (when known)
  +3  no_bet == false

Penalties:
  -25 HIGH_CONFLICT
  -8  no_bet == true
  -6  Top5 boundary instability (when known)
  -10 WDE/FT conflict
  -8  market-direction conflict (unless WDE is draw)

Incomplete no_bet diagnostics: informational only (no penalty without evidence).
Clamped to [0, 100].
"""


def _agree(a: str | None, b: str | None) -> bool:
    return bool(a and b and norm_dir(a) == norm_dir(b))


def alignment_score(
    *,
    dirs: dict[str, Any],
    consensus: str | None,
    no_bet: bool | None,
    top5_mass: float | None,
    top5_stable: bool | None = None,
    top5_boundary_unstable: bool | None = None,
) -> dict[str, Any]:
    wde = dirs.get("wde_decision")
    parts: list[dict[str, Any]] = []
    score = 0

    def add(label: str, pts: int) -> None:
        nonlocal score
        score += pts
        parts.append({"component": label, "points": pts})

    if _agree(wde, dirs.get("ecse_top5_majority")):
        add("wde_eq_ecse_top5_majority", 25)
    if _agree(wde, dirs.get("ecse_top3_majority")):
        add("wde_eq_ecse_top3_majority", 15)
    if _agree(wde, dirs.get("ecse_top1_direction")):
        add("wde_eq_ecse_top1", 12)
    if _agree(wde, dirs.get("ft_marginal")):
        add("wde_eq_ft_marginal", 12)
    if _agree(wde, dirs.get("market_direction")):
        add("wde_eq_market", 8)

    cons = str(consensus or "").upper()
    if cons == "HIGH_AGREEMENT":
        add("high_agreement", 10)

    mass = float(top5_mass) if top5_mass is not None else None
    if mass is not None:
        if mass >= 0.70:
            add("top5_mass_ge_070", 10)
        elif mass >= 0.60:
            add("top5_mass_060_069", 8)
        elif mass >= 0.52:
            add("top5_mass_052_059", 6)
        elif mass >= 0.45:
            add("top5_mass_045_051", 3)

    if top5_stable is True:
        add("top5_stable", 5)
    if no_bet is False:
        add("no_bet_false", 3)

    if cons == "HIGH_CONFLICT":
        add("penalty_high_conflict", -25)
    if no_bet is True:
        add("penalty_no_bet_true", -8)
    if top5_boundary_unstable is True:
        add("penalty_top5_boundary_unstable", -6)
    if wde and dirs.get("ft_marginal") and not _agree(wde, dirs.get("ft_marginal")):
        add("penalty_wde_ft_conflict", -10)
    if (
        wde
        and dirs.get("market_direction")
        and not _agree(wde, dirs.get("market_direction"))
        and norm_dir(wde) != "draw"
    ):
        add("penalty_market_conflict", -8)

    clamped = max(0, min(100, score))
    return {
        "alignment_score": clamped,
        "raw_score": score,
        "components": parts,
        "formula": SCORE_FORMULA.strip(),
        "research_only": True,
    }


def classify_alignment(
    *,
    dirs: dict[str, Any],
    consensus: str | None,
    no_bet: bool | None,
    top5_mass: float | None,
    odds_ready: bool,
    quality_conflict: bool = False,
    major_model_movement: bool = False,
) -> dict[str, Any]:
    wde = dirs.get("wde_decision")
    ft = dirs.get("ft_marginal")
    t1 = dirs.get("ecse_top1_direction")
    t3 = dirs.get("ecse_top3_majority")
    t5 = dirs.get("ecse_top5_majority")
    market = dirs.get("market_direction")
    cons = str(consensus or "").upper()
    reasons: list[str] = []
    caution = False

    if not odds_ready:
        return {
            "alignment_tier": TIER_REJECTED,
            "reject_reasons": ["odds_not_ready"],
            "selected_reason": None,
            "caution": False,
        }
    if dirs.get("ecse_direction_tie") or dirs.get("ecse_top5_majority_label") == "ECSE_DIRECTION_TIE":
        return {
            "alignment_tier": TIER_REJECTED,
            "reject_reasons": ["ECSE_DIRECTION_TIE"],
            "selected_reason": None,
            "caution": False,
        }
    if major_model_movement or quality_conflict:
        return {
            "alignment_tier": TIER_REJECTED,
            "reject_reasons": ["major_quality_or_model_movement"],
            "selected_reason": None,
            "caution": False,
        }
    if not wde or not t5:
        return {
            "alignment_tier": TIER_REJECTED,
            "reject_reasons": ["missing_wde_or_ecse_top5_majority"],
            "selected_reason": None,
            "caution": False,
        }
    if not _agree(wde, t5):
        return {
            "alignment_tier": TIER_REJECTED,
            "reject_reasons": ["WDE_ECSE_TOP5_MAJORITY_CONFLICT"],
            "selected_reason": None,
            "caution": False,
        }

    # --- Tier S ---
    market_ok = _agree(wde, market) or norm_dir(wde) == "draw"
    mass_ok = top5_mass is not None and float(top5_mass) >= TOP5_MASS_TIER_S_MIN
    tier_s_ok = (
        _agree(wde, ft)
        and _agree(wde, t1)
        and _agree(wde, t3)
        and _agree(wde, t5)
        and market_ok
        and cons == "HIGH_AGREEMENT"
        and no_bet is False
        and mass_ok
        and not quality_conflict
        and odds_ready
    )
    if tier_s_ok:
        return {
            "alignment_tier": TIER_S,
            "reject_reasons": [],
            "selected_reason": (
                "FULL_ALIGNMENT: WDE=FT=Top1=Top3maj=Top5maj; market ok; "
                "HIGH_AGREEMENT; no_bet=false; Top5 Mass>=0.52; fresh odds"
            ),
            "caution": False,
            "tier_s_failure_primary": None,
            "tier_s_failure_reasons": [],
        }

    # Collect explicit Tier S gate failures (for Tier A reporting)
    tier_s_failures: list[str] = []
    if no_bet is True:
        tier_s_failures.append("FAILED_TIER_S_NO_BET_TRUE")
    if top5_mass is None:
        tier_s_failures.append("FAILED_TIER_S_TOP5_MASS_UNAVAILABLE")
    elif float(top5_mass) < TOP5_MASS_TIER_S_MIN:
        tier_s_failures.append("FAILED_TIER_S_TOP5_MASS_BELOW_0_52")
    if wde and t1 and not _agree(wde, t1):
        tier_s_failures.append("FAILED_TIER_S_TOP1_DIRECTION_CONFLICT")
    if wde and t3 and not _agree(wde, t3):
        tier_s_failures.append("FAILED_TIER_S_TOP3_MAJORITY_CONFLICT")
    if wde and ft and not _agree(wde, ft):
        tier_s_failures.append("FAILED_TIER_S_FT_MARGINAL_CONFLICT")
    if not market_ok and market:
        tier_s_failures.append("FAILED_TIER_S_MARKET_DIRECTION_CONFLICT")
    if cons and cons != "HIGH_AGREEMENT":
        tier_s_failures.append("FAILED_TIER_S_CONSENSUS_NOT_HIGH_AGREEMENT")
    primary_fail = (
        "FAILED_TIER_S_MULTIPLE_GATES"
        if len(tier_s_failures) > 1
        else (tier_s_failures[0] if tier_s_failures else "FAILED_TIER_S_UNKNOWN_GATE")
    )

    # --- Tier A ---
    extras = sum(
        [
            _agree(wde, ft),
            _agree(wde, t1),
            _agree(wde, t3),
            _agree(wde, market) or (norm_dir(wde) == "draw" and market is not None),
        ]
    )
    tier_a_ok = (
        _agree(wde, t5)
        and extras >= 2
        and cons == "HIGH_AGREEMENT"
        and odds_ready
        and not quality_conflict
    )
    if tier_a_ok:
        if no_bet is True:
            caution = True
            reasons.append("CAUTION:no_bet=true")
        # no_bet=true cannot be Tier S (already enforced); allowed in Tier A with CAUTION
        # if no_bet is None, still allow Tier A but note missing diagnostics
        if no_bet is None:
            reasons.append("INFO:no_bet_diagnostics_incomplete")
        return {
            "alignment_tier": TIER_A,
            "reject_reasons": [],
            "selected_reason": (
                "STRONG_ALIGNMENT: WDE=ECSE Top5 majority; "
                f"{extras}/4 supporting signals; HIGH_AGREEMENT; fresh odds"
                + ("; " + "; ".join(reasons) if reasons else "")
            ),
            "caution": caution,
            "tier_s_failure_primary": primary_fail,
            "tier_s_failure_reasons": tier_s_failures,
        }

    # --- Tier B watchlist ---
    return {
        "alignment_tier": TIER_B,
        "reject_reasons": [],
        "selected_reason": "DIRECTIONAL_ALIGNMENT: WDE=ECSE Top5 majority; fresh odds; watchlist only",
        "caution": bool(no_bet is True),
        "tier_s_failure_primary": primary_fail,
        "tier_s_failure_reasons": tier_s_failures,
    }

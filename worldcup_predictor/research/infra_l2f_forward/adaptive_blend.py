"""Adaptive L2-F blend variants (shadow calibration — chronological eval only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.football_strength_foundation.lambda_v2 import (
    LambdaV2Output,
    football_only,
)
from worldcup_predictor.research.football_strength_foundation.team_strength_engine import MatchStrengthBundle
from worldcup_predictor.research.football_strength_foundation.totals_market import TotalsLine, invert_multi_line
from worldcup_predictor.research.lambda_team_strength.metrics import clip_lambda


def _pair(tot: float, share: float) -> tuple[float, float, float]:
    lh = clip_lambda(tot * share)
    la = clip_lambda(tot * (1.0 - share))
    return lh, la, lh + la


def l2f_adaptive(
    bundle: MatchStrengthBundle,
    lines: list[TotalsLine],
    mkt: LambdaV2Output,
    *,
    odds_fresh: bool = True,
    bookmaker_count: int | None = None,
    variant: str = "quality_uncertainty_disagreement",
) -> LambdaV2Output:
    """Adaptive blend with explicit guardrail-oriented weights."""
    foot = football_only(bundle)
    inv = invert_multi_line(lines)
    n = min(bundle.home.n_total, bundle.away.n_total)
    # base football weight from sample size
    w_foot = n / (n + 12.0)
    if bundle.home.low_data or bundle.away.low_data:
        w_foot *= 0.65
    if bundle.home.promoted_like or bundle.away.promoted_like:
        w_foot *= 0.85  # safer prior — do not force low-goal; reduce football confidence

    w_mkt = 1.0 - w_foot
    if not odds_fresh:
        w_mkt *= 0.55
    if bookmaker_count is not None and bookmaker_count < 5:
        w_mkt *= 0.75
    n_lines = int(inv.get("n_lines") or 0)
    if n_lines >= 2:
        w_mkt *= 1.1  # boost market when multi-line present
    elif n_lines == 0:
        w_mkt *= 0.9

    # disagreement-aware: if football and market totals diverge, trust higher-quality side
    foot_tot = foot.lambda_total
    mkt_tot = float(inv["lambda_total"]) if inv.get("lambda_total") is not None else mkt.lambda_total
    disagree = abs(foot_tot - mkt_tot)
    if variant == "fixed_050":
        w_foot, w_mkt = 0.5, 0.5
    elif variant == "quality_weighted":
        q_f = 1.0 - 0.15 * (bundle.home.fallback_count + bundle.away.fallback_count)
        q_m = 0.7 if odds_fresh else 0.4
        w_foot = max(0.05, q_f)
        w_mkt = max(0.05, q_m)
    elif variant == "uncertainty_weighted":
        unc = 0.5 * (bundle.home.uncertainty + bundle.away.uncertainty)
        w_foot = max(0.1, 0.55 * (1.0 - unc))
        w_mkt = 1.0 - w_foot
    elif variant == "disagreement_aware":
        if disagree > 0.75:
            # prefer market if fresh, else football if rich history
            if odds_fresh and (bookmaker_count or 0) >= 5:
                w_foot, w_mkt = 0.35, 0.65
            elif n >= 20:
                w_foot, w_mkt = 0.6, 0.4
            else:
                w_foot, w_mkt = 0.45, 0.55
    elif variant == "totals_aware":
        if n_lines >= 2:
            w_foot, w_mkt = 0.4, 0.6
        else:
            w_foot = n / (n + 10.0)
            w_mkt = 1.0 - w_foot
    # else quality_uncertainty_disagreement: keep w_foot/w_mkt from above, nudge by disagree
    else:
        if disagree > 1.0 and odds_fresh:
            w_mkt = min(0.75, w_mkt + 0.1)
            w_foot = 1.0 - w_mkt

    s = w_foot + w_mkt
    w_foot, w_mkt = w_foot / s, w_mkt / s
    share = mkt.lambda_home / mkt.lambda_total if mkt.lambda_total else 0.55
    tot = w_foot * foot_tot + w_mkt * mkt_tot
    # conditional expansion for volatile / collapse signals (not uniform)
    risk = 0.5 * (
        bundle.home.freq_over25
        + bundle.away.freq_over25
        + bundle.home.freq_score_3plus
        + bundle.away.freq_concede_3plus
    )
    if risk > 0.55:
        tot *= 1.0 + min(0.12, (risk - 0.55) * 0.25)
    lh, la, tot = _pair(tot, share)
    return LambdaV2Output(
        f"L2-F_adaptive_{variant}",
        lh,
        la,
        tot,
        0.5 * (bundle.home.uncertainty + bundle.away.uncertainty),
        w_foot,
        w_mkt,
        "adaptive_blend",
        0.5 * (foot.feature_quality + mkt.feature_quality),
        {"variant": variant, "disagree": disagree, "n_lines": n_lines, "n": n, "risk": risk},
    )

"""Lambda V2 candidates (shadow only — never overwrite extract_lambdas)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas
from worldcup_predictor.research.football_strength_foundation.constants import LAMBDA_CEIL, LAMBDA_FLOOR
from worldcup_predictor.research.football_strength_foundation.team_strength_engine import MatchStrengthBundle
from worldcup_predictor.research.football_strength_foundation.totals_market import TotalsLine, invert_multi_line
from worldcup_predictor.research.lambda_team_strength.metrics import clip_lambda


@dataclass
class LambdaV2Output:
    model_id: str
    lambda_home: float
    lambda_away: float
    lambda_total: float
    uncertainty: float
    football_contribution: float
    market_contribution: float
    fallback_path: str
    feature_quality: float
    explanation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clip_pair(lh: float, la: float) -> tuple[float, float, float]:
    lh = clip_lambda(lh, LAMBDA_FLOOR, LAMBDA_CEIL)
    la = clip_lambda(la, LAMBDA_FLOOR, LAMBDA_CEIL)
    return lh, la, lh + la


def football_only(bundle: MatchStrengthBundle) -> LambdaV2Output:
    """L2-A: attack vs opponent defense."""
    h, a = bundle.home, bundle.away
    # expected home goals ~ home attack_home vs away defense_away
    lh = 0.55 * h.attack_home + 0.45 * a.defense_away
    la = 0.55 * a.attack_away + 0.45 * h.defense_home
    # mild home advantage already in home/away splits
    unc = 0.5 * (h.uncertainty + a.uncertainty)
    lh, la, tot = _clip_pair(lh, la)
    q = 1.0 - 0.1 * (h.fallback_count + a.fallback_count)
    return LambdaV2Output(
        "L2-A_football_only",
        lh,
        la,
        tot,
        unc,
        1.0,
        0.0,
        "football_strength",
        max(0.0, q),
        {"mode": "attack_vs_defense"},
    )


def market_only_from_odds_row(odds_row: dict[str, Any] | None, *, fallback_lh: float, fallback_la: float) -> LambdaV2Output:
    """L2-B: reconstructed extract_lambdas baseline."""
    if odds_row:
        feat = extract_lambdas(odds_row)
        if feat:
            lh, la, tot = _clip_pair(float(feat["lambda_home"]), float(feat["lambda_away"]))
            return LambdaV2Output(
                "L2-B_market_only",
                lh,
                la,
                tot,
                0.15,
                0.0,
                1.0,
                "extract_lambdas",
                float(feat.get("data_quality_score") or 0.5),
                {"method_version": feat.get("method_version"), "source_features": feat.get("source_feature_count")},
            )
    lh, la, tot = _clip_pair(fallback_lh, fallback_la)
    return LambdaV2Output(
        "L2-B_market_only",
        lh,
        la,
        tot,
        0.2,
        0.0,
        1.0,
        "canonical_freeze_lambda",
        0.6,
        {"note": "used freeze lambdas as market reconstruction"},
    )


def blend(foot: LambdaV2Output, mkt: LambdaV2Output, w_foot: float, model_id: str, expl: dict[str, Any]) -> LambdaV2Output:
    w_foot = min(max(w_foot, 0.0), 1.0)
    lh = w_foot * foot.lambda_home + (1 - w_foot) * mkt.lambda_home
    la = w_foot * foot.lambda_away + (1 - w_foot) * mkt.lambda_away
    lh, la, tot = _clip_pair(lh, la)
    return LambdaV2Output(
        model_id,
        lh,
        la,
        tot,
        0.5 * (foot.uncertainty + mkt.uncertainty),
        w_foot,
        1 - w_foot,
        "blend",
        0.5 * (foot.feature_quality + mkt.feature_quality),
        expl,
    )


def football_hda_blend(bundle: MatchStrengthBundle, mkt: LambdaV2Output, *, share_from_hda: float | None = None) -> LambdaV2Output:
    """L2-C: football totals shape with optional H/D/A share."""
    foot = football_only(bundle)
    tot = 0.55 * foot.lambda_total + 0.45 * mkt.lambda_total
    if share_from_hda is None:
        share = mkt.lambda_home / mkt.lambda_total if mkt.lambda_total else 0.55
    else:
        share = share_from_hda
    lh, la, tot = _clip_pair(tot * share, tot * (1 - share))
    return LambdaV2Output(
        "L2-C_football_hda",
        lh,
        la,
        tot,
        0.5 * (foot.uncertainty + mkt.uncertainty),
        0.55,
        0.45,
        "football_total+hda_share",
        0.5 * (foot.feature_quality + mkt.feature_quality),
        {"share": share},
    )


def football_totals_blend(bundle: MatchStrengthBundle, lines: list[TotalsLine], mkt: LambdaV2Output) -> LambdaV2Output:
    """L2-D: football + multi-line totals inversion."""
    foot = football_only(bundle)
    inv = invert_multi_line(lines)
    if inv.get("lambda_total") is None:
        return blend(foot, mkt, 0.5, "L2-D_football_totals", {"inversion": inv, "fallback": "market"})
    tot_mkt = float(inv["lambda_total"])
    # keep share from market 1X2 reconstruction
    share = mkt.lambda_home / mkt.lambda_total if mkt.lambda_total else 0.55
    foot_share = foot.lambda_home / foot.lambda_total if foot.lambda_total else 0.55
    share = 0.5 * share + 0.5 * foot_share
    tot = 0.5 * foot.lambda_total + 0.5 * tot_mkt
    # regime bump if football high-total freqs elevated
    risk = 0.5 * (bundle.home.freq_over25 + bundle.away.freq_over25 + bundle.home.freq_score_3plus + bundle.away.freq_concede_3plus)
    if risk > 0.55 and inv.get("n_lines", 0) >= 1:
        tot *= 1.0 + min(0.18, (risk - 0.55) * 0.4)
    lh, la, tot = _clip_pair(tot * share, tot * (1 - share))
    return LambdaV2Output(
        "L2-D_football_totals",
        lh,
        la,
        tot,
        0.45 * foot.uncertainty + 0.2,
        0.5,
        0.5,
        "football+totals_inversion",
        foot.feature_quality,
        {"inversion": inv, "risk": risk},
    )


def full_blend(bundle: MatchStrengthBundle, lines: list[TotalsLine], mkt: LambdaV2Output) -> LambdaV2Output:
    """L2-E: football + H/D/A + totals."""
    d = football_totals_blend(bundle, lines, mkt)
    c = football_hda_blend(bundle, mkt)
    return blend(d, c, 0.55, "L2-E_full_blend", {"from": ["L2-D", "L2-C"]})


def uncertainty_aware_blend(
    bundle: MatchStrengthBundle,
    lines: list[TotalsLine],
    mkt: LambdaV2Output,
    *,
    odds_fresh: bool = True,
    bookmaker_count: int | None = None,
) -> LambdaV2Output:
    """L2-F: adaptive weights from data quality."""
    foot = football_only(bundle)
    inv = invert_multi_line(lines)
    n = min(bundle.home.n_total, bundle.away.n_total)
    w_foot = n / (n + 12.0)
    # reduce football when low data
    if bundle.home.low_data or bundle.away.low_data:
        w_foot *= 0.7
    # reduce market when stale / thin books / missing alternate totals
    w_mkt = 1.0 - w_foot
    if not odds_fresh:
        w_mkt *= 0.6
    if bookmaker_count is not None and bookmaker_count < 5:
        w_mkt *= 0.75
    if inv.get("n_lines", 0) < 2:
        w_mkt *= 0.85
    # renormalize
    s = w_foot + w_mkt
    w_foot, w_mkt = w_foot / s, w_mkt / s
    tot_mkt = float(inv["lambda_total"]) if inv.get("lambda_total") is not None else mkt.lambda_total
    share = mkt.lambda_home / mkt.lambda_total if mkt.lambda_total else 0.55
    tot = w_foot * foot.lambda_total + w_mkt * tot_mkt
    # conditional uncertainty expansion (not uniform tail inflate)
    unc = 0.5 * (bundle.home.uncertainty + bundle.away.uncertainty)
    if bundle.home.low_data or bundle.away.low_data:
        tot *= 1.0 + 0.08 * unc
    lh, la, tot = _clip_pair(tot * share, tot * (1 - share))
    return LambdaV2Output(
        "L2-F_uncertainty_aware",
        lh,
        la,
        tot,
        unc,
        w_foot,
        w_mkt,
        "adaptive_blend",
        0.5 * (foot.feature_quality + mkt.feature_quality),
        {"w_foot": w_foot, "w_mkt": w_mkt, "inversion": inv, "n": n},
    )

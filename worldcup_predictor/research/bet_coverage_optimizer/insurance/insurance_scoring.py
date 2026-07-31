"""Insurance candidate scoring (configurable weights)."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.insurance.constants import (
    DEFAULT_INSURANCE,
    DEFAULT_INSURANCE_WEIGHTS,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.schemas import InsuranceCandidate
from worldcup_predictor.research.bet_coverage_optimizer.scoring import normalize_batch
from worldcup_predictor.research.multi_market_odds_loader import FRESH_OK


def score_insurance_candidates(
    candidates: list[dict[str, Any]],
    *,
    insurance_cfg: dict[str, Any] | None = None,
    weights: dict[str, Any] | None = None,
) -> list[InsuranceCandidate]:
    cfg = {**DEFAULT_INSURANCE, **(insurance_cfg or {})}
    w = {**DEFAULT_INSURANCE_WEIGHTS, **(weights or {})}
    min_odds = float(cfg.get("min_odds", 1.55))
    max_odds = float(cfg.get("max_odds", 25.0))
    min_inc = float(cfg.get("min_incremental_uncovered_mass", 0.03))
    max_overlap = float(cfg.get("max_primary_overlap_ratio", 0.85))
    top_k = int(cfg.get("top_k_candidates", 5))

    # Pre-pass eligibility
    for c in candidates:
        reasons = list(c.get("rejection_reasons") or [])
        eligible = bool(c.get("eligible", True))
        odds = c.get("odds")
        freshness = str(c.get("odds_freshness_status") or "")
        inc = float(c.get("incremental_uncovered_probability_mass") or 0.0)
        overlap_ratio = float(c.get("primary_overlap_ratio") or 0.0)

        if odds is None:
            eligible = False
            reasons.append("MISSING_ODDS")
        else:
            try:
                o = float(odds)
            except (TypeError, ValueError):
                eligible = False
                reasons.append("INVALID_ODDS")
                o = None
            if o is not None:
                if o <= 1.0:
                    eligible = False
                    reasons.append("NON_POSITIVE_ODDS")
                if o < min_odds:
                    eligible = False
                    reasons.append(f"ODDS_BELOW_MIN:{min_odds}")
                if o > max_odds:
                    eligible = False
                    reasons.append(f"ODDS_ABOVE_MAX:{max_odds}")

        if freshness and freshness not in FRESH_OK and freshness not in {"FRESH", "fresh", "ODDS_FRESH"}:
            if freshness in {"STALE_ODDS", "REQUIRES_FRESH_ODDS", "stale", "STALE"}:
                eligible = False
                reasons.append("STALE_REAL_ODDS")

        if c.get("unsupported_semantics") or c.get("incomplete_mapping"):
            eligible = False
            reasons.append("UNSUPPORTED_MARKET_MAPPING")

        if inc < min_inc:
            eligible = False
            reasons.append(f"INCREMENTAL_MASS_BELOW_MIN:{min_inc}")

        if overlap_ratio > max_overlap:
            eligible = False
            reasons.append(f"PRIMARY_OVERLAP_TOO_HIGH:{max_overlap}")

        if inc <= 0:
            eligible = False
            reasons.append("FULLY_REDUNDANT_OR_ZERO_INCREMENT")

        c["eligible"] = eligible
        c["rejection_reasons"] = sorted(set(reasons))

    # Normalize components across pool
    incs = [c.get("incremental_uncovered_probability_mass") for c in candidates]
    risks = [c.get("residual_risk_reduction") for c in candidates]
    edges = [c.get("estimated_edge") if c.get("estimated_edge") is not None else -1.0 for c in candidates]
    logs = [math.log(float(c["odds"])) if c.get("odds") and float(c["odds"]) > 1.0 else 0.0 for c in candidates]
    divs = [c.get("diversification_score") for c in candidates]
    overlaps = [c.get("primary_overlap_ratio") for c in candidates]

    n_inc = normalize_batch(incs)
    n_risk = normalize_batch(risks)
    n_edge = normalize_batch(edges)
    n_log = normalize_batch(logs)
    n_div = normalize_batch(divs)
    n_ov = normalize_batch(overlaps)

    out: list[InsuranceCandidate] = []
    for i, c in enumerate(candidates):
        eligible = bool(c.get("eligible"))
        score = None
        if eligible:
            score = round(
                float(w["incremental_uncovered_probability_mass"]) * n_inc[i]
                + float(w["residual_risk_reduction"]) * n_risk[i]
                + float(w["estimated_edge"]) * n_edge[i]
                + float(w["log_odds"]) * n_log[i]
                + float(w["diversification"]) * n_div[i]
                - float(w["primary_overlap_penalty"]) * n_ov[i],
                8,
            )
            score = max(0.0, score)
        reasons = list(c.get("rejection_reasons") or [])
        out.append(
            InsuranceCandidate(
                fixture_id=int(c.get("fixture_id") or 0),
                rank=0,
                market_label=str(c.get("market_label") or ""),
                market_key=str(c.get("market_key") or ""),
                market_type=str(c.get("market_type") or ""),
                market_parameters=dict(c.get("market_parameters") or {}),
                bookmaker=c.get("bookmaker"),
                odds=c.get("odds"),
                covered_uncovered_scores=list(c.get("covered_uncovered_scores") or []),
                incremental_uncovered_probability_mass=float(c.get("incremental_uncovered_probability_mass") or 0.0),
                primary_overlap_mass=float(c.get("primary_overlap_mass") or 0.0),
                primary_overlap_ratio=float(c.get("primary_overlap_ratio") or 0.0),
                residual_uncovered_mass_after=float(c.get("residual_uncovered_mass_after") or 0.0),
                residual_risk_reduction=float(c.get("residual_risk_reduction") or 0.0),
                implied_probability=c.get("implied_probability"),
                model_probability=float(c.get("model_probability") or c.get("estimated_model_probability") or 0.0),
                estimated_edge=c.get("estimated_edge"),
                diversification_score=float(c.get("diversification_score") or 0.0),
                insurance_score=score,
                eligible=eligible,
                rejection_reason=(None if eligible else (reasons[0] if reasons else "NOT_ELIGIBLE")),
                rejection_reasons=reasons,
                source_type=c.get("source_type"),
                odds_timestamp=c.get("odds_timestamp"),
            )
        )

    out.sort(
        key=lambda x: (
            0 if x.eligible and x.insurance_score is not None else 1,
            -(x.insurance_score if x.insurance_score is not None else -1.0),
            -(x.incremental_uncovered_probability_mass or 0.0),
            str(x.market_key),
        )
    )
    for i, row in enumerate(out[:], start=1):
        row.rank = i
    # Keep full list ranked; consumers take top_k eligible
    _ = top_k
    return out

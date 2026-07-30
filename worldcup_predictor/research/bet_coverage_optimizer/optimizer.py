"""Core optimizer: 3 Exact + 1 Smart Coverage per fixture."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer import (
    RECOMMENDATION_VERSION,
    STATUS_COVERAGE_UNAVAILABLE,
    STATUS_OK,
)
from worldcup_predictor.research.bet_coverage_optimizer.config import (
    DEFAULT_TOP_CANDIDATES,
    scoring_weights_from_config,
    validate_top_n,
)
from worldcup_predictor.research.bet_coverage_optimizer.exact_consensus import (
    merge_top_n_targets,
    model_snapshot_hash,
    select_exact_scores,
)
from worldcup_predictor.research.bet_coverage_optimizer.evidence import evidence_hash
from worldcup_predictor.research.bet_coverage_optimizer.models import (
    CoverageMarketEvaluation,
    CoverageRecommendation,
    ExactSelection,
    ModelTopScores,
    ScoringWeights,
)
from worldcup_predictor.research.bet_coverage_optimizer.candidate_builder import load_and_build_candidates
from worldcup_predictor.research.bet_coverage_optimizer.scoring import score_candidates
from worldcup_predictor.research.multi_market_odds_loader import FRESH_OK, MarketPrice


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _eval_from_candidate(c: dict[str, Any]) -> CoverageMarketEvaluation:
    ev = CoverageMarketEvaluation(
        fixture_id=int(c["fixture_id"]),
        bookmaker=c.get("bookmaker"),
        provider=c.get("provider"),
        market_key=str(c.get("market_key") or ""),
        market_label=str(c.get("market_label") or ""),
        market_type=str(c.get("market_type") or ""),
        market_parameters=dict(c.get("market_parameters") or {}),
        odds=c.get("odds"),
        odds_timestamp=c.get("odds_timestamp"),
        odds_age_seconds=c.get("odds_age_seconds"),
        odds_freshness_status=c.get("odds_freshness_status"),
        target_scores=list(c.get("target_scores") or []),
        covered_scores=list(c.get("covered_scores") or []),
        covered_probability_mass=float(c.get("covered_probability_mass") or 0.0),
        exact_overlap_scores=list(c.get("exact_overlap_scores") or []),
        non_exact_covered_scores=list(c.get("non_exact_covered_scores") or []),
        exact_overlap_probability_mass=float(c.get("exact_overlap_probability_mass") or 0.0),
        non_exact_coverage_probability_mass=float(c.get("non_exact_coverage_probability_mass") or 0.0),
        estimated_model_probability=float(c.get("estimated_model_probability") or 0.0),
        implied_probability=c.get("implied_probability"),
        estimated_edge=c.get("estimated_edge"),
        coverage_score=c.get("coverage_score"),
        eligible=bool(c.get("eligible")),
        rejection_reasons=list(c.get("rejection_reasons") or []),
    )
    ev.evidence_hash = evidence_hash(
        {
            "fixture_id": ev.fixture_id,
            "market_key": ev.market_key,
            "market_parameters": ev.market_parameters,
            "odds": ev.odds,
            "odds_timestamp": ev.odds_timestamp,
            "odds_freshness_status": ev.odds_freshness_status,
            "covered_scores": ev.covered_scores,
            "coverage_score": ev.coverage_score,
        }
    )
    return ev


def attach_exact_odds(selections: list[ExactSelection], prices: list[MarketPrice]) -> None:
    by_score: dict[str, MarketPrice] = {}
    for p in prices:
        if p.market_family != "exact_score":
            continue
        if str(p.freshness or "") and str(p.freshness) not in FRESH_OK:
            continue
        by_score[str(p.selection).replace(" ", "")] = p
    for sel in selections:
        p = by_score.get(sel.score)
        if p:
            sel.odds = float(p.decimal_odds)
            sel.odds_freshness_status = p.freshness


def build_ranked_candidates(
    evals: list[CoverageMarketEvaluation],
    *,
    selected: CoverageMarketEvaluation | None,
    top_k: int = DEFAULT_TOP_CANDIDATES,
) -> list[dict[str, Any]]:
    """Top-K markets ranked by coverage_score (eligible first), then mass."""
    ordered = sorted(
        evals,
        key=lambda e: (
            0 if e.eligible and e.coverage_score is not None else 1,
            -(e.coverage_score if e.coverage_score is not None else -1.0),
            -(e.covered_probability_mass or 0.0),
            str(e.market_key or ""),
        ),
    )
    selected_key = selected.market_key if selected else None
    rows: list[dict[str, Any]] = []
    for i, ev in enumerate(ordered[: int(top_k)], start=1):
        rows.append(ev.to_ranked_row(rank=i, selected=(selected_key is not None and ev.market_key == selected_key)))
    return rows


def optimize_fixture(
    fixture_id: int,
    models: list[ModelTopScores],
    *,
    top_n_scores: int = 8,
    exact_count: int = 3,
    total_selections: int = 4,
    bookmaker_allowlist: list[str] | None = None,
    weights: ScoringWeights | None = None,
    config: dict[str, Any] | None = None,
    require_fresh: bool = True,
    extra_prices: list[MarketPrice] | None = None,
    raw_payload: dict[str, Any] | None = None,
    skip_db_odds: bool = False,
    top_candidates: int | None = None,
) -> CoverageRecommendation:
    if int(total_selections) != 4:
        raise ValueError("total_selections is fixed at 4 for this research optimizer")
    if int(exact_count) != 3:
        raise ValueError("exact_count is fixed at 3 for this research optimizer")

    top_n = validate_top_n(int(top_n_scores))
    if weights is None:
        weights = scoring_weights_from_config(config)
    top_k = int(top_candidates if top_candidates is not None else (config or {}).get("top_candidates") or DEFAULT_TOP_CANDIDATES)

    exacts = select_exact_scores(models, exact_count=exact_count)
    top_targets = merge_top_n_targets(models, top_n=top_n)
    target_pairs = [(s.score, float(s.probability)) for s in top_targets]
    snap_hash = model_snapshot_hash(models)

    candidates, bundle = load_and_build_candidates(
        int(fixture_id),
        target_scores=target_pairs,
        exact_scores=[e.score for e in exacts],
        bookmaker_allowlist=bookmaker_allowlist,
        require_fresh=require_fresh,
        extra_prices=extra_prices,
        raw_payload=raw_payload,
        skip_db_odds=skip_db_odds,
    )
    if bundle is not None:
        attach_exact_odds(exacts, bundle.prices)

    scored = score_candidates(candidates, weights=weights, require_fresh=require_fresh)
    evals = [_eval_from_candidate(c) for c in scored]
    eligible = [e for e in evals if e.eligible and e.coverage_score is not None]
    selected = eligible[0] if eligible else None
    rejected = [e for e in evals if e is not selected]
    ranked = build_ranked_candidates(evals, selected=selected, top_k=top_k)

    covered: list[str] = []
    if selected:
        covered = list(dict.fromkeys(list(selected.covered_scores) + [e.score for e in exacts]))
    else:
        covered = [e.score for e in exacts]
    uncovered = [s.score for s in top_targets if s.score not in set(covered)]

    status = STATUS_OK if selected else STATUS_COVERAGE_UNAVAILABLE
    blockers: list[str] = []
    if not selected:
        blockers.append(STATUS_COVERAGE_UNAVAILABLE)
        if not scored:
            blockers.append("NO_REAL_COMPATIBLE_MARKETS")

    return CoverageRecommendation(
        fixture_id=int(fixture_id),
        model_snapshot_hash=snap_hash,
        selected_exact_scores=exacts,
        selected_coverage_market=selected,
        top_n_scores_list=top_targets,
        total_top_n_probability_mass=round(sum(float(s.probability) for s in top_targets), 8),
        covered_top_n_scores=covered,
        uncovered_top_n_scores=uncovered,
        generated_at=_utc_now(),
        top_n=top_n,
        ranked_candidates=ranked,
        scoring_weights=weights.to_dict(),
        research_only=True,
        owner_only=True,
        recommendation_version=RECOMMENDATION_VERSION,
        status=status,
        blockers=blockers,
        rejected_candidates=rejected,
        candidate_count=len(evals),
    )

"""Build insurance market candidates from REAL odds only (no synthesis)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.candidate_builder import (
    build_candidates_from_bundle,
    build_candidates_from_raw_payload,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.schemas import UncoveredMassReport
from worldcup_predictor.research.bet_coverage_optimizer.insurance.uncovered_mass import uncovered_as_target_pairs
from worldcup_predictor.research.bet_coverage_optimizer.market_semantics import (
    classified_price_to_market,
    classify_raw_market,
    human_label,
    market_key_from_parts,
)
from worldcup_predictor.research.bet_coverage_optimizer.score_mapping import covered_scores_for_market
from worldcup_predictor.research.multi_market_odds_loader import MarketPrice, MultiMarketBundle


# Canonical insurance family labels for docs / filtering (mapping still via settles_as_win)
SUPPORTED_INSURANCE_LABELS = (
    "BTTS Yes",
    "BTTS No",
    "Over 1.5",
    "Over 2.5",
    "Over 3.5",
    "Over 4.5",
    "Under 2.5",
    "Under 3.5",
    "Under 4.5",
    "Home Win",
    "Draw",
    "Away Win",
    "1X",
    "X2",
    "12",
    "Home Draw No Bet",
    "Away Draw No Bet",
    "Home Win to Nil",
    "Away Win to Nil",
    "Home Win & BTTS Yes",
    "Away Win & BTTS Yes",
    "Home Win & BTTS No",
    "Away Win & BTTS No",
    "Home Win & Under 3.5",
    "Home Win & Under 4.5",
    "Away Win & Under 3.5",
    "Away Win & Under 4.5",
    "Home Win & Over 2.5",
    "Away Win & Over 2.5",
    "Winning Margin 1",
    "Winning Margin 2",
    "Winning Margin 3+",
    "Home Team Over goals",
    "Away Team Over goals",
    "Home Team Under goals",
    "Away Team Under goals",
)


def _is_exact_duplicate(market_type: str, params: dict[str, Any], exact_scores: set[str]) -> bool:
    if market_type != "exact_score":
        return False
    return str(params.get("score") or "") in exact_scores


def enrich_candidate_against_uncovered(
    cand: dict[str, Any],
    *,
    uncovered: UncoveredMassReport,
    exact_scores: set[str],
    primary_covered: set[str],
    top_n_pairs: list[tuple[str, float]],
) -> dict[str, Any] | None:
    """Attach incremental uncovered metrics; None if mapping unsupported."""
    mt = str(cand.get("market_type") or "")
    params = dict(cand.get("market_parameters") or {})
    if _is_exact_duplicate(mt, params, exact_scores):
        cand = dict(cand)
        cand["eligible"] = False
        cand["rejection_reasons"] = list(cand.get("rejection_reasons") or []) + ["IDENTICAL_TO_EXACT_SELECTION"]
        return cand

    uncovered_scores = [u.score for u in uncovered.primary_uncovered_scores]
    covered_all = covered_scores_for_market(mt, params, [s for s, _ in top_n_pairs])
    if covered_all is None:
        cand = dict(cand)
        cand["unsupported_semantics"] = True
        cand["incomplete_mapping"] = True
        cand["eligible"] = False
        cand["rejection_reasons"] = list(cand.get("rejection_reasons") or []) + ["UNSUPPORTED_MARKET_MAPPING"]
        return cand

    top_map = {s: p for s, p in top_n_pairs}
    covered_uncovered = [s for s in covered_all if s in set(uncovered_scores)]
    covered_primary = [s for s in covered_all if s in primary_covered]
    inc_mass = round(sum(top_map.get(s, 0.0) for s in covered_uncovered), 8)
    primary_overlap = round(sum(top_map.get(s, 0.0) for s in covered_primary), 8)
    primary_mass = float(uncovered.primary_covered_probability_mass or 0.0) or 1e-12
    overlap_ratio = round(primary_overlap / primary_mass, 8) if primary_mass > 0 else 0.0
    residual_after = round(max(0.0, float(uncovered.primary_uncovered_probability_mass) - inc_mass), 8)
    risk_reduction = round(float(uncovered.primary_uncovered_probability_mass) - residual_after, 8)
    model_p = round(sum(top_map.get(s, 0.0) for s in covered_all), 8)
    odds = cand.get("odds")
    implied = (1.0 / float(odds)) if odds and float(odds) > 1.0 else None
    edge = (model_p - implied) if implied is not None else None

    out = dict(cand)
    out.update(
        {
            "covered_scores": covered_all,
            "covered_uncovered_scores": covered_uncovered,
            "incremental_uncovered_probability_mass": inc_mass,
            "primary_overlap_mass": primary_overlap,
            "primary_overlap_ratio": overlap_ratio,
            "residual_uncovered_mass_after": residual_after,
            "residual_risk_reduction": risk_reduction,
            "estimated_model_probability": model_p,
            "model_probability": model_p,
            "implied_probability": round(implied, 8) if implied is not None else None,
            "estimated_edge": round(edge, 8) if edge is not None else None,
            "diversification_score": round(1.0 - min(1.0, overlap_ratio), 8),
        }
    )
    return out


def build_insurance_raw_candidates(
    fixture_id: int,
    *,
    uncovered: UncoveredMassReport,
    exact_scores: list[str],
    primary_covered: set[str],
    top_n_pairs: list[tuple[str, float]],
    raw_payload: dict[str, Any] | None = None,
    extra_prices: list[MarketPrice] | None = None,
    bookmaker_allowlist: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build from REAL bookmaker payload/prices only — never invent markets."""
    unc_pairs = uncovered_as_target_pairs(uncovered)
    # Candidate builder scores vs uncovered as "exact" overlap target for incremental focus
    exact_proxy = list(exact_scores)
    candidates: list[dict[str, Any]] = []
    if extra_prices:
        bundle = MultiMarketBundle(
            fixture_id=int(fixture_id),
            snapshot_at=None,
            freshness_class="FRESH_ODDS",
            prices=list(extra_prices),
            coverage={},
        )
        candidates.extend(
            build_candidates_from_bundle(
                bundle,
                target_scores=top_n_pairs,
                exact_scores=exact_proxy,
                bookmaker_allowlist=bookmaker_allowlist,
            )
        )
    if raw_payload:
        candidates.extend(
            build_candidates_from_raw_payload(
                int(fixture_id),
                raw_payload,
                target_scores=top_n_pairs,
                exact_scores=exact_proxy,
                freshness="FRESH_ODDS",
                bookmaker_allowlist=bookmaker_allowlist,
            )
        )

    # Also map 1x2 / DNB style from classified prices if present in payload via raw builder already
    enriched: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in candidates:
        key = str(c.get("market_key") or "")
        if key in seen:
            continue
        row = enrich_candidate_against_uncovered(
            c,
            uncovered=uncovered,
            exact_scores=set(exact_scores),
            primary_covered=primary_covered,
            top_n_pairs=top_n_pairs,
        )
        if row is None:
            continue
        seen.add(key)
        enriched.append(row)
    return enriched


def map_manual_market_row(row: dict[str, Any], *, fixture_id: int) -> dict[str, Any] | None:
    """Map a structured real-odds market row into settlement market_type/params."""
    family = str(row.get("market_family") or "").strip().lower()
    selection = str(row.get("selection") or row.get("raw_label") or "").strip()
    # Prefer raw classify using family as market name hint
    name_hint = family.replace("_", " ")
    mapped = classify_raw_market(name_hint, selection)
    if mapped is None:
        mapped = classified_price_to_market(family, selection)
    if mapped is None and family in {"1x2", "match_winner"}:
        from worldcup_predictor.research.bet_coverage_optimizer.market_semantics import normalize_result

        side = normalize_result(selection)
        if side:
            mapped = ("1x2", {"result": side})
    if mapped is None and family in {"draw_no_bet", "dnb"}:
        from worldcup_predictor.research.bet_coverage_optimizer.market_semantics import normalize_result

        side = normalize_result(selection)
        if side in {"home", "away"}:
            # Approximate DNB as 1x2 for settlement win/lose (push → unsupported in settles)
            mapped = ("1x2", {"result": side, "dnb": True})
    if mapped is None:
        return None
    mt, params = mapped
    if row.get("line") is not None and "line" not in params:
        try:
            params["line"] = float(row["line"])
        except (TypeError, ValueError):
            pass
    try:
        odds = float(row.get("odds"))
    except (TypeError, ValueError):
        return None
    return {
        "fixture_id": int(fixture_id),
        "bookmaker": row.get("bookmaker"),
        "provider": row.get("source_type"),
        "market_key": market_key_from_parts(mt, params),
        "market_label": human_label(mt, params) if not selection else selection,
        "market_type": mt,
        "market_parameters": params,
        "odds": odds,
        "odds_timestamp": row.get("captured_at_utc"),
        "odds_freshness_status": row.get("odds_freshness_status") or "FRESH_ODDS",
        "source_type": row.get("source_type"),
        "eligible": True,
        "rejection_reasons": [],
    }

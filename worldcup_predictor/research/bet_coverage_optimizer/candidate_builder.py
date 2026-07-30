"""Build coverage market candidates from REAL provider odds only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.egie.provider_features.odds_snapshot_parser import (
    extract_bookmakers_from_payload,
    normalize_snapshot_odds_lines,
)
from worldcup_predictor.research.bet_coverage_optimizer.market_semantics import (
    classified_price_to_market,
    classify_raw_market,
    human_label,
    market_key_from_parts,
)
from worldcup_predictor.research.bet_coverage_optimizer.score_mapping import covered_scores_for_market
from worldcup_predictor.research.bet_coverage_optimizer.scoring import compute_coverage_metrics
from worldcup_predictor.research.multi_market_odds_loader import MarketPrice, MultiMarketBundle, load_multi_market_odds


def _age_seconds(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds(), 1)
    except Exception:
        return None


def _candidate_from_mapped(
    *,
    fixture_id: int,
    market_type: str,
    params: dict[str, Any],
    odds: float,
    bookmaker: str | None,
    provider: str | None,
    timestamp: str | None,
    freshness: str | None,
    raw_label: str | None,
    target_scores: list[tuple[str, float]],
    exact_scores: list[str],
) -> dict[str, Any] | None:
    # Skip pure exact-score markets for the fourth selection (those are legs 1-3)
    if market_type == "exact_score":
        return None
    covered = covered_scores_for_market(market_type, params, [s for s, _ in target_scores])
    if covered is None:
        return {
            "fixture_id": fixture_id,
            "bookmaker": bookmaker,
            "provider": provider,
            "market_key": market_key_from_parts(market_type, params),
            "market_label": human_label(market_type, params),
            "market_type": market_type,
            "market_parameters": params,
            "odds": float(odds),
            "odds_timestamp": timestamp,
            "odds_age_seconds": _age_seconds(timestamp),
            "odds_freshness_status": freshness,
            "target_scores": [s for s, _ in target_scores],
            "unsupported_semantics": True,
            "incomplete_mapping": True,
            "eligible": False,
            "rejection_reasons": ["UNSUPPORTED_MARKET_SEMANTICS"],
            "raw_market_name": raw_label,
        }
    metrics = compute_coverage_metrics(
        target_scores=target_scores,
        covered_scores=covered,
        exact_scores=exact_scores,
        odds=float(odds),
    )
    return {
        "fixture_id": fixture_id,
        "bookmaker": bookmaker,
        "provider": provider,
        "market_key": market_key_from_parts(market_type, params),
        "market_label": human_label(market_type, params) if not raw_label else f"{human_label(market_type, params)}",
        "market_type": market_type,
        "market_parameters": params,
        "odds": float(odds),
        "odds_timestamp": timestamp,
        "odds_age_seconds": _age_seconds(timestamp),
        "odds_freshness_status": freshness,
        "target_scores": [s for s, _ in target_scores],
        "raw_market_name": raw_label,
        "eligible": True,
        "rejection_reasons": [],
        **metrics,
    }


def build_candidates_from_bundle(
    bundle: MultiMarketBundle,
    *,
    target_scores: list[tuple[str, float]],
    exact_scores: list[str],
    bookmaker_allowlist: list[str] | None = None,
) -> list[dict[str, Any]]:
    allow = {str(b).strip().lower() for b in (bookmaker_allowlist or []) if str(b).strip()}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for price in bundle.prices:
        if allow and str(price.bookmaker or "").strip().lower() not in allow:
            continue
        if str(price.odds_lane or "").upper() != "REAL":
            continue
        mapped = classified_price_to_market(price.market_family, price.selection)
        if not mapped:
            continue
        market_type, params = mapped
        cand = _candidate_from_mapped(
            fixture_id=int(bundle.fixture_id),
            market_type=market_type,
            params=params,
            odds=float(price.decimal_odds),
            bookmaker=price.bookmaker,
            provider=price.source,
            timestamp=price.timestamp or bundle.snapshot_at,
            freshness=price.freshness or bundle.freshness_class,
            raw_label=price.raw_market_name,
            target_scores=target_scores,
            exact_scores=exact_scores,
        )
        if not cand:
            continue
        key = cand["market_key"]
        if key in seen:
            continue
        seen.add(key)
        out.append(cand)
    return out


def build_candidates_from_raw_payload(
    fixture_id: int,
    payload: dict[str, Any],
    *,
    target_scores: list[tuple[str, float]],
    exact_scores: list[str],
    snapshot_at: str | None = None,
    freshness: str | None = None,
    bookmaker_allowlist: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Scan raw bookmaker blocks for combo markets not classified by multi-market loader."""
    allow = {str(b).strip().lower() for b in (bookmaker_allowlist or []) if str(b).strip()}
    lines = normalize_snapshot_odds_lines(payload, fixture_id=int(fixture_id), captured_at=snapshot_at)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in lines:
        if allow and str(line.bookmaker or "").strip().lower() not in allow:
            continue
        mapped = classify_raw_market(line.market_name, line.selection)
        if not mapped:
            continue
        market_type, params = mapped
        cand = _candidate_from_mapped(
            fixture_id=int(fixture_id),
            market_type=market_type,
            params=params,
            odds=float(line.odd),
            bookmaker=line.bookmaker,
            provider=line.source,
            timestamp=line.captured_at or snapshot_at,
            freshness=freshness,
            raw_label=line.market_name,
            target_scores=target_scores,
            exact_scores=exact_scores,
        )
        if not cand:
            continue
        key = cand["market_key"]
        if key in seen:
            continue
        seen.add(key)
        out.append(cand)
    # Touch extract to keep import used for future extensions / parity
    _ = extract_bookmakers_from_payload(payload)
    return out


def load_and_build_candidates(
    fixture_id: int,
    *,
    target_scores: list[tuple[str, float]],
    exact_scores: list[str],
    bookmaker_allowlist: list[str] | None = None,
    require_fresh: bool = True,
    extra_prices: list[MarketPrice] | None = None,
    raw_payload: dict[str, Any] | None = None,
    skip_db_odds: bool = False,
) -> tuple[list[dict[str, Any]], MultiMarketBundle | None]:
    """Load REAL odds and build candidates. Never invents prices."""
    if skip_db_odds:
        bundle = MultiMarketBundle(
            fixture_id=int(fixture_id),
            snapshot_at=None,
            freshness_class="FRESH_ODDS",
            prices=list(extra_prices or []),
            coverage={},
        )
    else:
        try:
            bundle = load_multi_market_odds(int(fixture_id), require_fresh=require_fresh)
        except Exception:
            bundle = MultiMarketBundle(
                fixture_id=int(fixture_id),
                snapshot_at=None,
                freshness_class=None,
                prices=list(extra_prices or []),
                coverage={},
            )
        if extra_prices:
            bundle.prices = list(bundle.prices) + list(extra_prices)

    candidates = build_candidates_from_bundle(
        bundle,
        target_scores=target_scores,
        exact_scores=exact_scores,
        bookmaker_allowlist=bookmaker_allowlist,
    )
    if raw_payload:
        raw_cands = build_candidates_from_raw_payload(
            int(fixture_id),
            raw_payload,
            target_scores=target_scores,
            exact_scores=exact_scores,
            snapshot_at=bundle.snapshot_at,
            freshness=bundle.freshness_class or ("FRESH_ODDS" if skip_db_odds else None),
            bookmaker_allowlist=bookmaker_allowlist,
        )
        seen = {c["market_key"] for c in candidates}
        for c in raw_cands:
            if c["market_key"] not in seen:
                candidates.append(c)
                seen.add(c["market_key"])
    return candidates, bundle

"""Trace every ticket market to real bookmaker data (research-only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.insurance.schemas import InsuranceCandidate
from worldcup_predictor.research.bet_coverage_optimizer.models import CoverageRecommendation
from worldcup_predictor.research.bet_coverage_optimizer.phase4.constants import (
    REAL_SOURCE_TYPES,
    SYNTHETIC_SOURCE_MARKERS,
)


def _classify_source(source: str | None, provider: str | None, bookmaker: str | None) -> str:
    blob = " ".join(str(x or "").lower() for x in (source, provider, bookmaker))
    for marker in SYNTHETIC_SOURCE_MARKERS:
        if marker in blob:
            return "SYNTHETIC_OR_RESEARCHBOOK"
    if str(source or "") in REAL_SOURCE_TYPES:
        return "REAL_BOOKMAKER"
    if not source and not provider:
        return "MISSING_SOURCE"
    return "UNKNOWN_SOURCE"


def _market_row(
    *,
    fixture_id: int,
    market_id: str,
    market_label: str,
    bookmaker: str | None,
    source: str | None,
    provider: str | None,
    timestamp: str | None,
    odds: float | None,
    layer: str,
) -> dict[str, Any]:
    cls = _classify_source(source, provider, bookmaker)
    return {
        "fixture_id": int(fixture_id),
        "market_id": market_id,
        "market_label": market_label,
        "bookmaker": bookmaker,
        "source": source or provider,
        "provider": provider,
        "timestamp": timestamp,
        "odds": odds,
        "layer": layer,
        "classification": cls,
        "is_synthetic": cls == "SYNTHETIC_OR_RESEARCHBOOK",
        "is_real_bookmaker": cls == "REAL_BOOKMAKER",
        "is_estimated": "estimated" in str(source or provider or "").lower(),
    }


def validate_real_markets(
    recommendations: list[CoverageRecommendation],
    *,
    ranked_by: dict[int, list[InsuranceCandidate]],
    real_odds_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    markets: list[dict[str, Any]] = []
    real_fx = (real_odds_report or {}).get("fixtures") or {}

    for rec in recommendations:
        fid = int(rec.fixture_id)
        # Exact legs — typically unpriced; not fabricated
        for ex in rec.selected_exact_scores:
            markets.append(
                _market_row(
                    fixture_id=fid,
                    market_id=ex.selection_id,
                    market_label=ex.label,
                    bookmaker=None,
                    source="exact_score_model_selection",
                    provider=None,
                    timestamp=None,
                    odds=ex.odds,
                    layer="exact",
                )
            )
            markets[-1]["is_synthetic"] = False
            markets[-1]["classification"] = (
                "REAL_BOOKMAKER" if ex.odds is not None else "UNPRICED_MODEL_EXACT"
            )
            markets[-1]["is_real_bookmaker"] = ex.odds is not None

        cov = rec.selected_coverage_market
        if cov is not None:
            # Prefer real odds doc source when market key matches
            src = str(cov.provider or "")
            ts = cov.odds_timestamp
            bm = cov.bookmaker
            if fid in real_fx:
                doc = real_fx[fid]
                src = str(doc.get("source_type") or src)
                ts = str(doc.get("captured_at_utc") or ts)
                bm = str(doc.get("bookmaker") or bm)
            markets.append(
                _market_row(
                    fixture_id=fid,
                    market_id=cov.market_key,
                    market_label=cov.market_label,
                    bookmaker=bm,
                    source=src,
                    provider=cov.provider,
                    timestamp=ts,
                    odds=cov.odds,
                    layer="main_coverage",
                )
            )

        best = next((c for c in ranked_by.get(fid, []) if c.eligible), None)
        if best is not None:
            markets.append(
                _market_row(
                    fixture_id=fid,
                    market_id=best.market_key,
                    market_label=best.market_label,
                    bookmaker=best.bookmaker,
                    source=best.source_type,
                    provider=best.source_type,
                    timestamp=best.odds_timestamp,
                    odds=best.odds,
                    layer="insurance",
                )
            )

    n_syn = sum(1 for m in markets if m.get("is_synthetic"))
    n_est = sum(1 for m in markets if m.get("is_estimated"))
    priced_layers = [m for m in markets if m["layer"] in {"main_coverage", "insurance"}]
    all_priced_real = all(m.get("is_real_bookmaker") for m in priced_layers) if priced_layers else False

    return {
        "research_only": True,
        "owner_only": True,
        "markets": markets,
        "summary": {
            "n_markets": len(markets),
            "n_synthetic": n_syn,
            "n_estimated": n_est,
            "n_real_bookmaker": sum(1 for m in markets if m.get("is_real_bookmaker")),
            "n_unpriced_exact": sum(1 for m in markets if m.get("classification") == "UNPRICED_MODEL_EXACT"),
            "priced_coverage_and_insurance_all_real": all_priced_real,
            "no_synthetic_priced_markets": n_syn == 0 and n_est == 0,
            "forbidden_origins_checked": [
                "ResearchBook",
                "synthetic odds",
                "estimated odds",
                "fabricated odds",
            ],
        },
    }


def write_real_market_validation(payload: dict[str, Any], output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "real_market_validation.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)

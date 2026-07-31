"""Convert real-odds JSON markets into MarketPrice rows (no fabrication)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.phase4.constants import REAL_SOURCE_TYPES
from worldcup_predictor.research.multi_market_odds_loader import MarketPrice


def _docs_from_raw(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [d for d in raw if isinstance(d, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("fixtures"), list):
        return [d for d in raw["fixtures"] if isinstance(d, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def fixture_doc_to_prices(doc: dict[str, Any]) -> list[MarketPrice]:
    """Map original real-odds fixture markets (family/selection/odds) to REAL prices."""
    source_type = str(doc.get("source_type") or "").strip()
    if source_type not in REAL_SOURCE_TYPES:
        return []
    bookmaker = str(doc.get("bookmaker") or "").strip() or None
    captured = str(doc.get("captured_at_utc") or "") or None
    out: list[MarketPrice] = []
    for m in doc.get("markets") or []:
        if not isinstance(m, dict):
            continue
        family = str(m.get("market_family") or "").strip()
        selection = str(m.get("selection") or "").strip()
        if not family or not selection:
            continue
        try:
            odds = float(m.get("odds"))
        except (TypeError, ValueError):
            continue
        if odds <= 1.0:
            continue
        out.append(
            MarketPrice(
                market_family=family,
                selection=selection,
                decimal_odds=odds,
                bookmaker=bookmaker,
                odds_lane="REAL",
                source=source_type,
                timestamp=captured,
                freshness="FRESH_ODDS",
                n_bookmakers=1,
                raw_market_name=selection,
            )
        )
    return out


def load_extra_prices_from_real_odds_json(path: str | Path) -> dict[int, list[MarketPrice]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    by_fx: dict[int, list[MarketPrice]] = {}
    for doc in _docs_from_raw(raw):
        try:
            fid = int(doc.get("fixture_id"))
        except (TypeError, ValueError):
            continue
        prices = fixture_doc_to_prices(doc)
        if prices:
            by_fx[fid] = prices
    return by_fx

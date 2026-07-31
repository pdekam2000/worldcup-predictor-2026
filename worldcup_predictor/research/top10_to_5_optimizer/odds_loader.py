"""Real-odds loading — no fabrication; preserve manual vs API source labels."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from worldcup_predictor.research.top10_to_5_optimizer.constants import MANUAL_SOURCE, REAL_SOURCE_TYPES, STALE_MARKERS
from worldcup_predictor.research.top10_to_5_optimizer.market_semantics import (
    classified_price_to_market,
    classify_raw_market,
    covered_scores_for_market,
    human_label,
    market_key_from_parts,
)
from worldcup_predictor.research.top10_to_5_optimizer.models import MarketCandidate


def _docs(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [d for d in raw if isinstance(d, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("fixtures"), list):
        return [d for d in raw["fixtures"] if isinstance(d, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def load_real_odds_json(path: str | Path) -> dict[int, dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[int, dict[str, Any]] = {}
    for doc in _docs(raw):
        try:
            fid = int(doc.get("fixture_id"))
        except (TypeError, ValueError):
            continue
        source_type = str(doc.get("source_type") or "").strip()
        out[fid] = {
            "fixture_id": fid,
            "bookmaker": doc.get("bookmaker"),
            "captured_at_utc": doc.get("captured_at_utc"),
            "source_type": source_type,
            "is_manual_screenshot": source_type == MANUAL_SOURCE,
            "is_api_source": source_type in {"live_provider_api", "structured_bookmaker_feed"},
            "screenshot_reference": doc.get("screenshot_reference"),
            "markets_raw": list(doc.get("markets") or []),
            "accepted_source": source_type in REAL_SOURCE_TYPES,
        }
    return out


def load_real_odds_csv(path: str | Path) -> dict[int, dict[str, Any]]:
    by: dict[int, dict[str, Any]] = {}
    with Path(path).open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                fid = int(row.get("fixture_id"))
            except (TypeError, ValueError):
                continue
            doc = by.setdefault(
                fid,
                {
                    "fixture_id": fid,
                    "bookmaker": row.get("bookmaker"),
                    "captured_at_utc": row.get("captured_at_utc"),
                    "source_type": str(row.get("source_type") or "").strip(),
                    "markets_raw": [],
                    "accepted_source": False,
                },
            )
            doc["markets_raw"].append(
                {
                    "market_family": row.get("market_family") or row.get("market_name"),
                    "selection": row.get("selection"),
                    "line": row.get("line"),
                    "odds": row.get("odds") or row.get("decimal_odds"),
                    "freshness": row.get("freshness"),
                }
            )
            st = str(doc.get("source_type") or "")
            doc["accepted_source"] = st in REAL_SOURCE_TYPES
            doc["is_manual_screenshot"] = st == MANUAL_SOURCE
    return by


def markets_from_odds_doc(
    doc: dict[str, Any],
    *,
    top10_scores: list[str] | None = None,
) -> tuple[list[MarketCandidate], dict[str, Any]]:
    validation = {
        "fixture_id": doc.get("fixture_id"),
        "source_type": doc.get("source_type"),
        "is_manual_screenshot_transcription": bool(doc.get("is_manual_screenshot")),
        "accepted_source": bool(doc.get("accepted_source")),
        "fabricated": False,
        "mapped": 0,
        "unmapped": 0,
        "unsupported_settlement": 0,
        "stale_blocked": False,
        "markets": [],
    }
    if not doc.get("accepted_source"):
        validation["error"] = "source_type_not_accepted"
        return [], validation

    candidates: list[MarketCandidate] = []
    for m in doc.get("markets_raw") or []:
        if not isinstance(m, dict):
            continue
        family = str(m.get("market_family") or m.get("market_name") or "").strip()
        selection = str(m.get("selection") or "").strip()
        freshness = str(m.get("freshness") or doc.get("freshness") or "FRESH_ODDS")
        if freshness.upper() in STALE_MARKERS or freshness.upper().startswith("STALE"):
            validation["stale_blocked"] = True
            continue
        try:
            odds = float(m.get("odds") or m.get("decimal_odds"))
        except (TypeError, ValueError):
            validation["unmapped"] += 1
            continue
        if odds <= 1.0:
            validation["unmapped"] += 1
            continue
        mapped = classified_price_to_market(family, selection)
        if mapped is None:
            mapped = classify_raw_market(family, selection)
        if mapped is None:
            validation["unmapped"] += 1
            continue
        mt, params = mapped
        if "line" in m and m.get("line") is not None and "line" not in params:
            try:
                params = {**params, "line": float(m["line"])}
            except (TypeError, ValueError):
                pass
        if top10_scores is not None:
            cov = covered_scores_for_market(mt, params, top10_scores)
            if cov is None:
                validation["unsupported_settlement"] += 1
                continue
            modeled = None
        else:
            modeled = None
        label = human_label(mt, params)
        key = market_key_from_parts(mt, params)
        cand = MarketCandidate(
            market_type=mt,
            market_parameters=params,
            label=label,
            decimal_odds=odds,
            bookmaker=str(doc.get("bookmaker") or "") or None,
            source_type=str(doc.get("source_type") or ""),
            freshness=freshness,
            market_key=key,
            modeled_probability=modeled,
        )
        candidates.append(cand)
        validation["mapped"] += 1
        validation["markets"].append(cand.to_dict())

    # Deduplicate by market_key keeping best (highest) odds? Prefer first deterministic
    seen = set()
    uniq: list[MarketCandidate] = []
    for c in sorted(candidates, key=lambda x: (x.market_key, -(x.decimal_odds or 0))):
        if c.market_key in seen:
            continue
        seen.add(c.market_key)
        uniq.append(c)
    return uniq, validation

"""Real bookmaker odds input (JSON/CSV) — research-only, no fabrication."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.insurance.constants import (
    DEFAULT_INSURANCE,
    SOURCE_TYPES,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.insurance_candidates import map_manual_market_row


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _age_hours(ts: str | None, *, now: datetime | None = None) -> float | None:
    dt = _parse_ts(ts)
    if not dt:
        return None
    ref = now or datetime.now(timezone.utc)
    return (ref - dt).total_seconds() / 3600.0


def validate_odds_document(
    doc: dict[str, Any],
    *,
    insurance_cfg: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate one fixture odds document. Returns (normalized_doc, errors)."""
    cfg = {**DEFAULT_INSURANCE, **(insurance_cfg or {})}
    errors: list[str] = []
    if not isinstance(doc, dict):
        return None, ["DOCUMENT_NOT_OBJECT"]

    try:
        fixture_id = int(doc.get("fixture_id"))
    except (TypeError, ValueError):
        return None, ["MALFORMED_FIXTURE_ID"]

    bookmaker = str(doc.get("bookmaker") or "").strip()
    if not bookmaker:
        errors.append("MISSING_BOOKMAKER")

    captured = str(doc.get("captured_at_utc") or "").strip()
    if not captured or _parse_ts(captured) is None:
        errors.append("MISSING_OR_INVALID_CAPTURED_AT")

    source_type = str(doc.get("source_type") or "").strip()
    if source_type not in SOURCE_TYPES:
        errors.append(f"UNSUPPORTED_SOURCE_TYPE:{source_type or 'missing'}")
    if source_type == "manual_screenshot_transcription":
        # Explicit labeling required — already present
        pass

    max_age = float(cfg.get("research_freshness_max_age_hours", 24.0))
    age = _age_hours(captured, now=now)
    freshness = "FRESH_ODDS"
    if age is not None and age > max_age:
        freshness = "STALE_ODDS"
        errors.append("STALE_REAL_ODDS")

    markets = doc.get("markets")
    if not isinstance(markets, list) or not markets:
        errors.append("MISSING_MARKETS")
        markets = []

    seen: dict[str, float] = {}
    normalized_markets: list[dict[str, Any]] = []
    for i, m in enumerate(markets):
        if not isinstance(m, dict):
            errors.append(f"MARKET_{i}_NOT_OBJECT")
            continue
        if m.get("odds") is None:
            errors.append(f"MARKET_{i}_MISSING_ODDS")
            continue
        try:
            odds = float(m["odds"])
        except (TypeError, ValueError):
            errors.append(f"MARKET_{i}_INVALID_ODDS")
            continue
        if odds <= 0:
            errors.append(f"MARKET_{i}_NON_POSITIVE_ODDS")
            continue
        family = str(m.get("market_family") or "").strip()
        selection = str(m.get("selection") or "").strip()
        if not family or not selection:
            errors.append(f"MARKET_{i}_MISSING_FAMILY_OR_SELECTION")
            continue
        key = f"{family}|{selection}|{m.get('line')}"
        if key in seen and abs(seen[key] - odds) > 1e-9:
            errors.append(f"DUPLICATE_CONFLICTING_MARKET:{key}")
            continue
        seen[key] = odds
        mapped = map_manual_market_row(
            {
                **m,
                "bookmaker": bookmaker,
                "captured_at_utc": captured,
                "source_type": source_type,
                "odds_freshness_status": freshness,
            },
            fixture_id=fixture_id,
        )
        if mapped is None:
            errors.append(f"MARKET_{i}_UNSUPPORTED_MAPPING:{family}/{selection}")
            continue
        mapped["odds_freshness_status"] = freshness
        mapped["source_type"] = source_type
        mapped["bookmaker"] = bookmaker
        mapped["odds_timestamp"] = captured
        mapped["raw_label"] = selection
        mapped["screenshot_reference"] = doc.get("screenshot_reference") or m.get("screenshot_reference")
        mapped["notes"] = m.get("notes")
        if source_type == "manual_screenshot_transcription":
            mapped["api_sourced"] = False
            mapped["manual_screenshot_transcription"] = True
        else:
            mapped["api_sourced"] = source_type == "provider_api"
        normalized_markets.append(mapped)

    if errors:
        return None, errors

    return {
        "fixture_id": fixture_id,
        "bookmaker": bookmaker,
        "captured_at_utc": captured,
        "source_type": source_type,
        "odds_freshness_status": freshness,
        "markets": normalized_markets,
        "screenshot_reference": doc.get("screenshot_reference"),
        "notes": doc.get("notes"),
        "api_sourced": source_type == "provider_api",
        "manual_screenshot_transcription": source_type == "manual_screenshot_transcription",
    }, []


def load_real_odds_json(
    path: str | Path,
    *,
    insurance_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load JSON file: single fixture object or {\"fixtures\": [...]} / list."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    docs: list[dict[str, Any]]
    if isinstance(raw, list):
        docs = [d for d in raw if isinstance(d, dict)]
    elif isinstance(raw, dict) and isinstance(raw.get("fixtures"), list):
        docs = [d for d in raw["fixtures"] if isinstance(d, dict)]
    elif isinstance(raw, dict):
        docs = [raw]
    else:
        return {"ok": False, "fixtures": {}, "errors": ["UNSUPPORTED_JSON_ROOT"], "rejected": []}

    fixtures: dict[int, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    for doc in docs:
        norm, errs = validate_odds_document(doc, insurance_cfg=insurance_cfg)
        if norm is None:
            rejected.append({"fixture_id": doc.get("fixture_id"), "errors": errs})
            continue
        fixtures[int(norm["fixture_id"])] = norm
    return {
        "ok": len(rejected) == 0,
        "fixtures": fixtures,
        "rejected": rejected,
        "n_fixtures": len(fixtures),
        "source_file": str(path),
    }


def load_real_odds_csv(
    path: str | Path,
    *,
    insurance_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    CSV columns: fixture_id,bookmaker,captured_at_utc,source_type,market_family,selection,odds[,line]
    """
    by_fx: dict[int, dict[str, Any]] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                fid = int(row["fixture_id"])
            except (KeyError, TypeError, ValueError):
                continue
            block = by_fx.setdefault(
                fid,
                {
                    "fixture_id": fid,
                    "bookmaker": row.get("bookmaker"),
                    "captured_at_utc": row.get("captured_at_utc"),
                    "source_type": row.get("source_type") or "csv_import",
                    "markets": [],
                },
            )
            m: dict[str, Any] = {
                "market_family": row.get("market_family"),
                "selection": row.get("selection"),
                "odds": row.get("odds"),
            }
            if row.get("line"):
                m["line"] = row.get("line")
            block["markets"].append(m)

    fixtures: dict[int, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    for fid, doc in by_fx.items():
        norm, errs = validate_odds_document(doc, insurance_cfg=insurance_cfg)
        if norm is None:
            rejected.append({"fixture_id": fid, "errors": errs})
            continue
        fixtures[fid] = norm
    return {
        "ok": len(rejected) == 0,
        "fixtures": fixtures,
        "rejected": rejected,
        "n_fixtures": len(fixtures),
        "source_file": str(path),
    }

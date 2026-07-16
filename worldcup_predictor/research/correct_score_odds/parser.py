"""Parse Correct Score lines from odds_snapshots payloads (cache-first)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.egie.provider_features.odds_snapshot_parser import (
    extract_bookmakers_from_payload,
)
from worldcup_predictor.research.correct_score_odds.mapping import (
    normalize_market_name,
    parse_selection,
)
from worldcup_predictor.research.correct_score_odds.statuses import CANONICAL_MARKET

_SECRET_RE = re.compile(
    r"(api[_-]?key|authorization|bearer\s+[a-z0-9]|token\s*[:=])",
    re.IGNORECASE,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            if fmt.endswith("%z") and "+" not in s[10:] and s.count(":") >= 2:
                # naive → assume UTC
                dt = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S" if "T" in s else "%Y-%m-%d %H:%M:%S")
                return dt.replace(tzinfo=timezone.utc)
            return datetime.strptime(s, fmt).astimezone(timezone.utc) if "%z" in fmt else datetime.strptime(
                s[:19] if len(s) >= 19 else s, fmt.replace("%z", "")
            ).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception:
        return None


def detect_provider(payload: dict[str, Any]) -> str:
    src = str(payload.get("source") or "").lower()
    if "api" in src and "sport" in src:
        return "api_football"
    if "api_football" in src or "api-sports" in src:
        return "api_football"
    if "sportmonk" in src:
        return "sportmonks"
    if "oddalert" in src:
        return "oddalerts"
    if "the_odds" in src or "odds_api" in src:
        return "the_odds_api"
    if payload.get("api_sports"):
        return "api_football"
    if payload.get("sportmonks"):
        return "sportmonks"
    return "odds_snapshots"


def secrets_present(blob: str) -> bool:
    return bool(_SECRET_RE.search(blob or ""))


def validate_line(
    *,
    decimal_odds: float,
    selection_meta: dict[str, Any],
    fetched_at: datetime | None,
    kickoff: datetime | None,
    market_status: str,
    settlement_scope: str,
) -> tuple[bool, str]:
    if decimal_odds is None or decimal_odds <= 1.0:
        return False, "odds_lte_1"
    if selection_meta is None:
        return False, "unparsed_selection"
    if settlement_scope != "90_MINUTES" and selection_meta.get("market") == CANONICAL_MARKET:
        # any-other may share scope; require 90 for exact
        if not selection_meta.get("is_any_other"):
            return False, "settlement_not_90"
    if str(market_status).lower() in {"suspended", "closed", "settled"}:
        return False, "market_suspended"
    if kickoff and fetched_at:
        if fetched_at >= kickoff:
            return False, "post_kickoff_or_live"
    if not fetched_at:
        return False, "missing_timestamp"
    return True, "ok"


def parse_payload_cs_lines(
    payload: dict[str, Any],
    *,
    fixture_id: int,
    snapshot_id: int | None,
    snapshot_at: str | None,
    kickoff_utc: str | None,
    ingestion_run_id: str,
    provider_hint: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (accepted_rows, rejected_rows)."""
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    provider = provider_hint or detect_provider(payload)
    fetched_raw = snapshot_at or payload.get("snapshot_at") or _utc_now()
    fetched_dt = _parse_ts(fetched_raw)
    kickoff_dt = _parse_ts(kickoff_utc)

    # strip secrets from stored reference
    try:
        ref_blob = json.dumps({"snapshot_id": snapshot_id, "provider": provider}, sort_keys=True)
    except Exception:
        ref_blob = f"snapshot:{snapshot_id}"
    if secrets_present(json.dumps(payload)[:5000]):
        # still parse markets but never store raw payload with secrets
        payload_reference = f"snapshot_id:{snapshot_id}:redacted"
    else:
        payload_reference = f"snapshot_id:{snapshot_id}"

    bookmakers = extract_bookmakers_from_payload(payload)
    # also check nested api_sports
    if not bookmakers and isinstance(payload.get("api_sports"), dict):
        bookmakers = extract_bookmakers_from_payload(payload["api_sports"])

    for bm in bookmakers or []:
        if not isinstance(bm, dict):
            continue
        bm_name = str(bm.get("name") or bm.get("bookmaker") or "unknown").strip() or "unknown"
        bm_id = str(bm.get("id") or "") or None
        for bet in bm.get("bets") or bm.get("markets") or []:
            if not isinstance(bet, dict):
                continue
            raw_market = str(bet.get("name") or bet.get("market") or "")
            canon = normalize_market_name(raw_market)
            if canon is None:
                if any(h in raw_market.lower() for h in ("correct", "exact score")):
                    rejected.append(
                        {
                            "fixture_id": fixture_id,
                            "reason": "rejected_market_scope",
                            "raw_market": raw_market,
                            "bookmaker": bm_name,
                        }
                    )
                continue
            for v in bet.get("values") or bet.get("odds") or []:
                if not isinstance(v, dict):
                    continue
                raw_sel = str(v.get("value") or v.get("selection") or v.get("name") or "")
                meta = parse_selection(raw_sel)
                try:
                    odd = float(v.get("odd") or v.get("price") or v.get("odds") or 0)
                except (TypeError, ValueError):
                    rejected.append(
                        {
                            "fixture_id": fixture_id,
                            "reason": "bad_odds",
                            "selection": raw_sel,
                            "bookmaker": bm_name,
                        }
                    )
                    continue
                status = str(v.get("status") or bet.get("status") or "open")
                ok, reason = validate_line(
                    decimal_odds=odd,
                    selection_meta=meta or {},
                    fetched_at=fetched_dt,
                    kickoff=kickoff_dt,
                    market_status=status,
                    settlement_scope="90_MINUTES",
                )
                if not ok or meta is None:
                    rejected.append(
                        {
                            "fixture_id": fixture_id,
                            "reason": reason if meta else "unparsed_selection",
                            "selection": raw_sel,
                            "bookmaker": bm_name,
                            "odd": odd,
                        }
                    )
                    continue
                age = None
                if fetched_dt and kickoff_dt:
                    age = (kickoff_dt - fetched_dt).total_seconds()
                src = f"{fixture_id}|{provider}|{bm_name}|{meta['market']}|{meta['selection']}|{odd}|{fetched_raw}"
                source_hash = hashlib.sha256(src.encode("utf-8")).hexdigest()[:40]
                prematch_status = "prematch"
                if kickoff_dt and fetched_dt and fetched_dt >= kickoff_dt:
                    prematch_status = "live_or_post"
                accepted.append(
                    {
                        "fixture_id": int(fixture_id),
                        "provider_fixture_id": str(fixture_id),
                        "bookmaker_id": bm_id,
                        "bookmaker_name": bm_name,
                        "market": meta["market"],
                        "selection": meta["selection"],
                        "home_goals": meta["home_goals"],
                        "away_goals": meta["away_goals"],
                        "decimal_odds": float(odd),
                        "raw_odds_format": "decimal",
                        "fetched_at_utc": fetched_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if fetched_dt else str(fetched_raw),
                        "valid_from_utc": None,
                        "kickoff_utc": kickoff_utc,
                        "prematch_status": prematch_status,
                        "settlement_scope": "90_MINUTES",
                        "provider": provider,
                        "source_hash": source_hash,
                        "payload_reference": payload_reference,
                        "snapshot_id": snapshot_id,
                        "is_complete_market": 0,
                        "is_fresh": 1 if (age is None or age > 0) else 0,
                        "odds_age_seconds": age,
                        "currency": None,
                        "minimum_stake": None,
                        "maximum_stake": None,
                        "market_status": status,
                        "ingestion_run_id": ingestion_run_id,
                        "odds_kind": "api_extracted",
                        "created_at_utc": _utc_now(),
                    }
                )
    return accepted, rejected

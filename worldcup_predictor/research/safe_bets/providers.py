"""PHASE SAFE-BETS-1 — Odds ingestion from providers."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import normalize_snapshot_odds_lines
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.research.safe_bets.store import log_api_call

PHASE = "SAFE-BETS-1"


@dataclass
class OddsLine:
    provider: str
    bookmaker: str
    market_name: str
    selection: str
    odd: float
    data_quality: float = 0.7
    source_detail: str = ""


@dataclass
class ProviderFetchResult:
    lines: list[OddsLine] = field(default_factory=list)
    api_calls: int = 0
    errors: list[str] = field(default_factory=list)


def _lines_from_payload(
    payload: Any,
    *,
    provider: str,
    fixture_id: int,
    data_quality: float,
) -> list[OddsLine]:
    normalized = normalize_snapshot_odds_lines(payload, fixture_id=fixture_id, source=provider)
    out: list[OddsLine] = []
    for line in normalized:
        out.append(
            OddsLine(
                provider=provider,
                bookmaker=line.bookmaker,
                market_name=line.market_name,
                selection=line.selection,
                odd=float(line.odd),
                data_quality=data_quality,
                source_detail=provider,
            )
        )
    return out


def fetch_api_football_odds(
    fixture_id: int,
    *,
    settings: Settings | None = None,
    conn: sqlite3.Connection | None = None,
    scan_batch_id: str = "",
) -> ProviderFetchResult:
    settings = settings or get_settings()
    result = ProviderFetchResult()
    client = ApiFootballClient(settings)
    if not client.is_configured:
        result.errors.append("api_football_not_configured")
        return result
    res = client.get_odds(int(fixture_id))
    result.api_calls += 1
    if conn is not None:
        log_api_call(
            conn,
            scan_batch_id=scan_batch_id,
            provider="api_football",
            endpoint="odds",
            entity_key=str(fixture_id),
            action="fetch",
            status="ok" if res.ok else "error",
            details={"error": res.error},
        )
    if not res.ok or not res.data:
        result.errors.append(res.error or "api_football_empty")
        return result
    payload = res.data[0] if isinstance(res.data, list) and res.data else res.data
    result.lines = _lines_from_payload(payload, provider="api_football", fixture_id=fixture_id, data_quality=0.85)
    return result


def fetch_sqlite_odds_snapshot(
    conn: sqlite3.Connection,
    fixture_id: int,
) -> ProviderFetchResult:
    result = ProviderFetchResult()
    row = conn.execute(
        """
        SELECT payload_json FROM odds_snapshots
        WHERE fixture_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return result
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        result.errors.append("sqlite_payload_invalid")
        return result
    result.lines = _lines_from_payload(payload, provider="sqlite_odds_snapshots", fixture_id=fixture_id, data_quality=0.65)
    return result


def fetch_sportmonks_odds_from_cache(
    conn: sqlite3.Connection,
    fixture_id: int,
    *,
    scan_batch_id: str = "",
) -> ProviderFetchResult:
    result = ProviderFetchResult()
    try:
        row = conn.execute(
            """
            SELECT raw_json, sportmonks_fixture_id
            FROM sportmonks_fixture_enrichment
            WHERE fixture_id_api_football = ? AND status = 'ok'
            ORDER BY id DESC LIMIT 1
            """,
            (int(fixture_id),),
        ).fetchone()
    except sqlite3.OperationalError:
        return result
    if not row:
        return result
    try:
        payload = json.loads(row["raw_json"])
    except (json.JSONDecodeError, TypeError):
        return result
    fixture = payload if isinstance(payload, dict) else {}
    if "data" in fixture and isinstance(fixture["data"], dict):
        fixture = fixture["data"]
    odds_block = fixture.get("odds") or []
    if isinstance(odds_block, list) and odds_block:
        synthetic = {"bookmakers": []}
        for o in odds_block:
            if isinstance(o, dict) and o.get("bookmaker"):
                synthetic["bookmakers"].append(o.get("bookmaker"))
        result.lines = _lines_from_payload(synthetic, provider="sportmonks", fixture_id=fixture_id, data_quality=0.75)
    if conn is not None:
        log_api_call(
            conn,
            scan_batch_id=scan_batch_id,
            provider="sportmonks",
            endpoint="enrichment_cache",
            entity_key=str(fixture_id),
            action="read",
            status="ok" if result.lines else "empty",
        )
    return result


def fetch_oddalerts_odds_history(
    oddalerts_fixture_id: int,
    *,
    conn: sqlite3.Connection | None = None,
    scan_batch_id: str = "",
) -> ProviderFetchResult:
    result = ProviderFetchResult()
    client = OddAlertsClient()
    if not client.is_configured:
        return result
    hist = client.get_odds_history(int(oddalerts_fixture_id))
    result.api_calls += 1
    if conn is not None:
        log_api_call(
            conn,
            scan_batch_id=scan_batch_id,
            provider="oddalerts",
            endpoint="odds/history",
            entity_key=str(oddalerts_fixture_id),
            action="fetch",
            status="ok" if hist.data else "error",
            details={"error": hist.error},
        )
    rows = (hist.data or {}).get("data") or []
    for row in rows:
        try:
            odd = float(row.get("closing") or row.get("opening") or 0)
        except (TypeError, ValueError):
            continue
        if odd < 1.01:
            continue
        result.lines.append(
            OddsLine(
                provider="oddalerts",
                bookmaker=str(row.get("bookmaker_name") or row.get("bookmaker") or "unknown"),
                market_name=str(row.get("market_key") or row.get("market") or "unknown"),
                selection=str(row.get("outcome") or row.get("selection") or "unknown"),
                odd=odd,
                data_quality=0.72,
            )
        )
    return result


def collect_all_odds_lines(
    conn: sqlite3.Connection,
    fixture_id: int,
    *,
    settings: Settings | None = None,
    scan_batch_id: str = "",
    oddalerts_fixture_id: int | None = None,
    use_live_api: bool = True,
) -> tuple[list[OddsLine], int]:
    settings = settings or get_settings()
    lines: list[OddsLine] = []
    api_calls = 0

    try:
        sqlite_res = fetch_sqlite_odds_snapshot(conn, fixture_id)
        lines.extend(sqlite_res.lines)
    except Exception:
        pass

    if use_live_api and settings.safe_bets_use_live_api:
        try:
            af = fetch_api_football_odds(
                fixture_id, settings=settings, conn=conn, scan_batch_id=scan_batch_id
            )
            lines.extend(af.lines)
            api_calls += af.api_calls
        except Exception:
            pass

    try:
        sm = fetch_sportmonks_odds_from_cache(conn, fixture_id, scan_batch_id=scan_batch_id)
        lines.extend(sm.lines)
    except Exception:
        pass

    if oddalerts_fixture_id:
        try:
            oa = fetch_oddalerts_odds_history(
                oddalerts_fixture_id, conn=conn, scan_batch_id=scan_batch_id
            )
            lines.extend(oa.lines)
            api_calls += oa.api_calls
        except Exception:
            pass

    return lines, api_calls

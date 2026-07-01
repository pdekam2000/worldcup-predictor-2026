"""PHASE API-GAP-1 — OddAlerts targeted harvest (missing markets only)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect, init_database
from worldcup_predictor.providers.oddalerts_historical_odds import (
    OddAlertsHistoricalOddsIngester,
    _parse_decimal,
    ensure_oddalerts_tables,
)
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.research.api_gap_staging import ensure_api_gap_tables, log_harvest, upsert_raw_payload

PROVIDER = "oddalerts"
TARGET_MARKETS = frozenset({"ft_result", "1x2", "match_winner", "correct_score", "correct score"})
TARGET_SELECTIONS_DRAW = frozenset({"draw"})
SKIP_EXISTING_BET365_1X2 = True


@dataclass
class OddAlertsHarvestStats:
    candidates: int = 0
    api_calls: int = 0
    cache_hits: int = 0
    odds_rows_inserted: int = 0
    odds_rows_skipped_duplicate: int = 0
    draw_rows_found: int = 0
    correct_score_rows_found: int = 0
    raw_staged: int = 0
    provider_no_draw: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": PROVIDER,
            "candidates": self.candidates,
            "api_calls": self.api_calls,
            "cache_hits": self.cache_hits,
            "odds_rows_inserted": self.odds_rows_inserted,
            "odds_rows_skipped_duplicate": self.odds_rows_skipped_duplicate,
            "draw_rows_found": self.draw_rows_found,
            "correct_score_rows_found": self.correct_score_rows_found,
            "raw_staged": self.raw_staged,
            "provider_no_draw": self.provider_no_draw,
            "errors": self.errors[:25],
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _draw_refetch_candidates(conn: sqlite3.Connection, *, limit: int = 200) -> list[int]:
    rows = conn.execute(
        """
        SELECT oddalerts_fixture_id AS oid
        FROM oddalerts_odds_history
        WHERE market IN ('ft_result','1x2','match_winner') AND selection IN ('home','away')
        GROUP BY oddalerts_fixture_id
        HAVING SUM(CASE WHEN selection = 'draw' THEN 1 ELSE 0 END) = 0
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [int(r["oid"]) for r in rows]


def _parse_odds_history(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract normalized odds rows from OddAlerts odds/history response."""
    out: list[dict[str, Any]] = []
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        data = payload.get("odds") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return out
    for entry in data:
        if not isinstance(entry, dict):
            continue
        market = str(entry.get("market") or entry.get("market_name") or "").lower().replace(" ", "_")
        selection = str(entry.get("selection") or entry.get("outcome") or entry.get("name") or "").lower()
        bookmaker = str(entry.get("bookmaker") or entry.get("bookmaker_name") or "unknown")
        closing = _parse_decimal(entry.get("closing") or entry.get("closing_odds") or entry.get("odds"))
        opening = _parse_decimal(entry.get("opening") or entry.get("opening_odds"))
        out.append(
            {
                "market": market or "unknown",
                "selection": selection,
                "bookmaker": bookmaker,
                "closing_odds": closing,
                "opening_odds": opening,
                "raw": entry,
            }
        )
    return out


def _row_exists(
    conn: sqlite3.Connection,
    *,
    oddalerts_fixture_id: int,
    bookmaker: str,
    market: str,
    selection: str,
) -> bool:
    return bool(
        conn.execute(
            """
            SELECT 1 FROM oddalerts_odds_history
            WHERE oddalerts_fixture_id = ? AND bookmaker = ? AND market = ? AND selection = ?
            LIMIT 1
            """,
            (oddalerts_fixture_id, bookmaker, market, selection),
        ).fetchone()
    )


def harvest_oddalerts_missing_markets(
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    max_api_calls: int = 50,
    candidate_limit: int = 200,
) -> dict[str, Any]:
    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    init_database(settings.sqlite_path)
    ensure_oddalerts_tables(conn)
    ensure_api_gap_tables(conn)

    stats = OddAlertsHarvestStats()
    client = OddAlertsClient()
    if not client.is_configured:
        stats.errors.append("oddalerts_not_configured")
        return stats.to_dict()

    ingester = OddAlertsHistoricalOddsIngester(settings=settings)
    candidates = _draw_refetch_candidates(conn, limit=candidate_limit)
    stats.candidates = len(candidates)

    for oa_id in candidates:
        if stats.api_calls >= max_api_calls:
            break
        cache_key = f"oddalerts:odds/history:id={oa_id}"
        cached = conn.execute(
            "SELECT payload_json FROM api_response_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if cached:
            try:
                payload = json.loads(cached["payload_json"])
            except (json.JSONDecodeError, TypeError):
                payload = None
            stats.cache_hits += 1
            log_harvest(conn, provider=PROVIDER, data_type="odds_history", entity_key=str(oa_id), action="cache_hit")
        else:
            result = client.get_odds_history(oa_id)
            stats.api_calls += 1
            client.throttle()
            if result.data is None or result.error:
                stats.errors.append(f"{oa_id}:{result.error}")
                log_harvest(
                    conn,
                    provider=PROVIDER,
                    data_type="odds_history",
                    entity_key=str(oa_id),
                    action="fetch_error",
                    details={"error": result.error},
                )
                continue
            payload = result.data
            if not dry_run:
                ingester.store.set_cache_payload(
                    cache_key=cache_key,
                    endpoint="odds/history",
                    params={"id": oa_id},
                    payload=payload,
                )
            log_harvest(conn, provider=PROVIDER, data_type="odds_history", entity_key=str(oa_id), action="fetched")

        if not isinstance(payload, dict):
            continue

        if upsert_raw_payload(
            conn,
            provider=PROVIDER,
            entity_key=f"oa:{oa_id}",
            data_type="odds_history",
            payload=payload,
            source="oddalerts_api",
            dry_run=dry_run,
        ):
            stats.raw_staged += 1

        parsed_rows = _parse_odds_history(payload)
        found_draw = False
        for row in parsed_rows:
            market = row["market"]
            selection = row["selection"]
            bookmaker = row["bookmaker"]
            if selection in TARGET_SELECTIONS_DRAW:
                found_draw = True
                stats.draw_rows_found += 1
            if "correct" in market and "score" in market:
                stats.correct_score_rows_found += 1

            if SKIP_EXISTING_BET365_1X2 and bookmaker.lower() in ("bet365", "bet 365"):
                if market in ("ft_result", "1x2", "match_winner") and selection in ("home", "away"):
                    stats.odds_rows_skipped_duplicate += 1
                    continue

            if _row_exists(conn, oddalerts_fixture_id=oa_id, bookmaker=bookmaker, market=market, selection=selection):
                stats.odds_rows_skipped_duplicate += 1
                continue

            if dry_run:
                stats.odds_rows_inserted += 1
                continue

            ok = ingester.store.insert_odds_row(
                oddalerts_fixture_id=oa_id,
                internal_fixture_id=None,
                league="api_gap",
                season=0,
                bookmaker=bookmaker,
                market=market,
                selection=selection,
                opening_odds=row.get("opening_odds"),
                closing_odds=row.get("closing_odds"),
                peak_odds=None,
                odds_timestamp=None,
                implied_probability=None,
                raw_json=row.get("raw") or {},
            )
            if ok:
                stats.odds_rows_inserted += 1
            else:
                stats.odds_rows_skipped_duplicate += 1

        if not found_draw:
            stats.provider_no_draw += 1

    if not dry_run:
        conn.commit()
    conn.close()
    return stats.to_dict()

"""Strict multi-provider live odds refresh for stale fixtures.

Provider order:
1. API-Football live (forced cache bypass)
2. Sportmonks live pre-match odds (using the stored fixture crosswalk)
3. OddAlerts live odds history (only with an explicit fixture crosswalk)

A provider is accepted only when it returns parseable, usable odds. Failed or
partial providers are recorded in the attempt trace and the next provider is
tried. Old cache entries are never re-stamped as fresh.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from worldcup_predictor.backtesting.phase31e_backfill import normalize_odds_bookmakers
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner.euro_c_odds_import import (
    is_fake_odds_payload,
    normalize_uefa_odds_snapshot,
)
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.owner_daily.odds_import import (
    _build_daily_storage_payload,
    _oddalerts_lines_to_bookmakers,
    _probabilities_valid,
)
from worldcup_predictor.odds.freshness_metadata import enrich_snapshot_payload_metadata
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.research.safe_bets.providers import fetch_oddalerts_odds_history

RAW_DIR = Path("artifacts/daily_owner/raw_odds_payloads")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _market_quality(normalized: Any) -> dict[str, bool]:
    return {
        "match_winner": bool(getattr(normalized, "match_winner", None)),
        "over_under_2_5": bool(getattr(normalized, "over_under_2_5", None)),
        "btts": bool(getattr(normalized, "btts", None)),
    }


def _usable_for_prediction(normalized: Any) -> bool:
    """Require the two core odds inputs used by WDE/ECSE odds consumers."""
    quality = _market_quality(normalized)
    return (
        quality["match_winner"]
        and quality["over_under_2_5"]
        and _probabilities_valid(normalized)
    )


def _normalize_candidate(
    bookmakers: list[Any],
    *,
    fixture_id: int,
    raw_path: str | None = None,
) -> tuple[Any, bool, dict[str, bool]]:
    normalized = normalize_uefa_odds_snapshot(
        bookmakers,
        fixture_id=fixture_id,
        raw_odds_path=raw_path,
    )
    return normalized, _usable_for_prediction(normalized), _market_quality(normalized)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _positive_int(value: Any) -> int | None:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _sportmonks_fixture_id(conn: sqlite3.Connection, api_fixture_id: int) -> int | None:
    """Resolve an API-Football fixture ID to a Sportmonks fixture ID."""
    try:
        row = conn.execute(
            """
            SELECT sportmonks_fixture_id
            FROM sportmonks_fixture_enrichment
            WHERE fixture_id_api_football = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(api_fixture_id),),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row and row["sportmonks_fixture_id"] is not None:
        return int(row["sportmonks_fixture_id"])
    return None


def _explicit_crosswalk_from_table(
    conn: sqlite3.Connection,
    *,
    table: str,
    internal_fixture_id: int,
) -> int | None:
    if not _table_exists(conn, table):
        return None
    columns = {
        str(row["name"] if isinstance(row, sqlite3.Row) else row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    internal_candidates = (
        "internal_fixture_id",
        "fixture_id",
        "api_football_fixture_id",
        "fixture_id_api_football",
    )
    provider_candidates = (
        "oddalerts_fixture_id",
        "provider_fixture_id",
    )
    internal_col = next((c for c in internal_candidates if c in columns), None)
    provider_col = next((c for c in provider_candidates if c in columns), None)
    if not internal_col or not provider_col:
        return None

    provider_filter = ""
    params: list[Any] = [int(internal_fixture_id)]
    if "provider" in columns:
        provider_filter = " AND LOWER(provider) = ?"
        params.append("oddalerts")
    elif "provider_name" in columns:
        provider_filter = " AND LOWER(provider_name) = ?"
        params.append("oddalerts")

    try:
        row = conn.execute(
            f"SELECT {provider_col} AS provider_fixture_id FROM {table} "
            f"WHERE {internal_col} = ?{provider_filter} ORDER BY rowid DESC LIMIT 1",
            tuple(params),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    return _positive_int(row["provider_fixture_id"])


def _oddalerts_fixture_id(conn: sqlite3.Connection, internal_fixture_id: int) -> int | None:
    """Resolve OddAlerts fixture ID without assuming provider IDs are interchangeable."""
    # Generic provider feed can hold an explicit provider fixture ID.
    if _table_exists(conn, "euro_fixture_feed"):
        try:
            row = conn.execute(
                """
                SELECT provider_fixture_id
                FROM euro_fixture_feed
                WHERE fixture_id = ? AND LOWER(provider) = 'oddalerts'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (int(internal_fixture_id),),
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        if row:
            value = _positive_int(row["provider_fixture_id"])
            if value is not None:
                return value

    # Support explicit crosswalk tables if/when present in a deployment DB.
    for table in (
        "oddalerts_fixture_crosswalk",
        "provider_fixture_crosswalk",
        "fixture_provider_crosswalk",
    ):
        value = _explicit_crosswalk_from_table(
            conn,
            table=table,
            internal_fixture_id=internal_fixture_id,
        )
        if value is not None:
            return value

    # Historical OddAlerts CSV rows are already crosswalked to internal fixtures.
    # Use only an explicit OddAlerts fixture-id field from the raw source row;
    # never reinterpret the internal fixture ID as a provider ID.
    if _table_exists(conn, "oddalerts_probability_market_rows"):
        try:
            rows = conn.execute(
                """
                SELECT raw_row_json
                FROM oddalerts_probability_market_rows
                WHERE internal_fixture_id = ?
                  AND raw_row_json IS NOT NULL
                ORDER BY id DESC
                LIMIT 50
                """,
                (int(internal_fixture_id),),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

        candidates: set[int] = set()
        accepted_keys = {
            "oddalertsfixtureid",
            "oddalertsfixture",
            "oddalertsid",
        }
        for row in rows:
            try:
                payload = json.loads(row["raw_row_json"])
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
            if not isinstance(payload, dict):
                continue
            for key, value in payload.items():
                normalized_key = "".join(ch for ch in str(key).lower() if ch.isalnum())
                if normalized_key not in accepted_keys:
                    continue
                parsed = _positive_int(value)
                if parsed is not None:
                    candidates.add(parsed)
        if len(candidates) == 1:
            return next(iter(candidates))

    return None


def _normalize_sportmonks_market_name(value: Any) -> str:
    name = str(value or "").strip()
    key = name.lower()
    if key in {"fulltime result", "full time result", "3-way result", "match result"}:
        return "Match Winner"
    if "both teams" in key and "score" in key:
        return "Both Teams To Score"
    if "over/under" in key or "over under" in key or "total goals" in key:
        return "Goals Over/Under"
    return name or "Unknown Market"


def _normalize_sportmonks_selection(
    selection: Any,
    *,
    market_name: str,
    total: Any = None,
) -> str:
    label = str(selection or "").strip()
    if market_name == "Match Winner":
        mapping = {
            "1": "Home",
            "x": "Draw",
            "2": "Away",
            "home": "Home",
            "draw": "Draw",
            "away": "Away",
        }
        return mapping.get(label.lower(), label)
    if market_name == "Goals Over/Under" and total not in (None, ""):
        lower = label.lower()
        if lower in {"over", "under"}:
            return f"{label.title()} {total}"
    return label


def _sportmonks_odds_to_bookmakers(payload: Any) -> list[dict[str, Any]]:
    """Convert Sportmonks pre-match odds rows to API-Football bookmaker blocks."""
    data = payload.get("data") if isinstance(payload, dict) else payload
    odds_rows = data if isinstance(data, list) else []

    grouped: dict[str, dict[str, list[dict[str, str]]]] = {}
    for row in odds_rows:
        if not isinstance(row, dict):
            continue

        bookmaker_obj = row.get("bookmaker")
        market_obj = row.get("market")
        bookmaker_name = (
            bookmaker_obj.get("name") if isinstance(bookmaker_obj, dict) else None
        ) or row.get("bookmaker_name") or f"sportmonks:{row.get('bookmaker_id', 'unknown')}"

        raw_market_name = (
            market_obj.get("name") if isinstance(market_obj, dict) else None
        ) or row.get("market_description") or row.get("market_name")
        market_name = _normalize_sportmonks_market_name(raw_market_name)

        raw_selection = row.get("label") or row.get("name") or row.get("selection") or row.get("outcome")
        selection = _normalize_sportmonks_selection(
            raw_selection,
            market_name=market_name,
            total=row.get("total"),
        )
        odd = row.get("value") or row.get("odds") or row.get("decimal") or row.get("price")
        try:
            odd_value = float(odd)
        except (TypeError, ValueError):
            continue
        if odd_value <= 1.0 or not selection:
            continue

        grouped.setdefault(str(bookmaker_name), {}).setdefault(market_name, []).append(
            {"value": selection, "odd": str(odd_value)}
        )

    bookmakers: list[dict[str, Any]] = []
    for bookmaker_name, markets in grouped.items():
        bets = [
            {"name": market_name, "values": values}
            for market_name, values in markets.items()
            if values
        ]
        if bets:
            bookmakers.append({"name": bookmaker_name, "bets": bets})
    return bookmakers


def _write_raw_payload(fixture_id: int, provider: str, payload: Any) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{fixture_id}_{stamp}_{provider}-live.json"
    path.write_text(
        json.dumps(
            {
                "fixture_id": fixture_id,
                "fetched_at": _utc_now_iso(),
                "provider": provider,
                "source": "live",
                "data": payload,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return str(path)


def _try_api_football(
    fixture_id: int,
    settings: Settings,
) -> tuple[list[Any], Any, dict[str, Any]]:
    attempt: dict[str, Any] = {
        "provider": "api-football",
        "configured": settings.api_football_configured,
        "call_made": False,
        "success": False,
    }
    if not settings.api_football_configured:
        attempt["reason"] = "not_configured"
        return [], None, attempt

    client = ApiFootballClient(settings)
    result = client.get_odds(fixture_id, force_refresh=True)
    attempt.update(
        {
            "call_made": True,
            "source": result.source,
            "error": result.error,
            "response_count": result.response_count,
        }
    )
    if result.source != "live" or not result.ok or is_fake_odds_payload(result.data, source=result.source):
        attempt["reason"] = "live_empty_invalid_or_failed"
        return [], result.data, attempt

    bookmakers = normalize_odds_bookmakers(result.data)
    attempt["bookmaker_count"] = len(bookmakers)
    if not bookmakers:
        attempt["reason"] = "no_bookmakers"
        return [], result.data, attempt

    attempt["success"] = True
    return bookmakers, result.data, attempt


def _try_sportmonks(
    fixture_id: int,
    settings: Settings,
    conn: sqlite3.Connection,
) -> tuple[list[Any], Any, dict[str, Any]]:
    provider = SportmonksProvider(settings)
    attempt: dict[str, Any] = {
        "provider": "sportmonks",
        "configured": provider.is_configured,
        "call_made": False,
        "success": False,
    }
    if not provider.is_configured:
        attempt["reason"] = "not_configured"
        return [], None, attempt

    sportmonks_id = _sportmonks_fixture_id(conn, fixture_id)
    attempt["sportmonks_fixture_id"] = sportmonks_id
    if sportmonks_id is None:
        attempt["reason"] = "crosswalk_missing"
        return [], None, attempt

    status_code, payload, error = provider.safe_get(
        f"/odds/pre-match/fixtures/{sportmonks_id}",
        params={"include": "bookmaker;market", "per_page": 50},
    )
    attempt.update(
        {
            "call_made": True,
            "status_code": status_code,
            "error": error,
        }
    )
    if error or payload is None:
        attempt["reason"] = "live_empty_or_failed"
        return [], payload, attempt

    bookmakers = _sportmonks_odds_to_bookmakers(payload)
    attempt["bookmaker_count"] = len(bookmakers)
    if not bookmakers:
        attempt["reason"] = "unparseable_or_no_bookmakers"
        return [], payload, attempt

    attempt["success"] = True
    return bookmakers, payload, attempt


def _try_oddalerts(
    fixture_id: int,
    conn: sqlite3.Connection,
) -> tuple[list[Any], Any, dict[str, Any]]:
    client = OddAlertsClient()
    attempt: dict[str, Any] = {
        "provider": "oddalerts",
        "configured": client.is_configured,
        "call_made": False,
        "success": False,
    }
    if not client.is_configured:
        attempt["reason"] = "not_configured"
        return [], None, attempt

    oddalerts_id = _oddalerts_fixture_id(conn, fixture_id)
    attempt["oddalerts_fixture_id"] = oddalerts_id
    if oddalerts_id is None:
        attempt["reason"] = "crosswalk_missing"
        return [], None, attempt

    result = fetch_oddalerts_odds_history(oddalerts_id, conn=conn)
    attempt.update(
        {
            "call_made": bool(result.api_calls),
            "api_calls": result.api_calls,
            "errors": result.errors,
            "line_count": len(result.lines),
        }
    )
    if not result.lines:
        attempt["reason"] = "live_empty_or_failed"
        return [], None, attempt

    bookmakers = _oddalerts_lines_to_bookmakers(result.lines)
    attempt["bookmaker_count"] = len(bookmakers)
    if not bookmakers:
        attempt["reason"] = "unparseable_or_no_bookmakers"
        return [], None, attempt

    attempt["success"] = True
    return bookmakers, {"line_count": len(result.lines)}, attempt


def refresh_fixture_odds_live(
    fixture: DailyFixture,
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    max_live_calls: int | None = None,
) -> dict[str, Any]:
    """Try configured live providers in order until usable odds are found."""
    settings = settings or get_settings()
    fid = int(fixture.provider_fixture_id)
    conn = connect(settings.sqlite_path)
    attempts: list[dict[str, Any]] = []

    provider_chain: tuple[
        tuple[str, Callable[[], tuple[list[Any], Any, dict[str, Any]]]], ...
    ] = (
        ("api-football", lambda: _try_api_football(fid, settings)),
        ("sportmonks", lambda: _try_sportmonks(fid, settings, conn)),
        ("oddalerts", lambda: _try_oddalerts(fid, conn)),
    )

    selected_provider: str | None = None
    selected_bookmakers: list[Any] = []
    selected_normalized: Any = None
    selected_quality: dict[str, bool] = {}
    selected_raw_path: str | None = None
    live_calls = 0

    try:
        for provider_name, provider_call in provider_chain:
            if max_live_calls is not None and live_calls >= max(0, int(max_live_calls)):
                attempts.append(
                    {
                        "provider": provider_name,
                        "configured": True,
                        "call_made": False,
                        "success": False,
                        "reason": "provider_call_budget_exhausted",
                    }
                )
                break

            bookmakers, raw_payload, attempt = provider_call()
            attempts.append(attempt)
            if attempt.get("call_made"):
                live_calls += 1
            if not bookmakers:
                continue

            raw_path = _write_raw_payload(fid, provider_name, raw_payload)
            normalized, usable, quality = _normalize_candidate(
                bookmakers,
                fixture_id=fid,
                raw_path=raw_path,
            )
            attempt["market_quality"] = quality
            attempt["usable_for_prediction"] = usable
            if not usable:
                attempt["success"] = False
                attempt["reason"] = "required_markets_missing_or_invalid"
                continue

            selected_provider = provider_name
            selected_bookmakers = bookmakers
            selected_normalized = normalized
            selected_quality = quality
            selected_raw_path = raw_path
            break
    finally:
        conn.close()

    if selected_provider is None or selected_normalized is None:
        return {
            "fixture_id": fid,
            "status": "all_live_providers_failed_or_unusable",
            "source": "none",
            "provider": None,
            "attempts": attempts,
            "providers_tried": [a.get("provider") for a in attempts],
            "live_call_made": live_calls > 0,
            "live_calls": live_calls,
            "imported": False,
        }

    payload = _build_daily_storage_payload(
        bookmakers=selected_bookmakers,
        normalized=selected_normalized,
        provider=selected_provider,
        provider_fixture_id=fid,
        api_source="live",
        raw_path=selected_raw_path,
        freshness="fresh",
    )
    mw = getattr(selected_normalized, "match_winner", None) or {}
    payload = enrich_snapshot_payload_metadata(
        payload,
        fixture_id=fid,
        kickoff_utc=fixture.kickoff_utc,
        provider=selected_provider or "unknown",
        bookmaker=(selected_bookmakers[0].get("name") if selected_bookmakers else None),
        home_odds=mw.get("home"),
        draw_odds=mw.get("draw"),
        away_odds=mw.get("away"),
        freshness_status="FRESH_ODDS",
        freshness_reason="strict_live_refresh",
        raw_payload=selected_normalized,
    )
    payload["strict_live_refresh"] = True
    payload["cache_bypassed"] = True
    payload["provider_fallback_chain"] = ["api-football", "sportmonks", "oddalerts"]
    payload["provider_attempts"] = attempts
    payload["selected_live_provider"] = selected_provider
    payload["market_quality"] = selected_quality

    if dry_run:
        return {
            "fixture_id": fid,
            "status": "dry_run_live_odds_valid",
            "source": "live",
            "provider": selected_provider,
            "bookmaker_count": selected_normalized.bookmaker_count,
            "market_quality": selected_quality,
            "attempts": attempts,
            "live_call_made": live_calls > 0,
            "live_calls": live_calls,
            "imported": False,
        }

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    repo.save_snapshot(
        "odds_snapshots",
        fixture_id=fid,
        competition_key=fixture.competition_key,
        payload=payload,
        snapshot_at=payload.get("snapshot_at"),
    )

    return {
        "fixture_id": fid,
        "status": "imported_live",
        "source": "live",
        "provider": selected_provider,
        "snapshot_at": payload.get("snapshot_at"),
        "bookmaker_count": selected_normalized.bookmaker_count,
        "market_quality": selected_quality,
        "attempts": attempts,
        "live_call_made": live_calls > 0,
        "live_calls": live_calls,
        "imported": True,
    }

"""Provider truth audit — direct odds coverage check across API-Football, Sportmonks, OddAlerts."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.backtesting.phase31e_backfill import normalize_odds_bookmakers
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import normalize_snapshot_odds_lines
from worldcup_predictor.egie.uefa_club.config import UEFA_FULL_INCLUDES
from worldcup_predictor.owner.euro_c_odds_import import (
    _build_storage_payload,
    is_fake_odds_payload,
    normalize_uefa_odds_snapshot,
)
from worldcup_predictor.owner.euro_c2_sportmonks_odds import (
    _extract_fixture_data,
    sportmonks_odds_to_bookmakers,
)
from worldcup_predictor.owner_daily.odds_import import (
    _oddalerts_lines_to_bookmakers,
    _probabilities_valid,
    flattened_probabilities,
)
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.providers.sportmonks_fixture_lookup import team_names_match

PHASE = "PROVIDER-TRUTH-AUDIT"
AUDIT_DATE = datetime.now(timezone.utc).strftime("%Y%m%d")

SAMPLE_FIXTURE_IDS: tuple[int, ...] = (
    1564789,
    1565177,
    1567306,
    1554361,
    1554366,
    1554368,
    1554444,
    1554442,
    1554410,
    1554389,
)

MARKET_CHECKS = (
    "1x2",
    "ou_1_5",
    "ou_2_5",
    "ou_3_5",
    "btts",
    "double_chance",
    "correct_score",
    "draw_no_bet",
    "asian_handicap",
)

_SECRET_PATTERNS = (
    re.compile(r"(api[_-]?key|api[_-]?token|x-apisports-key)\s*[:=]\s*['\"]?\S+", re.I),
    re.compile(r"api_token=[^&\s]+", re.I),
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _redact_secrets(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(lambda m: m.group(0).split("=")[0] + "=***REDACTED***", out)
    return out


def _market_flags_from_names(names: set[str]) -> dict[str, bool]:
    joined = " | ".join(sorted(names)).lower()
    return {
        "1x2": any(
            t in joined
            for t in ("match winner", "1x2", "match result", "home/draw/away", "fulltime result", "ft_result")
        ),
        "ou_1_5": "over 1.5" in joined or "under 1.5" in joined or "1.5" in joined and "over" in joined,
        "ou_2_5": "over 2.5" in joined or "under 2.5" in joined or "2.5" in joined and "over" in joined,
        "ou_3_5": "over 3.5" in joined or "under 3.5" in joined or "3.5" in joined and "over" in joined,
        "btts": any(t in joined for t in ("both teams score", "btts", "both teams to score")),
        "double_chance": "double chance" in joined,
        "correct_score": "correct score" in joined,
        "draw_no_bet": "draw no bet" in joined or "dnb" in joined,
        "asian_handicap": "asian handicap" in joined or "handicap" in joined,
    }


def _collect_market_names(payload: Any) -> set[str]:
    names: set[str] = set()
    if not payload:
        return names

    def walk(obj: Any, depth: int = 0) -> None:
        if depth > 12 or obj is None:
            return
        if isinstance(obj, dict):
            for key in ("name", "market_name", "market_key", "market", "label"):
                val = obj.get(key)
                if isinstance(val, str) and val.strip():
                    names.add(val.strip())
            for key in ("bets", "values", "odds", "data", "response", "bookmakers"):
                child = obj.get(key)
                if isinstance(child, list):
                    for item in child:
                        walk(item, depth + 1)
                elif isinstance(child, dict):
                    walk(child, depth + 1)
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    walk(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, depth + 1)

    walk(payload)
    return names


def _count_bookmakers_and_odds(payload: Any) -> tuple[int, int]:
    bookmakers = normalize_odds_bookmakers(payload) if payload else []
    if not bookmakers and isinstance(payload, dict):
        inner = payload.get("bookmakers")
        if isinstance(inner, list):
            bookmakers = [b for b in inner if isinstance(b, dict)]
    odds_count = 0
    for bm in bookmakers:
        bets = bm.get("bets") or []
        for bet in bets:
            vals = bet.get("values") or []
            odds_count += len(vals)
    if odds_count == 0 and isinstance(payload, dict):
        rows = (payload.get("data") or []) if isinstance(payload.get("data"), list) else []
        odds_count = len(rows)
    return len(bookmakers), odds_count


def _extract_timestamps(payload: Any) -> tuple[str | None, str | None]:
    stamps: list[str] = []
    if isinstance(payload, dict):
        for key in ("updated_at", "captured_at", "snapshot_at", "timestamp", "latest_bookmaker_update"):
            val = payload.get(key)
            if val:
                stamps.append(str(val))
        rows = payload.get("data")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for key in ("latest_bookmaker_update", "captured_at", "updated_at"):
                    val = row.get(key)
                    if val:
                        stamps.append(str(val))
    if not stamps:
        return None, None
    stamps.sort()
    return stamps[0], stamps[-1]


@dataclass
class QuotaGuard:
    max_api_football: int = 15
    max_sportmonks: int = 15
    max_oddalerts: int = 20
    api_football_used: int = 0
    sportmonks_used: int = 0
    oddalerts_used: int = 0

    def can_call(self, provider: str) -> bool:
        if provider == "api_football":
            return self.api_football_used < self.max_api_football
        if provider == "sportmonks":
            return self.sportmonks_used < self.max_sportmonks
        if provider == "oddalerts":
            return self.oddalerts_used < self.max_oddalerts
        return False

    def mark(self, provider: str) -> None:
        if provider == "api_football":
            self.api_football_used += 1
        elif provider == "sportmonks":
            self.sportmonks_used += 1
        elif provider == "oddalerts":
            self.oddalerts_used += 1


@dataclass
class AuditCallLog:
    path: Path
    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, row: dict[str, Any]) -> None:
        safe = {k: _redact_secrets(str(v)) if isinstance(v, str) else v for k, v in row.items()}
        safe["timestamp"] = _utc_now_iso()
        self.entries.append(safe)

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            for row in self.entries:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.entries.clear()


def part_a_provider_config(settings: Settings) -> dict[str, Any]:
    oa = OddAlertsClient()
    return {
        "api_football": {
            "token_configured": bool(settings.api_football_key.strip()),
            "base_url": settings.api_football_base_url,
            "client_exists": True,
            "client_module": "worldcup_predictor.clients.api_football.ApiFootballClient",
            "odds_endpoint_implemented": True,
            "fixture_endpoint_implemented": True,
            "endpoints_used": [
                "odds?fixture={id}",
                "fixtures?id={id}",
                "fixtures?league={id}&season={year}",
            ],
            "rate_limit": {
                "api_throttle_delay_seconds": settings.api_throttle_delay_seconds,
                "api_daily_live_limit": settings.api_daily_live_limit,
            },
        },
        "sportmonks": {
            "token_configured": settings.sportmonks_configured,
            "base_url": settings.sportmonks_base_url,
            "client_exists": True,
            "client_module": "worldcup_predictor.providers.sportmonks_provider.SportmonksProvider",
            "odds_endpoint_implemented": True,
            "fixture_endpoint_implemented": True,
            "endpoints_used": [
                f"/fixtures/{{id}}?include={UEFA_FULL_INCLUDES[:40]}...",
                "/fixtures/date/{YYYY-MM-DD}",
                "/leagues/732",
            ],
            "rate_limit": {
                "timeout_seconds": settings.sportmonks_timeout_seconds,
                "owner_cycle_cap": 100,
            },
        },
        "oddalerts": {
            "token_configured": oa.is_configured,
            "base_url": oa._base_url,
            "client_exists": True,
            "client_module": "worldcup_predictor.providers.oddalerts_provider.OddAlertsClient",
            "odds_endpoint_implemented": True,
            "fixture_endpoint_implemented": True,
            "endpoints_used": [
                "odds/history?id={id}",
                "odds/latest",
                "fixtures/{id}",
                "value/upcoming",
            ],
            "rate_limit": {"client_throttle_seconds": 0.15, "owner_cycle_cap": 100},
        },
    }


def _load_fixture_row(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status
        FROM fixtures WHERE fixture_id = ?
        """,
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else None


def _mapping_for_fixture(conn: sqlite3.Connection, fixture: dict[str, Any]) -> dict[str, Any]:
    fid = int(fixture["fixture_id"])
    comp = str(fixture["competition_key"])
    home = str(fixture["home_team"])
    away = str(fixture["away_team"])

    wc = conn.execute(
        "SELECT sportmonks_fixture_id, mapping_confidence FROM wc_fixture_mapping WHERE api_football_fixture_id = ?",
        (fid,),
    ).fetchone()
    feed_rows = conn.execute(
        """
        SELECT provider, provider_fixture_id FROM euro_fixture_feed
        WHERE competition_key = ? AND home_team = ? AND away_team = ?
        """,
        (comp, home, away),
    ).fetchall()
    sm_en = conn.execute(
        "SELECT sportmonks_fixture_id FROM sportmonks_fixture_enrichment WHERE fixture_id_api_football = ?",
        (fid,),
    ).fetchone()
    hist = conn.execute(
        """
        SELECT provider, provider_fixture_id, confidence_score
        FROM historical_provider_mapping WHERE registry_fixture_id = ?
        """,
        (fid,),
    ).fetchall()

    af_id = fid
    sm_id = None
    sm_conf = 0.0
    for r in feed_rows:
        if r["provider"] == "sportmonks":
            sm_id = int(r["provider_fixture_id"])
            sm_conf = max(sm_conf, 0.99)
    if sm_en and sm_en["sportmonks_fixture_id"]:
        sm_id = int(sm_en["sportmonks_fixture_id"])
        sm_conf = max(sm_conf, float(wc["mapping_confidence"]) if wc and wc["mapping_confidence"] else 0.95)
    if wc and wc["sportmonks_fixture_id"]:
        sm_id = int(wc["sportmonks_fixture_id"])
        sm_conf = max(sm_conf, float(wc["mapping_confidence"] or 0.0))

    oa_id = None
    oa_conf = 0.0
    for r in hist:
        if r["provider"] == "oddalerts":
            oa_id = int(r["provider_fixture_id"])
            oa_conf = float(r["confidence_score"] or 0.0)

    return {
        "local_fixture_id": fid,
        "competition_key": comp,
        "kickoff_time": fixture["kickoff_utc"],
        "home_team": home,
        "away_team": away,
        "api_football_fixture_id": af_id,
        "api_football_mapping_confidence": 1.0,
        "sportmonks_fixture_id": sm_id,
        "sportmonks_mapping_confidence": sm_conf if sm_id else 0.0,
        "oddalerts_fixture_id": oa_id,
        "oddalerts_mapping_confidence": oa_conf if oa_id else 0.0,
        "oddalerts_mapping_status": "mapped" if oa_id else "pending_search",
    }


def _oddalerts_teams_match(expected_home: str, expected_away: str, row: dict[str, Any]) -> bool:
    h = str(row.get("home_name") or row.get("home") or "")
    a = str(row.get("away_name") or row.get("away") or "")
    return team_names_match(expected_home, h) and team_names_match(expected_away, a)


def resolve_oddalerts_mappings(
    conn: sqlite3.Connection,
    mappings: list[dict[str, Any]],
    *,
    settings: Settings,
    call_log: AuditCallLog,
    quota: QuotaGuard,
) -> None:
    del conn, settings
    oa = OddAlertsClient()
    if not oa.is_configured:
        for m in mappings:
            if not m.get("oddalerts_fixture_id"):
                m["oddalerts_mapping_status"] = "ODDALERTS_NOT_CONFIGURED"
        return

    upcoming_pool: list[dict[str, Any]] = []
    if quota.can_call("oddalerts"):
        upcoming = oa.get_value_upcoming(per_page=250)
        quota.mark("oddalerts")
        oa.throttle(0.15)
        call_log.record(
            {
                "phase": PHASE,
                "provider": "oddalerts",
                "endpoint": "value/upcoming",
                "action": "fixture_search_pool",
                "success": upcoming.data is not None,
                "error": upcoming.error,
                "call_made": True,
            }
        )
        upcoming_pool = (upcoming.data or {}).get("data") or []

    for m in mappings:
        if m.get("oddalerts_fixture_id"):
            m["oddalerts_mapping_status"] = "mapped_db"
            continue
        found_id = None
        for row in upcoming_pool:
            if _oddalerts_teams_match(m["home_team"], m["away_team"], row):
                found_id = int(row.get("id") or 0)
                if found_id:
                    break
        if found_id:
            m["oddalerts_fixture_id"] = found_id
            m["oddalerts_mapping_confidence"] = 0.82
            m["oddalerts_mapping_status"] = "mapped_search"
        else:
            m["oddalerts_mapping_status"] = "ODDALERTS_MAPPING_MISSING"


def _parser_dry_run(
    payload: Any,
    *,
    fixture_id: int,
    provider: str,
    competition_key: str,
) -> dict[str, Any]:
    if not payload:
        return {
            "label": "PROVIDER_EMPTY",
            "parser_ok": False,
            "store_ok": False,
            "flat_probabilities": {},
        }

    bookmakers: list[Any] = []
    if provider == "sportmonks":
        fixture_data = _extract_fixture_data(payload) if isinstance(payload, dict) else {}
        odds_entries = fixture_data.get("odds") or []
        if isinstance(odds_entries, list):
            bookmakers = sportmonks_odds_to_bookmakers(odds_entries)
    elif provider == "oddalerts":
        rows = (payload or {}).get("data") or [] if isinstance(payload, dict) else []
        from worldcup_predictor.research.safe_bets.providers import OddsLine

        lines = [
            OddsLine(
                provider="oddalerts",
                bookmaker=str(r.get("bookmaker_name") or r.get("bookmaker") or "unknown"),
                market_name=str(r.get("market_key") or r.get("market") or "unknown"),
                selection=str(r.get("outcome") or r.get("selection") or "unknown"),
                odd=float(r.get("closing") or r.get("opening") or 0),
            )
            for r in rows
            if isinstance(r, dict) and float(r.get("closing") or r.get("opening") or 0) > 1.0
        ]
        bookmakers = _oddalerts_lines_to_bookmakers(lines)
    else:
        bookmakers = normalize_odds_bookmakers(payload)
    parse_input: Any = {"bookmakers": bookmakers} if bookmakers else payload

    if is_fake_odds_payload(parse_input, source=provider):
        return {
            "label": "PROVIDER_EMPTY",
            "parser_ok": False,
            "store_ok": False,
            "flat_probabilities": {},
            "note": "fake_or_placeholder_payload",
        }

    normalized = normalize_uefa_odds_snapshot(parse_input, fixture_id=fixture_id)
    flat = flattened_probabilities(normalized)
    parser_ok = bool(normalized.match_winner or normalized.over_under_2_5 or normalized.btts)
    if bookmakers and not parser_ok:
        label = "PARSER_GAP"
    elif not bookmakers and payload:
        label = "PARSER_GAP"
    else:
        label = "OK"

    store_ok = False
    store_error = None
    try:
        storage_payload = _build_storage_payload(
            bookmakers=bookmakers or [],
            normalized=normalized,
            provider=provider,
            provider_fixture_id=fixture_id,
            api_source="provider_truth_audit_dry_run",
            raw_path=None,
        )
        storage_payload["flat_probabilities"] = flat
        storage_payload["competition_key"] = competition_key
        json.dumps(storage_payload)
        store_ok = _probabilities_valid(normalized) or bool(normalized.match_winner)
    except Exception as exc:
        store_error = _redact_secrets(str(exc))
        label = "STORAGE_GAP"

    if parser_ok and not store_ok and label != "STORAGE_GAP":
        label = "STORAGE_GAP"

    return {
        "label": label,
        "parser_ok": parser_ok,
        "store_ok": store_ok,
        "store_error": store_error,
        "flat_probabilities": {
            "ph": flat.get("ph"),
            "pd": flat.get("pd"),
            "pa": flat.get("pa"),
            "p_o25": flat.get("p_o25"),
            "p_u25": flat.get("p_u25"),
            "p_btts_yes": flat.get("p_btts_yes"),
            "p_btts_no": flat.get("p_btts_no"),
        },
        "missing_markets": normalized.missing_markets,
        "bookmaker_count": normalized.bookmaker_count,
    }


def fetch_api_football_odds(
    fixture_id: int,
    *,
    settings: Settings,
    raw_dir: Path,
    call_log: AuditCallLog,
    quota: QuotaGuard,
    force_refresh: bool = True,
) -> dict[str, Any]:
    provider = "api_football"
    if not quota.can_call(provider):
        return {"provider": provider, "error": "quota_exceeded", "endpoint_not_called": True}

    client = ApiFootballClient(settings)
    if not client.is_configured:
        return {"provider": provider, "error": "not_configured", "endpoint_not_called": True}

    quota.mark(provider)
    result = client.get_odds(int(fixture_id), force_refresh=force_refresh)
    call_log.record(
        {
            "phase": PHASE,
            "provider": provider,
            "endpoint": "odds",
            "fixture_id": fixture_id,
            "provider_fixture_id": fixture_id,
            "http_ok": result.ok,
            "error": result.error,
            "call_made": True,
        }
    )

    payload = None
    if result.ok and result.data:
        payload = result.data[0] if isinstance(result.data, list) and result.data else result.data

    raw_path = None
    if payload is not None:
        raw_path = raw_dir / f"api_football_{fixture_id}_odds.json"
        raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    market_names = _collect_market_names(payload)
    flags = _market_flags_from_names(market_names)
    bm_count, odds_count = _count_bookmakers_and_odds(payload)
    first_ts, last_ts = _extract_timestamps(payload)

    return {
        "provider": provider,
        "response_status": "ok" if result.ok else "error",
        "error": result.error,
        "raw_payload_path": str(raw_path) if raw_path else None,
        "markets_found": flags,
        "market_name_sample": sorted(market_names)[:30],
        "bookmaker_count": bm_count,
        "odds_count": odds_count,
        "first_odds_timestamp": first_ts,
        "latest_odds_timestamp": last_ts,
        "empty_list": bm_count == 0 and odds_count == 0,
        "endpoint_error": not result.ok,
        "payload": payload,
    }


def fetch_sportmonks_odds(
    sportmonks_fixture_id: int,
    api_fixture_id: int,
    *,
    settings: Settings,
    raw_dir: Path,
    call_log: AuditCallLog,
    quota: QuotaGuard,
) -> dict[str, Any]:
    provider = "sportmonks"
    if not quota.can_call(provider):
        return {"provider": provider, "error": "quota_exceeded", "endpoint_not_called": True}

    sm = SportmonksProvider(settings)
    if not sm.is_configured:
        return {"provider": provider, "error": "not_configured", "endpoint_not_called": True}

    quota.mark(provider)
    status, payload, err = sm.safe_get(
        f"/fixtures/{int(sportmonks_fixture_id)}",
        params={"include": "odds.bookmaker;odds.market;participants"},
    )
    call_log.record(
        {
            "phase": PHASE,
            "provider": provider,
            "endpoint": f"/fixtures/{sportmonks_fixture_id}",
            "fixture_id": api_fixture_id,
            "provider_fixture_id": sportmonks_fixture_id,
            "http_status": status,
            "error": err,
            "call_made": True,
        }
    )

    raw_path = None
    if payload is not None:
        raw_path = raw_dir / f"sportmonks_{sportmonks_fixture_id}_odds.json"
        raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    market_names = _collect_market_names(payload)
    flags = _market_flags_from_names(market_names)
    fixture_data = _extract_fixture_data(payload) if isinstance(payload, dict) else {}
    odds_entries = fixture_data.get("odds") or []
    bookmakers = sportmonks_odds_to_bookmakers(odds_entries) if isinstance(odds_entries, list) else []
    bm_count = len(bookmakers)
    odds_count = sum(len(b.get("bets") or []) for b in bookmakers)
    first_ts, last_ts = _extract_timestamps(payload)

    return {
        "provider": provider,
        "response_status": "ok" if status and status < 400 and not err else "error",
        "error": err,
        "http_status": status,
        "raw_payload_path": str(raw_path) if raw_path else None,
        "markets_found": flags,
        "market_name_sample": sorted(market_names)[:30],
        "bookmaker_count": bm_count,
        "odds_count": odds_count,
        "first_odds_timestamp": first_ts,
        "latest_odds_timestamp": last_ts,
        "empty_list": bm_count == 0 and odds_count == 0,
        "endpoint_error": bool(err) or (status is not None and status >= 400),
        "payload": payload,
    }


def fetch_oddalerts_odds(
    oddalerts_fixture_id: int,
    api_fixture_id: int,
    *,
    raw_dir: Path,
    call_log: AuditCallLog,
    quota: QuotaGuard,
) -> dict[str, Any]:
    provider = "oddalerts"
    if not quota.can_call(provider):
        return {"provider": provider, "error": "quota_exceeded", "endpoint_not_called": True}

    oa = OddAlertsClient()
    if not oa.is_configured:
        return {"provider": provider, "error": "not_configured", "endpoint_not_called": True}

    quota.mark(provider)
    result = oa.get_odds_history(int(oddalerts_fixture_id))
    oa.throttle(0.15)
    call_log.record(
        {
            "phase": PHASE,
            "provider": provider,
            "endpoint": "odds/history",
            "fixture_id": api_fixture_id,
            "provider_fixture_id": oddalerts_fixture_id,
            "success": result.data is not None,
            "error": result.error,
            "call_made": True,
        }
    )

    payload = result.data
    raw_path = None
    if payload is not None:
        raw_path = raw_dir / f"oddalerts_{oddalerts_fixture_id}_odds.json"
        raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    market_names = _collect_market_names(payload)
    flags = _market_flags_from_names(market_names)
    rows = (payload or {}).get("data") or [] if isinstance(payload, dict) else []
    odds_count = len(rows) if isinstance(rows, list) else 0
    bookmakers = {str(r.get("bookmaker_name") or r.get("bookmaker") or "unknown") for r in rows if isinstance(r, dict)}
    first_ts, last_ts = _extract_timestamps(payload)

    return {
        "provider": provider,
        "response_status": "ok" if result.data and not result.error else "error",
        "error": result.error,
        "raw_payload_path": str(raw_path) if raw_path else None,
        "markets_found": flags,
        "market_name_sample": sorted(market_names)[:30],
        "bookmaker_count": len(bookmakers),
        "odds_count": odds_count,
        "first_odds_timestamp": first_ts,
        "latest_odds_timestamp": last_ts,
        "empty_list": odds_count == 0,
        "endpoint_error": bool(result.error),
        "payload": payload,
    }


def _final_blocker(
    *,
    mapped: bool,
    mapping_status: str,
    provider_result: dict[str, Any],
    parser_result: dict[str, Any],
) -> str:
    if not mapped:
        if "ODDALERTS" in mapping_status:
            return "MAPPING_MISSING"
        if mapping_status.endswith("MISSING"):
            return "MAPPING_MISSING"
        return "MAPPING_MISSING"
    if provider_result.get("endpoint_not_called"):
        if provider_result.get("error") == "not_configured":
            return "ENDPOINT_NOT_IMPLEMENTED"
        return "ENDPOINT_NOT_IMPLEMENTED"
    if provider_result.get("endpoint_error"):
        return "MARKET_NOT_INCLUDED_IN_PLAN"
    if provider_result.get("empty_list"):
        return "PROVIDER_EMPTY"
    label = parser_result.get("label", "")
    if label == "PARSER_GAP":
        return "PARSER_GAP"
    if label == "STORAGE_GAP":
        return "STORAGE_GAP"
    if label == "PROVIDER_EMPTY":
        return "PROVIDER_EMPTY"
    return "OK"


def build_truth_table(
    mappings: list[dict[str, Any]],
    provider_results: list[dict[str, Any]],
    parser_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    parser_by_key = {
        (p["fixture_id"], p["provider"]): p for p in parser_results
    }
    result_by_key = {
        (r["fixture_id"], r["provider"]): r for r in provider_results
    }

    for m in mappings:
        fid = int(m["local_fixture_id"])
        label_home = f"{m['home_team']} vs {m['away_team']}"
        for provider, pid_key, conf_key, status_key in (
            ("api_football", "api_football_fixture_id", "api_football_mapping_confidence", None),
            ("sportmonks", "sportmonks_fixture_id", "sportmonks_mapping_confidence", None),
            ("oddalerts", "oddalerts_fixture_id", "oddalerts_mapping_confidence", "oddalerts_mapping_status"),
        ):
            pid = m.get(pid_key)
            mapped = pid is not None
            prov = result_by_key.get((fid, provider), {})
            parser = parser_by_key.get((fid, provider), {"label": "PROVIDER_EMPTY", "parser_ok": False, "store_ok": False})
            markets = prov.get("markets_found") or {}
            mapping_status = m.get(status_key) or ("mapped" if mapped else "missing")
            blocker = _final_blocker(
                mapped=mapped,
                mapping_status=str(mapping_status),
                provider_result=prov,
                parser_result=parser,
            )
            rows.append(
                {
                    "fixture": label_home,
                    "fixture_id": fid,
                    "provider": provider,
                    "mapped": mapped,
                    "mapping_confidence": m.get(conf_key, 0.0),
                    "1x2": markets.get("1x2", False),
                    "ou_2_5": markets.get("ou_2_5", False),
                    "btts": markets.get("btts", False),
                    "correct_score": markets.get("correct_score", False),
                    "raw_odds": not prov.get("empty_list", True) and prov.get("response_status") == "ok",
                    "parser_ok": parser.get("parser_ok", False),
                    "store_ok": parser.get("store_ok", False),
                    "final_blocker": blocker,
                }
            )
    return rows


def _system_fingerprints(conn: sqlite3.Connection) -> dict[str, Any]:
    def count(table: str) -> int:
        try:
            return int(conn.execute(f"SELECT COUNT(1) FROM {table}").fetchone()[0])
        except sqlite3.OperationalError:
            return -1

    return {
        "predictions": count("predictions"),
        "worldcup_stored_predictions": count("worldcup_stored_predictions"),
        "ecse_live_snapshots": count("ecse_live_snapshots"),
        "odds_snapshots": count("odds_snapshots"),
        "billing_subscriptions": count("subscriptions"),
    }


def run_provider_truth_audit(
    *,
    settings: Settings | None = None,
    raw_dir: Path | None = None,
    artifacts_dir: Path | None = None,
    log_dir: Path | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    artifacts_dir = artifacts_dir or Path("artifacts")
    raw_dir = raw_dir or artifacts_dir / "provider_truth_audit_raw"
    log_dir = log_dir or Path("logs")
    raw_dir.mkdir(parents=True, exist_ok=True)

    call_log_path = log_dir / f"provider_truth_audit_calls_{AUDIT_DATE}.jsonl"
    call_log = AuditCallLog(path=call_log_path)
    quota = QuotaGuard()

    conn = connect(get_db_path(settings.sqlite_path))
    fingerprints_before = _system_fingerprints(conn)

    part_a = part_a_provider_config(settings)

    mappings: list[dict[str, Any]] = []
    for fid in SAMPLE_FIXTURE_IDS:
        row = _load_fixture_row(conn, fid)
        if not row:
            mappings.append({"local_fixture_id": fid, "error": "fixture_not_in_db"})
            continue
        mappings.append(_mapping_for_fixture(conn, row))

    resolve_oddalerts_mappings(conn, mappings, settings=settings, call_log=call_log, quota=quota)

    provider_results: list[dict[str, Any]] = []
    parser_results: list[dict[str, Any]] = []

    for m in mappings:
        if m.get("error"):
            continue
        fid = int(m["local_fixture_id"])
        comp = str(m["competition_key"])

        af = fetch_api_football_odds(
            fid, settings=settings, raw_dir=raw_dir, call_log=call_log, quota=quota
        )
        af_entry = {**af, "fixture_id": fid, "provider_fixture_id": fid}
        del af_entry["payload"]
        provider_results.append(af_entry)
        parser_results.append(
            {
                "fixture_id": fid,
                "provider": "api_football",
                **_parser_dry_run(af.get("payload"), fixture_id=fid, provider="api-football", competition_key=comp),
            }
        )

        sm_id = m.get("sportmonks_fixture_id")
        if sm_id:
            sm = fetch_sportmonks_odds(
                int(sm_id), fid, settings=settings, raw_dir=raw_dir, call_log=call_log, quota=quota
            )
            sm_entry = {**sm, "fixture_id": fid, "provider_fixture_id": sm_id}
            del sm_entry["payload"]
            provider_results.append(sm_entry)
            parser_results.append(
                {
                    "fixture_id": fid,
                    "provider": "sportmonks",
                    **_parser_dry_run(sm.get("payload"), fixture_id=fid, provider="sportmonks", competition_key=comp),
                }
            )
        else:
            provider_results.append(
                {
                    "fixture_id": fid,
                    "provider": "sportmonks",
                    "mapped": False,
                    "error": "mapping_missing",
                    "empty_list": True,
                }
            )

        oa_id = m.get("oddalerts_fixture_id")
        if oa_id:
            oa = fetch_oddalerts_odds(int(oa_id), fid, raw_dir=raw_dir, call_log=call_log, quota=quota)
            oa_entry = {**oa, "fixture_id": fid, "provider_fixture_id": oa_id}
            del oa_entry["payload"]
            provider_results.append(oa_entry)
            parser_results.append(
                {
                    "fixture_id": fid,
                    "provider": "oddalerts",
                    **_parser_dry_run(oa.get("payload"), fixture_id=fid, provider="oddalerts", competition_key=comp),
                }
            )
        else:
            provider_results.append(
                {
                    "fixture_id": fid,
                    "provider": "oddalerts",
                    "mapped": False,
                    "error": m.get("oddalerts_mapping_status", "ODDALERTS_MAPPING_MISSING"),
                    "empty_list": True,
                }
            )

    truth_table = build_truth_table(mappings, provider_results, parser_results)
    call_log.flush()

    fingerprints_after = _system_fingerprints(conn)
    conn.close()

    summary = {
        "phase": PHASE,
        "audit_date": AUDIT_DATE,
        "generated_at": _utc_now_iso(),
        "sample_fixture_count": len(SAMPLE_FIXTURE_IDS),
        "provider_config": part_a,
        "quota_used": {
            "api_football": quota.api_football_used,
            "sportmonks": quota.sportmonks_used,
            "oddalerts": quota.oddalerts_used,
        },
        "call_log_path": str(call_log_path),
        "raw_payload_dir": str(raw_dir),
        "truth_table": truth_table,
        "system_fingerprints_before": fingerprints_before,
        "system_fingerprints_after": fingerprints_after,
        "unchanged_checks": {
            k: fingerprints_before.get(k) == fingerprints_after.get(k)
            for k in fingerprints_before
        },
        "recommendation": _derive_recommendation(truth_table, part_a),
    }

    fixture_table = {
        "fixtures": mappings,
        "provider_calls": provider_results,
        "parser_dry_runs": parser_results,
    }

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "provider_truth_audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (artifacts_dir / "provider_truth_audit_fixture_table.json").write_text(
        json.dumps(fixture_table, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "summary": summary,
        "fixture_table": fixture_table,
        "truth_table": truth_table,
        "part_a": part_a,
        "mappings": mappings,
    }


def _derive_recommendation(truth_table: list[dict[str, Any]], part_a: dict[str, Any]) -> str:
    uefa_ids = {1554361, 1554366, 1554368, 1554444, 1554442, 1554410, 1554389}
    wc_ids = {1564789, 1565177, 1567306}

    uefa_rows = [r for r in truth_table if r["fixture_id"] in uefa_ids]
    wc_rows = [r for r in truth_table if r["fixture_id"] in wc_ids]

    parser_gaps = [r for r in truth_table if r["final_blocker"] == "PARSER_GAP" and r.get("raw_odds")]
    storage_gaps = [r for r in truth_table if r["final_blocker"] == "STORAGE_GAP"]

    if storage_gaps:
        return "STORAGE_SCHEMA_FIX_REQUIRED"
    if parser_gaps:
        sm_parser = [r for r in parser_gaps if r["provider"] == "sportmonks"]
        af_parser = [r for r in parser_gaps if r["provider"] == "api_football"]
        if sm_parser:
            return "SPORTMONKS_MARKET_PARSER_FIX_REQUIRED"
        if af_parser:
            return "API_FOOTBALL_MARKET_PARSER_FIX_REQUIRED"

    def _has_ou25(provider: str, fids: set[int]) -> bool:
        return any(
            r["fixture_id"] in fids and r["provider"] == provider and (
                r.get("ou_2_5") or (r.get("parser_ok") and r.get("raw_odds"))
            )
            for r in truth_table
        )

    wc_ecse_ready = all(
        any(
            r["fixture_id"] == fid and r["provider"] in ("api_football", "sportmonks")
            and r.get("parser_ok") and r.get("1x2")
            for r in wc_rows
        )
        for fid in wc_ids
    )

    uefa_af_empty = all(
        r["final_blocker"] == "PROVIDER_EMPTY"
        for r in uefa_rows
        if r["provider"] == "api_football" and r["mapped"]
    )
    uefa_sm_no_ou25 = not any(
        r["provider"] == "sportmonks" and r.get("ou_2_5")
        for r in uefa_rows
    )
    uefa_sm_has_1x2 = any(
        r["provider"] == "sportmonks" and r.get("1x2") and r.get("parser_ok")
        for r in uefa_rows
    )

    if uefa_af_empty and uefa_sm_no_ou25 and uefa_sm_has_1x2:
        return "PROVIDERS_EMPTY_WAIT_CLOSER_TO_KICKOFF"

    importer_needed = [
        r for r in truth_table
        if r.get("raw_odds") and r.get("parser_ok") and r.get("store_ok")
        and not r.get("ou_2_5") and r["fixture_id"] in uefa_ids
    ]
    if importer_needed and uefa_sm_has_1x2:
        return "PROVIDERS_HAVE_ODDS_FIX_IMPORTER"

    oa_missing = sum(1 for r in truth_table if r["provider"] == "oddalerts" and r["final_blocker"] == "MAPPING_MISSING")
    if oa_missing == len(SAMPLE_FIXTURE_IDS) and not wc_ecse_ready:
        return "ODDALERTS_MAPPING_FIX_REQUIRED"

    if wc_ecse_ready:
        return "ECSE_READY_AFTER_IMPORT"

    if any(r.get("raw_odds") for r in truth_table):
        return "PROVIDERS_HAVE_ODDS_FIX_IMPORTER"
    return "PROVIDERS_EMPTY_WAIT_CLOSER_TO_KICKOFF"

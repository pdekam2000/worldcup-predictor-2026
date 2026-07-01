"""PHASE EURO-C4 — OddAlerts UEFA odds truth audit + import (owner/internal only)."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.data_import.uefa_result_matching import (
    KICKOFF_WINDOW_HOURS,
    kickoff_delta_hours,
    parse_kickoff,
    team_similarity,
    teams_exact,
    teams_fuzzy_score,
)
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import normalize_snapshot_odds_lines
from worldcup_predictor.owner.euro_c3_odds_watch import (
    _market_flags,
    _probabilities_valid,
    load_readiness_index,
)
from worldcup_predictor.owner.euro_c_odds_import import (
    GENERATED_BY_WDE,
    _existing_is_newer_than,
    _latest_odds_snapshot,
    _markets_complete,
    assess_ecse_readiness,
    filter_uefa_target_fixtures,
    is_fake_odds_payload,
    normalize_uefa_odds_snapshot,
)
from worldcup_predictor.owner_daily.odds_import import _oddalerts_lines_to_bookmakers
from worldcup_predictor.owner_daily.provider_call_log import DailyProviderCallLog, ProviderQuotaGuard
from worldcup_predictor.providers.oddalerts_historical_odds import ODDALERTS_LEAGUE_MAP
from worldcup_predictor.providers.oddalerts_provider import DEFAULT_BASE_URL, OddAlertsClient

PHASE = "EURO-C4"
MIN_CROSSWALK_CONFIDENCE = 0.90
AMBIGUOUS_TOP_DELTA = 0.02

CONFIG_AUDIT_PATH = Path("artifacts/euro_c4_oddalerts_config_audit.json")
CROSSWALK_PATH = Path("artifacts/euro_c4_oddalerts_crosswalk.json")
AVAILABILITY_PATH = Path("artifacts/euro_c4_oddalerts_odds_availability.json")
READINESS_PATH = Path("artifacts/euro_c4_ecse_readiness_after_oddalerts.json")
RAW_DIR = Path("artifacts/euro_c4/raw_oddalerts_payloads")
EURO_C3_SUMMARY = Path("artifacts/euro_c3_uefa_odds_watch_summary.json")

EcseReadinessStatus = Literal[
    "READY_FULL",
    "READY_PARTIAL",
    "ODDS_PARTIAL_1X2_ONLY",
    "ODDS_MISSING",
    "MAPPING_MISSING",
    "PROVIDER_EMPTY",
    "PROVIDER_ERROR",
    "MARKET_PARSER_GAP",
    "STORAGE_GAP",
]

UEFA_ODDALERTS_COMPETITION_HINTS: dict[str, list[str]] = {
    "champions_league": ["Champions League", "UEFA Champions League"],
    "europa_league": ["Europa League", "UEFA Europa League"],
    "conference_league": ["Conference League", "Europa Conference League", "UEFA Conference League"],
}

# Known OddAlerts competition IDs (extended at runtime via competitions search).
UEFA_ODDALERTS_COMPETITION_IDS: dict[str, int | None] = {
    "champions_league": 51,
    "europa_league": 32,
    "conference_league": None,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _mask_token(value: str | None) -> str:
    if not value:
        return ""
    v = str(value).strip()
    if len(v) <= 8:
        return "***"
    return f"{v[:4]}...{v[-4:]}"


def _oddalerts_payload_status(payload: dict[str, Any] | None) -> tuple[bool, str | None]:
    """Return (ok, error_code) for OddAlerts JSON payloads (HTTP 200 with info errors)."""
    if not payload:
        return False, "empty_response"
    info = str(payload.get("info") or "").strip()
    if not info:
        rows = payload.get("data")
        if rows is None and payload.get("code") not in (None, 200):
            return False, f"code_{payload.get('code')}"
        return True, None
    lowered = info.lower()
    if lowered in {"ok", "success"}:
        return True, None
    if "incorrect permissions" in lowered:
        return False, "incorrect_permissions"
    return False, info[:120]


def _probe_oddalerts_permissions(client: OddAlertsClient) -> dict[str, Any]:
    probes: list[dict[str, Any]] = []
    endpoints = [
        ("competitions", {"page": 1, "per_page": 1}),
        ("value/upcoming", {"page": 1, "per_page": 1}),
        ("fixtures/upcoming", {"page": 1, "per_page": 1}),
        ("odds/latest", {"since_minutes": 60, "page": 1, "per_page": 1}),
    ]
    ok_any = False
    permission_denied = False
    for endpoint, params in endpoints:
        res = client._get(endpoint, params=params)
        ok, err = _oddalerts_payload_status(res.data if isinstance(res.data, dict) else None)
        row_count = len((res.data or {}).get("data") or []) if isinstance(res.data, dict) else 0
        if err == "incorrect_permissions":
            permission_denied = True
        ok_any = ok_any or (ok and row_count >= 0)
        probes.append(
            {
                "endpoint": endpoint,
                "http_ok": res.error is None,
                "payload_ok": ok,
                "error": err or res.error,
                "row_count": row_count,
                "info": (res.data or {}).get("info") if isinstance(res.data, dict) else None,
            }
        )
    return {
        "probes": probes,
        "api_permissions_ok": ok_any and not permission_denied,
        "permission_denied": permission_denied,
        "permission_error": "incorrect_permissions" if permission_denied else None,
    }


def audit_oddalerts_config(*, settings: Settings | None = None) -> dict[str, Any]:
    """Part A — OddAlerts config and endpoint audit (no secrets)."""
    settings = settings or get_settings()
    client = OddAlertsClient()
    import os

    token_env = bool((os.getenv("ODDALERTS_API_KEY") or "").strip())
    base_env = bool((os.getenv("ODDALERTS_BASE_URL") or "").strip())

    audit: dict[str, Any] = {
        "phase": PHASE,
        "generated_at_utc": _utc_now_iso(),
        "token_configured": client.is_configured,
        "token_env_var": "ODDALERTS_API_KEY",
        "token_present_in_env": token_env,
        "token_masked": _mask_token(os.getenv("ODDALERTS_API_KEY")),
        "base_url_configured": True,
        "base_url_env_var": "ODDALERTS_BASE_URL",
        "base_url": client._base_url if hasattr(client, "_base_url") else DEFAULT_BASE_URL,
        "base_url_from_env": base_env,
        "client_implemented": True,
        "endpoints": {
            "fixture_search": {"exists": True, "methods": ["get_value_upcoming", "get_competitions", "discover_fixtures"]},
            "odds": {"exists": True, "methods": ["get_odds_history", "get_odds_latest"]},
            "value_bets": {"exists": True, "methods": ["get_value_upcoming", "get_trends"]},
        },
        "supported_market_names_known": True,
        "known_league_map_keys": list(ODDALERTS_LEAGUE_MAP.keys()),
        "uefa_competition_ids": dict(UEFA_ODDALERTS_COMPETITION_IDS),
        "euro_c3_oddalerts_calls_zero_reasons": [],
    }

    reasons: list[str] = []
    if not client.is_configured:
        reasons.append("ODDALERTS_API_KEY not configured — OddAlerts branch skipped in EURO-C3")
    reasons.append(
        "EURO-C3 passed API-Football fixture_id to fetch_oddalerts_odds_history without OddAlerts crosswalk"
    )
    reasons.append("No euro_c4/euro_c2-style OddAlerts crosswalk existed at EURO-C3 run time")
    if EURO_C3_SUMMARY.exists():
        try:
            c3 = json.loads(EURO_C3_SUMMARY.read_text(encoding="utf-8"))
            audit["euro_c3_provider_calls"] = c3.get("provider_calls")
            if int((c3.get("provider_calls") or {}).get("oddalerts", 0)) == 0:
                reasons.append("EURO-C3 summary confirms oddalerts call count = 0")
        except (json.JSONDecodeError, OSError):
            pass
    audit["euro_c3_oddalerts_calls_zero_reasons"] = reasons

    if client.is_configured:
        probe = _probe_oddalerts_permissions(client)
        audit["connectivity_probe"] = probe
        audit["api_permissions_ok"] = probe.get("api_permissions_ok")
        audit["permission_denied"] = probe.get("permission_denied")
        audit["permission_error"] = probe.get("permission_error")
        if probe.get("permission_denied"):
            reasons.append(
                "OddAlerts API token present but endpoints return Incorrect Permissions — fixture/odds data inaccessible"
            )
            audit["euro_c3_oddalerts_calls_zero_reasons"] = reasons
    else:
        audit["api_permissions_ok"] = False
        audit["permission_denied"] = False
        audit["permission_error"] = "token_missing"

    CONFIG_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_AUDIT_PATH.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return audit


def _resolve_oddalerts_competition_id(
    client: OddAlertsClient,
    competition_key: str,
    *,
    log: DailyProviderCallLog | None = None,
    api_calls: dict[str, int] | None = None,
) -> int | None:
    if competition_key in UEFA_ODDALERTS_COMPETITION_IDS:
        cid = UEFA_ODDALERTS_COMPETITION_IDS.get(competition_key)
        if cid is not None:
            return int(cid)
    cfg = ODDALERTS_LEAGUE_MAP.get(competition_key)
    if cfg:
        return int(cfg["competition_id"])

    hints = UEFA_ODDALERTS_COMPETITION_HINTS.get(competition_key, [])
    for hint in hints:
        res = client.get_competitions(search=hint, per_page=50)
        if api_calls is not None:
            api_calls["oddalerts"] = api_calls.get("oddalerts", 0) + 1
        log and log.record(
            provider="oddalerts",
            endpoint="competitions",
            action="search_competition",
            competition_key=competition_key,
            call_made=True,
            success=bool(res.data),
        )
        for row in (res.data or {}).get("data") or []:
            name = str(row.get("name") or "")
            if any(h.lower() in name.lower() for h in hints):
                cid = int(row.get("id") or 0)
                if cid > 0:
                    UEFA_ODDALERTS_COMPETITION_IDS[competition_key] = cid
                    return cid
    return None


def discover_oddalerts_uefa_pool(
    client: OddAlertsClient,
    *,
    competition_keys: list[str],
    max_api_calls: int = 50,
    log: DailyProviderCallLog | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Fetch OddAlerts upcoming fixtures for UEFA competitions."""
    api_calls: dict[str, int] = {"oddalerts": 0}
    pool: dict[int, dict[str, Any]] = {}

    comp_ids: dict[str, int] = {}
    permission_denied = False
    for key in competition_keys:
        cid = _resolve_oddalerts_competition_id(client, key, log=log, api_calls=api_calls)
        if cid:
            comp_ids[key] = cid
        if api_calls["oddalerts"] >= max_api_calls:
            break

    remaining = max(0, max_api_calls - api_calls["oddalerts"])
    per_comp_budget = max(1, remaining // max(1, len(comp_ids) or 1))

    for comp_key, comp_id in comp_ids.items():
        for page in range(1, per_comp_budget + 1):
            if api_calls["oddalerts"] >= max_api_calls:
                break
            for endpoint, params in (
                ("fixtures/upcoming", {"competitions": comp_id, "page": page, "per_page": 250}),
                ("value/upcoming", {"competitions": comp_id, "page": page, "per_page": 250}),
            ):
                if api_calls["oddalerts"] >= max_api_calls:
                    break
                res = client._get(endpoint, params=params)
                api_calls["oddalerts"] += 1
                payload_ok, payload_err = _oddalerts_payload_status(
                    res.data if isinstance(res.data, dict) else None
                )
                if payload_err == "incorrect_permissions":
                    permission_denied = True
                log and log.record(
                    provider="oddalerts",
                    endpoint=endpoint,
                    action="discover_pool",
                    competition_key=comp_key,
                    call_made=True,
                    success=payload_ok,
                    error=payload_err or res.error,
                )
                if permission_denied:
                    return list(pool.values()), {**api_calls, "permission_denied": True}
                rows = (res.data or {}).get("data") or []
                if not rows:
                    continue
                for row in rows:
                    comp = row.get("competition") or {}
                    comp_id_row = int(comp.get("id") or 0)
                    if comp_id_row != comp_id:
                        continue
                    fid = int(row.get("id") or 0)
                    if not fid:
                        continue
                    kickoff_unix = row.get("unix")
                    kickoff_iso = None
                    if kickoff_unix:
                        kickoff_iso = datetime.fromtimestamp(int(kickoff_unix), tz=timezone.utc).isoformat()
                    pool[fid] = {
                        "oddalerts_fixture_id": fid,
                        "competition_key": comp_key,
                        "competition_id": comp_id,
                        "competition_name": comp.get("name"),
                        "home_team": str(row.get("home_name") or row.get("home") or ""),
                        "away_team": str(row.get("away_name") or row.get("away") or ""),
                        "kickoff_utc": kickoff_iso,
                        "status": row.get("status"),
                        "source": endpoint,
                    }
                info = (res.data or {}).get("info") or {}
                if not info.get("next_page_url"):
                    break

    if not pool and remaining > api_calls["oddalerts"] and not permission_denied:
        for page in range(1, min(3, remaining) + 1):
            if api_calls["oddalerts"] >= max_api_calls:
                break
            res = client.get_value_upcoming(page=page, per_page=250)
            api_calls["oddalerts"] += 1
            payload_ok, payload_err = _oddalerts_payload_status(
                res.data if isinstance(res.data, dict) else None
            )
            if payload_err == "incorrect_permissions":
                permission_denied = True
                break
            log and log.record(
                provider="oddalerts",
                endpoint="value/upcoming",
                action="discover_pool_fallback",
                call_made=True,
                success=payload_ok,
                error=payload_err or res.error,
            )
            rows = (res.data or {}).get("data") or []
            if not rows:
                break
            for row in rows:
                comp = row.get("competition") or {}
                comp_id = int(comp.get("id") or 0)
                comp_key = next((k for k, cid in comp_ids.items() if cid == comp_id), None)
                if comp_key is None:
                    continue
                fid = int(row.get("id") or 0)
                if not fid:
                    continue
                kickoff_unix = row.get("unix")
                kickoff_iso = None
                if kickoff_unix:
                    kickoff_iso = datetime.fromtimestamp(int(kickoff_unix), tz=timezone.utc).isoformat()
                pool[fid] = {
                    "oddalerts_fixture_id": fid,
                    "competition_key": comp_key,
                    "competition_id": comp_id,
                    "competition_name": comp.get("name"),
                    "home_team": str(row.get("home_name") or ""),
                    "away_team": str(row.get("away_name") or ""),
                    "kickoff_utc": kickoff_iso,
                    "status": row.get("status"),
                    "source": "value/upcoming",
                }
            info = (res.data or {}).get("info") or {}
            if not info.get("next_page_url"):
                break

    if permission_denied:
        api_calls["permission_denied"] = True
    return list(pool.values()), api_calls


def _time_match_score(delta_hours: float | None) -> float:
    if delta_hours is None:
        return 0.0
    if delta_hours <= KICKOFF_WINDOW_HOURS:
        return round(1.0 - delta_hours / KICKOFF_WINDOW_HOURS, 4)
    return 0.0


def _score_oddalerts_candidate(
    api_home: str,
    api_away: str,
    api_kickoff: str,
    oa_row: dict[str, Any],
) -> tuple[float, float, float, float, bool] | None:
    dh = kickoff_delta_hours(api_kickoff, str(oa_row.get("kickoff_utc") or ""))
    time_score = _time_match_score(dh)
    if time_score <= 0:
        return None
    home_score = team_similarity(api_home, str(oa_row.get("home_team") or ""))
    away_score = team_similarity(api_away, str(oa_row.get("away_team") or ""))
    fuzzy = teams_fuzzy_score(
        api_home, api_away, str(oa_row.get("home_team") or ""), str(oa_row.get("away_team") or "")
    )
    combined = round((time_score + home_score + away_score) / 3.0, 4)
    if fuzzy >= 0.88:
        combined = max(combined, round((time_score + fuzzy) / 2.0, 4))
    exact = teams_exact(
        api_home, api_away, str(oa_row.get("home_team") or ""), str(oa_row.get("away_team") or "")
    )
    return time_score, home_score, away_score, combined, exact


def build_uefa_oddalerts_crosswalk(
    conn: sqlite3.Connection,
    *,
    competition_keys: list[str] | None = None,
    days_ahead: int = 30,
    max_api_calls: int = 50,
    settings: Settings | None = None,
    log: DailyProviderCallLog | None = None,
) -> dict[str, Any]:
    """Part B — Map canonical API-Football UEFA fixtures to OddAlerts fixture IDs."""
    settings = settings or get_settings()
    client = OddAlertsClient()
    keys = list(competition_keys or UEFA_CUP_KEYS)
    api_fixtures = filter_uefa_target_fixtures(conn, competition_keys=keys, days_ahead=days_ahead)

    pool: list[dict[str, Any]] = []
    api_calls: dict[str, int] = {"oddalerts": 0}
    if client.is_configured:
        pool, api_calls = discover_oddalerts_uefa_pool(
            client,
            competition_keys=keys,
            max_api_calls=max_api_calls,
            log=log,
        )

    by_comp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pool:
        by_comp[str(row.get("competition_key") or "")].append(row)

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for sel in api_fixtures:
        api_id = int(sel.provider_fixture_id)
        comp = sel.competition_key
        candidates: list[tuple[float, dict[str, Any], tuple]] = []
        for oa in by_comp.get(comp, []):
            scored = _score_oddalerts_candidate(
                sel.home_team, sel.away_team, sel.kickoff_utc, oa
            )
            if scored is None:
                continue
            candidates.append((scored[3], oa, scored))

        candidates.sort(key=lambda x: -x[0])
        best = candidates[0] if candidates else None
        second = candidates[1] if len(candidates) > 1 else None
        ambiguous = bool(
            best
            and second
            and (best[0] - second[0]) < AMBIGUOUS_TOP_DELTA
            and best[0] >= MIN_CROSSWALK_CONFIDENCE
        )

        row: dict[str, Any] = {
            "local_fixture_id": api_id,
            "api_football_fixture_id": api_id,
            "oddalerts_fixture_id": None,
            "competition_key": comp,
            "teams": {"home": sel.home_team, "away": sel.away_team},
            "kickoff_times": {"api_football": sel.kickoff_utc, "oddalerts": None},
            "confidence": None,
            "accepted": False,
            "rejection_reason": "no_oddalerts_pool" if not client.is_configured else "no_match",
            "ambiguous": ambiguous,
            "candidate_count": len(candidates),
        }

        if not client.is_configured:
            row["rejection_reason"] = "oddalerts_not_configured"
            rejected.append(row)
            continue

        if not candidates:
            rejected.append(row)
            continue

        if ambiguous:
            row["rejection_reason"] = "ambiguous_match"
            row["confidence"] = best[0]
            rejected.append(row)
            continue

        conf = float(best[0])
        oa = best[1]
        if conf < MIN_CROSSWALK_CONFIDENCE:
            row["rejection_reason"] = "confidence_below_90"
            row["confidence"] = conf
            rejected.append(row)
            continue

        row.update(
            {
                "oddalerts_fixture_id": int(oa["oddalerts_fixture_id"]),
                "kickoff_times": {
                    "api_football": sel.kickoff_utc,
                    "oddalerts": oa.get("kickoff_utc"),
                },
                "confidence": conf,
                "accepted": True,
                "rejection_reason": None,
                "time_match_score": best[2][0],
                "home_team_score": best[2][1],
                "away_team_score": best[2][2],
            }
        )
        kickoff_dt = parse_kickoff(sel.kickoff_utc)
        if kickoff_dt:
            hours = (kickoff_dt.replace(tzinfo=timezone.utc) - now).total_seconds() / 3600.0
            row["hours_until_kickoff"] = round(hours, 2)
            row["priority_48h"] = hours <= 48
            row["priority_7d"] = hours <= 7 * 24
        accepted.append(row)

    summary = {
        "phase": PHASE,
        "generated_at_utc": _utc_now_iso(),
        "competition_keys": keys,
        "days_ahead": days_ahead,
        "api_fixture_count": len(api_fixtures),
        "oddalerts_pool_size": len(pool),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "provider_calls": api_calls,
        "oddalerts_configured": client.is_configured,
        "discovery_permission_denied": bool(api_calls.get("permission_denied")),
        "discovery_error": "incorrect_permissions" if api_calls.get("permission_denied") else None,
        "accepted": accepted,
        "rejected": rejected,
    }
    CROSSWALK_PATH.parent.mkdir(parents=True, exist_ok=True)
    CROSSWALK_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def load_oddalerts_crosswalk_map(path: Path | None = None) -> dict[int, dict[str, Any]]:
    p = path or CROSSWALK_PATH
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for row in data.get("accepted") or []:
        if not row.get("accepted"):
            continue
        fid = int(row.get("api_football_fixture_id") or row.get("local_fixture_id") or 0)
        if fid > 0:
            out[fid] = row
    return out


def _market_keys_from_raw_rows(rows: list[dict[str, Any]]) -> dict[str, bool]:
    flags = {
        "1x2": False,
        "ou25": False,
        "btts": False,
        "ou15": False,
        "ou35": False,
        "double_chance": False,
        "correct_score": False,
    }
    for row in rows:
        mk = str(row.get("market_key") or row.get("market") or "").lower()
        outcome = str(row.get("outcome") or row.get("selection") or "").lower()
        if any(t in mk for t in ("fulltime_result", "match_winner", "1x2", "full_time_result")):
            flags["1x2"] = True
        if "btts" in mk or "both_teams" in mk:
            flags["btts"] = True
        if "double_chance" in mk or "double chance" in mk:
            flags["double_chance"] = True
        if "correct_score" in mk or "correct score" in mk:
            flags["correct_score"] = True
        if re.search(r"over.?under.*2.?5|ou_?2_?5|goals_over_under_2", mk):
            flags["ou25"] = True
        if re.search(r"over.?under.*1.?5|ou_?1_?5", mk):
            flags["ou15"] = True
        if re.search(r"over.?under.*3.?5|ou_?3_?5", mk):
            flags["ou35"] = True
        if "over 2.5" in outcome or "under 2.5" in outcome:
            flags["ou25"] = True
        if "over 1.5" in outcome or "under 1.5" in outcome:
            flags["ou15"] = True
        if "over 3.5" in outcome or "under 3.5" in outcome:
            flags["ou35"] = True
    return flags


def compute_readiness_status(
    *,
    has_crosswalk: bool,
    flags: dict[str, bool],
    lambda_available: bool,
    provider_error: bool = False,
    provider_empty: bool = False,
    parser_gap: bool = False,
    storage_gap: bool = False,
) -> EcseReadinessStatus:
    if storage_gap:
        return "STORAGE_GAP"
    if parser_gap:
        return "MARKET_PARSER_GAP"
    if provider_error:
        return "PROVIDER_ERROR"
    has_1x2 = flags.get("1x2", False)
    has_ou25 = flags.get("ou25", False)
    has_btts = flags.get("btts", False)
    if not has_1x2 and not has_ou25 and provider_empty:
        return "PROVIDER_EMPTY"
    if has_1x2 and has_ou25 and has_btts and lambda_available:
        return "READY_FULL"
    if has_1x2 and has_ou25 and lambda_available:
        return "READY_PARTIAL"
    if has_1x2 and not has_ou25:
        return "ODDS_PARTIAL_1X2_ONLY"
    if not has_crosswalk and not has_1x2:
        return "MAPPING_MISSING"
    return "ODDS_MISSING"


def scan_oddalerts_uefa_odds(
    conn: sqlite3.Connection,
    *,
    crosswalk: dict[int, dict[str, Any]] | None = None,
    max_api_calls: int = 100,
    dry_run: bool = False,
    settings: Settings | None = None,
    log: DailyProviderCallLog | None = None,
    prioritize_hours: float | None = None,
) -> dict[str, Any]:
    """Part C — Direct OddAlerts odds scan for accepted crosswalk fixtures."""
    settings = settings or get_settings()
    client = OddAlertsClient()
    cw = crosswalk or load_oddalerts_crosswalk_map()
    rows_out: list[dict[str, Any]] = []
    api_calls: dict[str, int] = {"oddalerts": 0}
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    targets = list(cw.values())
    if prioritize_hours is not None:
        targets.sort(
            key=lambda r: (
                0 if r.get("priority_48h") else 1,
                0 if r.get("priority_7d") else 1,
                float(r.get("hours_until_kickoff") or 9999),
            )
        )

    for cw_row in targets:
        if api_calls["oddalerts"] >= max_api_calls:
            break
        api_id = int(cw_row.get("api_football_fixture_id") or 0)
        oa_id = int(cw_row.get("oddalerts_fixture_id") or 0)
        if not oa_id:
            continue

        entry: dict[str, Any] = {
            "fixture_id": api_id,
            "oddalerts_fixture_id": oa_id,
            "competition_key": cw_row.get("competition_key"),
            "teams": cw_row.get("teams"),
            "crosswalk_confidence": cw_row.get("confidence"),
            "provider": "oddalerts",
            "endpoint": "odds/history",
        }

        if not client.is_configured:
            entry.update({"status": "oddalerts_not_configured", "provider_empty": True})
            rows_out.append(entry)
            continue

        if dry_run:
            entry.update({"status": "dry_run", "call_made": False})
            rows_out.append(entry)
            continue

        hist = client.get_odds_history(oa_id)
        api_calls["oddalerts"] += 1
        log and log.record(
            provider="oddalerts",
            endpoint="odds/history",
            action="scan_odds",
            fixture_id=api_id,
            provider_fixture_id=oa_id,
            call_made=True,
            success=bool(hist.data),
        )
        raw_payload = hist.data or {}
        raw_path = RAW_DIR / f"{api_id}_{oa_id}_odds_history.json"
        raw_path.write_text(json.dumps(raw_payload, indent=2, default=str), encoding="utf-8")
        raw_rows: list[dict[str, Any]] = list(raw_payload.get("data") or [])

        from worldcup_predictor.research.safe_bets.providers import OddsLine

        lines = []
        for row in raw_rows:
            try:
                odd = float(row.get("closing") or row.get("opening") or 0)
            except (TypeError, ValueError):
                continue
            if odd < 1.01:
                continue
            lines.append(
                OddsLine(
                    provider="oddalerts",
                    bookmaker=str(row.get("bookmaker_name") or row.get("bookmaker") or "unknown"),
                    market_name=str(row.get("market_key") or row.get("market") or "unknown"),
                    selection=str(row.get("outcome") or row.get("selection") or "unknown"),
                    odd=odd,
                    data_quality=0.72,
                )
            )

        raw_flags = _market_keys_from_raw_rows(raw_rows)
        bookmakers = _oddalerts_lines_to_bookmakers(lines) if lines else []
        normalized = normalize_uefa_odds_snapshot(bookmakers, fixture_id=api_id, raw_odds_path=str(raw_path)) if bookmakers else None
        norm_flags = _market_flags(normalized)

        parser_gap = any(raw_flags.values()) and not any(
            norm_flags.get(k) for k in ("1x2", "ou25", "btts")
        )
        provider_empty = not raw_rows and not lines

        readiness = assess_ecse_readiness(conn, api_id, normalized=normalized)
        status = compute_readiness_status(
            has_crosswalk=True,
            flags=norm_flags if normalized else raw_flags,
            lambda_available=readiness.get("lambda_inputs_available", False),
            provider_empty=provider_empty,
            parser_gap=parser_gap,
        )

        entry.update(
            {
                "raw_markets": raw_flags,
                "normalized_markets": norm_flags,
                "market_lines_count": len(lines),
                "raw_rows_count": len(raw_rows),
                "parser_gap": parser_gap,
                "provider_empty": provider_empty,
                "ecse_readiness_status": status,
                "raw_odds_path": str(raw_path),
                "status": "scanned",
            }
        )
        rows_out.append(entry)

    by_market = defaultdict(int)
    for r in rows_out:
        for k, v in (r.get("normalized_markets") or r.get("raw_markets") or {}).items():
            if v:
                by_market[k] += 1

    summary = {
        "phase": PHASE,
        "generated_at_utc": _utc_now_iso(),
        "fixtures_scanned": len(rows_out),
        "provider_calls": api_calls,
        "market_coverage": dict(by_market),
        "parser_gap_count": sum(1 for r in rows_out if r.get("parser_gap")),
        "provider_empty_count": sum(1 for r in rows_out if r.get("provider_empty")),
        "fixtures": rows_out,
    }
    AVAILABILITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    AVAILABILITY_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def _build_import_payload(
    *,
    bookmakers: list[Any],
    normalized,
    fixture_id: int,
    oddalerts_fixture_id: int,
    crosswalk_confidence: float,
    api_source: str,
    raw_path: str | None,
) -> dict[str, Any]:
    return {
        "snapshot_at": _utc_now_iso(),
        "source": "euro_c4_oddalerts_import",
        "provider": "oddalerts",
        "phase": PHASE,
        "api_call_source": api_source,
        "api_football_fixture_id": fixture_id,
        "oddalerts_fixture_id": oddalerts_fixture_id,
        "crosswalk_confidence": crosswalk_confidence,
        "bookmakers": bookmakers,
        "normalized": normalized.to_dict(),
        "raw_odds_path": raw_path,
    }


@dataclass
class OddAlertsImportResult:
    phase: str = PHASE
    dry_run: bool = False
    fixtures_scanned: int = 0
    imported_count: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    provider_calls: dict[str, int] = field(default_factory=dict)
    fixture_rows: list[dict[str, Any]] = field(default_factory=list)
    log_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "dry_run": self.dry_run,
            "fixtures_scanned": self.fixtures_scanned,
            "imported_count": self.imported_count,
            "skipped": self.skipped,
            "provider_calls": self.provider_calls,
            "fixture_rows": self.fixture_rows,
            "log_path": self.log_path,
        }


def import_oddalerts_uefa_odds(
    repo: FootballIntelligenceRepository,
    *,
    competition_keys: list[str] | None = None,
    days_ahead: int = 30,
    dry_run: bool = False,
    max_api_calls: int = 100,
    force: bool = False,
    cache_first: bool = True,
    only_missing: bool = True,
    crosswalk_path: Path | None = None,
    settings: Settings | None = None,
    log: DailyProviderCallLog | None = None,
) -> OddAlertsImportResult:
    """Part D — Import OddAlerts odds for accepted crosswalk fixtures."""
    settings = settings or get_settings()
    conn = repo._conn
    client = OddAlertsClient()
    result = OddAlertsImportResult(dry_run=dry_run)
    cw = load_oddalerts_crosswalk_map(crosswalk_path)
    c3_index = load_readiness_index()

    targets = filter_uefa_target_fixtures(
        conn, competition_keys=competition_keys or list(UEFA_CUP_KEYS), days_ahead=days_ahead
    )
    result.fixtures_scanned = len(targets)

    for sel in targets:
        fid = int(sel.provider_fixture_id)
        comp = sel.competition_key
        cw_row = cw.get(fid)
        if not cw_row or not cw_row.get("accepted"):
            result.skipped["mapping_missing"] = result.skipped.get("mapping_missing", 0) + 1
            continue
        if float(cw_row.get("confidence") or 0) < MIN_CROSSWALK_CONFIDENCE:
            result.skipped["low_confidence_crosswalk"] = result.skipped.get("low_confidence_crosswalk", 0) + 1
            continue

        existing = _latest_odds_snapshot(conn, fid)
        existing_norm = None
        if existing:
            existing_norm = normalize_uefa_odds_snapshot(existing.get("payload") or {}, fixture_id=fid)
        if only_missing and existing_norm and _markets_complete(existing_norm):
            result.skipped["already_complete"] = result.skipped.get("already_complete", 0) + 1
            continue
        if existing and not force and _existing_is_newer_than(existing.get("snapshot_at"), _utc_now_iso()):
            result.skipped["newer_snapshot_exists"] = result.skipped.get("newer_snapshot_exists", 0) + 1
            continue

        oa_id = int(cw_row.get("oddalerts_fixture_id") or 0)
        if not oa_id:
            result.skipped["mapping_missing"] = result.skipped.get("mapping_missing", 0) + 1
            continue

        if result.provider_calls.get("oddalerts", 0) >= max_api_calls:
            result.skipped["api_cap_reached"] = result.skipped.get("api_cap_reached", 0) + 1
            break

        if not client.is_configured:
            result.skipped["oddalerts_not_configured"] = result.skipped.get("oddalerts_not_configured", 0) + 1
            continue

        raw_path: str | None = None
        bookmakers: list[Any] = []

        if cache_first:
            cached = RAW_DIR / f"{fid}_{oa_id}_odds_history.json"
            if cached.exists():
                try:
                    payload = json.loads(cached.read_text(encoding="utf-8"))
                    from worldcup_predictor.research.safe_bets.providers import OddsLine

                    lines = []
                    for row in payload.get("data") or []:
                        try:
                            odd = float(row.get("closing") or row.get("opening") or 0)
                        except (TypeError, ValueError):
                            continue
                        if odd < 1.01:
                            continue
                        lines.append(
                            OddsLine(
                                provider="oddalerts",
                                bookmaker=str(row.get("bookmaker_name") or "unknown"),
                                market_name=str(row.get("market_key") or row.get("market") or "unknown"),
                                selection=str(row.get("outcome") or row.get("selection") or "unknown"),
                                odd=odd,
                                data_quality=0.72,
                            )
                        )
                    if lines:
                        bookmakers = _oddalerts_lines_to_bookmakers(lines)
                        raw_path = str(cached)
                except (json.JSONDecodeError, OSError):
                    pass

        if not bookmakers and not dry_run:
            hist = client.get_odds_history(oa_id)
            result.provider_calls["oddalerts"] = result.provider_calls.get("oddalerts", 0) + 1
            log and log.record(
                provider="oddalerts",
                endpoint="odds/history",
                action="import_odds",
                fixture_id=fid,
                provider_fixture_id=oa_id,
                competition_key=comp,
                call_made=True,
                success=bool(hist.data),
            )
            raw_path = str(RAW_DIR / f"{fid}_{oa_id}_odds_history.json")
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            Path(raw_path).write_text(json.dumps(hist.data or {}, indent=2, default=str), encoding="utf-8")
            from worldcup_predictor.research.safe_bets.providers import OddsLine

            lines = []
            for row in (hist.data or {}).get("data") or []:
                try:
                    odd = float(row.get("closing") or row.get("opening") or 0)
                except (TypeError, ValueError):
                    continue
                if odd < 1.01:
                    continue
                lines.append(
                    OddsLine(
                        provider="oddalerts",
                        bookmaker=str(row.get("bookmaker_name") or row.get("bookmaker") or "unknown"),
                        market_name=str(row.get("market_key") or row.get("market") or "unknown"),
                        selection=str(row.get("outcome") or row.get("selection") or "unknown"),
                        odd=odd,
                        data_quality=0.72,
                    )
                )
            if lines:
                bookmakers = _oddalerts_lines_to_bookmakers(lines)

        if not bookmakers:
            result.skipped["provider_empty"] = result.skipped.get("provider_empty", 0) + 1
            result.fixture_rows.append(
                {"fixture_id": fid, "status": "PROVIDER_EMPTY", "oddalerts_fixture_id": oa_id}
            )
            continue

        normalized = normalize_uefa_odds_snapshot(bookmakers, fixture_id=fid, raw_odds_path=raw_path)
        if not _probabilities_valid(normalized):
            result.skipped["invalid_probabilities"] = result.skipped.get("invalid_probabilities", 0) + 1
            continue

        raw_flags = _market_keys_from_raw_rows(json.loads(Path(raw_path).read_text()).get("data") or []) if raw_path and Path(raw_path).exists() else {}
        norm_flags = _market_flags(normalized)
        parser_gap = any(raw_flags.values()) and not any(norm_flags.get(k) for k in ("1x2", "ou25", "btts"))

        if dry_run:
            result.fixture_rows.append({"fixture_id": fid, "status": "would_import", "oddalerts_fixture_id": oa_id})
            continue

        payload = _build_import_payload(
            bookmakers=bookmakers,
            normalized=normalized,
            fixture_id=fid,
            oddalerts_fixture_id=oa_id,
            crosswalk_confidence=float(cw_row.get("confidence") or 0),
            api_source="oddalerts",
            raw_path=raw_path,
        )
        try:
            repo.save_snapshot(
                "odds_snapshots",
                fixture_id=fid,
                competition_key=comp,
                payload=payload,
                snapshot_at=payload["snapshot_at"],
            )
            result.imported_count += 1
            readiness = assess_ecse_readiness(conn, fid, normalized=normalized)
            status = compute_readiness_status(
                has_crosswalk=True,
                flags=norm_flags,
                lambda_available=readiness.get("lambda_inputs_available", False),
                parser_gap=parser_gap,
            )
            result.fixture_rows.append(
                {
                    "fixture_id": fid,
                    "status": status,
                    "oddalerts_fixture_id": oa_id,
                    "markets": norm_flags,
                }
            )
        except Exception as exc:
            result.skipped["storage_gap"] = result.skipped.get("storage_gap", 0) + 1
            result.fixture_rows.append(
                {"fixture_id": fid, "status": "STORAGE_GAP", "error": str(exc)}
            )

    return result


def compute_ecse_readiness_after_oddalerts(
    conn: sqlite3.Connection,
    *,
    crosswalk: dict[int, dict[str, Any]] | None = None,
    availability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Part E/F — ECSE readiness + parser/storage gap summary after OddAlerts."""
    cw = crosswalk or load_oddalerts_crosswalk_map()
    avail = availability
    if avail is None and AVAILABILITY_PATH.exists():
        avail = json.loads(AVAILABILITY_PATH.read_text(encoding="utf-8"))

    c3_index = load_readiness_index()
    fixtures = filter_uefa_target_fixtures(conn, days_ahead=30)
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)

    for sel in fixtures:
        fid = int(sel.provider_fixture_id)
        snap = _latest_odds_snapshot(conn, fid)
        payload = (snap or {}).get("payload") or {}
        provider = str(payload.get("provider") or payload.get("source") or "")
        is_oa = "oddalerts" in provider.lower()

        normalized = None
        if snap:
            normalized = normalize_uefa_odds_snapshot(payload, fixture_id=fid)
        flags = _market_flags(normalized)
        readiness = assess_ecse_readiness(conn, fid, normalized=normalized)

        cw_row = cw.get(fid)
        has_crosswalk = bool(cw_row and cw_row.get("accepted"))
        parser_gap = False
        storage_gap = False
        if avail:
            for a in avail.get("fixtures") or []:
                if int(a.get("fixture_id") or 0) == fid:
                    parser_gap = bool(a.get("parser_gap"))
                    break

        c3_status = (c3_index.get(fid) or {}).get("ecse_readiness_status")
        status = compute_readiness_status(
            has_crosswalk=has_crosswalk,
            flags=flags,
            lambda_available=readiness.get("lambda_inputs_available", False),
            provider_empty=not flags.get("1x2") and not flags.get("ou25") and is_oa,
            parser_gap=parser_gap,
        )
        counts[status] += 1
        rows.append(
            {
                "fixture_id": fid,
                "competition_key": sel.competition_key,
                "teams": f"{sel.home_team} vs {sel.away_team}",
                "kickoff_utc": sel.kickoff_utc,
                "oddalerts_crosswalk": has_crosswalk,
                "oddalerts_fixture_id": (cw_row or {}).get("oddalerts_fixture_id"),
                "provider_source": provider or None,
                "ecse_readiness_status": status,
                "euro_c3_status": c3_status,
                "markets": flags,
                "has_1x2": flags.get("1x2"),
                "has_ou25": flags.get("ou25"),
                "has_btts": flags.get("btts"),
                "parser_gap": parser_gap,
            }
        )

    c3_ready_full = 0
    if EURO_C3_SUMMARY.exists():
        try:
            c3_ready_full = int(json.loads(EURO_C3_SUMMARY.read_text(encoding="utf-8")).get("ready_full_after", 0))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            c3_ready_full = 0
    comparison = {
        "euro_c3_ready_full": c3_ready_full,
        "oddalerts_ready_full": counts.get("READY_FULL", 0),
        "oddalerts_ready_partial": counts.get("READY_PARTIAL", 0),
        "oddalerts_1x2_only": counts.get("ODDS_PARTIAL_1X2_ONLY", 0),
        "oddalerts_provider_empty": counts.get("PROVIDER_EMPTY", 0),
        "parser_gap": counts.get("MARKET_PARSER_GAP", 0),
        "storage_gap": counts.get("STORAGE_GAP", 0),
    }

    summary = {
        "phase": PHASE,
        "generated_at_utc": _utc_now_iso(),
        "fixture_count": len(rows),
        "status_counts": dict(counts),
        "comparison_vs_euro_c3": comparison,
        "fixtures": rows,
    }
    READINESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    READINESS_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def run_euro_c4_pipeline(
    repo: FootballIntelligenceRepository,
    *,
    competition_keys: list[str] | None = None,
    days_ahead: int = 30,
    dry_run: bool = False,
    max_api_calls: int = 100,
    force: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Full EURO-C4 pipeline: audit → crosswalk → scan → import → readiness."""
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(".env"))
    except ImportError:
        pass
    settings = settings or get_settings()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log = DailyProviderCallLog(
        run_date=datetime.now(timezone.utc).date().isoformat(),
        quota=ProviderQuotaGuard(max_oddalerts=max_api_calls, no_provider_calls=dry_run),
    )
    log._log_path = Path("logs") / f"euro_c4_oddalerts_{stamp}.jsonl"

    config_audit = audit_oddalerts_config(settings=settings)
    crosswalk_budget = max(10, max_api_calls // 3)
    crosswalk = build_uefa_oddalerts_crosswalk(
        repo._conn,
        competition_keys=competition_keys,
        days_ahead=days_ahead,
        max_api_calls=crosswalk_budget,
        settings=settings,
        log=log,
    )
    scan_budget = max(10, max_api_calls - crosswalk.get("provider_calls", {}).get("oddalerts", 0))
    availability = scan_oddalerts_uefa_odds(
        repo._conn,
        max_api_calls=scan_budget,
        dry_run=dry_run,
        settings=settings,
        log=log,
    )
    import_budget = max(
        0,
        max_api_calls
        - crosswalk.get("provider_calls", {}).get("oddalerts", 0)
        - availability.get("provider_calls", {}).get("oddalerts", 0),
    )
    import_result = import_oddalerts_uefa_odds(
        repo,
        competition_keys=competition_keys,
        days_ahead=days_ahead,
        dry_run=dry_run,
        max_api_calls=import_budget,
        force=force,
        settings=settings,
        log=log,
    )
    readiness = compute_ecse_readiness_after_oddalerts(repo._conn, availability=availability)

    log.flush()
    log_path = str(log._log_path)
    import_result.log_path = log_path

    total_calls = (
        crosswalk.get("provider_calls", {}).get("oddalerts", 0)
        + availability.get("provider_calls", {}).get("oddalerts", 0)
        + import_result.provider_calls.get("oddalerts", 0)
    )

    recommendation = _final_recommendation(
        config_audit=config_audit,
        crosswalk=crosswalk,
        availability=availability,
        readiness=readiness,
        total_calls=total_calls,
    )

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now_iso(),
        "config_audit": config_audit,
        "crosswalk_summary": {
            "accepted": crosswalk.get("accepted_count"),
            "rejected": crosswalk.get("rejected_count"),
            "provider_calls": crosswalk.get("provider_calls"),
        },
        "availability_summary": {
            "fixtures_scanned": availability.get("fixtures_scanned"),
            "market_coverage": availability.get("market_coverage"),
            "parser_gap_count": availability.get("parser_gap_count"),
            "provider_calls": availability.get("provider_calls"),
        },
        "import_summary": import_result.to_dict() if hasattr(import_result, "to_dict") else {
            "imported_count": import_result.imported_count,
            "provider_calls": import_result.provider_calls,
            "skipped": import_result.skipped,
        },
        "readiness_summary": {
            "status_counts": readiness.get("status_counts"),
            "comparison_vs_euro_c3": readiness.get("comparison_vs_euro_c3"),
        },
        "total_oddalerts_calls": total_calls,
        "log_path": log_path,
        "final_recommendation": recommendation,
        "public_output_changed": False,
    }


def _final_recommendation(
    *,
    config_audit: dict[str, Any],
    crosswalk: dict[str, Any],
    availability: dict[str, Any],
    readiness: dict[str, Any],
    total_calls: int,
) -> str:
    if not config_audit.get("token_configured"):
        return "ODDALERTS_CONFIG_MISSING"
    if config_audit.get("permission_denied") or not config_audit.get("api_permissions_ok", True):
        return "ODDALERTS_CONFIG_MISSING"
    if int(crosswalk.get("accepted_count") or 0) == 0:
        if crosswalk.get("discovery_permission_denied"):
            return "ODDALERTS_CONFIG_MISSING"
        return "ODDALERTS_MAPPING_FIX_REQUIRED"
    if int(availability.get("parser_gap_count") or 0) > 0:
        return "ODDALERTS_PARSER_FIX_REQUIRED"
    counts = readiness.get("status_counts") or {}
    if int(counts.get("READY_FULL", 0)) > 0:
        return "ODDALERTS_ODDS_READY_FOR_ECSE"
    if int(counts.get("READY_PARTIAL", 0)) > 0:
        return "PARTIAL_ODDALERTS_ODDS_READY"
    if total_calls > 0 and int(availability.get("provider_empty_count") or 0) == int(
        availability.get("fixtures_scanned") or 0
    ):
        return "ODDALERTS_PROVIDER_EMPTY"
    if int(counts.get("ODDS_PARTIAL_1X2_ONLY", 0)) > 0:
        return "ODDALERTS_MARKETS_INSUFFICIENT"
    return "DO_NOT_RUN_ECSE_YET"

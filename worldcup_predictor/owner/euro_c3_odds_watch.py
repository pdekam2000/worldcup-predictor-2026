"""PHASE EURO-C3 — UEFA odds watch + ECSE readiness monitor (owner/internal only)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.backtesting.phase31e_backfill import (
    collect_cached_odds_sources,
    normalize_odds_bookmakers,
)
from worldcup_predictor.cache.api_cache import get_api_cache
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.data_import.uefa_result_matching import parse_kickoff
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner.euro_b_fixture_selector import UefaFixtureSelection
from worldcup_predictor.owner.euro_c_odds_import import (
    _existing_is_newer_than,
    _latest_odds_snapshot,
    _markets_complete,
    assess_ecse_readiness,
    filter_uefa_target_fixtures,
    is_fake_odds_payload,
    normalize_uefa_odds_snapshot,
)
from worldcup_predictor.owner.euro_c2_sportmonks_odds import (
    MIN_CROSSWALK_CONFIDENCE,
    fetch_sportmonks_odds_live,
    fixture_data_to_bookmakers,
    load_sportmonks_odds_payload,
)
from worldcup_predictor.owner_daily.odds_import import (
    _oddalerts_lines_to_bookmakers,
    _sportmonks_lines_to_bookmakers,
)
from worldcup_predictor.owner_daily.provider_call_log import DailyProviderCallLog, ProviderQuotaGuard
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.research.safe_bets.providers import fetch_oddalerts_odds_history

PHASE = "EURO-C3"
READINESS_PATH = Path("artifacts/euro_c3_uefa_ecse_readiness.jsonl")
SUMMARY_PATH = Path("artifacts/euro_c3_uefa_odds_watch_summary.json")
CROSSWALK_DEFAULT = Path("artifacts/euro_c2_sportmonks_crosswalk.json")
RAW_DIR = Path("artifacts/euro_c3/raw_odds_payloads")

EcseReadinessStatus = Literal[
    "READY_FULL",
    "READY_PARTIAL",
    "ODDS_PARTIAL_1X2_ONLY",
    "ODDS_MISSING",
    "MAPPING_MISSING",
    "PROVIDER_EMPTY",
    "PROVIDER_ERROR",
]
RecheckPriority = Literal["HIGH", "MEDIUM", "LOW"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def load_crosswalk_map(path: Path | None = None) -> dict[int, dict[str, Any]]:
    p = path or CROSSWALK_DEFAULT
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
        api_id = int(row.get("api_football_fixture_id") or 0)
        if api_id > 0:
            out[api_id] = row
    return out


def load_readiness_index(path: Path | None = None) -> dict[int, dict[str, Any]]:
    """Latest readiness row per fixture_id from JSONL artifact."""
    p = path or READINESS_PATH
    if not p.exists():
        return {}
    index: dict[int, dict[str, Any]] = {}
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            fid = int(row.get("fixture_id") or row.get("api_football_fixture_id") or 0)
            if fid > 0:
                index[fid] = row
    except (json.JSONDecodeError, OSError):
        return {}
    return index


def _market_flags(normalized) -> dict[str, bool]:
    if normalized is None:
        return {
            "1x2": False,
            "ou25": False,
            "btts": False,
            "ou15": False,
            "ou35": False,
            "correct_score": False,
            "double_chance": False,
        }
    return {
        "1x2": bool(normalized.match_winner),
        "ou25": bool(normalized.over_under_2_5),
        "btts": bool(normalized.btts),
        "ou15": bool(normalized.over_under_1_5),
        "ou35": bool(normalized.over_under_3_5),
        "correct_score": bool(normalized.has_correct_score),
        "double_chance": bool(normalized.has_double_chance),
    }


def _best_provider_source(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    return str(
        payload.get("provider")
        or payload.get("source")
        or payload.get("api_call_source")
        or ""
    ) or None


def _odds_freshness(snapshot_at: str | None) -> str:
    if not snapshot_at:
        return "missing"
    dt = parse_kickoff(snapshot_at.replace(" UTC", "+00:00") if " UTC" in str(snapshot_at) else snapshot_at)
    if dt is None:
        return "unknown"
    age_h = (datetime.now(timezone.utc) - dt.replace(tzinfo=timezone.utc)).total_seconds() / 3600.0
    if age_h < 6:
        return "fresh"
    if age_h < 24:
        return "recent"
    if age_h < 72:
        return "stale"
    return "old"


def next_recheck_priority(kickoff_utc: str, *, odds_missing: bool) -> RecheckPriority:
    dt = parse_kickoff(kickoff_utc)
    if dt is None:
        return "MEDIUM"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    hours = (dt - now).total_seconds() / 3600.0
    if hours < 0:
        return "LOW"
    if hours < 48 and odds_missing:
        return "HIGH"
    if hours <= 7 * 24:
        return "MEDIUM"
    return "LOW"


def compute_ecse_readiness_status(
    *,
    has_crosswalk: bool,
    has_1x2: bool,
    has_ou25: bool,
    has_btts: bool,
    lambda_available: bool,
    provider_error: bool = False,
    provider_empty: bool = False,
) -> EcseReadinessStatus:
    if provider_error:
        return "PROVIDER_ERROR"
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


def _missing_required_markets(flags: dict[str, bool]) -> list[str]:
    missing: list[str] = []
    if not flags.get("1x2"):
        missing.append("1x2")
    if not flags.get("ou25"):
        missing.append("over_under_2_5")
    if not flags.get("btts"):
        missing.append("btts")
    return missing


def _available_markets(flags: dict[str, bool]) -> list[str]:
    return [k for k, v in flags.items() if v]


def assess_fixture_readiness(
    conn,
    fixture_id: int,
    *,
    crosswalk: dict[str, Any] | None,
    provider_error: bool = False,
    provider_empty: bool = False,
) -> dict[str, Any]:
    snap = _latest_odds_snapshot(conn, fixture_id)
    payload = snap["payload"] if snap and not is_fake_odds_payload(snap.get("payload")) else None
    normalized = normalize_uefa_odds_snapshot(payload, fixture_id=fixture_id) if payload else None
    readiness = assess_ecse_readiness(conn, fixture_id, normalized=normalized)
    flags = _market_flags(normalized)
    status = compute_ecse_readiness_status(
        has_crosswalk=bool(crosswalk),
        has_1x2=flags["1x2"],
        has_ou25=flags["ou25"],
        has_btts=flags["btts"],
        lambda_available=bool(readiness.get("lambda_inputs_available")),
        provider_error=provider_error,
        provider_empty=provider_empty,
    )
    missing_reason = _missing_required_markets(flags)
    if status == "PROVIDER_EMPTY":
        missing_reason = ["provider_empty"]
    elif status == "MAPPING_MISSING" and not crosswalk:
        missing_reason = ["sportmonks_crosswalk_missing"] + missing_reason
    return {
        "fixture_id": fixture_id,
        "ecse_readiness_status": status,
        "missing_required_markets": missing_reason,
        "available_markets": _available_markets(flags),
        "best_provider_source": _best_provider_source(payload if isinstance(payload, dict) else None),
        "odds_freshness": _odds_freshness(snap["snapshot_at"] if snap else None),
        "has_1x2": flags["1x2"],
        "has_ou25": flags["ou25"],
        "has_btts": flags["btts"],
        "lambda_inputs_available": readiness.get("lambda_inputs_available"),
        "ECSE_ready": readiness.get("ecse_ready"),
        "sportmonks_fixture_id": (crosswalk or {}).get("sportmonks_fixture_id"),
        "crosswalk_confidence": (crosswalk or {}).get("combined_confidence"),
    }


def _probabilities_valid(normalized) -> bool:
    for probs in normalized.normalized_probabilities.values():
        if not isinstance(probs, dict):
            continue
        for v in probs.values():
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v) or v < 0 or v > 1)):
                return False
    return True


def _build_watch_payload(
    *,
    bookmakers: list[Any],
    normalized,
    provider: str,
    fixture_id: int,
    api_source: str,
    raw_path: str | None,
    sportmonks_fixture_id: int | None = None,
    crosswalk_confidence: float | None = None,
) -> dict[str, Any]:
    return {
        "snapshot_at": _utc_now_iso(),
        "source": f"euro_c3_{provider}_watch",
        "provider": provider,
        "phase": PHASE,
        "api_call_source": api_source,
        "api_football_fixture_id": fixture_id,
        "sportmonks_fixture_id": sportmonks_fixture_id,
        "crosswalk_confidence": crosswalk_confidence,
        "bookmakers": bookmakers,
        "normalized": normalized.to_dict(),
        "raw_odds_path": raw_path,
    }


@dataclass
class EuroC3WatchResult:
    phase: str = PHASE
    dry_run: bool = False
    fixtures_scanned: int = 0
    ready_full_before: int = 0
    ready_full_after: int = 0
    ready_partial_before: int = 0
    ready_partial_after: int = 0
    odds_1x2_only_count: int = 0
    odds_missing_count: int = 0
    provider_empty_count: int = 0
    provider_error_count: int = 0
    mapping_missing_count: int = 0
    imported_count: int = 0
    newly_ready_fixtures: list[dict[str, Any]] = field(default_factory=list)
    fixture_rows: list[dict[str, Any]] = field(default_factory=list)
    provider_calls: dict[str, int] = field(default_factory=dict)
    markets_by_competition: dict[str, dict[str, int]] = field(default_factory=dict)
    log_path: str | None = None
    skipped_reasons: dict[str, int] = field(default_factory=dict)


def watch_uefa_odds_readiness(
    repo: FootballIntelligenceRepository,
    *,
    competition_keys: list[str] | None = None,
    days_ahead: int = 30,
    dry_run: bool = False,
    max_api_football_calls: int = 100,
    max_sportmonks_calls: int = 100,
    max_oddalerts_calls: int = 100,
    cache_first: bool = True,
    only_missing: bool = True,
    force: bool = False,
    crosswalk_path: Path | None = None,
    settings: Settings | None = None,
    call_log: DailyProviderCallLog | None = None,
) -> EuroC3WatchResult:
    settings = settings or get_settings()
    conn = repo._conn
    conn.execute("PRAGMA busy_timeout = 60000")
    result = EuroC3WatchResult(dry_run=dry_run)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    log = call_log or DailyProviderCallLog(
        run_date=datetime.now(timezone.utc).date().isoformat(),
        quota=ProviderQuotaGuard(
            max_api_football=max_api_football_calls,
            max_sportmonks=max_sportmonks_calls,
            max_oddalerts=max_oddalerts_calls,
            no_provider_calls=dry_run,
        ),
    )
    log._log_path = Path("logs") / f"euro_c3_odds_watch_{stamp}.jsonl"
    result.log_path = str(log._log_path)

    crosswalk_map = load_crosswalk_map(crosswalk_path)
    previous_index = load_readiness_index()
    keys = list(competition_keys or UEFA_CUP_KEYS)
    fixtures = filter_uefa_target_fixtures(conn, competition_keys=keys, days_ahead=days_ahead)
    result.fixtures_scanned = len(fixtures)

    api = ApiFootballClient(settings)
    oa = OddAlertsClient()
    disk_cache = get_api_cache(settings.api_cache_dir, settings.api_cache_ttl_seconds)
    cached_sources = collect_cached_odds_sources(repo, disk_cache=disk_cache) if cache_first else {}

    status_counts_before = {"READY_FULL": 0, "READY_PARTIAL": 0}

    for sel in fixtures:
        fid = sel.provider_fixture_id
        comp = sel.competition_key
        cw = crosswalk_map.get(fid)
        entry = {
            "fixture_id": fid,
            "competition_key": comp,
            "home_team": sel.home_team,
            "away_team": sel.away_team,
            "kickoff_utc": sel.kickoff_utc,
        }

        before = assess_fixture_readiness(conn, fid, crosswalk=cw)
        entry["readiness_before"] = before["ecse_readiness_status"]
        if before["ecse_readiness_status"] in status_counts_before:
            status_counts_before[before["ecse_readiness_status"]] += 1

        provider_error = False
        provider_empty = False
        imported = False

        existing = _latest_odds_snapshot(conn, fid)
        if (
            existing
            and not is_fake_odds_payload(existing["payload"])
            and only_missing
            and not force
        ):
            norm = normalize_uefa_odds_snapshot(existing["payload"], fixture_id=fid)
            if _markets_complete(norm) and norm.btts:
                result.skipped_reasons["already_ready_full"] = (
                    result.skipped_reasons.get("already_ready_full", 0) + 1
                )
                after = assess_fixture_readiness(conn, fid, crosswalk=cw)
                entry.update(after)
                entry["import_action"] = "skip_already_complete"
                result.fixture_rows.append(entry)
                continue

        bookmakers: list[Any] = []
        provider = ""
        api_source = "none"
        raw_path: str | None = None

        if cache_first and fid in cached_sources:
            bookmakers = list(cached_sources[fid].get("bookmakers") or [])
            provider = "api-football"
            api_source = str(cached_sources[fid].get("source") or "cache")
            log.record(
                provider="api_football",
                endpoint="odds",
                action="cache_hit",
                fixture_id=fid,
                competition_key=comp,
                request_reason="cache_first",
                cache_hit=True,
                call_made=False,
                success=bool(bookmakers),
            )

        if not bookmakers and log.quota.can_call("api_football") and api.is_configured:
            if not dry_run:
                odds_result = api.get_odds(fid)
                live = odds_result.source == "live" and not odds_result.from_cache
                log.record(
                    provider="api_football",
                    endpoint="odds",
                    action="fetch_odds",
                    fixture_id=fid,
                    competition_key=comp,
                    request_reason="watch_missing_markets",
                    cache_hit=odds_result.from_cache,
                    call_made=live,
                    success=odds_result.ok,
                )
            else:
                log.record(
                    provider="api_football",
                    endpoint="odds",
                    action="fetch_odds",
                    fixture_id=fid,
                    competition_key=comp,
                    request_reason="watch_missing_markets",
                    call_made=False,
                    success=False,
                )
                odds_result = None
            if not dry_run:
                if odds_result.source == "placeholder" or is_fake_odds_payload(
                    odds_result.data, source=odds_result.source
                ):
                    provider_error = True
                elif not normalize_odds_bookmakers(odds_result.data):
                    if live or odds_result.from_cache:
                        provider_empty = True
                else:
                    bookmakers = normalize_odds_bookmakers(odds_result.data)
                    provider = "api-football"
                    api_source = odds_result.source
                    raw_path = str(RAW_DIR / f"{fid}_{stamp}_api-football.json")
                    Path(raw_path).write_text(
                        json.dumps(
                            {"fixture_id": fid, "fetched_at": _utc_now_iso(), "data": odds_result.data},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )

        if not bookmakers and log.quota.can_call("oddalerts") and oa.is_configured:
            log.record(
                provider="oddalerts",
                endpoint="odds/history",
                action="fetch_odds",
                fixture_id=fid,
                competition_key=comp,
                request_reason="api_football_empty",
                call_made=not dry_run,
                success=False,
            )
            if not dry_run:
                oa_res = fetch_oddalerts_odds_history(fid, conn=conn)
                result.provider_calls["oddalerts"] = result.provider_calls.get("oddalerts", 0) + oa_res.api_calls
                if oa_res.lines:
                    bookmakers = _oddalerts_lines_to_bookmakers(oa_res.lines)
                    provider = "oddalerts"
                    api_source = "oddalerts"
                    log.entries[-1]["success"] = True
                elif oa_res.errors:
                    provider_error = True
                else:
                    provider_empty = True

        if not bookmakers and cw and log.quota.can_call("sportmonks"):
            sm_id = int(cw.get("sportmonks_fixture_id") or 0)
            if sm_id > 0 and float(cw.get("combined_confidence") or 0) >= MIN_CROSSWALK_CONFIDENCE:
                fixture_data, sm_source, sm_raw = load_sportmonks_odds_payload(conn, sm_id, settings=settings)
                if fixture_data:
                    bookmakers = fixture_data_to_bookmakers(fixture_data)
                    provider = "sportmonks"
                    api_source = sm_source
                    raw_path = sm_raw
                    log.record(
                        provider="sportmonks",
                        endpoint="enrichment_cache",
                        action="cache_hit",
                        fixture_id=fid,
                        provider_fixture_id=sm_id,
                        competition_key=comp,
                        cache_hit=True,
                        call_made=False,
                        success=bool(bookmakers),
                    )
                elif not dry_run:
                    log.record(
                        provider="sportmonks",
                        endpoint=f"/fixtures/{sm_id}",
                        action="fetch_odds",
                        fixture_id=fid,
                        provider_fixture_id=sm_id,
                        competition_key=comp,
                        call_made=True,
                        success=False,
                    )
                    fixture_data, sm_source, sm_raw = fetch_sportmonks_odds_live(sm_id, settings=settings)
                    result.provider_calls["sportmonks"] = result.provider_calls.get("sportmonks", 0) + 1
                    log.entries[-1]["success"] = fixture_data is not None
                    if fixture_data:
                        bookmakers = fixture_data_to_bookmakers(fixture_data)
                        provider = "sportmonks"
                        api_source = sm_source
                        raw_path = sm_raw
                    else:
                        provider_empty = provider_empty or sm_source in {
                            "live_empty_odds",
                            "none",
                        }

        if bookmakers and not dry_run:
            normalized = normalize_uefa_odds_snapshot(bookmakers, fixture_id=fid, raw_odds_path=raw_path)
            if not _probabilities_valid(normalized):
                result.skipped_reasons["invalid_probabilities"] = (
                    result.skipped_reasons.get("invalid_probabilities", 0) + 1
                )
            elif existing and not force and _existing_is_newer_than(
                existing.get("snapshot_at"), _utc_now_iso()
            ):
                result.skipped_reasons["newer_snapshot_exists"] = (
                    result.skipped_reasons.get("newer_snapshot_exists", 0) + 1
                )
            else:
                payload = _build_watch_payload(
                    bookmakers=bookmakers,
                    normalized=normalized,
                    provider=provider,
                    fixture_id=fid,
                    api_source=api_source,
                    raw_path=raw_path,
                    sportmonks_fixture_id=int(cw["sportmonks_fixture_id"]) if cw else None,
                    crosswalk_confidence=float(cw["combined_confidence"]) if cw else None,
                )
                repo.save_snapshot(
                    "odds_snapshots",
                    fixture_id=fid,
                    competition_key=comp,
                    payload=payload,
                    snapshot_at=payload["snapshot_at"],
                )
                result.imported_count += 1
                imported = True
                entry["import_action"] = "imported"
        elif dry_run and bookmakers:
            entry["import_action"] = "would_import"
        elif not bookmakers:
            entry["import_action"] = "no_odds"

        after = assess_fixture_readiness(
            conn,
            fid,
            crosswalk=cw,
            provider_error=provider_error,
            provider_empty=provider_empty and not bookmakers,
        )
        after["next_recheck_priority"] = next_recheck_priority(
            sel.kickoff_utc,
            odds_missing=after["ecse_readiness_status"]
            not in ("READY_FULL", "READY_PARTIAL"),
        )
        after["missing_odds_reason"] = ", ".join(after.get("missing_required_markets") or [])
        entry.update(after)
        entry["imported_this_run"] = imported
        result.fixture_rows.append(entry)

        prev = previous_index.get(fid, {})
        prev_status = str(prev.get("ecse_readiness_status") or before["ecse_readiness_status"])
        new_status = after["ecse_readiness_status"]
        if new_status in ("READY_FULL", "READY_PARTIAL") and prev_status not in (
            "READY_FULL",
            "READY_PARTIAL",
        ):
            result.newly_ready_fixtures.append(
                {
                    "fixture_id": fid,
                    "competition_key": comp,
                    "home_team": sel.home_team,
                    "away_team": sel.away_team,
                    "kickoff_utc": sel.kickoff_utc,
                    "ecse_readiness_status": new_status,
                    "best_provider_source": after.get("best_provider_source"),
                }
            )

        comp_stats = result.markets_by_competition.setdefault(
            comp,
            {"1x2": 0, "ou25": 0, "btts": 0, "ready_full": 0, "ready_partial": 0},
        )
        if after.get("has_1x2"):
            comp_stats["1x2"] += 1
        if after.get("has_ou25"):
            comp_stats["ou25"] += 1
        if after.get("has_btts"):
            comp_stats["btts"] += 1
        if new_status == "READY_FULL":
            comp_stats["ready_full"] += 1
            result.ready_full_after += 1
        elif new_status == "READY_PARTIAL":
            comp_stats["ready_partial"] += 1
            result.ready_partial_after += 1
        elif new_status == "ODDS_PARTIAL_1X2_ONLY":
            result.odds_1x2_only_count += 1
        elif new_status == "ODDS_MISSING":
            result.odds_missing_count += 1
        elif new_status == "MAPPING_MISSING":
            result.mapping_missing_count += 1
        elif new_status == "PROVIDER_EMPTY":
            result.provider_empty_count += 1
        elif new_status == "PROVIDER_ERROR":
            result.provider_error_count += 1

    result.ready_full_before = status_counts_before["READY_FULL"]
    result.ready_partial_before = status_counts_before["READY_PARTIAL"]
    result.provider_calls = log.quota.to_dict()

    if log.entries:
        log.flush()

    return result


def append_readiness_jsonl(rows: list[dict[str, Any]], path: Path | None = None) -> Path:
    p = path or READINESS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_now_iso()
    with p.open("a", encoding="utf-8") as fh:
        for row in rows:
            out = {**row, "phase": PHASE, "recorded_at_utc": stamp}
            fh.write(json.dumps(out, ensure_ascii=False) + "\n")
    return p


def build_watch_summary(
    result: EuroC3WatchResult,
    *,
    final_recommendation: str,
) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now_iso(),
        "dry_run": result.dry_run,
        "fixtures_scanned": result.fixtures_scanned,
        "ready_full_before": result.ready_full_before,
        "ready_full_after": result.ready_full_after,
        "ready_partial_before": result.ready_partial_before,
        "ready_partial_after": result.ready_partial_after,
        "odds_1x2_only_count": result.odds_1x2_only_count,
        "odds_missing_count": result.odds_missing_count,
        "mapping_missing_count": result.mapping_missing_count,
        "provider_empty_count": result.provider_empty_count,
        "provider_error_count": result.provider_error_count,
        "newly_imported_odds_count": result.imported_count,
        "markets_coverage_by_competition": result.markets_by_competition,
        "newly_ready_fixtures": result.newly_ready_fixtures,
        "provider_calls": result.provider_calls,
        "skipped_reasons": result.skipped_reasons,
        "log_path": result.log_path,
        "final_recommendation": final_recommendation,
    }


def final_recommendation(result: EuroC3WatchResult) -> str:
    if result.ready_full_after > 0:
        return "UEFA_ECSE_READY_FIXTURES_FOUND"
    if result.ready_partial_after > 0:
        return "UEFA_ECSE_READY_FIXTURES_FOUND"
    if result.odds_1x2_only_count > 0 and result.provider_empty_count < result.fixtures_scanned:
        return "NEED_SPORTMONKS_MARKET_FIX"
    if result.mapping_missing_count > result.fixtures_scanned * 0.1:
        return "NEED_ODDALERTS_MAPPING"
    if result.provider_empty_count >= result.fixtures_scanned * 0.8:
        return "PROVIDERS_STILL_EMPTY"
    if result.dry_run:
        return "DO_NOT_RUN_ECSE_YET"
    return "CONTINUE_ODDS_WATCH"


def readiness_for_owner_report(fixture_id: int, path: Path | None = None) -> dict[str, Any] | None:
    row = load_readiness_index(path).get(int(fixture_id))
    if not row:
        return None
    return {
        "ecse_readiness_status": row.get("ecse_readiness_status"),
        "available_markets": row.get("available_markets") or [],
        "missing_odds_reason": row.get("missing_odds_reason")
        or ", ".join(row.get("missing_required_markets") or []),
        "next_recheck_priority": row.get("next_recheck_priority"),
        "best_provider_source": row.get("best_provider_source"),
        "odds_freshness": row.get("odds_freshness"),
        "wde_prediction_available": True,
    }

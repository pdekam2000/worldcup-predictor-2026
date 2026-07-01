"""PHASE EURO-C — UEFA odds scan/import for ECSE enablement (owner/internal only)."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.backtesting.phase31e_backfill import (
    collect_cached_odds_sources,
    normalize_odds_bookmakers,
)
from worldcup_predictor.cache.api_cache import ApiCache, get_api_cache
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.clients.api_response import ApiCallResult
from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import (
    NormalizedOddsLine,
    normalize_snapshot_odds_lines,
    parse_implied_1x2,
    parse_implied_btts,
    parse_implied_ou25,
    _implied_prob,
    _is_match_winner_market,
    _normalize_probs,
)
from worldcup_predictor.owner.euro_b_fixture_selector import (
    MIN_CROSSWALK_CONFIDENCE,
    UefaFixtureSelection,
    select_upcoming_uefa_fixtures,
)

PHASE = "EURO-C"
GENERATED_BY_WDE = "owner_euro_b"
FAKE_BOOKMAKER_MARKERS = frozenset({"sample bookmaker", "placeholder bookmaker"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _parse_snapshot_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S UTC", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(value.replace(" UTC", ""), fmt.replace(" UTC", "").replace("%z", ""))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def is_fake_odds_payload(payload: Any, *, source: str | None = None) -> bool:
    if source == "placeholder":
        return True
    if payload is None:
        return False
    if isinstance(payload, list) and len(payload) == 0:
        return False
    if isinstance(payload, dict) and not payload:
        return False
    text = json.dumps(payload, ensure_ascii=False).lower()
    if any(marker in text for marker in FAKE_BOOKMAKER_MARKERS):
        return True
    if isinstance(payload, dict):
        phase = str(payload.get("phase") or "")
        if phase.upper() == "PLACEHOLDER":
            return True
        if payload.get("is_placeholder") is True:
            return True
    return False


def _is_ou_line_market(name: str, selection: str, line: str) -> bool:
    if any(t in name.lower() for t in ("first half", "second half", "corner", "team total")):
        return False
    n = name.lower().strip()
    if "over/under" in n or "goals over" in n or n in {"totals", "total_goals"}:
        return line in selection.lower()
    return False


def _selection_key_ou(line: str, label: str) -> str | None:
    key = label.lower().strip()
    if key == f"over {line}":
        return f"over_{line.replace('.', '_')}"
    if key == f"under {line}":
        return f"under_{line.replace('.', '_')}"
    return None


def _aggregate_implied_custom(
    lines: list[NormalizedOddsLine],
    *,
    market_filter,
    selection_mapper,
    min_keys: int = 1,
) -> dict[str, float]:
    per_bm: dict[str, dict[str, float]] = {}
    for line in lines:
        if not market_filter(line.market_name, line.selection):
            continue
        key = selection_mapper(line.selection)
        if key is None:
            continue
        implied = _implied_prob(line.odd)
        if implied is None:
            continue
        per_bm.setdefault(line.bookmaker, {})[key] = implied
    rows = [_normalize_probs(v) for v in per_bm.values() if len(v) >= min_keys]
    if not rows and per_bm:
        rows = [_normalize_probs(v) for v in per_bm.values() if v]
    if not rows:
        return {}
    keys = tuple(rows[0].keys())
    totals = {k: 0.0 for k in keys}
    counts = {k: 0 for k in keys}
    for row in rows:
        for k in keys:
            if k in row:
                totals[k] += row[k]
                counts[k] += 1
    return _normalize_probs({k: totals[k] / counts[k] for k in keys if counts[k] > 0})


def parse_implied_ou15(lines: list[NormalizedOddsLine]) -> dict[str, float]:
    return _aggregate_implied_custom(
        lines,
        market_filter=lambda n, s: _is_ou_line_market(n, s, "1.5"),
        selection_mapper=lambda s: _selection_key_ou("1.5", s),
    )


def parse_implied_ou35(lines: list[NormalizedOddsLine]) -> dict[str, float]:
    return _aggregate_implied_custom(
        lines,
        market_filter=lambda n, s: _is_ou_line_market(n, s, "3.5"),
        selection_mapper=lambda s: _selection_key_ou("3.5", s),
    )


def _has_correct_score(lines: list[NormalizedOddsLine]) -> bool:
    for line in lines:
        if "correct score" in line.market_name.lower():
            return True
    return False


def _has_double_chance(lines: list[NormalizedOddsLine]) -> bool:
    for line in lines:
        if "double chance" in line.market_name.lower():
            return True
    return False


def _overround_1x2(raw_implied: dict[str, float]) -> float | None:
    keys = ("home", "draw", "away")
    vals = [raw_implied[k] for k in keys if k in raw_implied]
    if len(vals) < 2:
        return None
    total = sum(vals)
    return round(total, 6) if total > 0 else None


def _raw_implied_1x2(lines: list[NormalizedOddsLine]) -> dict[str, float]:
    per_bm: dict[str, dict[str, float]] = {}
    for line in lines:
        if not _is_match_winner_market(line.market_name):
            continue
        key = line.selection.lower().strip()
        if key not in {"home", "draw", "away"}:
            continue
        implied = _implied_prob(line.odd)
        if implied is None:
            continue
        per_bm.setdefault(line.bookmaker, {})[key] = implied
    if not per_bm:
        return {}
    # median bookmaker vector
    rows = list(per_bm.values())
    keys = ("home", "draw", "away")
    out: dict[str, float] = {}
    for k in keys:
        vals = [r[k] for r in rows if k in r]
        if vals:
            vals.sort()
            out[k] = vals[len(vals) // 2]
    return out


@dataclass
class NormalizedOddsSnapshot:
    bookmaker_count: int
    consensus_method: str
    overround_1x2: float | None
    match_winner: dict[str, float]
    over_under_2_5: dict[str, float]
    btts: dict[str, float]
    over_under_1_5: dict[str, float]
    over_under_3_5: dict[str, float]
    has_correct_score: bool
    has_double_chance: bool
    missing_markets: list[str]
    normalized_probabilities: dict[str, Any]
    raw_odds_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bookmaker_count": self.bookmaker_count,
            "consensus_method": self.consensus_method,
            "overround_1x2": self.overround_1x2,
            "match_winner": self.match_winner,
            "over_under_2_5": self.over_under_2_5,
            "btts": self.btts,
            "over_under_1_5": self.over_under_1_5,
            "over_under_3_5": self.over_under_3_5,
            "has_correct_score": self.has_correct_score,
            "has_double_chance": self.has_double_chance,
            "missing_markets": self.missing_markets,
            "normalized_probabilities": self.normalized_probabilities,
            "raw_odds_path": self.raw_odds_path,
        }


def normalize_uefa_odds_snapshot(
    payload: Any,
    *,
    fixture_id: int | None = None,
    captured_at: str | None = None,
    raw_odds_path: str | None = None,
) -> NormalizedOddsSnapshot:
    lines = normalize_snapshot_odds_lines(payload, fixture_id=fixture_id, captured_at=captured_at)
    bookmakers = {line.bookmaker for line in lines}
    x12 = parse_implied_1x2(lines)
    ou25 = parse_implied_ou25(lines)
    btts = parse_implied_btts(lines)
    ou15 = parse_implied_ou15(lines)
    ou35 = parse_implied_ou35(lines)
    raw_x12 = _raw_implied_1x2(lines)

    missing: list[str] = []
    if not x12:
        missing.append("match_winner")
    if not ou25:
        missing.append("over_under_2_5")
    if not btts:
        missing.append("btts")
    if not ou15:
        missing.append("over_under_1_5")
    if not ou35:
        missing.append("over_under_3_5")
    if not _has_correct_score(lines):
        missing.append("correct_score")
    if not _has_double_chance(lines):
        missing.append("double_chance")

    norm_probs = {
        "match_winner": x12,
        "over_under_2_5": ou25,
        "btts": btts,
        "over_under_1_5": ou15,
        "over_under_3_5": ou35,
    }

    return NormalizedOddsSnapshot(
        bookmaker_count=len(bookmakers),
        consensus_method="median_implied_across_bookmakers",
        overround_1x2=_overround_1x2(raw_x12),
        match_winner=x12,
        over_under_2_5=ou25,
        btts=btts,
        over_under_1_5=ou15,
        over_under_3_5=ou35,
        has_correct_score=_has_correct_score(lines),
        has_double_chance=_has_double_chance(lines),
        missing_markets=missing,
        normalized_probabilities=norm_probs,
        raw_odds_path=raw_odds_path,
    )


def _latest_odds_snapshot(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, snapshot_at, payload_json, competition_key
        FROM odds_snapshots
        WHERE fixture_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return {
        "id": int(row["id"]),
        "snapshot_at": row["snapshot_at"],
        "competition_key": row["competition_key"],
        "payload": payload,
    }


def assess_ecse_readiness(
    conn: sqlite3.Connection,
    fixture_id: int,
    *,
    normalized: NormalizedOddsSnapshot | None = None,
) -> dict[str, Any]:
    from worldcup_predictor.research.ecse_live.prediction_builder import build_odds_feature_row
    from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas

    snap = _latest_odds_snapshot(conn, fixture_id)
    if normalized is None and snap:
        normalized = normalize_uefa_odds_snapshot(snap["payload"], fixture_id=fixture_id)

    lambda_available = False
    odds_row = build_odds_feature_row(conn, fixture_id)
    if odds_row:
        lambda_available = extract_lambdas(odds_row) is not None

    has_1x2 = bool(normalized and normalized.match_winner)
    has_ou25 = bool(normalized and normalized.over_under_2_5)
    has_btts = bool(normalized and normalized.btts)

    # ECSE build_odds_feature_row requires 1X2 (home or away) + O/U 2.5; BTTS optional.
    ecse_ready = has_1x2 and has_ou25 and lambda_available
    ecse_partial = (has_1x2 or has_ou25) and not ecse_ready
    ecse_full_markets = has_1x2 and has_ou25 and has_btts

    blockers: list[str] = []
    if not has_1x2:
        blockers.append("missing_1x2")
    if not has_ou25:
        blockers.append("missing_ou25")
    if not lambda_available:
        blockers.append("missing_lambda_inputs")
    if not has_btts:
        blockers.append("missing_btts_optional")

    return {
        "fixture_id": fixture_id,
        "ecse_ready": ecse_ready,
        "ecse_partial": ecse_partial,
        "ecse_full_markets": ecse_full_markets,
        "has_1x2": has_1x2,
        "has_ou25": has_ou25,
        "has_btts": has_btts,
        "lambda_inputs_available": lambda_available,
        "blockers": blockers,
    }


def filter_uefa_target_fixtures(
    conn: sqlite3.Connection,
    *,
    competition_keys: list[str] | None = None,
    days_ahead: int = 30,
    require_owner_wde: bool = True,
) -> list[UefaFixtureSelection]:
    keys = competition_keys or list(UEFA_CUP_KEYS)
    selections = select_upcoming_uefa_fixtures(conn, competition_keys=keys, days_ahead=days_ahead)
    out: list[UefaFixtureSelection] = []
    for sel in selections:
        if sel.skip_reason:
            continue
        if sel.crosswalk_status == "sportmonks_only" and sel.crosswalk_confidence < MIN_CROSSWALK_CONFIDENCE:
            continue
        if sel.duplicate_risk:
            continue
        if require_owner_wde:
            has_wde = conn.execute(
                """
                SELECT 1 FROM worldcup_stored_predictions
                WHERE fixture_id = ? AND competition_key = ?
                  AND source = ?
                  AND (is_active IS NULL OR is_active = 1)
                LIMIT 1
                """,
                (sel.provider_fixture_id, sel.competition_key, GENERATED_BY_WDE),
            ).fetchone()
            if not has_wde:
                continue
        out.append(sel)
    return out


def scan_fixture_odds_availability(
    conn: sqlite3.Connection,
    selection: UefaFixtureSelection,
) -> dict[str, Any]:
    fid = selection.provider_fixture_id
    snap = _latest_odds_snapshot(conn, fid)
    payload = snap["payload"] if snap else None
    source = None
    snapshot_time = None
    if snap:
        snapshot_time = snap["snapshot_at"]
        if isinstance(payload, dict):
            source = str(payload.get("source") or payload.get("provider") or "odds_snapshots")
    if payload and is_fake_odds_payload(payload, source=source):
        payload = None
        source = None
        snapshot_time = None

    normalized = normalize_uefa_odds_snapshot(payload, fixture_id=fid) if payload else None
    readiness = assess_ecse_readiness(conn, fid, normalized=normalized)

    missing_markets = list(normalized.missing_markets) if normalized else [
        "match_winner",
        "over_under_2_5",
        "btts",
        "over_under_1_5",
        "over_under_3_5",
        "correct_score",
        "double_chance",
    ]

    return {
        "fixture_id": fid,
        "competition_key": selection.competition_key,
        "provider_fixture_id": fid,
        "kickoff_time": selection.kickoff_utc,
        "home_team": selection.home_team,
        "away_team": selection.away_team,
        "has_1x2": readiness["has_1x2"],
        "has_ou25": readiness["has_ou25"],
        "has_btts": readiness["has_btts"],
        "has_ou15": bool(normalized and normalized.over_under_1_5),
        "has_ou35": bool(normalized and normalized.over_under_3_5),
        "has_correct_score": bool(normalized and normalized.has_correct_score),
        "has_double_chance": bool(normalized and normalized.has_double_chance),
        "odds_source": source,
        "odds_snapshot_time": snapshot_time,
        "missing_markets": missing_markets,
        "ECSE_ready": readiness["ecse_ready"],
        "ECSE_partial": readiness["ecse_partial"],
        "lambda_inputs_available": readiness["lambda_inputs_available"],
    }


def scan_uefa_odds_availability(
    conn: sqlite3.Connection,
    *,
    competition_keys: list[str] | None = None,
    days_ahead: int = 30,
) -> dict[str, Any]:
    fixtures = filter_uefa_target_fixtures(
        conn, competition_keys=competition_keys, days_ahead=days_ahead
    )
    rows = [scan_fixture_odds_availability(conn, sel) for sel in fixtures]
    ecse_ready = sum(1 for r in rows if r["ECSE_ready"])
    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now_iso(),
        "fixtures_scanned": len(rows),
        "ecse_ready_count": ecse_ready,
        "ecse_partial_count": sum(1 for r in rows if r.get("ECSE_partial")),
        "fixtures": rows,
    }


@dataclass
class EuroCOddsImportResult:
    phase: str = PHASE
    dry_run: bool = False
    fixtures_scanned: int = 0
    fixtures_with_odds_before: int = 0
    fixtures_with_odds_after: int = 0
    imported_count: int = 0
    api_calls_used: int = 0
    cache_hits: int = 0
    skipped: list[dict[str, Any]] = field(default_factory=list)
    imported: list[dict[str, Any]] = field(default_factory=list)
    provider_errors: list[dict[str, Any]] = field(default_factory=list)
    markets_by_competition: dict[str, dict[str, int]] = field(default_factory=dict)
    ecse_ready_count: int = 0
    log_path: str | None = None


def _append_log(log_path: Path, entry: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _markets_complete(normalized: NormalizedOddsSnapshot, *, require_btts: bool = False) -> bool:
    ok = bool(normalized.match_winner and normalized.over_under_2_5)
    if require_btts:
        ok = ok and bool(normalized.btts)
    return ok


def _existing_is_newer_than(existing_at: str | None, incoming_at: str) -> bool:
    ex = _parse_snapshot_time(existing_at)
    inc = _parse_snapshot_time(incoming_at)
    if ex is None:
        return False
    if inc is None:
        return True
    return ex >= inc


def _build_storage_payload(
    *,
    bookmakers: list[Any],
    normalized: NormalizedOddsSnapshot,
    provider: str,
    provider_fixture_id: int,
    api_source: str,
    raw_path: str | None,
) -> dict[str, Any]:
    stamp = _utc_now_iso()
    return {
        "snapshot_at": stamp,
        "source": f"euro_c_{provider}_import",
        "provider": provider,
        "provider_fixture_id": provider_fixture_id,
        "phase": PHASE,
        "api_call_source": api_source,
        "bookmakers": bookmakers,
        "normalized": normalized.to_dict(),
        "raw_odds_path": raw_path,
    }


def _count_api_live(result: ApiCallResult) -> bool:
    return result.source == "live"


def import_uefa_odds(
    repo: FootballIntelligenceRepository,
    *,
    competition_keys: list[str] | None = None,
    days_ahead: int = 30,
    dry_run: bool = False,
    max_api_calls: int = 100,
    cache_first: bool = True,
    only_missing: bool = True,
    force: bool = False,
    settings: Settings | None = None,
    log_path: Path | None = None,
) -> EuroCOddsImportResult:
    settings = settings or get_settings()
    conn = repo._conn
    result = EuroCOddsImportResult(dry_run=dry_run)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = log_path or Path("logs") / f"euro_c_odds_import_{stamp}.jsonl"
    result.log_path = str(log_file)
    raw_dir = Path("artifacts/euro_c/raw_odds_payloads")
    raw_dir.mkdir(parents=True, exist_ok=True)

    api = ApiFootballClient(settings)
    disk_cache = get_api_cache(settings.api_cache_dir, settings.api_cache_ttl_seconds)
    cached_sources = collect_cached_odds_sources(repo, disk_cache=disk_cache) if cache_first else {}

    fixtures = filter_uefa_target_fixtures(
        conn, competition_keys=competition_keys, days_ahead=days_ahead
    )
    result.fixtures_scanned = len(fixtures)

    before_ready = 0
    for sel in fixtures:
        snap = _latest_odds_snapshot(conn, sel.provider_fixture_id)
        if snap and not is_fake_odds_payload(snap["payload"]):
            norm = normalize_uefa_odds_snapshot(snap["payload"], fixture_id=sel.provider_fixture_id)
            if _markets_complete(norm):
                result.fixtures_with_odds_before += 1
                if assess_ecse_readiness(conn, sel.provider_fixture_id, normalized=norm)["ecse_ready"]:
                    before_ready += 1

    api_calls = 0
    for sel in fixtures:
        fid = sel.provider_fixture_id
        comp = sel.competition_key
        entry_base = {
            "phase": PHASE,
            "fixture_id": fid,
            "competition_key": comp,
            "home_team": sel.home_team,
            "away_team": sel.away_team,
            "dry_run": dry_run,
        }

        existing = _latest_odds_snapshot(conn, fid)
        if existing and not is_fake_odds_payload(existing["payload"]):
            existing_norm = normalize_uefa_odds_snapshot(existing["payload"], fixture_id=fid)
            if only_missing and _markets_complete(existing_norm):
                result.skipped.append({**entry_base, "reason": "already_has_required_markets"})
                _append_log(log_file, {**entry_base, "action": "skip", "reason": "already_has_required_markets"})
                continue

        bookmakers: list[Any] = []
        provider = "api-football"
        api_source = "none"
        raw_path: str | None = None
        cache_ref: str | None = None
        cache_entry: dict[str, Any] | None = None

        if cache_first and fid in cached_sources:
            cache_entry = cached_sources[fid]
            bookmakers = list(cache_entry.get("bookmakers") or [])
            api_source = str(cache_entry.get("source") or "cache")
            cache_ref = str(cache_entry.get("endpoint") or "cache")
            result.cache_hits += 1
            _append_log(
                log_file,
                {**entry_base, "action": "cache_hit", "cache_source": api_source, "endpoint": cache_ref},
            )

        if existing and not is_fake_odds_payload(existing["payload"]) and bookmakers:
            incoming_at = str((cache_entry or {}).get("cached_at") or _utc_now_iso())
            if not force and _existing_is_newer_than(existing["snapshot_at"], incoming_at):
                result.skipped.append({**entry_base, "reason": "newer_snapshot_exists"})
                _append_log(log_file, {**entry_base, "action": "skip", "reason": "newer_snapshot_exists"})
                continue

        if not bookmakers and sel.crosswalk_status != "sportmonks_only":
            if api_calls >= max_api_calls:
                result.skipped.append({**entry_base, "reason": "max_api_calls_reached"})
                _append_log(log_file, {**entry_base, "action": "skip", "reason": "max_api_calls_reached"})
                continue
            if not api.is_configured:
                result.skipped.append({**entry_base, "reason": "api_football_not_configured"})
                result.provider_errors.append({**entry_base, "error": "api_football_not_configured"})
                _append_log(log_file, {**entry_base, "action": "skip", "reason": "api_football_not_configured"})
                continue

            odds_result = api.get_odds(fid)
            _append_log(
                log_file,
                {
                    **entry_base,
                    "action": "api_call",
                    "endpoint": "odds",
                    "source": odds_result.source,
                    "ok": odds_result.ok,
                    "error": odds_result.error,
                    "from_cache": odds_result.from_cache,
                    "response_count": odds_result.response_count,
                },
            )
            bookmakers = normalize_odds_bookmakers(odds_result.data)
            if (
                not bookmakers
                and odds_result.from_cache
                and api_calls < max_api_calls
            ):
                odds_result = api.get_odds(fid, force_refresh=True)
                _append_log(
                    log_file,
                    {
                        **entry_base,
                        "action": "api_call_force_refresh",
                        "endpoint": "odds",
                        "source": odds_result.source,
                        "ok": odds_result.ok,
                        "error": odds_result.error,
                        "from_cache": odds_result.from_cache,
                        "response_count": odds_result.response_count,
                    },
                )
                bookmakers = normalize_odds_bookmakers(odds_result.data)

            if _count_api_live(odds_result):
                api_calls += 1
                result.api_calls_used = api_calls

            if odds_result.source == "placeholder" or is_fake_odds_payload(
                odds_result.data, source=odds_result.source
            ):
                result.skipped.append({**entry_base, "reason": "provider_no_odds_or_placeholder"})
                result.provider_errors.append(
                    {**entry_base, "error": odds_result.error or "placeholder_odds"}
                )
                continue

            if not bookmakers:
                result.skipped.append({**entry_base, "reason": "provider_no_odds_available"})
                result.provider_errors.append({**entry_base, "error": "empty_odds_response"})
                _append_log(log_file, {**entry_base, "action": "skip", "reason": "provider_no_odds_available"})
                continue

            api_source = odds_result.source
            if bookmakers:
                raw_path = str(raw_dir / f"{fid}_{stamp}.json")
                if not dry_run:
                    raw_path_obj = Path(raw_path)
                    raw_path_obj.write_text(
                        json.dumps(
                            {
                                "fixture_id": fid,
                                "fetched_at": _utc_now_iso(),
                                "api_source": api_source,
                                "data": odds_result.data,
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )

        if not bookmakers:
            if sel.crosswalk_status == "sportmonks_only" and sel.crosswalk_confidence >= MIN_CROSSWALK_CONFIDENCE:
                result.skipped.append({**entry_base, "reason": "need_sportmonks_odds_crosswalk"})
            else:
                result.skipped.append({**entry_base, "reason": "no_odds_available"})
            _append_log(log_file, {**entry_base, "action": "skip", "reason": result.skipped[-1]["reason"]})
            continue

        normalized = normalize_uefa_odds_snapshot(bookmakers, fixture_id=fid, raw_odds_path=raw_path)
        if not normalized.match_winner and not normalized.over_under_2_5:
            result.skipped.append({**entry_base, "reason": "unparseable_odds_payload"})
            _append_log(log_file, {**entry_base, "action": "skip", "reason": "unparseable_odds_payload"})
            continue

        # Validate probabilities
        invalid = False
        for market_name, probs in normalized.normalized_probabilities.items():
            if not isinstance(probs, dict):
                continue
            for k, v in probs.items():
                if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v) or v < 0 or v > 1)):
                    invalid = True
        if invalid:
            result.skipped.append({**entry_base, "reason": "invalid_implied_probabilities"})
            continue

        payload = _build_storage_payload(
            bookmakers=bookmakers,
            normalized=normalized,
            provider=provider,
            provider_fixture_id=fid,
            api_source=api_source,
            raw_path=raw_path,
        )

        if dry_run:
            result.imported.append(
                {
                    **entry_base,
                    "action": "would_import",
                    "markets": {
                        "1x2": bool(normalized.match_winner),
                        "ou25": bool(normalized.over_under_2_5),
                        "btts": bool(normalized.btts),
                    },
                    "bookmaker_count": normalized.bookmaker_count,
                    "overround_1x2": normalized.overround_1x2,
                }
            )
            _append_log(log_file, {**entry_base, "action": "dry_run_import"})
            continue

        repo.save_snapshot(
            "odds_snapshots",
            fixture_id=fid,
            competition_key=comp,
            payload=payload,
            snapshot_at=payload["snapshot_at"],
        )
        result.imported_count += 1
        result.imported.append(
            {
                **entry_base,
                "action": "imported",
                "snapshot_at": payload["snapshot_at"],
                "bookmaker_count": normalized.bookmaker_count,
                "overround_1x2": normalized.overround_1x2,
                "missing_markets": normalized.missing_markets,
            }
        )
        _append_log(log_file, {**entry_base, "action": "imported", "snapshot_at": payload["snapshot_at"]})

    # After stats
    markets_by_comp: dict[str, dict[str, int]] = {}
    after_with_odds = 0
    ecse_ready = 0
    for sel in fixtures:
        comp = sel.competition_key
        markets_by_comp.setdefault(
            comp,
            {"1x2": 0, "ou25": 0, "btts": 0, "ou15": 0, "ou35": 0, "correct_score": 0, "ecse_ready": 0},
        )
        snap = _latest_odds_snapshot(conn, sel.provider_fixture_id)
        if not snap or is_fake_odds_payload(snap["payload"]):
            continue
        norm = normalize_uefa_odds_snapshot(snap["payload"], fixture_id=sel.provider_fixture_id)
        if norm.match_winner or norm.over_under_2_5:
            after_with_odds += 1
        if norm.match_winner:
            markets_by_comp[comp]["1x2"] += 1
        if norm.over_under_2_5:
            markets_by_comp[comp]["ou25"] += 1
        if norm.btts:
            markets_by_comp[comp]["btts"] += 1
        if norm.over_under_1_5:
            markets_by_comp[comp]["ou15"] += 1
        if norm.over_under_3_5:
            markets_by_comp[comp]["ou35"] += 1
        if norm.has_correct_score:
            markets_by_comp[comp]["correct_score"] += 1
        readiness = assess_ecse_readiness(conn, sel.provider_fixture_id, normalized=norm)
        if readiness["ecse_ready"]:
            markets_by_comp[comp]["ecse_ready"] += 1
            ecse_ready += 1

    result.fixtures_with_odds_after = after_with_odds
    result.markets_by_competition = markets_by_comp
    result.ecse_ready_count = ecse_ready
    return result


def build_import_summary(
    scan: dict[str, Any],
    import_result: EuroCOddsImportResult,
) -> dict[str, Any]:
    skip_reasons: dict[str, int] = {}
    for item in import_result.skipped:
        reason = str(item.get("reason") or "unknown")
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    blockers: list[str] = []
    if import_result.ecse_ready_count == 0:
        blockers.append("no_ecse_ready_fixtures")
    if import_result.api_calls_used >= import_result.fixtures_scanned:
        blockers.append("api_quota_pressure")
    if skip_reasons.get("provider_no_odds_available", 0) > 0:
        blockers.append("provider_missing_odds")
    if skip_reasons.get("provider_no_odds_or_placeholder", 0) > 0:
        blockers.append("provider_missing_odds")
    if skip_reasons.get("need_sportmonks_odds_crosswalk", 0) > 0:
        blockers.append("sportmonks_crosswalk_needed")

    recommendation = _final_recommendation(scan, import_result, skip_reasons)

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now_iso(),
        "fixtures_scanned": import_result.fixtures_scanned,
        "fixtures_with_odds_before": import_result.fixtures_with_odds_before,
        "fixtures_with_odds_after": import_result.fixtures_with_odds_after,
        "imported_odds_count": import_result.imported_count,
        "markets_coverage_by_competition": import_result.markets_by_competition,
        "ecse_ready_count": import_result.ecse_ready_count,
        "ecse_ready_before": scan.get("ecse_ready_count", 0),
        "api_calls_used": import_result.api_calls_used,
        "cache_hits": import_result.cache_hits,
        "dry_run": import_result.dry_run,
        "provider_errors": import_result.provider_errors,
        "skipped_reasons": skip_reasons,
        "remaining_blockers": blockers,
        "log_path": import_result.log_path,
        "final_recommendation": recommendation,
    }


def _final_recommendation(
    scan: dict[str, Any],
    import_result: EuroCOddsImportResult,
    skip_reasons: dict[str, int],
) -> str:
    ready = import_result.ecse_ready_count
    scanned = max(1, import_result.fixtures_scanned)
    ready_ratio = ready / scanned

    if ready > 0 and ready_ratio >= 0.8:
        return "UEFA_ODDS_READY_FOR_ECSE"
    if ready > 0:
        return "PARTIAL_ODDS_READY"
    if skip_reasons.get("need_sportmonks_odds_crosswalk", 0) > 0:
        return "NEED_SPORTMONKS_ODDS_CROSSWALK"
    if skip_reasons.get("unparseable_odds_payload", 0) > 0:
        return "NEED_ODDS_SCHEMA_FIX"
    if skip_reasons.get("provider_no_odds_available", 0) >= scanned * 0.5:
        return "PROVIDER_NO_ODDS_AVAILABLE"
    if skip_reasons.get("provider_no_odds_or_placeholder", 0) >= scanned * 0.5:
        return "PROVIDER_NO_ODDS_AVAILABLE"
    if import_result.dry_run:
        return "DO_NOT_RUN_ECSE_YET"
    return "DO_NOT_RUN_ECSE_YET"

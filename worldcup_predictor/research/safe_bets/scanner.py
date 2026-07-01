"""PHASE SAFE-BETS-1 — High probability market scanner."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.config.competitions import get_competition, list_competition_keys
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.research.ecse_live.fixture_resolver import resolve_sportmonks_fixture
from worldcup_predictor.research.ecse_live.fixture_resolver import ResolvedFixture
from worldcup_predictor.research.safe_bets.markets import classify_market, normalize_market_label, normalize_selection
from worldcup_predictor.research.safe_bets.providers import collect_all_odds_lines
from worldcup_predictor.research.safe_bets.scoring import score_candidate
from worldcup_predictor.research.safe_bets.store import (
    candidate_key,
    ensure_safe_bets_tables,
    finish_scan_run,
    insert_candidate,
    start_scan_run,
)

PHASE = "SAFE-BETS-1"
UPCOMING_STATUSES = frozenset({"NS", "TBD", "SCHEDULED", "NOT STARTED", "TIMED"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def discover_ecse_snapshot_fixtures(conn: sqlite3.Connection, *, hours: int) -> list[dict[str, Any]]:
    """Supplemental fixture list from frozen ECSE live snapshots."""
    now = _utc_now()
    cutoff = now + timedelta(hours=hours)
    rows: list[dict[str, Any]] = []
    try:
        cur = conn.execute(
            """
            SELECT fixture_id, home_team, away_team, kickoff_utc, competition_key
            FROM ecse_prediction_snapshots
            ORDER BY id DESC
            """
        )
    except sqlite3.OperationalError:
        return rows
    for row in cur.fetchall():
        kickoff = _parse_kickoff(row["kickoff_utc"])
        if kickoff is None or kickoff > cutoff:
            continue
        rows.append(
            {
                "fixture_id": int(row["fixture_id"]),
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "kickoff_utc": row["kickoff_utc"],
                "competition_key": row["competition_key"] or "world_cup_2026",
                "status": "NS",
            }
        )
    return rows


def discover_fixtures_in_window(
    settings: Settings,
    *,
    hours: int,
    limit_per_competition: int = 80,
) -> list[dict[str, Any]]:
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    now = _utc_now()
    cutoff = now + timedelta(hours=hours)
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()

    for comp_key in list_competition_keys(enabled_only=True):
        try:
            comp = get_competition(comp_key)
        except KeyError:
            continue
        if not comp.enabled:
            continue
        for row in repo.list_upcoming_fixtures(comp_key, season=comp.season, limit=limit_per_competition):
            fid = int(row["fixture_id"])
            if fid in seen:
                continue
            kickoff = _parse_kickoff(row.get("kickoff_utc"))
            if kickoff is None or kickoff > cutoff:
                continue
            seen.add(fid)
            item = dict(row)
            item["competition_key"] = comp_key
            rows.append(item)

    if not rows:
        from worldcup_predictor.clients.api_football import ApiFootballClient

        client = ApiFootballClient(settings)
        if client.is_configured:
            comp = get_competition("world_cup_2026")
            coll = client.fetch_upcoming_fixtures(comp, limit=50)
            for fx in coll.fixtures:
                kickoff = fx.kickoff_utc
                if kickoff and kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=timezone.utc)
                if kickoff and kickoff <= cutoff:
                    fid = int(fx.id)
                    if fid not in seen:
                        seen.add(fid)
                        rows.append(
                            {
                                "fixture_id": fid,
                                "home_team": fx.home_team,
                                "away_team": fx.away_team,
                                "kickoff_utc": kickoff.isoformat(),
                                "status": fx.status,
                                "competition_key": comp.key,
                            }
                        )
    return sorted(rows, key=lambda r: str(r.get("kickoff_utc") or ""))


@dataclass
class ScanResult:
    scan_batch_id: str
    fixtures_scanned: int = 0
    candidates_stored: int = 0
    duplicates_skipped: int = 0
    traps_flagged: int = 0
    meaningful_85_plus: int = 0
    api_calls: int = 0
    errors: list[str] = field(default_factory=list)
    top_meaningful: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": PHASE,
            "status": "ok",
            "scan_batch_id": self.scan_batch_id,
            "fixtures_scanned": self.fixtures_scanned,
            "candidates_stored": self.candidates_stored,
            "duplicates_skipped": self.duplicates_skipped,
            "traps_flagged": self.traps_flagged,
            "meaningful_85_plus": self.meaningful_85_plus,
            "api_calls": self.api_calls,
            "errors": self.errors[:20],
            "top_meaningful": self.top_meaningful[:25],
        }


def _scan_fixture(
    conn: sqlite3.Connection,
    fx: dict[str, Any],
    *,
    settings: Settings,
    scan_batch_id: str,
    result: ScanResult,
) -> None:
    fid = int(fx["fixture_id"])
    home = str(fx.get("home_team") or "")
    away = str(fx.get("away_team") or "")
    match_name = f"{home} vs {away}"

    resolved = ResolvedFixture(
        home_team=home,
        away_team=away,
        fixture_id=fid,
        kickoff_utc=str(fx.get("kickoff_utc") or ""),
        competition_key=str(fx.get("competition_key") or "world_cup_2026"),
    )
    try:
        resolve_sportmonks_fixture(resolved, settings=settings)
    except Exception:
        pass

    lines, api_calls = collect_all_odds_lines(
        conn,
        fid,
        settings=settings,
        scan_batch_id=scan_batch_id,
        oddalerts_fixture_id=resolved.oddalerts_fixture_id,
        use_live_api=not settings.safe_bets_dry_run,
    )
    result.api_calls += api_calls

    seen_keys: set[str] = set()
    batch_candidates: list[dict[str, Any]] = []

    for line in lines:
        market_type = classify_market(line.market_name, line.selection)
        if market_type is None:
            continue
        market_label = normalize_market_label(line.market_name, market_type)
        sel_norm = normalize_selection(line.selection)
        dedupe = f"{line.provider}|{line.bookmaker}|{market_label}|{sel_norm}"
        if dedupe in seen_keys:
            continue
        seen_keys.add(dedupe)

        scored = score_candidate(
            odds=line.odd,
            market_type=market_type,
            market_name=line.market_name,
            selection=line.selection,
            data_quality=line.data_quality,
            allow_trivial=settings.safe_bets_allow_trivial,
        )
        if scored is None:
            continue

        payload = {
            "scan_batch_id": scan_batch_id,
            "fixture_id": fid,
            "match_name": match_name,
            "kickoff_utc": fx.get("kickoff_utc"),
            "market": market_label,
            "market_type": market_type,
            "selection": line.selection,
            "odds": line.odd,
            "provider": line.provider,
            "bookmaker": line.bookmaker,
            "data_quality": line.data_quality,
            **scored,
        }
        payload["candidate_key"] = candidate_key(
            fixture_id=fid,
            provider=line.provider,
            bookmaker=line.bookmaker or "unknown",
            market=market_label,
            selection=sel_norm,
        )
        batch_candidates.append(payload)

    for payload in batch_candidates:
        if settings.safe_bets_dry_run:
            continue
        ok, reason = insert_candidate(conn, payload)
        if ok:
            result.candidates_stored += 1
            if payload.get("trap_flag"):
                result.traps_flagged += 1
            elif float(payload.get("devigged_probability") or 0) >= 0.85:
                result.meaningful_85_plus += 1
                if payload["usefulness_score"] >= 70:
                    result.top_meaningful.append(
                        {
                            "match": match_name,
                            "market": payload["market"],
                            "selection": payload["selection"],
                            "odds": payload["odds"],
                            "bucket": payload["probability_bucket"],
                            "usefulness": payload["usefulness_score"],
                        }
                    )
        elif reason == "duplicate":
            result.duplicates_skipped += 1

    if not settings.safe_bets_dry_run:
        conn.commit()


def run_safe_bets_scan(
    conn: sqlite3.Connection,
    *,
    settings: Settings | None = None,
    hours: int = 72,
    limit: int = 100,
) -> ScanResult:
    settings = settings or get_settings()
    ensure_safe_bets_tables(conn)
    scan_batch_id = _utc_now().strftime("SAFE-BETS-%Y%m%d-%H%M%S")
    result = ScanResult(scan_batch_id=scan_batch_id)

    if not settings.safe_bets_dry_run:
        start_scan_run(conn, scan_batch_id, hours_window=hours)

    fixtures = discover_fixtures_in_window(settings, hours=hours)[:limit]
    ecse_extra = discover_ecse_snapshot_fixtures(conn, hours=hours)
    seen_ids = {int(f["fixture_id"]) for f in fixtures}
    for fx in ecse_extra:
        fid = int(fx["fixture_id"])
        if fid not in seen_ids:
            fixtures.append(fx)
            seen_ids.add(fid)
    fixtures = fixtures[:limit]
    result.fixtures_scanned = len(fixtures)

    for fx in fixtures:
        if result.api_calls >= settings.safe_bets_max_api_calls:
            result.errors.append("max_api_calls_reached")
            break
        try:
            _scan_fixture(conn, fx, settings=settings, scan_batch_id=scan_batch_id, result=result)
        except Exception as exc:
            result.errors.append(f"fixture_{fx.get('fixture_id')}: {exc}")

    result.top_meaningful.sort(key=lambda x: -float(x.get("usefulness") or 0))

    if not settings.safe_bets_dry_run:
        finish_scan_run(conn, scan_batch_id, result.to_dict())
        conn.commit()

    return result

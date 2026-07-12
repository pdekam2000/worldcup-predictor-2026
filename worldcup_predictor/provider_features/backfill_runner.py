"""Pilot prematch feature backfill — cache-first, capped, no DB txn during network."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.process_lock import ProcessLockError, single_instance_lock
from worldcup_predictor.provider_features.coverage import measure_coverage
from worldcup_predictor.provider_features.mapping import pilot_competitions, tier_for_key
from worldcup_predictor.provider_features.repository import ensure_tables, insert_snapshot, update_checkpoint
from worldcup_predictor.provider_features.snapshot_builder import (
    from_api_football_injuries,
    from_api_football_lineups,
    from_stored_enrichment_lineup,
)
from worldcup_predictor.provider_features.timestamp_policy import utc_now_iso
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

PHASE = "PREMATCH-PILOT-BACKFILL"
MAX_API_CALLS = 50
MAX_SPORTMONKS_CALLS = 50
FIXTURES_PER_COMPETITION = 15


def _parse_ko(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        from datetime import timezone as tz

        dt = dt.replace(tzinfo=tz.utc)
    return dt.astimezone(timezone.utc)


def _select_pilot_fixtures(conn: sqlite3.Connection, competition_key: str, limit: int) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT f.fixture_id, f.competition_key, f.kickoff_utc, f.status, f.home_team, f.away_team
        FROM fixtures f
        WHERE f.competition_key = ?
        ORDER BY
          CASE WHEN f.status IN ('NS','TBD','SCHEDULED','TIMED') THEN 0 ELSE 1 END,
          f.kickoff_utc DESC
        LIMIT ?
        """,
        (competition_key, limit),
    ).fetchall()
    return list(rows)


def _enrichment_row(conn: sqlite3.Connection, fixture_id: int) -> sqlite3.Row | None:
    try:
        return conn.execute(
            "SELECT lineups_json, updated_at FROM fixture_enrichment WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None


def run_pilot_backfill(
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    max_api_calls: int = MAX_API_CALLS,
    max_sportmonks_calls: int = MAX_SPORTMONKS_CALLS,
) -> dict[str, Any]:
    settings = settings or get_settings()
    report: dict[str, Any] = {
        "phase": PHASE,
        "started_at_utc": utc_now_iso(),
        "dry_run": dry_run,
        "api_calls_used": 0,
        "sportmonks_calls_used": 0,
        "fixtures_targeted": 0,
        "snapshots_inserted": 0,
        "snapshots_duplicate": 0,
        "snapshots_rejected": 0,
        "empty_lineups": 0,
        "empty_injuries": 0,
        "enrichment_rejected": 0,
        "errors": [],
    }

    try:
        with single_instance_lock("prematch-feature-pilot-backfill", blocking=False):
            conn = connect(settings.sqlite_path)
            ensure_tables(conn)
            coverage_before = measure_coverage(conn)

            api = ApiFootballClient(settings) if settings.api_football_configured and not dry_run else None
            sm = SportmonksProvider(settings) if settings.sportmonks_configured and not dry_run else None

            for comp in pilot_competitions():
                key = comp["canonical_key"]
                tier = comp.get("tier")
                rows = _select_pilot_fixtures(conn, key, FIXTURES_PER_COMPETITION)
                report["fixtures_targeted"] += len(rows)

                for row in rows:
                    fid = int(row["fixture_id"])
                    kickoff = str(row["kickoff_utc"] or "")
                    now = datetime.now(timezone.utc)
                    ko = _parse_ko(kickoff)
                    is_upcoming = ko is not None and ko > now

                    # 1) Stored enrichment for completed (no API)
                    if not is_upcoming:
                        enr = _enrichment_row(conn, fid)
                        if enr and enr["lineups_json"]:
                            snap = from_stored_enrichment_lineup(
                                fixture_id=fid,
                                competition_key=key,
                                tier=tier,
                                kickoff_utc=kickoff,
                                lineups_json=str(enr["lineups_json"]),
                                enrichment_updated_at=str(enr["updated_at"] or utc_now_iso()),
                            )
                            if snap:
                                result = insert_snapshot(conn, snap, allow_future=False)
                                if result == "inserted":
                                    report["snapshots_inserted"] += 1
                                elif result == "duplicate":
                                    report["snapshots_duplicate"] += 1
                                else:
                                    report["snapshots_rejected"] += 1
                                    report["enrichment_rejected"] += 1

                    if dry_run or not api:
                        continue

                    if not is_upcoming:
                        continue

                    if report["api_calls_used"] >= max_api_calls:
                        break

                    # Injuries first (often available before lineups)
                    league_id = comp.get("provider_league_id") or 1
                    ir = api.get_injuries(fixture_id=fid, league_id=int(league_id), season=2026)
                    if ir.source == "live":
                        report["api_calls_used"] += 1
                    fetched = utc_now_iso()
                    snap_inj = from_api_football_injuries(
                        fixture_id=fid,
                        competition_key=key,
                        tier=tier,
                        kickoff_utc=kickoff,
                        injuries_data=ir.data,
                        fetched_at_utc=fetched,
                        feature_available_at_utc=fetched,
                        is_upcoming=True,
                    )
                    if snap_inj:
                        result = insert_snapshot(conn, snap_inj)
                        if result == "inserted":
                            report["snapshots_inserted"] += 1
                        elif result == "duplicate":
                            report["snapshots_duplicate"] += 1
                        else:
                            report["snapshots_rejected"] += 1
                    else:
                        report["empty_injuries"] += 1

                    if report["api_calls_used"] >= max_api_calls:
                        continue

                    lr = api.get_fixture_lineups(fid)
                    if lr.source == "live":
                        report["api_calls_used"] += 1
                    snap_line = from_api_football_lineups(
                        fixture_id=fid,
                        competition_key=key,
                        tier=tier,
                        kickoff_utc=kickoff,
                        lineups_data=lr.data,
                        fetched_at_utc=fetched,
                        feature_available_at_utc=fetched,
                        is_upcoming=True,
                    )
                    if snap_line:
                        result = insert_snapshot(conn, snap_line)
                        if result == "inserted":
                            report["snapshots_inserted"] += 1
                        elif result == "duplicate":
                            report["snapshots_duplicate"] += 1
                        else:
                            report["snapshots_rejected"] += 1
                    else:
                        report["empty_lineups"] += 1
                    if key == "world_cup_2026" and sm and sm.is_configured and is_upcoming:
                        if report["sportmonks_calls_used"] >= max_sportmonks_calls:
                            continue
                        map_row = conn.execute(
                            "SELECT sportmonks_fixture_id FROM wc_fixture_mapping WHERE api_football_fixture_id = ? LIMIT 1",
                            (fid,),
                        ).fetchone()
                        if map_row:
                            sm_id = int(map_row[0])
                            status, payload, err = sm.safe_get(
                                f"/fixtures/{sm_id}",
                                params={"include": "xGFixture"},
                            )
                            report["sportmonks_calls_used"] += 1
                            if status == 200 and payload:
                                from worldcup_predictor.provider_features.snapshot_builder import (
                                    from_sportmonks_xg_fixture,
                                )

                                snap = from_sportmonks_xg_fixture(
                                    fixture_id=fid,
                                    competition_key=key,
                                    sportmonks_fixture_id=sm_id,
                                    kickoff_utc=kickoff,
                                    xg_payload=(payload.get("data") if isinstance(payload, dict) else payload),
                                    fetched_at_utc=utc_now_iso(),
                                    is_upcoming=True,
                                )
                                if snap:
                                    result = insert_snapshot(conn, snap)
                                    if result == "inserted":
                                        report["snapshots_inserted"] += 1
                                    elif result == "duplicate":
                                        report["snapshots_duplicate"] += 1
                                    else:
                                        report["snapshots_rejected"] += 1

            update_checkpoint(
                conn,
                phase=PHASE,
                last_fixture_id=None,
                api_calls=report["api_calls_used"],
                sportmonks_calls=report["sportmonks_calls_used"],
            )
            report["coverage_before"] = coverage_before
            report["coverage_after"] = measure_coverage(conn)
            conn.close()

    except ProcessLockError:
        report["status"] = "skipped_overlap"
        return report

    report["status"] = "ok"
    report["finished_at_utc"] = utc_now_iso()
    return report

"""Cache-first Correct Score odds ingestion from odds_snapshots (+ optional live)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.correct_score_odds.ddl import ensure_correct_score_odds_schema
from worldcup_predictor.research.correct_score_odds.parser import parse_payload_cs_lines
from worldcup_predictor.research.correct_score_odds.store import finish_run, insert_lines, start_run


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _kickoff_for(conn, fixture_id: int) -> str | None:
    row = conn.execute(
        "SELECT kickoff_utc FROM fixtures WHERE fixture_id = ?",
        (fixture_id,),
    ).fetchone()
    if row and row["kickoff_utc"]:
        return str(row["kickoff_utc"])
    # registry fallback
    try:
        row = conn.execute(
            """
            SELECT kickoff_utc FROM historical_fixture_registry
            WHERE internal_fixture_id = ? OR registry_fixture_id = ?
            LIMIT 1
            """,
            (fixture_id, fixture_id),
        ).fetchone()
        if row and row["kickoff_utc"]:
            return str(row["kickoff_utc"])
    except Exception:
        pass
    return None


def ingest_from_odds_snapshots(
    conn,
    *,
    max_snapshots: int | None = None,
    fixture_ids: list[int] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Extract CS lines from existing odds_snapshots (no API calls).
    Does not overwrite snapshots. Append-only into correct_score_odds_lines.
    """
    ensure_correct_score_odds_schema(conn)
    run_id = run_id or f"cs_snap_{uuid.uuid4().hex[:12]}"
    started = _utc_now()
    start_run(conn, run_id, "cache_snapshots", started)

    q = "SELECT id, fixture_id, snapshot_at, payload_json FROM odds_snapshots"
    params: list[Any] = []
    if fixture_ids:
        placeholders = ",".join("?" * len(fixture_ids))
        q += f" WHERE fixture_id IN ({placeholders})"
        params.extend(int(x) for x in fixture_ids)
    q += " ORDER BY id ASC"
    if max_snapshots:
        q += f" LIMIT {int(max_snapshots)}"

    rows = conn.execute(q, params).fetchall()
    fixtures_seen: set[int] = set()
    inserted_total = 0
    rejected_total = 0
    deduped_total = 0
    rejected_samples: list[dict] = []
    accepted_count = 0

    kickoff_cache: dict[int, str | None] = {}

    for r in rows:
        fid = int(r["fixture_id"])
        fixtures_seen.add(fid)
        if fid not in kickoff_cache:
            kickoff_cache[fid] = _kickoff_for(conn, fid)
        try:
            payload = json.loads(r["payload_json"])
        except Exception:
            rejected_total += 1
            rejected_samples.append({"fixture_id": fid, "reason": "bad_json", "snapshot_id": r["id"]})
            continue
        if not isinstance(payload, dict):
            continue
        accepted, rejected = parse_payload_cs_lines(
            payload,
            fixture_id=fid,
            snapshot_id=int(r["id"]),
            snapshot_at=str(r["snapshot_at"]) if r["snapshot_at"] else None,
            kickoff_utc=kickoff_cache[fid],
            ingestion_run_id=run_id,
        )
        # mark completeness later; batch insert
        if accepted:
            # mark is_complete_market if >= 15 exact scores for bookmaker in this batch
            by_bm: dict[str, int] = {}
            for a in accepted:
                if a["market"] == "CORRECT_SCORE_90_MINUTES":
                    by_bm[a["bookmaker_name"]] = by_bm.get(a["bookmaker_name"], 0) + 1
            for a in accepted:
                if by_bm.get(a["bookmaker_name"], 0) >= 15:
                    a["is_complete_market"] = 1
            ins, ded = insert_lines(conn, accepted)
            inserted_total += ins
            deduped_total += ded
            accepted_count += len(accepted)
        rejected_total += len(rejected)
        if len(rejected_samples) < 500:
            rejected_samples.extend(rejected[:20])

    # update completeness flags per fixture/bookmaker
    _refresh_completeness(conn)

    status = "ok" if inserted_total or accepted_count else "no_cs_lines"
    finish_run(
        conn,
        run_id,
        finished=_utc_now(),
        fixtures_scanned=len(fixtures_seen),
        lines_inserted=inserted_total,
        lines_rejected=rejected_total,
        lines_deduped=deduped_total,
        status=status,
        notes={"accepted_parsed": accepted_count, "snapshots": len(rows)},
    )
    return {
        "ingestion_run_id": run_id,
        "mode": "cache_snapshots",
        "snapshots_scanned": len(rows),
        "fixtures_scanned": len(fixtures_seen),
        "lines_inserted": inserted_total,
        "lines_deduped": deduped_total,
        "lines_rejected": rejected_total,
        "accepted_parsed": accepted_count,
        "rejected_samples": rejected_samples[:200],
        "status": status,
        "api_calls": 0,
        "prediction_jobs_created": 0,
        "freezes_modified": 0,
    }


def _refresh_completeness(conn) -> None:
    conn.execute(
        """
        UPDATE correct_score_odds_lines
        SET is_complete_market = 1
        WHERE id IN (
            SELECT l.id FROM correct_score_odds_lines l
            JOIN (
                SELECT fixture_id, bookmaker_name, fetched_at_utc, COUNT(*) AS c
                FROM correct_score_odds_lines
                WHERE market = 'CORRECT_SCORE_90_MINUTES'
                GROUP BY fixture_id, bookmaker_name, fetched_at_utc
                HAVING c >= 15
            ) x
            ON l.fixture_id = x.fixture_id
           AND l.bookmaker_name = x.bookmaker_name
           AND l.fetched_at_utc = x.fetched_at_utc
        )
        """
    )
    conn.commit()


def collect_live_cs_for_fixtures(
    conn,
    fixture_ids: list[int],
    *,
    settings,
    max_api_calls: int = 5,
) -> dict[str, Any]:
    """
    Optional bounded live fetch via API-Football get_odds (cache-first client).
    Stores new odds_snapshots append-only, then extracts CS lines.
    Does not create prediction jobs or touch freezes.
    """
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    ensure_correct_score_odds_schema(conn)
    run_id = f"cs_live_{uuid.uuid4().hex[:12]}"
    started = _utc_now()
    start_run(conn, run_id, "live_bounded", started)

    if not getattr(settings, "api_football_key", None):
        finish_run(
            conn,
            run_id,
            finished=_utc_now(),
            fixtures_scanned=0,
            lines_inserted=0,
            lines_rejected=0,
            lines_deduped=0,
            status="provider_blocked_no_key",
            notes={},
        )
        return {
            "ingestion_run_id": run_id,
            "status": "CS_ODDS_PROVIDER_BLOCKED",
            "api_calls": 0,
            "lines_inserted": 0,
        }

    client = ApiFootballClient(settings)
    repo = FootballIntelligenceRepository(conn)
    calls = 0
    new_snap_ids: list[int] = []
    for fid in fixture_ids:
        if calls >= max_api_calls:
            break
        result = client.get_odds(int(fid), force_refresh=False)
        calls += 1
        data = getattr(result, "data", None) or getattr(result, "payload", None)
        if not data:
            continue
        # wrap in snapshot shape
        payload = {
            "snapshot_at": _utc_now(),
            "source": "api_football_cs_enrichment",
            "api_sports": data if isinstance(data, dict) else {"response": data},
        }
        # append-only — never UPDATE existing snapshots
        try:
            repo.save_snapshot(
                "odds_snapshots",
                fixture_id=int(fid),
                competition_key="cs_enrichment",
                payload=payload,
                snapshot_at=payload["snapshot_at"],
            )
            new_snap_ids.append(int(fid))
        except Exception:
            conn.execute(
                """
                INSERT INTO odds_snapshots (fixture_id, competition_key, snapshot_at, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (int(fid), "cs_enrichment", payload["snapshot_at"], json.dumps(payload)),
            )
            conn.commit()
            new_snap_ids.append(int(fid))

    extract = ingest_from_odds_snapshots(conn, fixture_ids=new_snap_ids or fixture_ids[:0], run_id=run_id + "_x")
    finish_run(
        conn,
        run_id,
        finished=_utc_now(),
        fixtures_scanned=len(new_snap_ids),
        lines_inserted=int(extract.get("lines_inserted") or 0),
        lines_rejected=int(extract.get("lines_rejected") or 0),
        lines_deduped=int(extract.get("lines_deduped") or 0),
        status="ok",
        notes={"api_calls": calls, "extract": extract.get("status")},
    )
    return {
        "ingestion_run_id": run_id,
        "status": "ok",
        "api_calls": calls,
        "fixtures_fetched": new_snap_ids,
        "extract": extract,
        "prediction_jobs_created": 0,
        "freezes_modified": 0,
    }

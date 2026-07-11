#!/usr/bin/env python3
"""Export non-secret odds snapshot forensics for bridge debugging."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.odds.canonical_snapshot import extract_odds_fetched_at_utc, get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.odds.timestamp_normalization import parse_timestamp_utc


def _row_fields(row: sqlite3.Row) -> dict[str, Any]:
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        payload = {}
    provider = payload.get("provider") or payload.get("source")
    fetched_dt, fetched_iso, ts_field = extract_odds_fetched_at_utc(
        {"snapshot_at": row["snapshot_at"], "payload": payload}
    )
    return {
        "table": "odds_snapshots",
        "row_id": int(row["id"]),
        "internal_fixture_id": int(row["fixture_id"]),
        "provider_fixture_id": payload.get("provider_fixture_id") or payload.get("fixture_id"),
        "provider": provider,
        "bookmaker": payload.get("bookmaker"),
        "market": payload.get("market"),
        "home_odds": payload.get("home_odds"),
        "draw_odds": payload.get("draw_odds"),
        "away_odds": payload.get("away_odds"),
        "snapshot_at_column": row["snapshot_at"],
        "payload_fetched_at_utc": payload.get("fetched_at_utc"),
        "payload_fetched_at": payload.get("fetched_at"),
        "payload_snapshot_at": payload.get("snapshot_at"),
        "payload_created_at": payload.get("created_at"),
        "extracted_fetched_at_utc": fetched_iso,
        "timestamp_source_field": ts_field,
        "created_at": None,
        "updated_at": None,
        "bookmaker_count_payload": len(payload.get("bookmakers") or []),
        "parsed_timestamp_ok": fetched_dt is not None,
    }


def export_forensics(fixture_ids: list[int], *, out_path: Path) -> dict[str, Any]:
    settings = get_settings()
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    report: dict[str, Any] = {
        "exported_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "fixture_ids": fixture_ids,
        "fixtures": {},
    }
    try:
        for fid in fixture_ids:
            rows = conn.execute(
                """
                SELECT id, fixture_id, competition_key, snapshot_at, payload_json
                FROM odds_snapshots
                WHERE fixture_id = ?
                ORDER BY id DESC
                LIMIT 20
                """,
                (int(fid),),
            ).fetchall()
            kickoff_row = conn.execute(
                "SELECT kickoff_utc FROM fixtures WHERE fixture_id = ? LIMIT 1",
                (int(fid),),
            ).fetchone()
            kickoff = kickoff_row["kickoff_utc"] if kickoff_row else None
            canonical = get_latest_valid_1x2_odds_snapshot(conn, int(fid), kickoff_utc=kickoff)
            candidates = [_row_fields(r) for r in rows]
            for c in candidates:
                if canonical.row_id and c["row_id"] == canonical.row_id:
                    c["selected"] = True
                    c["selection_reason"] = f"canonical:{canonical.freshness_class}"
                else:
                    c["selected"] = False
                    c["selection_reason"] = "not_canonical_latest_valid"
            report["fixtures"][str(fid)] = {
                "kickoff_utc": kickoff,
                "canonical_selection": canonical.to_dict(),
                "candidate_rows": candidates,
            }
    finally:
        conn.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixtures",
        default="1581037,1494694,1495730,1494206,1494692",
        help="Comma-separated fixture IDs",
    )
    parser.add_argument(
        "--out",
        default="artifacts/odds_bridge/five_fixture_snapshot_forensics.json",
    )
    args = parser.parse_args()
    fixture_ids = [int(x.strip()) for x in args.fixtures.split(",") if x.strip()]
    export_forensics(fixture_ids, out_path=Path(args.out))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()

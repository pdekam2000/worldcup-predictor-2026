"""Read-only report of league import status in SQLite."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from pathlib import Path as _Path
import runpy

runpy.run_path(str(_Path(__file__).resolve().with_name("bootstrap_path.py")))

from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.database.schema import DEFAULT_DB_PATH


def main() -> int:
    db = Path(DEFAULT_DB_PATH)
    if not db.exists():
        print(f"DATABASE: not found at {db.resolve()}")
        return 1

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    print("=" * 72)
    print("  SQLite Database Status — football_intelligence.db")
    print("=" * 72)
    print(f"Path: {db.resolve()}")
    print(f"Size: {db.stat().st_size / 1024:.1f} KB")

    v = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    print(f"Schema version: {v['value'] if v else 'unknown'}")
    print()

    print("--- Fixtures per league ---")
    rows = conn.execute(
        """
        SELECT competition_key,
               COUNT(*) AS fixture_count,
               COUNT(DISTINCT season) AS season_count,
               GROUP_CONCAT(DISTINCT season) AS seasons,
               MIN(kickoff_utc) AS earliest,
               MAX(kickoff_utc) AS latest
        FROM fixtures
        WHERE is_placeholder = 0
        GROUP BY competition_key
        ORDER BY fixture_count DESC
        """
    ).fetchall()
    if not rows:
        print("  (no fixtures)")
    for r in rows:
        label = r["competition_key"]
        try:
            label = f"{get_competition(r['competition_key']).display_name} ({r['competition_key']})"
        except KeyError:
            pass
        print(f"  {label}")
        print(f"    fixtures: {r['fixture_count']} | seasons: {r['season_count']} [{r['seasons'] or 'NULL'}]")
        print(f"    kickoff: {r['earliest'] or '—'} → {r['latest'] or '—'}")

    print()
    print("--- Fixtures per league + season ---")
    rows = conn.execute(
        """
        SELECT competition_key, season, COUNT(*) AS n
        FROM fixtures
        WHERE is_placeholder = 0
        GROUP BY competition_key, season
        ORDER BY competition_key, season
        """
    ).fetchall()
    if not rows:
        print("  (none)")
    for r in rows:
        print(f"  {r['competition_key']} / season {r['season']}: {r['n']} fixtures")

    print()
    print("--- Finished results per league ---")
    rows = conn.execute(
        """
        SELECT competition_key, COUNT(*) AS result_count
        FROM fixture_results
        GROUP BY competition_key
        ORDER BY result_count DESC
        """
    ).fetchall()
    if not rows:
        print("  (none)")
    for r in rows:
        print(f"  {r['competition_key']}: {r['result_count']} results")

    print()
    print("--- Fixture enrichment ---")
    if _table_exists(conn, "fixture_enrichment"):
        rows = conn.execute(
            """
            SELECT competition_key, COUNT(*) AS n
            FROM fixture_enrichment
            GROUP BY competition_key
            ORDER BY n DESC
            """
        ).fetchall()
        if not rows:
            print("  (none)")
        for r in rows:
            print(f"  {r['competition_key']}: {r['n']} enriched")
    else:
        print("  (table not present)")

    print()
    print("--- Last import date (sync state) ---")
    if _table_exists(conn, "league_sync_state"):
        rows = conn.execute(
            """
            SELECT competition_key, season, last_imported_fixture_id,
                   last_imported_date, last_sync_at, sync_mode
            FROM league_sync_state
            ORDER BY last_sync_at DESC
            """
        ).fetchall()
        if not rows:
            print("  (no sync state — last import date not tracked yet)")
        for r in rows:
            print(
                f"  {r['competition_key']} season {r['season']}: "
                f"last_sync={r['last_sync_at'] or '—'}, "
                f"last_fixture_id={r['last_imported_fixture_id'] or '—'}, "
                f"last_date={r['last_imported_date'] or '—'}, "
                f"mode={r['sync_mode']}"
            )
    else:
        print("  (league_sync_state table not present)")

    print()
    print("--- Import runs (latest 15) ---")
    if _table_exists(conn, "league_import_runs"):
        rows = conn.execute(
            """
            SELECT id, competition_key, league_id, season, fixtures_imported,
                   fixtures_skipped, enrichment_errors, status, message,
                   started_at, finished_at
            FROM league_import_runs
            ORDER BY started_at DESC
            LIMIT 15
            """
        ).fetchall()
        if not rows:
            print("  (no import runs logged)")
        for r in rows:
            print(
                f"  [{r['status']}] #{r['id']} {r['competition_key']} season {r['season']} "
                f"(league {r['league_id']})"
            )
            print(
                f"    imported={r['fixtures_imported']}, skipped={r['fixtures_skipped']}, "
                f"errors={r['enrichment_errors']}"
            )
            print(f"    started={r['started_at']}, finished={r['finished_at'] or 'NULL'}")
            if r["message"]:
                print(f"    → {r['message'][:140]}")
    else:
        print("  (league_import_runs table not present)")

    print()
    print("--- Incomplete import runs ---")
    if _table_exists(conn, "league_import_runs"):
        rows = conn.execute(
            """
            SELECT id, competition_key, season, status, started_at, finished_at, message
            FROM league_import_runs
            WHERE finished_at IS NULL OR status IN ('running', 'failed')
            ORDER BY started_at DESC
            """
        ).fetchall()
        if not rows:
            print("  None — all logged runs appear complete.")
        for r in rows:
            print(
                f"  run #{r['id']}: {r['competition_key']} season {r['season']} "
                f"status={r['status']} started={r['started_at']} finished={r['finished_at']}"
            )
            if r["message"]:
                print(f"    {r['message'][:150]}")
    else:
        print("  (table not present)")

    print()
    print("--- Successful import runs ---")
    if _table_exists(conn, "league_import_runs"):
        rows = conn.execute(
            """
            SELECT competition_key, season, fixtures_imported, started_at, finished_at
            FROM league_import_runs
            WHERE status = 'ok'
            ORDER BY finished_at DESC
            """
        ).fetchall()
        if not rows:
            print("  (none)")
        for r in rows:
            print(
                f"  {r['competition_key']} season {r['season']}: "
                f"{r['fixtures_imported']} fixtures — finished {r['finished_at']}"
            )

    print()
    print("--- Stuck 'running' runs (finished_at NULL) ---")
    if _table_exists(conn, "league_import_runs"):
        rows = conn.execute(
            """
            SELECT id, competition_key, season, status, started_at, finished_at, message
            FROM league_import_runs
            WHERE status = 'running' OR finished_at IS NULL
            ORDER BY started_at DESC
            """
        ).fetchall()
        if not rows:
            print("  None")
        for r in rows:
            print(
                f"  run #{r['id']}: {r['competition_key']} season {r['season']} "
                f"status={r['status']} started={r['started_at']}"
            )

    print()
    print("--- Import run totals by status ---")
    if _table_exists(conn, "league_import_runs"):
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM league_import_runs GROUP BY status ORDER BY n DESC"
        ).fetchall()
        for r in rows:
            print(f"  {r['status']}: {r['n']}")

    conn.close()
    print()
    print("=" * 72)
    return 0


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


if __name__ == "__main__":
    sys.exit(main())

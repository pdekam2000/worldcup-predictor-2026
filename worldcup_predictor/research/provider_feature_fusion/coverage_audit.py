"""Coverage audit from stored SQLite data only — no provider calls."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.research.provider_feature_fusion.constants import COVERAGE_PATH, PHASE


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_count(conn: sqlite3.Connection, table: str) -> int | None:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.OperationalError:
        return None


def _completed_fixtures(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM fixtures f
        JOIN fixture_results r ON r.fixture_id = f.fixture_id
        WHERE f.status IN ('FT','AET','PEN')
        """
    ).fetchone()
    return int(row[0]) if row else 0


def audit_coverage(*, db_path: str | Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    conn = connect(db_path or settings.sqlite_path)
    try:
        completed = _completed_fixtures(conn)
        tables = {
            "fixtures": _table_count(conn, "fixtures"),
            "fixture_results": _table_count(conn, "fixture_results"),
            "odds_snapshots": _table_count(conn, "odds_snapshots"),
            "xg_snapshots": _table_count(conn, "xg_snapshots"),
            "team_form_snapshots": _table_count(conn, "team_form_snapshots"),
            "fixture_enrichment": _table_count(conn, "fixture_enrichment"),
            "predictions": _table_count(conn, "predictions"),
            "sportmonks_fixture_enrichment": _table_count(conn, "sportmonks_fixture_enrichment"),
            "oddalerts_probability_market_rows": _table_count(conn, "oddalerts_probability_market_rows"),
            "oddalerts_odds_history": _table_count(conn, "oddalerts_odds_history"),
            "api_response_cache": _table_count(conn, "api_response_cache"),
        }

        def _distinct_join(sql: str) -> int:
            try:
                return int(conn.execute(sql).fetchone()[0])
            except sqlite3.OperationalError:
                return 0

        features = {
            "odds_snapshots": {
                "eligible_fixtures": completed,
                "fixtures_with_feature": _distinct_join(
                    """
                    SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
                    JOIN fixture_results r ON r.fixture_id=f.fixture_id
                    JOIN odds_snapshots o ON o.fixture_id=f.fixture_id
                    WHERE f.status IN ('FT','AET','PEN')
                    """
                ),
            },
            "xg_snapshots": {
                "eligible_fixtures": completed,
                "fixtures_with_feature": _distinct_join(
                    """
                    SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
                    JOIN fixture_results r ON r.fixture_id=f.fixture_id
                    JOIN xg_snapshots x ON x.fixture_id=f.fixture_id
                    WHERE f.status IN ('FT','AET','PEN')
                    """
                ),
            },
            "fixture_enrichment": {
                "eligible_fixtures": completed,
                "fixtures_with_feature": _distinct_join(
                    """
                    SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
                    JOIN fixture_results r ON r.fixture_id=f.fixture_id
                    JOIN fixture_enrichment e ON e.fixture_id=f.fixture_id
                    WHERE f.status IN ('FT','AET','PEN')
                    """
                ),
            },
            "enrichment_lineups": {
                "eligible_fixtures": _table_count(conn, "fixture_enrichment") or 0,
                "fixtures_with_feature": _distinct_join(
                    """
                    SELECT COUNT(*) FROM fixture_enrichment
                    WHERE lineups_json IS NOT NULL AND lineups_json != '' AND lineups_json != '[]'
                    """
                ),
            },
            "enrichment_statistics": {
                "eligible_fixtures": _table_count(conn, "fixture_enrichment") or 0,
                "fixtures_with_feature": _distinct_join(
                    """
                    SELECT COUNT(*) FROM fixture_enrichment
                    WHERE statistics_json IS NOT NULL AND statistics_json != ''
                    """
                ),
            },
            "oddalerts_probability_rows": {
                "eligible_fixtures": completed,
                "fixtures_with_feature": _distinct_join(
                    """
                    SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
                    JOIN fixture_results r ON r.fixture_id=f.fixture_id
                    JOIN oddalerts_probability_market_rows o ON o.internal_fixture_id=f.fixture_id
                    WHERE f.status IN ('FT','AET','PEN')
                    """
                ),
            },
            "predictions": {
                "eligible_fixtures": completed,
                "fixtures_with_feature": _distinct_join(
                    """
                    SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
                    JOIN fixture_results r ON r.fixture_id=f.fixture_id
                    JOIN predictions p ON p.fixture_id=f.fixture_id
                    WHERE f.status IN ('FT','AET','PEN')
                    """
                ),
            },
        }

        by_competition: list[dict[str, Any]] = []
        try:
            rows = conn.execute(
                """
                SELECT f.competition_key,
                       COUNT(DISTINCT f.fixture_id) AS completed,
                       COUNT(DISTINCT o.fixture_id) AS with_odds
                FROM fixtures f
                JOIN fixture_results r ON r.fixture_id = f.fixture_id
                LEFT JOIN odds_snapshots o ON o.fixture_id = f.fixture_id
                WHERE f.status IN ('FT','AET','PEN')
                GROUP BY f.competition_key
                ORDER BY completed DESC
                """
            ).fetchall()
            for row in rows:
                comp = row[0]
                done = int(row[1])
                odds = int(row[2])
                by_competition.append(
                    {
                        "competition_key": comp,
                        "completed_fixtures": done,
                        "with_odds": odds,
                        "odds_coverage_pct": round(100.0 * odds / done, 2) if done else 0.0,
                    }
                )
        except sqlite3.OperationalError:
            pass

        for name, meta in features.items():
            elig = int(meta.get("eligible_fixtures") or 0)
            have = int(meta.get("fixtures_with_feature") or 0)
            meta["coverage_pct"] = round(100.0 * have / elig, 2) if elig else 0.0

        report = {
            "phase": PHASE,
            "audited_at_utc": _utc_now(),
            "completed_fixtures": completed,
            "table_counts": tables,
            "feature_coverage": features,
            "by_competition": by_competition,
            "provider_calls_made": 0,
        }
        COVERAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        COVERAGE_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    finally:
        conn.close()

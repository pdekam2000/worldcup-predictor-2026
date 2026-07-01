"""PHASE ECSE-X2-M1 — Build ecse_score_distributions_m1 from baseline + market geometry."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.ecse_score_distribution import PROB_SUM_TOLERANCE
from worldcup_predictor.research.ecse_x2_m1.constants import BASELINE_TABLE, METHOD_VERSION, TABLE_NAME
from worldcup_predictor.research.ecse_x2_m1.filter import apply_m1_quadrant_filter
from worldcup_predictor.research.ecse_x2_m1.quadrants import resolve_market_probs

MARKET_SQL = """
    SELECT
        registry_fixture_id,
        btts_yes_closing,
        btts_no_closing,
        ou_over_25_closing,
        ou_under_25_closing
    FROM ecse_training_dataset
"""

LAMBDA_SQL = """
    SELECT registry_fixture_id, lambda_home, lambda_away, data_quality_score
    FROM ecse_lambda_features
"""

BASELINE_STREAM_SQL = f"""
    SELECT
        registry_fixture_id, scoreline, home_goals, away_goals, probability, rank,
        method_version, lambda_home, lambda_away, data_quality_score
    FROM {BASELINE_TABLE}
    ORDER BY registry_fixture_id, rank
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _build_batch_id() -> str:
    return f"ECSE-X2-M1-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"


def _ddl_statements() -> tuple[str, ...]:
    return (
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            registry_fixture_id INTEGER NOT NULL,
            scoreline TEXT NOT NULL,
            home_goals INTEGER NOT NULL,
            away_goals INTEGER NOT NULL,
            probability REAL NOT NULL,
            rank INTEGER NOT NULL,
            method_version TEXT NOT NULL,
            lambda_home REAL NOT NULL,
            lambda_away REAL NOT NULL,
            data_quality_score REAL NOT NULL,
            p_btts_yes REAL,
            p_over_25 REAL,
            dominant_quadrant TEXT,
            quadrant_probs_json TEXT,
            market_source TEXT,
            build_batch TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(registry_fixture_id, scoreline),
            FOREIGN KEY (registry_fixture_id) REFERENCES ecse_lambda_features(registry_fixture_id)
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_ecse_score_dist_m1_fixture
        ON {TABLE_NAME}(registry_fixture_id)
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_ecse_score_dist_m1_rank
        ON {TABLE_NAME}(registry_fixture_id, rank)
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_ecse_score_dist_m1_quadrant
        ON {TABLE_NAME}(dominant_quadrant)
        """,
    )


def ensure_ecse_score_distributions_m1_table(conn: sqlite3.Connection) -> None:
    for ddl in _ddl_statements():
        conn.execute(ddl)
    conn.commit()


@dataclass
class M1BuildStats:
    fixtures_scanned: int = 0
    fixtures_built: int = 0
    fixtures_skipped_existing: int = 0
    fixtures_missing_market: int = 0
    distribution_rows_inserted: int = 0
    build_batch: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": "ECSE-X2-M1",
            "method_version": METHOD_VERSION,
            "table": TABLE_NAME,
            "fixtures_scanned": self.fixtures_scanned,
            "fixtures_built": self.fixtures_built,
            "fixtures_skipped_existing": self.fixtures_skipped_existing,
            "fixtures_missing_market": self.fixtures_missing_market,
            "distribution_rows_inserted": self.distribution_rows_inserted,
            "build_batch": self.build_batch,
        }


def _load_market_maps(conn: sqlite3.Connection) -> tuple[dict[int, dict], dict[int, dict]]:
    market: dict[int, dict] = {}
    for row in conn.execute(MARKET_SQL):
        fid = int(row["registry_fixture_id"])
        market[fid] = dict(row)
    lambdas: dict[int, dict] = {}
    for row in conn.execute(LAMBDA_SQL):
        fid = int(row["registry_fixture_id"])
        lambdas[fid] = dict(row)
    return market, lambdas


def baseline_table_row_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute(f"SELECT COUNT(1) FROM {BASELINE_TABLE}").fetchone()[0])


def poisson_table_unchanged(conn: sqlite3.Connection, *, expected_rows: int) -> bool:
    return baseline_table_row_count(conn) == expected_rows


def build_ecse_score_distributions_m1(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    rebuild: bool = False,
    limit: int | None = None,
) -> M1BuildStats:
    """Build M1 filtered distributions; never modifies baseline or source tables."""
    ensure_ecse_score_distributions_m1_table(conn)
    stats = M1BuildStats(build_batch=_build_batch_id())

    if rebuild and not dry_run:
        conn.execute(f"DELETE FROM {TABLE_NAME}")

    existing: set[int] = set()
    if not rebuild and not dry_run:
        existing = {
            int(r[0])
            for r in conn.execute(f"SELECT DISTINCT registry_fixture_id FROM {TABLE_NAME}")
        }

    market_map, lambda_map = _load_market_maps(conn)

    insert_sql = f"""
        INSERT OR IGNORE INTO {TABLE_NAME} (
            registry_fixture_id, scoreline, home_goals, away_goals, probability, rank,
            method_version, lambda_home, lambda_away, data_quality_score,
            p_btts_yes, p_over_25, dominant_quadrant, quadrant_probs_json, market_source,
            build_batch, created_at
        ) VALUES (
            :registry_fixture_id, :scoreline, :home_goals, :away_goals, :probability, :rank,
            :method_version, :lambda_home, :lambda_away, :data_quality_score,
            :p_btts_yes, :p_over_25, :dominant_quadrant, :quadrant_probs_json, :market_source,
            :build_batch, :created_at
        )
    """

    batch: list[dict[str, Any]] = []
    created_at = _utc_now()
    current_id: int | None = None
    current_rows: list[dict[str, Any]] = []

    def flush_fixture(fid: int, rows: list[dict[str, Any]]) -> None:
        nonlocal batch
        stats.fixtures_scanned += 1
        if fid in existing:
            stats.fixtures_skipped_existing += 1
            return
        if limit is not None and stats.fixtures_built >= limit:
            return

        mrow = market_map.get(fid, {})
        lrow = lambda_map.get(fid, {})
        market = resolve_market_probs(
            btts_yes_closing=mrow.get("btts_yes_closing"),
            btts_no_closing=mrow.get("btts_no_closing"),
            ou_over_25_closing=mrow.get("ou_over_25_closing"),
            ou_under_25_closing=mrow.get("ou_under_25_closing"),
            lambda_home=lrow.get("lambda_home"),
            lambda_away=lrow.get("lambda_away"),
        )
        if not market.get("ok"):
            stats.fixtures_missing_market += 1
            filtered = rows
            market = {
                "ok": False,
                "p_btts_yes": None,
                "p_over_25": None,
                "dominant_quadrant": None,
                "quadrant_probs": {},
                "source": "insufficient",
            }
        else:
            filtered = apply_m1_quadrant_filter(rows, market)

        meta = rows[0]
        for entry in filtered:
            batch.append(
                {
                    "registry_fixture_id": fid,
                    "scoreline": entry["scoreline"],
                    "home_goals": entry["home_goals"],
                    "away_goals": entry["away_goals"],
                    "probability": round(float(entry["probability"]), 10),
                    "rank": int(entry["rank"]),
                    "method_version": METHOD_VERSION,
                    "lambda_home": float(meta["lambda_home"]),
                    "lambda_away": float(meta["lambda_away"]),
                    "data_quality_score": float(meta["data_quality_score"]),
                    "p_btts_yes": market.get("p_btts_yes"),
                    "p_over_25": market.get("p_over_25"),
                    "dominant_quadrant": market.get("dominant_quadrant"),
                    "quadrant_probs_json": json.dumps(market.get("quadrant_probs") or {}),
                    "market_source": market.get("source"),
                    "build_batch": stats.build_batch,
                    "created_at": created_at,
                }
            )

        stats.fixtures_built += 1
        if stats.fixtures_built % 5000 == 0 and batch and not dry_run:
            conn.executemany(insert_sql, batch)
            stats.distribution_rows_inserted += len(batch)
            batch.clear()

    for row in conn.execute(BASELINE_STREAM_SQL):
        fid = int(row["registry_fixture_id"])
        if current_id is not None and fid != current_id:
            flush_fixture(current_id, current_rows)
            current_rows = []
        current_id = fid
        current_rows.append(dict(row))

    if current_id is not None and current_rows:
        flush_fixture(current_id, current_rows)

    if batch:
        if not dry_run:
            conn.executemany(insert_sql, batch)
        stats.distribution_rows_inserted += len(batch)

    if not dry_run:
        conn.commit()
    return stats


def audit_ecse_score_distributions_m1(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_ecse_score_distributions_m1_table(conn)
    total_rows = conn.execute(f"SELECT COUNT(1) FROM {TABLE_NAME}").fetchone()[0]
    fixtures = conn.execute(
        f"SELECT COUNT(DISTINCT registry_fixture_id) FROM {TABLE_NAME}"
    ).fetchone()[0]
    if fixtures == 0:
        return {"rows": 0, "fixtures": 0}

    bad_sums = conn.execute(
        f"""
        SELECT COUNT(1) FROM (
            SELECT registry_fixture_id, ABS(SUM(probability) - 1.0) AS delta
            FROM {TABLE_NAME}
            GROUP BY registry_fixture_id
            HAVING delta > {PROB_SUM_TOLERANCE}
        )
        """
    ).fetchone()[0]

    by_quadrant = {
        str(r[0]): int(r[1])
        for r in conn.execute(
            f"""
            SELECT dominant_quadrant, COUNT(DISTINCT registry_fixture_id)
            FROM {TABLE_NAME}
            GROUP BY dominant_quadrant
            """
        ).fetchall()
    }

    return {
        "rows": int(total_rows),
        "fixtures": int(fixtures),
        "fixtures_prob_sum_off": int(bad_sums),
        "by_dominant_quadrant": by_quadrant,
        "method_version": METHOD_VERSION,
    }

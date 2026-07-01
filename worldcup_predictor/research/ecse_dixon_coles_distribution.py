"""PHASE ECSE-1F — Dixon–Coles score distributions (separate table, research only)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.ecse_score_distribution import (
    DIXON_COLES_RHO_DEFAULT,
    LAMBDA_SELECT_SQL,
    MAX_GOALS,
    PROB_SUM_TOLERANCE,
    generate_score_distribution,
    grid_scorelines_per_fixture,
)

METHOD_VERSION = "ECSE-1F-v1"
TABLE_NAME = "ecse_score_distributions_dc"
DC_LOW_SCORE_LINES = frozenset({"0-0", "1-0", "0-1", "1-1"})

POISSON_TABLE = "ecse_score_distributions"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _build_batch_id() -> str:
    return f"ECSE-1F-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"


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
            rho REAL NOT NULL,
            lambda_home REAL NOT NULL,
            lambda_away REAL NOT NULL,
            data_quality_score REAL NOT NULL,
            build_batch TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(registry_fixture_id, scoreline),
            FOREIGN KEY (registry_fixture_id) REFERENCES ecse_lambda_features(registry_fixture_id)
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_ecse_score_dist_dc_fixture
        ON {TABLE_NAME}(registry_fixture_id)
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_ecse_score_dist_dc_rank
        ON {TABLE_NAME}(registry_fixture_id, rank)
        """,
    )


def ensure_ecse_score_distributions_dc_table(conn: sqlite3.Connection) -> None:
    for ddl in _ddl_statements():
        conn.execute(ddl)
    conn.commit()


@dataclass
class DixonColesBuildStats:
    lambda_rows_scanned: int = 0
    fixtures_built: int = 0
    distribution_rows_inserted: int = 0
    fixtures_skipped_existing: int = 0
    fixtures_skipped_invalid: int = 0
    avg_top1_probability: float = 0.0
    avg_other_mass: float = 0.0
    avg_low_score_mass: float = 0.0
    rho: float = DIXON_COLES_RHO_DEFAULT
    build_batch: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "lambda_rows_scanned": self.lambda_rows_scanned,
            "fixtures_built": self.fixtures_built,
            "distribution_rows_inserted": self.distribution_rows_inserted,
            "fixtures_skipped_existing": self.fixtures_skipped_existing,
            "fixtures_skipped_invalid": self.fixtures_skipped_invalid,
            "avg_top1_probability": self.avg_top1_probability,
            "avg_other_mass": self.avg_other_mass,
            "avg_low_score_mass": self.avg_low_score_mass,
            "rho": self.rho,
            "build_batch": self.build_batch,
            "method_version": METHOD_VERSION,
            "table": TABLE_NAME,
            "corrected_scorelines": sorted(DC_LOW_SCORE_LINES),
            "scorelines_per_fixture": grid_scorelines_per_fixture(),
        }


def build_ecse_score_distributions_dc(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    rebuild: bool = False,
    rho: float = DIXON_COLES_RHO_DEFAULT,
) -> DixonColesBuildStats:
    """Build Dixon–Coles corrected distributions; does not modify Poisson table."""
    ensure_ecse_score_distributions_dc_table(conn)
    stats = DixonColesBuildStats(build_batch=_build_batch_id(), rho=rho)

    if rebuild and not dry_run:
        conn.execute(f"DELETE FROM {TABLE_NAME}")

    existing: set[int] = set()
    if not rebuild and not dry_run:
        existing = {
            int(r[0])
            for r in conn.execute(f"SELECT DISTINCT registry_fixture_id FROM {TABLE_NAME}")
        }

    insert_sql = f"""
        INSERT OR IGNORE INTO {TABLE_NAME} (
            registry_fixture_id, scoreline, home_goals, away_goals, probability, rank,
            method_version, rho, lambda_home, lambda_away, data_quality_score,
            build_batch, created_at
        ) VALUES (
            :registry_fixture_id, :scoreline, :home_goals, :away_goals, :probability, :rank,
            :method_version, :rho, :lambda_home, :lambda_away, :data_quality_score,
            :build_batch, :created_at
        )
    """

    batch: list[dict[str, Any]] = []
    top1_probs: list[float] = []
    other_masses: list[float] = []
    low_score_masses: list[float] = []
    created_at = _utc_now()

    for row in conn.execute(LAMBDA_SELECT_SQL):
        stats.lambda_rows_scanned += 1
        fid = int(row["registry_fixture_id"])
        if fid in existing:
            stats.fixtures_skipped_existing += 1
            continue

        lh = float(row["lambda_home"])
        la = float(row["lambda_away"])
        quality = float(row["data_quality_score"])
        dist = generate_score_distribution(
            lh,
            la,
            max_goals=MAX_GOALS,
            use_dixon_coles=True,
            rho=rho,
        )
        if not dist:
            stats.fixtures_skipped_invalid += 1
            continue

        top1_probs.append(float(dist[0]["probability"]))
        other_entry = next(e for e in dist if e["scoreline"] == "OTHER")
        other_masses.append(float(other_entry["probability"]))
        low_score_masses.append(
            sum(float(e["probability"]) for e in dist if e["scoreline"] in DC_LOW_SCORE_LINES)
        )

        for entry in dist:
            batch.append(
                {
                    "registry_fixture_id": fid,
                    "scoreline": entry["scoreline"],
                    "home_goals": entry["home_goals"],
                    "away_goals": entry["away_goals"],
                    "probability": round(entry["probability"], 10),
                    "rank": entry["rank"],
                    "method_version": METHOD_VERSION,
                    "rho": rho,
                    "lambda_home": lh,
                    "lambda_away": la,
                    "data_quality_score": quality,
                    "build_batch": stats.build_batch,
                    "created_at": created_at,
                }
            )

        stats.fixtures_built += 1
        if stats.fixtures_built % 5000 == 0 and batch:
            if not dry_run:
                conn.executemany(insert_sql, batch)
            stats.distribution_rows_inserted += len(batch)
            batch.clear()

    if batch:
        if not dry_run:
            conn.executemany(insert_sql, batch)
        stats.distribution_rows_inserted += len(batch)

    if top1_probs:
        stats.avg_top1_probability = round(sum(top1_probs) / len(top1_probs), 6)
    if other_masses:
        stats.avg_other_mass = round(sum(other_masses) / len(other_masses), 6)
    if low_score_masses:
        stats.avg_low_score_mass = round(sum(low_score_masses) / len(low_score_masses), 6)

    if not dry_run:
        conn.commit()
    return stats


def audit_ecse_score_distributions_dc(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_ecse_score_distributions_dc_table(conn)
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

    low_mass = conn.execute(
        f"""
        SELECT AVG(sub.m) FROM (
            SELECT SUM(probability) AS m
            FROM {TABLE_NAME}
            WHERE scoreline IN ('0-0', '1-0', '0-1', '1-1')
            GROUP BY registry_fixture_id
        ) sub
        """
    ).fetchone()[0]

    rho_val = conn.execute(f"SELECT DISTINCT rho FROM {TABLE_NAME} LIMIT 1").fetchone()

    return {
        "rows": total_rows,
        "fixtures": fixtures,
        "fixtures_prob_sum_off": bad_sums,
        "avg_low_score_mass": round(float(low_mass or 0), 6),
        "rho": float(rho_val[0]) if rho_val else None,
        "method_version": METHOD_VERSION,
    }


def dc_fingerprint(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        f"SELECT COUNT(1), SUM(probability), COUNT(DISTINCT registry_fixture_id) FROM {TABLE_NAME}"
    ).fetchone()
    payload = json.dumps({"n": row[0], "sp": row[1], "fx": row[2]}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def poisson_table_unchanged(conn: sqlite3.Connection, *, expected_rows: int) -> bool:
    n = conn.execute(f"SELECT COUNT(1) FROM {POISSON_TABLE}").fetchone()[0]
    return int(n) == expected_rows

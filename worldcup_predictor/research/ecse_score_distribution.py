"""PHASE ECSE-1D / ECSE-1D-B — Poisson score distribution (research only)."""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

METHOD_VERSION = "ECSE-1D-B-v1"
LEGACY_METHOD_VERSION = "ECSE-1D-v1"
MAX_GOALS = 7
LEGACY_MAX_GOALS = 5
OTHER_SCORELINE = "OTHER"
OTHER_HOME = -1
OTHER_AWAY = -1
PROB_SUM_TOLERANCE = 1e-6
DIXON_COLES_RHO_DEFAULT = -0.13
LEGACY_AVG_OTHER_MASS = 0.016445

LAMBDA_SELECT_SQL = """
    SELECT
        registry_fixture_id,
        lambda_home,
        lambda_away,
        data_quality_score
    FROM ecse_lambda_features
    WHERE lambda_home > 0 AND lambda_away > 0
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def poisson_pmf(k: int, lam: float) -> float:
    lam = max(lam, 1e-9)
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def scoreline_label(home: int, away: int) -> str:
    return f"{home}-{away}"


def dixon_coles_tau(home: int, away: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    """Dixon–Coles dependence factor τ(x,y). Disabled when rho=0."""
    if rho == 0.0:
        return 1.0
    if home == 0 and away == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if home == 0 and away == 1:
        return 1.0 + lambda_away * rho
    if home == 1 and away == 0:
        return 1.0 + lambda_home * rho
    if home == 1 and away == 1:
        return 1.0 - rho
    return 1.0


def grid_scorelines_per_fixture(max_goals: int = MAX_GOALS) -> int:
    return (max_goals + 1) ** 2 + 1


def generate_score_distribution(
    lambda_home: float,
    lambda_away: float,
    *,
    max_goals: int = MAX_GOALS,
    use_dixon_coles: bool = False,
    rho: float = DIXON_COLES_RHO_DEFAULT,
) -> list[dict[str, Any]]:
    """Build normalized grid 0-0..max_goals-max_goals plus OTHER bucket."""
    grid: list[tuple[int, int, float]] = []
    grid_mass = 0.0
    for home in range(max_goals + 1):
        for away in range(max_goals + 1):
            prob = poisson_pmf(home, lambda_home) * poisson_pmf(away, lambda_away)
            if use_dixon_coles:
                prob *= dixon_coles_tau(home, away, lambda_home, lambda_away, rho)
            grid.append((home, away, max(prob, 0.0)))
            grid_mass += grid[-1][2]

    other_mass = max(0.0, 1.0 - grid_mass)
    entries: list[dict[str, Any]] = []
    for home, away, prob in grid:
        entries.append(
            {
                "scoreline": scoreline_label(home, away),
                "home_goals": home,
                "away_goals": away,
                "probability": prob,
            }
        )
    entries.append(
        {
            "scoreline": OTHER_SCORELINE,
            "home_goals": OTHER_HOME,
            "away_goals": OTHER_AWAY,
            "probability": other_mass,
        }
    )

    total = sum(e["probability"] for e in entries)
    if total <= 0:
        return []
    for e in entries:
        e["probability"] = e["probability"] / total

    entries.sort(key=lambda x: x["probability"], reverse=True)
    for rank, e in enumerate(entries, start=1):
        e["rank"] = rank
    return entries


def _top_scorelines(dist: list[dict[str, Any]], n: int, *, include_other: bool = False) -> list[str]:
    out: list[str] = []
    for e in dist:
        if e["scoreline"] == OTHER_SCORELINE and not include_other:
            continue
        out.append(e["scoreline"])
        if len(out) >= n:
            break
    return out


def compare_grid_rank_stability(
    lambda_home: float,
    lambda_away: float,
    *,
    sample_top_n: int = 5,
) -> dict[str, Any]:
    """Compare legacy 5x5 vs upgraded 7x7 independent Poisson rankings."""
    legacy = generate_score_distribution(lambda_home, lambda_away, max_goals=LEGACY_MAX_GOALS)
    upgraded = generate_score_distribution(lambda_home, lambda_away, max_goals=MAX_GOALS)
    if not legacy or not upgraded:
        return {"top1_match": False, "top3_overlap": 0}

    leg_top1 = _top_scorelines(legacy, 1)
    up_top1 = _top_scorelines(upgraded, 1)
    leg_top3 = set(_top_scorelines(legacy, 3))
    up_top3 = set(_top_scorelines(upgraded, 3))
    leg_other = next(e for e in legacy if e["scoreline"] == OTHER_SCORELINE)["probability"]
    up_other = next(e for e in upgraded if e["scoreline"] == OTHER_SCORELINE)["probability"]

    return {
        "top1_match": leg_top1 == up_top1,
        "top3_overlap": len(leg_top3 & up_top3),
        "legacy_top1": leg_top1[0] if leg_top1 else None,
        "upgraded_top1": up_top1[0] if up_top1 else None,
        "legacy_other_mass": round(leg_other, 6),
        "upgraded_other_mass": round(up_other, 6),
        f"top{sample_top_n}_legacy": _top_scorelines(legacy, sample_top_n),
        f"top{sample_top_n}_upgraded": _top_scorelines(upgraded, sample_top_n),
    }


def audit_grid_upgrade_sample(conn: sqlite3.Connection, *, sample_size: int = 500) -> dict[str, Any]:
    rows = conn.execute(
        f"""
        SELECT lambda_home, lambda_away
        FROM ecse_lambda_features
        ORDER BY registry_fixture_id
        LIMIT {int(sample_size)}
        """
    ).fetchall()
    if not rows:
        return {"sample_size": 0}

    top1_matches = 0
    top3_overlap_sum = 0
    legacy_other_sum = 0.0
    upgraded_other_sum = 0.0
    grid_mass_legacy_sum = 0.0
    grid_mass_upgraded_sum = 0.0

    for row in rows:
        lh, la = float(row[0]), float(row[1])
        cmp = compare_grid_rank_stability(lh, la)
        top1_matches += int(cmp["top1_match"])
        top3_overlap_sum += int(cmp["top3_overlap"])
        legacy_other_sum += float(cmp["legacy_other_mass"])
        upgraded_other_sum += float(cmp["upgraded_other_mass"])
        grid_mass_legacy_sum += 1.0 - float(cmp["legacy_other_mass"])
        grid_mass_upgraded_sum += 1.0 - float(cmp["upgraded_other_mass"])

    n = len(rows)
    return {
        "sample_size": n,
        "top1_stable_pct": round(100.0 * top1_matches / n, 4),
        "avg_top3_overlap": round(top3_overlap_sum / n, 4),
        "avg_legacy_other_mass": round(legacy_other_sum / n, 6),
        "avg_upgraded_other_mass": round(upgraded_other_sum / n, 6),
        "other_mass_reduction_pct": round(
            100.0 * (1.0 - (upgraded_other_sum / max(legacy_other_sum, 1e-12))), 4
        ),
        "avg_grid_mass_legacy_pct": round(100.0 * grid_mass_legacy_sum / n, 4),
        "avg_grid_mass_upgraded_pct": round(100.0 * grid_mass_upgraded_sum / n, 4),
    }


def _ddl_statements() -> tuple[str, ...]:
    return (
        """
        CREATE TABLE IF NOT EXISTS ecse_score_distributions (
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
            build_batch TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(registry_fixture_id, scoreline),
            FOREIGN KEY (registry_fixture_id) REFERENCES ecse_lambda_features(registry_fixture_id)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ecse_score_dist_fixture
        ON ecse_score_distributions(registry_fixture_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ecse_score_dist_rank
        ON ecse_score_distributions(registry_fixture_id, rank)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ecse_score_dist_method
        ON ecse_score_distributions(method_version)
        """,
    )


def ensure_ecse_score_distributions_table(conn: sqlite3.Connection) -> None:
    for ddl in _ddl_statements():
        conn.execute(ddl)
    conn.commit()


def _build_batch_id() -> str:
    return f"ECSE-1D-B-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"


@dataclass
class DistributionBuildStats:
    lambda_rows_scanned: int = 0
    fixtures_built: int = 0
    distribution_rows_inserted: int = 0
    fixtures_skipped_existing: int = 0
    fixtures_skipped_invalid: int = 0
    avg_top1_probability: float = 0.0
    avg_other_mass: float = 0.0
    avg_grid_mass_pct: float = 0.0
    build_batch: str = ""
    max_goals: int = MAX_GOALS
    use_dixon_coles: bool = False
    dixon_coles_rho: float = DIXON_COLES_RHO_DEFAULT

    def to_dict(self) -> dict[str, Any]:
        return {
            "lambda_rows_scanned": self.lambda_rows_scanned,
            "fixtures_built": self.fixtures_built,
            "distribution_rows_inserted": self.distribution_rows_inserted,
            "fixtures_skipped_existing": self.fixtures_skipped_existing,
            "fixtures_skipped_invalid": self.fixtures_skipped_invalid,
            "avg_top1_probability": self.avg_top1_probability,
            "avg_other_mass": self.avg_other_mass,
            "avg_grid_mass_pct": self.avg_grid_mass_pct,
            "build_batch": self.build_batch,
            "method_version": METHOD_VERSION,
            "max_goals": self.max_goals,
            "scorelines_per_fixture": grid_scorelines_per_fixture(self.max_goals),
            "use_dixon_coles": self.use_dixon_coles,
            "dixon_coles_rho": self.dixon_coles_rho if self.use_dixon_coles else 0.0,
        }


def build_ecse_score_distributions(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    rebuild: bool = False,
    max_goals: int = MAX_GOALS,
    use_dixon_coles: bool = False,
    rho: float = DIXON_COLES_RHO_DEFAULT,
) -> DistributionBuildStats:
    ensure_ecse_score_distributions_table(conn)
    stats = DistributionBuildStats(
        build_batch=_build_batch_id(),
        max_goals=max_goals,
        use_dixon_coles=use_dixon_coles,
        dixon_coles_rho=rho,
    )

    if rebuild and not dry_run:
        conn.execute("DELETE FROM ecse_score_distributions")

    existing: set[int] = set()
    if not rebuild and not dry_run:
        existing = {
            int(r[0])
            for r in conn.execute(
                "SELECT DISTINCT registry_fixture_id FROM ecse_score_distributions"
            )
        }

    insert_sql = """
        INSERT OR IGNORE INTO ecse_score_distributions (
            registry_fixture_id, scoreline, home_goals, away_goals, probability, rank,
            method_version, lambda_home, lambda_away, data_quality_score,
            build_batch, created_at
        ) VALUES (
            :registry_fixture_id, :scoreline, :home_goals, :away_goals, :probability, :rank,
            :method_version, :lambda_home, :lambda_away, :data_quality_score,
            :build_batch, :created_at
        )
    """

    batch: list[dict[str, Any]] = []
    top1_probs: list[float] = []
    other_masses: list[float] = []
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
            max_goals=max_goals,
            use_dixon_coles=use_dixon_coles,
            rho=rho,
        )
        if not dist:
            stats.fixtures_skipped_invalid += 1
            continue

        top1_probs.append(float(dist[0]["probability"]))
        other_entry = next(e for e in dist if e["scoreline"] == OTHER_SCORELINE)
        other_masses.append(float(other_entry["probability"]))

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
        stats.avg_grid_mass_pct = round(100.0 * (1.0 - stats.avg_other_mass), 4)

    if not dry_run:
        conn.commit()
    return stats


def fetch_top_scorelines(
    conn: sqlite3.Connection,
    registry_fixture_id: int,
    *,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """Return top-N most likely scorelines for a fixture (excludes OTHER by default)."""
    rows = conn.execute(
        """
        SELECT scoreline, home_goals, away_goals, probability, rank
        FROM ecse_score_distributions
        WHERE registry_fixture_id = ?
          AND scoreline != ?
        ORDER BY rank ASC
        LIMIT ?
        """,
        (registry_fixture_id, OTHER_SCORELINE, top_n),
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_top_scorelines_including_other(
    conn: sqlite3.Connection,
    registry_fixture_id: int,
    *,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT scoreline, home_goals, away_goals, probability, rank
        FROM ecse_score_distributions
        WHERE registry_fixture_id = ?
        ORDER BY rank ASC
        LIMIT ?
        """,
        (registry_fixture_id, top_n),
    ).fetchall()
    return [dict(r) for r in rows]


def sample_top_n_summary(
    conn: sqlite3.Connection,
    *,
    sample_fixtures: int = 5,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    fixture_ids = [
        int(r[0])
        for r in conn.execute(
            """
            SELECT registry_fixture_id FROM ecse_score_distributions
            GROUP BY registry_fixture_id
            ORDER BY registry_fixture_id
            LIMIT ?
            """,
            (sample_fixtures,),
        ).fetchall()
    ]
    out: list[dict[str, Any]] = []
    for fid in fixture_ids:
        out.append(
            {
                "registry_fixture_id": fid,
                f"top_{top_n}": fetch_top_scorelines(conn, fid, top_n=top_n),
            }
        )
    return out


def audit_ecse_score_distributions(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_ecse_score_distributions_table(conn)
    total_rows = conn.execute("SELECT COUNT(1) FROM ecse_score_distributions").fetchone()[0]
    fixtures = conn.execute(
        "SELECT COUNT(DISTINCT registry_fixture_id) FROM ecse_score_distributions"
    ).fetchone()[0]
    if fixtures == 0:
        return {"rows": 0, "fixtures": 0}

    non_positive = conn.execute(
        "SELECT COUNT(1) FROM ecse_score_distributions WHERE probability <= 0"
    ).fetchone()[0]

    bad_sums = conn.execute(
        f"""
        SELECT COUNT(1) FROM (
            SELECT registry_fixture_id, ABS(SUM(probability) - 1.0) AS delta
            FROM ecse_score_distributions
            GROUP BY registry_fixture_id
            HAVING delta > {PROB_SUM_TOLERANCE}
        )
        """
    ).fetchone()[0]

    bad_ranks = conn.execute(
        """
        SELECT COUNT(1) FROM (
            SELECT registry_fixture_id
            FROM ecse_score_distributions
            GROUP BY registry_fixture_id
            HAVING MIN(rank) != 1 OR MAX(rank) != COUNT(1)
               OR COUNT(DISTINCT rank) != COUNT(1)
        )
        """
    ).fetchone()[0]

    other_row = conn.execute(
        """
        SELECT AVG(probability) FROM ecse_score_distributions WHERE scoreline = ?
        """,
        (OTHER_SCORELINE,),
    ).fetchone()[0]

    top1 = conn.execute(
        """
        SELECT AVG(probability) FROM ecse_score_distributions WHERE rank = 1
        """
    ).fetchone()[0]

    max_h = conn.execute(
        "SELECT MAX(home_goals) FROM ecse_score_distributions WHERE scoreline != ?",
        (OTHER_SCORELINE,),
    ).fetchone()[0]

    return {
        "rows": total_rows,
        "fixtures": fixtures,
        "rows_per_fixture": round(total_rows / fixtures, 2),
        "max_grid_goals": int(max_h or 0),
        "non_positive_probabilities": non_positive,
        "fixtures_prob_sum_off": bad_sums,
        "fixtures_rank_errors": bad_ranks,
        "avg_other_probability": round(float(other_row or 0), 6),
        "avg_rank1_probability": round(float(top1 or 0), 6),
        "avg_grid_mass_pct": round(100.0 * (1.0 - float(other_row or 0)), 4),
        "method_versions": [
            {"version": r[0], "count": r[1]}
            for r in conn.execute(
                "SELECT method_version, COUNT(1) FROM ecse_score_distributions GROUP BY method_version"
            ).fetchall()
        ],
    }


def distribution_fingerprint(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """
        SELECT COUNT(1), SUM(probability), COUNT(DISTINCT registry_fixture_id)
        FROM ecse_score_distributions
        """
    ).fetchone()
    payload = json.dumps({"n": row[0], "sp": row[1], "fx": row[2]}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def generation_uses_result_labels() -> bool:
    """Verify SQL + generator never reference result label tables/columns."""
    forbidden = ("historical_fixture_results", "ecse_training_dataset", "exact_score")
    audited = LAMBDA_SELECT_SQL + "\n" + inspect.getsource(generate_score_distribution)
    return any(token in audited for token in forbidden)

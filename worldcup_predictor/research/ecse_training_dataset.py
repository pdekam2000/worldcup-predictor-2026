"""PHASE ECSE-1A — Exact Correct Score Engine training dataset builder (research only)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from worldcup_predictor.data_import.historical_prematch_odds_clean import kickoff_to_unix
from worldcup_predictor.research.historical_odds_baseline_backtest import _team_side_from_source

FIXTURE_BASE_SQL = """
    SELECT
        res.registry_fixture_id,
        reg.registry_key,
        reg.league,
        reg.season,
        reg.kickoff_utc,
        reg.home_team,
        reg.away_team,
        res.home_goals,
        res.away_goals,
        res.total_goals
    FROM historical_fixture_results res
    INNER JOIN historical_fixture_registry reg
        ON reg.registry_fixture_id = res.registry_fixture_id
"""

ODDS_STREAM_SQL = """
    SELECT
        c.registry_fixture_id,
        c.market,
        c.selection,
        c.source_file,
        c.opening_odds,
        c.closing_odds,
        c.closing_unix,
        c.source_odds_id
    FROM historical_csv_odds_prematch_clean c
    INNER JOIN historical_fixture_results res
        ON res.registry_fixture_id = c.registry_fixture_id
    ORDER BY c.registry_fixture_id, c.market, c.selection, c.source_odds_id
"""


@dataclass(frozen=True)
class OddsFeatureSpec:
    column_stem: str
    market: str
    selection: str
    team_side: str | None = None


ODDS_FEATURE_SPECS: tuple[OddsFeatureSpec, ...] = (
    # Full-time result
    OddsFeatureSpec("ft_home", "ft_result", "home"),
    OddsFeatureSpec("ft_away", "ft_result", "away"),
    OddsFeatureSpec("ft_draw", "ft_result", "draw"),
    # BTTS
    OddsFeatureSpec("btts_yes", "btts", "yes"),
    OddsFeatureSpec("btts_no", "btts", "no"),
    # Match over/under
    OddsFeatureSpec("ou_over_15", "over_under", "over_15"),
    OddsFeatureSpec("ou_under_15", "over_under", "under_15"),
    OddsFeatureSpec("ou_over_25", "over_under", "over_25"),
    OddsFeatureSpec("ou_under_25", "over_under", "under_25"),
    OddsFeatureSpec("ou_over_35", "over_under", "over_35"),
    OddsFeatureSpec("ou_under_35", "over_under", "under_35"),
    OddsFeatureSpec("ou_over_45", "over_under", "over_45"),
    OddsFeatureSpec("ou_under_45", "over_under", "under_45"),
    # Team goal markets (home)
    OddsFeatureSpec("team_home_over_05", "team_over_under", "over_05", "home"),
    OddsFeatureSpec("team_home_under_05", "team_over_under", "under_05", "home"),
    OddsFeatureSpec("team_home_over_15", "team_over_under", "over_15", "home"),
    OddsFeatureSpec("team_home_under_15", "team_over_under", "under_15", "home"),
    # Team goal markets (away)
    OddsFeatureSpec("team_away_over_05", "team_over_under", "over_05", "away"),
    OddsFeatureSpec("team_away_under_05", "team_over_under", "under_05", "away"),
    OddsFeatureSpec("team_away_over_15", "team_over_under", "over_15", "away"),
    OddsFeatureSpec("team_away_under_15", "team_over_under", "under_15", "away"),
    # First half
    OddsFeatureSpec("fh_home", "first_half_winner", "home"),
    OddsFeatureSpec("fh_draw", "first_half_winner", "draw"),
    OddsFeatureSpec("fh_away", "first_half_winner", "away"),
    # Double chance
    OddsFeatureSpec("dc_home_draw", "double_chance", "home_draw"),
    OddsFeatureSpec("dc_home_away", "double_chance", "home_away"),
    OddsFeatureSpec("dc_draw_away", "double_chance", "draw_away"),
    # Corners
    OddsFeatureSpec("corner_over_55", "corners_over_under", "over_55"),
    OddsFeatureSpec("corner_over_65", "corners_over_under", "over_65"),
    OddsFeatureSpec("corner_over_75", "corners_over_under", "over_75"),
    OddsFeatureSpec("corner_over_85", "corners_over_under", "over_85"),
    OddsFeatureSpec("corner_over_95", "corners_over_under", "over_95"),
    OddsFeatureSpec("corner_over_105", "corners_over_under", "over_105"),
    OddsFeatureSpec("corner_under_95", "corners_over_under", "under_95"),
    OddsFeatureSpec("corner_under_105", "corners_over_under", "under_105"),
    OddsFeatureSpec("corner_under_115", "corners_over_under", "under_115"),
    OddsFeatureSpec("corner_under_125", "corners_over_under", "under_125"),
    OddsFeatureSpec("corner_under_135", "corners_over_under", "under_135"),
    OddsFeatureSpec("corner_under_145", "corners_over_under", "under_145"),
    OddsFeatureSpec("corner_under_155", "corners_over_under", "under_155"),
    OddsFeatureSpec("corner_under_165", "corners_over_under", "under_165"),
)

FEATURE_COLUMNS: tuple[str, ...] = tuple(
    col
    for spec in ODDS_FEATURE_SPECS
    for col in (f"{spec.column_stem}_opening", f"{spec.column_stem}_closing", f"{spec.column_stem}_movement")
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _movement(opening: float | None, closing: float | None) -> float | None:
    if opening is None or closing is None:
        return None
    return round(closing - opening, 6)


def _is_dup_source(source_file: str | None) -> bool:
    return "__dup" in (source_file or "").lower()


def _odds_lookup_key(market: str, selection: str, source_file: str | None) -> tuple[Any, ...] | None:
    if market == "team_over_under":
        side = _team_side_from_source(source_file or "")
        if side not in ("home", "away"):
            return None
        return (market, side, selection)
    return (market, selection)


def _prefer_odds_row(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    ex_dup = _is_dup_source(existing.get("source_file"))
    cand_dup = _is_dup_source(candidate.get("source_file"))
    if ex_dup != cand_dup:
        return candidate if not cand_dup else existing
    ex_close = existing.get("closing_unix") or 0
    cand_close = candidate.get("closing_unix") or 0
    if cand_close != ex_close:
        return candidate if cand_close > ex_close else existing
    ex_id = existing.get("source_odds_id") or 0
    cand_id = candidate.get("source_odds_id") or 0
    return candidate if cand_id < ex_id else existing


def _build_batch_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"ECSE-1A-{stamp}"


def _ddl_statements() -> tuple[str, ...]:
    feature_cols = ",\n        ".join(f"{col} REAL" for col in FEATURE_COLUMNS)
    return (
        f"""
        CREATE TABLE IF NOT EXISTS ecse_training_dataset (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            registry_fixture_id INTEGER NOT NULL UNIQUE,
            registry_key TEXT,
            league TEXT,
            season TEXT,
            kickoff_utc TEXT,
            kickoff_unix INTEGER,
            home_team TEXT,
            away_team TEXT,
            exact_score TEXT NOT NULL,
            home_goals INTEGER NOT NULL,
            away_goals INTEGER NOT NULL,
            goal_difference INTEGER NOT NULL,
            total_goals INTEGER NOT NULL,
            {feature_cols},
            feature_coverage_count INTEGER NOT NULL DEFAULT 0,
            build_batch TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (registry_fixture_id) REFERENCES historical_fixture_registry(registry_fixture_id)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ecse_training_league
        ON ecse_training_dataset(league, season)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ecse_training_kickoff
        ON ecse_training_dataset(kickoff_unix)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ecse_training_exact_score
        ON ecse_training_dataset(exact_score)
        """,
    )


def ensure_ecse_training_dataset_table(conn: sqlite3.Connection) -> None:
    for ddl in _ddl_statements():
        conn.execute(ddl)
    conn.commit()


def _spec_lookup_key(spec: OddsFeatureSpec) -> tuple[Any, ...]:
    if spec.team_side:
        return (spec.market, spec.team_side, spec.selection)
    return (spec.market, spec.selection)


def _extract_feature_values(odds_map: dict[tuple[Any, ...], dict[str, Any]]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for spec in ODDS_FEATURE_SPECS:
        row = odds_map.get(_spec_lookup_key(spec))
        opening = float(row["opening_odds"]) if row and row.get("opening_odds") is not None else None
        closing = float(row["closing_odds"]) if row and row.get("closing_odds") is not None else None
        out[f"{spec.column_stem}_opening"] = opening
        out[f"{spec.column_stem}_closing"] = closing
        out[f"{spec.column_stem}_movement"] = _movement(opening, closing)
    return out


def _feature_coverage(features: dict[str, float | None]) -> int:
    stems = {spec.column_stem for spec in ODDS_FEATURE_SPECS}
    covered = 0
    for stem in stems:
        if features.get(f"{stem}_closing") is not None:
            covered += 1
    return covered


def _exact_score(home_goals: int, away_goals: int) -> str:
    return f"{home_goals}-{away_goals}"


@dataclass
class EcseBuildStats:
    fixtures_eligible: int = 0
    fixtures_with_odds: int = 0
    rows_inserted: int = 0
    rows_skipped_existing: int = 0
    rows_skipped_no_odds: int = 0
    avg_feature_coverage: float = 0.0
    build_batch: str = ""
    feature_column_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixtures_eligible": self.fixtures_eligible,
            "fixtures_with_odds": self.fixtures_with_odds,
            "rows_inserted": self.rows_inserted,
            "rows_skipped_existing": self.rows_skipped_existing,
            "rows_skipped_no_odds": self.rows_skipped_no_odds,
            "avg_feature_coverage": self.avg_feature_coverage,
            "build_batch": self.build_batch,
            "feature_column_count": self.feature_column_count,
        }


def _aggregate_odds_by_fixture(conn: sqlite3.Connection) -> dict[int, dict[tuple[Any, ...], dict[str, Any]]]:
    by_fixture: dict[int, dict[tuple[Any, ...], dict[str, Any]]] = {}
    for row in conn.execute(ODDS_STREAM_SQL):
        fid = int(row["registry_fixture_id"])
        key = _odds_lookup_key(row["market"], row["selection"], row["source_file"])
        if key is None:
            continue
        fixture_map = by_fixture.setdefault(fid, {})
        candidate = dict(row)
        if key in fixture_map:
            fixture_map[key] = _prefer_odds_row(fixture_map[key], candidate)
        else:
            fixture_map[key] = candidate
    return by_fixture


def build_ecse_training_dataset(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    rebuild: bool = False,
) -> EcseBuildStats:
    ensure_ecse_training_dataset_table(conn)
    stats = EcseBuildStats(
        build_batch=_build_batch_id(),
        feature_column_count=len(FEATURE_COLUMNS),
    )

    if rebuild and not dry_run:
        conn.execute("DELETE FROM ecse_training_dataset")

    existing_ids: set[int] = set()
    if not rebuild and not dry_run:
        existing_ids = {
            int(r[0]) for r in conn.execute("SELECT registry_fixture_id FROM ecse_training_dataset")
        }

    fixtures = [dict(r) for r in conn.execute(FIXTURE_BASE_SQL)]
    stats.fixtures_eligible = len(fixtures)
    odds_by_fixture = _aggregate_odds_by_fixture(conn)
    stats.fixtures_with_odds = len(odds_by_fixture)

    insert_cols = [
        "registry_fixture_id",
        "registry_key",
        "league",
        "season",
        "kickoff_utc",
        "kickoff_unix",
        "home_team",
        "away_team",
        "exact_score",
        "home_goals",
        "away_goals",
        "goal_difference",
        "total_goals",
        *FEATURE_COLUMNS,
        "feature_coverage_count",
        "build_batch",
        "created_at",
    ]
    placeholders = ", ".join("?" for _ in insert_cols)
    col_sql = ", ".join(insert_cols)
    insert_sql = f"INSERT INTO ecse_training_dataset ({col_sql}) VALUES ({placeholders})"

    coverage_total = 0
    batch_rows: list[tuple[Any, ...]] = []
    created_at = _utc_now()

    for fx in fixtures:
        fid = int(fx["registry_fixture_id"])
        if fid in existing_ids:
            stats.rows_skipped_existing += 1
            continue
        odds_map = odds_by_fixture.get(fid)
        if not odds_map:
            stats.rows_skipped_no_odds += 1
            continue

        home_goals = int(fx["home_goals"])
        away_goals = int(fx["away_goals"])
        total_goals = int(fx["total_goals"])
        features = _extract_feature_values(odds_map)
        coverage = _feature_coverage(features)
        coverage_total += coverage

        row_values: list[Any] = [
            fid,
            fx.get("registry_key"),
            fx.get("league"),
            fx.get("season"),
            fx.get("kickoff_utc"),
            kickoff_to_unix(fx.get("kickoff_utc")),
            fx.get("home_team"),
            fx.get("away_team"),
            _exact_score(home_goals, away_goals),
            home_goals,
            away_goals,
            home_goals - away_goals,
            total_goals,
        ]
        row_values.extend(features[col] for col in FEATURE_COLUMNS)
        row_values.extend([coverage, stats.build_batch, created_at])
        batch_rows.append(tuple(row_values))

        if len(batch_rows) >= 2000:
            if not dry_run:
                conn.executemany(insert_sql, batch_rows)
            stats.rows_inserted += len(batch_rows)
            batch_rows.clear()

    if batch_rows:
        if not dry_run:
            conn.executemany(insert_sql, batch_rows)
        stats.rows_inserted += len(batch_rows)

    if stats.rows_inserted:
        stats.avg_feature_coverage = round(coverage_total / stats.rows_inserted, 4)

    if not dry_run:
        conn.commit()
    return stats


def audit_ecse_training_dataset(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_ecse_training_dataset_table(conn)
    row_count = conn.execute("SELECT COUNT(1) FROM ecse_training_dataset").fetchone()[0]
    eligible = conn.execute(
        """
        SELECT COUNT(DISTINCT res.registry_fixture_id)
        FROM historical_fixture_results res
        INNER JOIN historical_csv_odds_prematch_clean c
            ON c.registry_fixture_id = res.registry_fixture_id
        """
    ).fetchone()[0]
    orphan = conn.execute(
        """
        SELECT COUNT(1) FROM ecse_training_dataset d
        LEFT JOIN historical_fixture_results r ON r.registry_fixture_id = d.registry_fixture_id
        WHERE r.registry_fixture_id IS NULL
        """
    ).fetchone()[0]
    label_mismatch = conn.execute(
        """
        SELECT COUNT(1) FROM ecse_training_dataset d
        INNER JOIN historical_fixture_results r ON r.registry_fixture_id = d.registry_fixture_id
        WHERE d.exact_score != (r.home_goals || '-' || r.away_goals)
           OR d.home_goals != r.home_goals
           OR d.away_goals != r.away_goals
           OR d.total_goals != r.total_goals
           OR d.goal_difference != (r.home_goals - r.away_goals)
        """
    ).fetchone()[0]
    avg_cov = conn.execute("SELECT AVG(feature_coverage_count) FROM ecse_training_dataset").fetchone()[0]
    score_dist = conn.execute(
        """
        SELECT exact_score, COUNT(1) AS c
        FROM ecse_training_dataset
        GROUP BY exact_score
        ORDER BY c DESC
        LIMIT 10
        """
    ).fetchall()
    return {
        "dataset_rows": row_count,
        "eligible_fixtures": eligible,
        "orphan_rows": orphan,
        "label_mismatch_rows": label_mismatch,
        "avg_feature_coverage": round(float(avg_cov or 0), 4),
        "top_exact_scores": [{"exact_score": r[0], "count": r[1]} for r in score_dist],
        "feature_columns": len(FEATURE_COLUMNS),
        "feature_specs": len(ODDS_FEATURE_SPECS),
    }


def dataset_fingerprint(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """
        SELECT COUNT(1) AS n,
               SUM(home_goals) AS hg,
               SUM(away_goals) AS ag,
               SUM(feature_coverage_count) AS cov
        FROM ecse_training_dataset
        """
    ).fetchone()
    payload = json.dumps(
        {
            "n": row[0],
            "hg": row[1],
            "ag": row[2],
            "cov": row[3],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]

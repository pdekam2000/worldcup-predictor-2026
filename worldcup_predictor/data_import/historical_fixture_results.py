"""PHASE DATA-1D — Historical result labels from OddAlerts CSV odds (staging, no API).

Schema reuse audit:
- ``fixture_results`` — production results keyed by ``fixtures.fixture_id``; not used here.
- ``historical_fixture_registry`` — DATA-1C staging identities; read for context only.
- ``historical_fixture_results`` — NEW staging labels keyed by ``registry_fixture_id``.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE = "oddalerts_csv"
SETTLED_STATUSES = frozenset({"FT", "FT_PEN", "AET", "AWARDED"})

DATA_1D_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS historical_fixture_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        registry_fixture_id INTEGER NOT NULL,
        source TEXT NOT NULL DEFAULT 'oddalerts_csv',
        home_goals INTEGER NOT NULL,
        away_goals INTEGER NOT NULL,
        total_goals INTEGER NOT NULL,
        match_status TEXT NOT NULL,
        ht_score TEXT,
        ht_home_goals INTEGER,
        ht_away_goals INTEGER,
        corners_total INTEGER,
        result_1x2 TEXT NOT NULL,
        btts_actual INTEGER NOT NULL,
        over_15_actual INTEGER NOT NULL,
        over_25_actual INTEGER NOT NULL,
        over_35_actual INTEGER NOT NULL,
        corners_over_85_actual INTEGER,
        corners_over_95_actual INTEGER,
        corners_over_105_actual INTEGER,
        source_file TEXT,
        raw_result_json TEXT NOT NULL,
        dedup_key TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (registry_fixture_id) REFERENCES historical_fixture_registry(registry_fixture_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_historical_fixture_results_registry
    ON historical_fixture_results(registry_fixture_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_historical_fixture_results_source
    ON historical_fixture_results(source)
    """,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _result_1x2(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    if away_goals > home_goals:
        return "away"
    return "draw"


def _over_actual(total_goals: int, line: float) -> int:
    return 1 if total_goals > line else 0


def _corners_over_actual(corners: int | None, line: float) -> int | None:
    if corners is None:
        return None
    return 1 if corners > line else 0


def _parse_ht_score(ht_score: str | None) -> tuple[int | None, int | None]:
    if not ht_score:
        return None, None
    m = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", str(ht_score))
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def _dedup_key(registry_fixture_id: int, source: str) -> str:
    raw = f"{registry_fixture_id}|{source}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ensure_historical_fixture_results_table(conn: sqlite3.Connection) -> None:
    for ddl in DATA_1D_DDL:
        conn.execute(ddl)
    conn.commit()


def build_result_labels(
    home_goals: int,
    away_goals: int,
    *,
    match_status: str,
    ht_score: str | None = None,
    corners_total: int | None = None,
) -> dict[str, Any]:
    total = home_goals + away_goals
    ht_home, ht_away = _parse_ht_score(ht_score)
    return {
        "home_goals": home_goals,
        "away_goals": away_goals,
        "total_goals": total,
        "match_status": match_status,
        "ht_score": ht_score,
        "ht_home_goals": ht_home,
        "ht_away_goals": ht_away,
        "corners_total": corners_total,
        "result_1x2": _result_1x2(home_goals, away_goals),
        "btts_actual": 1 if home_goals >= 1 and away_goals >= 1 else 0,
        "over_15_actual": _over_actual(total, 1.5),
        "over_25_actual": _over_actual(total, 2.5),
        "over_35_actual": _over_actual(total, 3.5),
        "corners_over_85_actual": _corners_over_actual(corners_total, 8.5),
        "corners_over_95_actual": _corners_over_actual(corners_total, 9.5),
        "corners_over_105_actual": _corners_over_actual(corners_total, 10.5),
    }


def _extract_corners_and_ht(raw_json: str | None) -> tuple[int | None, str | None]:
    if not raw_json:
        return None, None
    try:
        row = json.loads(raw_json)
    except json.JSONDecodeError:
        return None, None
    corners = _parse_int(row.get("Corners"))
    ht = (row.get("HT Score") or "").strip() or None
    return corners, ht


@dataclass
class ResultsBuildStats:
    registry_total: int = 0
    odds_rows_scanned: int = 0
    settled_candidate_fixtures: int = 0
    results_inserted: int = 0
    results_skipped_duplicate: int = 0
    results_skipped_no_score: int = 0
    results_skipped_unsettled: int = 0
    results_skipped_ambiguous: int = 0
    csv_result_fields_present: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_total": self.registry_total,
            "odds_rows_scanned": self.odds_rows_scanned,
            "settled_candidate_fixtures": self.settled_candidate_fixtures,
            "results_inserted": self.results_inserted,
            "results_skipped_duplicate": self.results_skipped_duplicate,
            "results_skipped_no_score": self.results_skipped_no_score,
            "results_skipped_unsettled": self.results_skipped_unsettled,
            "results_skipped_ambiguous": self.results_skipped_ambiguous,
            "csv_result_fields_present": self.csv_result_fields_present,
            "errors": self.errors[:50],
        }


def inspect_csv_result_fields(conn: sqlite3.Connection) -> dict[str, Any]:
    sample = conn.execute(
        "SELECT raw_json FROM historical_csv_odds_imports WHERE raw_json IS NOT NULL LIMIT 1"
    ).fetchone()
    if not sample:
        return {"present": False, "reason": "no_odds_rows"}
    try:
        row = json.loads(sample["raw_json"])
    except json.JSONDecodeError:
        return {"present": False, "reason": "invalid_raw_json"}

    required = ("Status", "Home Goals", "Away Goals")
    optional = ("Corners", "HT Score", "Outcome")
    missing = [k for k in required if k not in row]
    return {
        "present": not missing,
        "missing_required": missing,
        "columns_found": list(row.keys()),
        "optional_present": [k for k in optional if k in row],
    }


def _aggregate_registry_scores(conn: sqlite3.Connection) -> tuple[
    dict[int, dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Return registry_id -> canonical result payload, ambiguous log, no-result log."""
    score_rows = conn.execute(
        """
        SELECT registry_fixture_id, home_goals, away_goals, match_status, COUNT(*) AS c
        FROM historical_csv_odds_imports
        WHERE registry_fixture_id IS NOT NULL
          AND home_goals IS NOT NULL
          AND away_goals IS NOT NULL
          AND match_status IN ('FT', 'FT_PEN', 'AET', 'AWARDED')
        GROUP BY registry_fixture_id, home_goals, away_goals, match_status
        """
    ).fetchall()

    by_registry: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in score_rows:
        by_registry[int(row["registry_fixture_id"])].append(dict(row))

    all_registry_ids = {
        int(r["registry_fixture_id"])
        for r in conn.execute(
            "SELECT registry_fixture_id FROM historical_fixture_registry"
        ).fetchall()
    }

    status_rows = conn.execute(
        """
        SELECT registry_fixture_id, match_status, COUNT(*) AS c
        FROM historical_csv_odds_imports
        WHERE registry_fixture_id IS NOT NULL
        GROUP BY registry_fixture_id, match_status
        """
    ).fetchall()
    statuses_by_registry: dict[int, dict[str, int]] = defaultdict(dict)
    for row in status_rows:
        statuses_by_registry[int(row["registry_fixture_id"])][str(row["match_status"] or "unknown")] = int(
            row["c"]
        )

    sample_rows = conn.execute(
        """
        SELECT registry_fixture_id, home_goals, away_goals, match_status,
               MIN(source_file) AS source_file, MIN(raw_json) AS raw_json
        FROM historical_csv_odds_imports
        WHERE registry_fixture_id IS NOT NULL
          AND home_goals IS NOT NULL
          AND away_goals IS NOT NULL
          AND match_status IN ('FT', 'FT_PEN', 'AET', 'AWARDED')
          AND raw_json IS NOT NULL
        GROUP BY registry_fixture_id, home_goals, away_goals, match_status
        """
    ).fetchall()
    sample_index: dict[tuple[int, int, int, str], dict[str, Any]] = {}
    for row in sample_rows:
        key = (
            int(row["registry_fixture_id"]),
            int(row["home_goals"]),
            int(row["away_goals"]),
            str(row["match_status"]),
        )
        sample_index[key] = dict(row)

    canonical: dict[int, dict[str, Any]] = {}
    ambiguous_log: list[dict[str, Any]] = []
    no_result_log: list[dict[str, Any]] = []

    for registry_id in sorted(all_registry_ids):
        variants = by_registry.get(registry_id, [])
        if not variants:
            statuses = statuses_by_registry.get(registry_id, {})
            has_score = any(
                s not in ("NS", "POSTPONED", "CANCELLED", "POSTP", "CANCL", "AWAITING_UPDATES", "unknown")
                for s in statuses
            )
            no_result_log.append(
                {
                    "registry_fixture_id": registry_id,
                    "reason": "unsettled_or_missing_score" if has_score else "no_score_in_csv",
                    "statuses": statuses,
                }
            )
            continue

        goal_votes: Counter[tuple[int, int]] = Counter()
        status_by_goals: dict[tuple[int, int], Counter[str]] = defaultdict(Counter)
        score_variant_log: dict[str, int] = {}
        for row in variants:
            hg, ag = int(row["home_goals"]), int(row["away_goals"])
            st = str(row["match_status"])
            cnt = int(row["c"])
            goal_votes[(hg, ag)] += cnt
            status_by_goals[(hg, ag)][st] += cnt
            score_variant_log[f"{hg}-{ag}@{st}"] = cnt

        if len(goal_votes) > 1:
            ambiguous_log.append({"registry_fixture_id": registry_id, "scores": score_variant_log})
            top_count = goal_votes.most_common(1)[0][1]
            if len(goal_votes) > 1 and goal_votes.most_common(2)[1][1] == top_count:
                ambiguous_log.append(
                    {
                        "registry_fixture_id": registry_id,
                        "reason": "ambiguous_score_tie",
                        "goal_votes": {f"{k[0]}-{k[1]}": v for k, v in goal_votes.items()},
                    }
                )
                continue

        hg, ag = goal_votes.most_common(1)[0][0]
        st = status_by_goals[(hg, ag)].most_common(1)[0][0]
        sample = sample_index.get((registry_id, hg, ag, st), {})
        source_file = sample.get("source_file")
        corners, ht = _extract_corners_and_ht(sample.get("raw_json"))
        raw_payload: dict[str, Any] = {}
        if sample.get("raw_json"):
            try:
                raw_payload = json.loads(sample["raw_json"])
            except json.JSONDecodeError:
                raw_payload = {}

        labels = build_result_labels(hg, ag, match_status=st, ht_score=ht, corners_total=corners)
        canonical[registry_id] = {
            "registry_fixture_id": registry_id,
            "source": SOURCE,
            "source_file": source_file,
            "raw_result_json": json.dumps(
                {
                    "home_goals": hg,
                    "away_goals": ag,
                    "match_status": st,
                    "ht_score": ht,
                    "corners_total": corners,
                    "csv_fields_used": ["Status", "Home Goals", "Away Goals", "Corners", "HT Score"],
                    "csv_sample": {
                        k: raw_payload.get(k)
                        for k in (
                            "Status",
                            "Home Goals",
                            "Away Goals",
                            "Corners",
                            "HT Score",
                            "Outcome",
                            "Fixture",
                            "Kickoff",
                        )
                        if k in raw_payload
                    },
                },
                ensure_ascii=False,
            ),
            "dedup_key": _dedup_key(registry_id, SOURCE),
            **labels,
        }

    return canonical, ambiguous_log, no_result_log


def build_and_insert_historical_results(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
) -> tuple[ResultsBuildStats, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    ensure_historical_fixture_results_table(conn)
    stats = ResultsBuildStats()

    field_audit = inspect_csv_result_fields(conn)
    stats.csv_result_fields_present = bool(field_audit.get("present"))
    if not stats.csv_result_fields_present:
        stats.errors.append(f"csv_result_fields_missing: {field_audit}")
        return stats, [], [], field_audit

    stats.registry_total = int(
        conn.execute("SELECT COUNT(*) AS c FROM historical_fixture_registry").fetchone()["c"]
    )
    stats.odds_rows_scanned = int(
        conn.execute("SELECT COUNT(*) AS c FROM historical_csv_odds_imports").fetchone()["c"]
    )

    canonical, ambiguous_log, no_result_log = _aggregate_registry_scores(conn)
    stats.settled_candidate_fixtures = len(canonical)
    stats.results_skipped_ambiguous = sum(
        1 for a in ambiguous_log if a.get("reason") == "ambiguous_score_tie"
    )
    stats.results_skipped_unsettled = sum(
        1 for n in no_result_log if n.get("reason") == "unsettled_or_missing_score"
    )
    stats.results_skipped_no_score = sum(
        1 for n in no_result_log if n.get("reason") == "no_score_in_csv"
    )

    now = _utc_now()
    insert_sql = """
        INSERT OR IGNORE INTO historical_fixture_results (
            registry_fixture_id, source, home_goals, away_goals, total_goals,
            match_status, ht_score, ht_home_goals, ht_away_goals, corners_total,
            result_1x2, btts_actual, over_15_actual, over_25_actual, over_35_actual,
            corners_over_85_actual, corners_over_95_actual, corners_over_105_actual,
            source_file, raw_result_json, dedup_key, created_at, updated_at
        ) VALUES (
            :registry_fixture_id, :source, :home_goals, :away_goals, :total_goals,
            :match_status, :ht_score, :ht_home_goals, :ht_away_goals, :corners_total,
            :result_1x2, :btts_actual, :over_15_actual, :over_25_actual, :over_35_actual,
            :corners_over_85_actual, :corners_over_95_actual, :corners_over_105_actual,
            :source_file, :raw_result_json, :dedup_key, :created_at, :updated_at
        )
    """

    payloads = []
    for payload in canonical.values():
        payload["created_at"] = now
        payload["updated_at"] = now
        payloads.append(payload)
        if dry_run:
            stats.results_inserted += 1

    if not dry_run and payloads:
        before_count = conn.execute("SELECT COUNT(*) AS c FROM historical_fixture_results").fetchone()["c"]
        conn.executemany(insert_sql, payloads)
        after_count = conn.execute("SELECT COUNT(*) AS c FROM historical_fixture_results").fetchone()["c"]
        stats.results_inserted = after_count - before_count
        stats.results_skipped_duplicate = len(payloads) - stats.results_inserted

    if not dry_run:
        conn.commit()

    readiness = query_backtest_readiness(conn)
    return stats, ambiguous_log, no_result_log, readiness


def query_backtest_readiness(conn: sqlite3.Connection) -> dict[str, Any]:
    results_count = conn.execute("SELECT COUNT(*) AS c FROM historical_fixture_results").fetchone()["c"]
    registry_count = conn.execute("SELECT COUNT(*) AS c FROM historical_fixture_registry").fetchone()["c"]
    joinable = conn.execute(
        """
        SELECT COUNT(DISTINCT o.id) AS c
        FROM historical_csv_odds_imports o
        INNER JOIN historical_fixture_results r ON r.registry_fixture_id = o.registry_fixture_id
        """
    ).fetchone()["c"]
    by_market = [
        dict(row)
        for row in conn.execute(
            """
            SELECT o.market,
                   COUNT(*) AS odds_rows,
                   COUNT(DISTINCT o.registry_fixture_id) AS fixtures_with_results
            FROM historical_csv_odds_imports o
            INNER JOIN historical_fixture_results r ON r.registry_fixture_id = o.registry_fixture_id
            GROUP BY o.market
            ORDER BY odds_rows DESC
            """
        ).fetchall()
    ]
    label_dist = [
        dict(row)
        for row in conn.execute(
            """
            SELECT result_1x2, COUNT(*) AS c
            FROM historical_fixture_results
            GROUP BY result_1x2
            ORDER BY c DESC
            """
        ).fetchall()
    ]
    return {
        "registry_fixtures": int(registry_count),
        "fixtures_with_results": int(results_count),
        "registry_coverage_pct": round(100.0 * int(results_count) / max(int(registry_count), 1), 2),
        "odds_rows_joinable_to_results": int(joinable),
        "odds_join_coverage_pct": round(100.0 * int(joinable) / 2063334, 2),
        "by_market": by_market,
        "result_1x2_distribution": label_dist,
    }


def backup_database_data1d(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"football_intelligence_pre_data1d_{stamp}.db"
    dest.write_bytes(db_path.read_bytes())
    return dest


__all__ = [
    "backup_database_data1d",
    "build_and_insert_historical_results",
    "build_result_labels",
    "ensure_historical_fixture_results_table",
    "inspect_csv_result_fields",
    "query_backtest_readiness",
]

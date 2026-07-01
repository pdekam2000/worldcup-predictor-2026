"""PHASE DATA-1G — Clean pre-match odds dataset (derived staging, no API)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from worldcup_predictor.research.historical_odds_baseline_backtest import (
    BetAccumulator,
    _pick_odds,
    _strategy_filters,
    evaluate_selection,
    odds_band,
)

STRATEGIES_AD = (
    "A_all_selections",
    "B_odds_gte_2",
    "C_odds_gte_3_5",
    "D_odds_3_5_to_12",
)

DATA_1G_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS historical_csv_odds_prematch_clean (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_odds_id INTEGER NOT NULL UNIQUE,
        registry_fixture_id INTEGER NOT NULL,
        provider TEXT NOT NULL,
        market TEXT NOT NULL,
        selection TEXT NOT NULL,
        league TEXT,
        season TEXT,
        bookmaker TEXT,
        kickoff_utc TEXT NOT NULL,
        kickoff_unix INTEGER NOT NULL,
        closing_unix INTEGER NOT NULL,
        opening_unix INTEGER,
        closing_odds REAL NOT NULL,
        opening_odds REAL,
        source_file TEXT,
        prematch_verified INTEGER NOT NULL DEFAULT 1,
        build_batch TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (source_odds_id) REFERENCES historical_csv_odds_imports(id),
        FOREIGN KEY (registry_fixture_id) REFERENCES historical_fixture_registry(registry_fixture_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prematch_clean_registry
    ON historical_csv_odds_prematch_clean(registry_fixture_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prematch_clean_market
    ON historical_csv_odds_prematch_clean(market)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prematch_clean_kickoff_unix
    ON historical_csv_odds_prematch_clean(kickoff_unix)
    """,
)

CLEAN_JOIN_SQL = """
    SELECT
        c.source_odds_id AS odds_id,
        c.registry_fixture_id,
        c.market,
        c.selection,
        c.source_file,
        c.opening_odds,
        c.closing_odds,
        c.league,
        c.season,
        c.kickoff_unix,
        c.closing_unix,
        res.home_goals,
        res.away_goals,
        res.total_goals,
        res.result_1x2,
        res.btts_actual,
        res.over_15_actual,
        res.over_25_actual,
        res.over_35_actual,
        res.corners_total,
        res.ht_home_goals,
        res.ht_away_goals
    FROM historical_csv_odds_prematch_clean c
    INNER JOIN historical_fixture_registry r ON r.registry_fixture_id = c.registry_fixture_id
    INNER JOIN historical_fixture_results res ON res.registry_fixture_id = c.registry_fixture_id
"""

RAW_JOIN_SQL = """
    SELECT
        o.id AS odds_id,
        o.registry_fixture_id,
        o.market,
        o.selection,
        o.source_file,
        o.opening_odds,
        o.closing_odds,
        o.league,
        o.season,
        o.kickoff_utc,
        o.closing_unix,
        o.opening_unix,
        res.home_goals,
        res.away_goals,
        res.total_goals,
        res.result_1x2,
        res.btts_actual,
        res.over_15_actual,
        res.over_25_actual,
        res.over_35_actual,
        res.corners_total,
        res.ht_home_goals,
        res.ht_away_goals
    FROM historical_csv_odds_imports o
    INNER JOIN historical_fixture_registry r ON r.registry_fixture_id = o.registry_fixture_id
    INNER JOIN historical_fixture_results res ON res.registry_fixture_id = o.registry_fixture_id
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def kickoff_to_unix(kickoff_utc: str | None) -> int | None:
    if not kickoff_utc:
        return None
    text = kickoff_utc.strip().replace("Z", "+00:00")
    try:
        if "T" in text:
            dt = datetime.fromisoformat(text)
        else:
            dt = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
            dt = dt.replace(tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, TypeError, OSError):
        return None


def is_prematch_row(row: dict[str, Any]) -> tuple[bool, str]:
    closing_unix = row.get("closing_unix")
    opening_unix = row.get("opening_unix")
    peak_unix = row.get("peak_unix")
    kickoff_unix = row.get("kickoff_unix")
    if kickoff_unix is None:
        kickoff_unix = kickoff_to_unix(row.get("kickoff_utc"))
    if closing_unix is None:
        return False, "missing_closing_unix"
    if kickoff_unix is None:
        return False, "missing_kickoff_unix"
    if int(closing_unix) > int(kickoff_unix):
        return False, "closing_after_kickoff"
    if opening_unix is not None and int(opening_unix) > int(kickoff_unix):
        return False, "opening_after_kickoff"
    if peak_unix is not None and int(peak_unix) > int(kickoff_unix):
        return False, "peak_after_kickoff"
    closing_odds = row.get("closing_odds")
    if closing_odds is None or float(closing_odds) < 1.0:
        return False, "invalid_closing_odds"
    return True, "prematch_ok"


def ensure_prematch_clean_table(conn: sqlite3.Connection) -> None:
    for ddl in DATA_1G_DDL:
        conn.execute(ddl)
    conn.commit()


@dataclass
class CleanBuildStats:
    source_rows_scanned: int = 0
    rows_inserted: int = 0
    rows_skipped_duplicate: int = 0
    excluded_missing_closing_unix: int = 0
    excluded_missing_kickoff_unix: int = 0
    excluded_closing_after_kickoff: int = 0
    excluded_opening_after_kickoff: int = 0
    excluded_peak_after_kickoff: int = 0
    excluded_invalid_odds: int = 0
    excluded_no_registry: int = 0
    build_batch: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_rows_scanned": self.source_rows_scanned,
            "rows_inserted": self.rows_inserted,
            "rows_skipped_duplicate": self.rows_skipped_duplicate,
            "excluded_missing_closing_unix": self.excluded_missing_closing_unix,
            "excluded_missing_kickoff_unix": self.excluded_missing_kickoff_unix,
            "excluded_closing_after_kickoff": self.excluded_closing_after_kickoff,
            "excluded_opening_after_kickoff": self.excluded_opening_after_kickoff,
            "excluded_peak_after_kickoff": self.excluded_peak_after_kickoff,
            "excluded_invalid_odds": self.excluded_invalid_odds,
            "excluded_no_registry": self.excluded_no_registry,
            "build_batch": self.build_batch,
            "retention_pct": round(
                100.0 * self.rows_inserted / max(self.source_rows_scanned, 1), 4
            ),
        }


def build_prematch_clean_dataset(conn: sqlite3.Connection, *, dry_run: bool = False) -> CleanBuildStats:
    ensure_prematch_clean_table(conn)
    stats = CleanBuildStats()
    stats.build_batch = hashlib.sha256(_utc_now().encode()).hexdigest()[:16]
    now = _utc_now()

    insert_sql = """
        INSERT OR IGNORE INTO historical_csv_odds_prematch_clean (
            source_odds_id, registry_fixture_id, provider, market, selection,
            league, season, bookmaker, kickoff_utc, kickoff_unix, closing_unix,
            opening_unix, closing_odds, opening_odds, source_file,
            prematch_verified, build_batch, created_at
        ) VALUES (
            :source_odds_id, :registry_fixture_id, :provider, :market, :selection,
            :league, :season, :bookmaker, :kickoff_utc, :kickoff_unix, :closing_unix,
            :opening_unix, :closing_odds, :opening_odds, :source_file,
            1, :build_batch, :created_at
        )
    """

    cur = conn.execute(
        """
        SELECT
            o.id, o.registry_fixture_id, o.provider, o.market, o.selection,
            o.league, o.season, o.bookmaker, o.kickoff_utc,
            o.opening_unix, o.closing_unix, o.peak_unix,
            o.opening_odds, o.closing_odds, o.source_file
        FROM historical_csv_odds_imports o
        WHERE o.registry_fixture_id IS NOT NULL
        """
    )

    payloads: list[dict[str, Any]] = []
    while True:
        batch = cur.fetchmany(50000)
        if not batch:
            break
        for row in batch:
            stats.source_rows_scanned += 1
            rec = dict(row)
            kickoff_unix = kickoff_to_unix(rec.get("kickoff_utc"))
            rec["kickoff_unix"] = kickoff_unix
            ok, reason = is_prematch_row(rec)
            if not ok:
                if reason == "missing_closing_unix":
                    stats.excluded_missing_closing_unix += 1
                elif reason == "missing_kickoff_unix":
                    stats.excluded_missing_kickoff_unix += 1
                elif reason == "closing_after_kickoff":
                    stats.excluded_closing_after_kickoff += 1
                elif reason == "opening_after_kickoff":
                    stats.excluded_opening_after_kickoff += 1
                elif reason == "peak_after_kickoff":
                    stats.excluded_peak_after_kickoff += 1
                else:
                    stats.excluded_invalid_odds += 1
                continue

            payloads.append(
                {
                    "source_odds_id": rec["id"],
                    "registry_fixture_id": rec["registry_fixture_id"],
                    "provider": rec["provider"],
                    "market": rec["market"],
                    "selection": rec["selection"],
                    "league": rec.get("league"),
                    "season": rec.get("season"),
                    "bookmaker": rec.get("bookmaker"),
                    "kickoff_utc": rec["kickoff_utc"],
                    "kickoff_unix": kickoff_unix,
                    "closing_unix": rec["closing_unix"],
                    "opening_unix": rec.get("opening_unix"),
                    "closing_odds": rec["closing_odds"],
                    "opening_odds": rec.get("opening_odds"),
                    "source_file": rec.get("source_file"),
                    "build_batch": stats.build_batch,
                    "created_at": now,
                }
            )

    if dry_run:
        stats.rows_inserted = len(payloads)
        return stats

    before = conn.execute("SELECT COUNT(1) AS c FROM historical_csv_odds_prematch_clean").fetchone()["c"]
    for i in range(0, len(payloads), 10000):
        conn.executemany(insert_sql, payloads[i : i + 10000])
    conn.commit()
    after = conn.execute("SELECT COUNT(1) AS c FROM historical_csv_odds_prematch_clean").fetchone()["c"]
    stats.rows_inserted = after - before
    stats.rows_skipped_duplicate = len(payloads) - stats.rows_inserted
    return stats


@dataclass
class AdBacktestState:
    label: str
    dataset_rows: int = 0
    evaluable_rows: int = 0
    strategies: dict[str, BetAccumulator] = field(default_factory=dict)
    by_market: dict[str, dict[str, BetAccumulator]] = field(default_factory=dict)
    by_league: dict[str, dict[str, BetAccumulator]] = field(default_factory=dict)
    by_season: dict[str, dict[str, BetAccumulator]] = field(default_factory=dict)
    by_odds_band: dict[str, dict[str, BetAccumulator]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for s in STRATEGIES_AD:
            self.strategies[s] = BetAccumulator()

    def _acc(self, bucket: dict[str, dict[str, BetAccumulator]], key: str, strategy: str) -> BetAccumulator:
        if key not in bucket:
            bucket[key] = {s: BetAccumulator() for s in STRATEGIES_AD}
        return bucket[key][strategy]

    def record(self, *, strategy: str, won: bool, odds: float, market: str, league: str | None, season: str | None) -> None:
        self.strategies[strategy].add(won, odds)
        self._acc(self.by_market, market, strategy).add(won, odds)
        self._acc(self.by_league, league or "unknown", strategy).add(won, odds)
        self._acc(self.by_season, season or "unknown", strategy).add(won, odds)
        self._acc(self.by_odds_band, odds_band(odds), strategy).add(won, odds)


def iter_join_rows(conn: sqlite3.Connection, join_sql: str, batch_size: int = 50000) -> Iterator[dict[str, Any]]:
    cur = conn.execute(join_sql)
    while True:
        batch = cur.fetchmany(batch_size)
        if not batch:
            break
        for row in batch:
            yield dict(row)


def run_ad_backtest(
    conn: sqlite3.Connection,
    *,
    join_sql: str,
    label: str,
    closing_only: bool = False,
) -> AdBacktestState:
    state = AdBacktestState(label=label)
    for row in iter_join_rows(conn, join_sql):
        state.dataset_rows += 1
        won = evaluate_selection(
            market=row["market"],
            selection=row["selection"],
            source_file=row.get("source_file") or "",
            home_goals=int(row["home_goals"]),
            away_goals=int(row["away_goals"]),
            total_goals=int(row["total_goals"]),
            result_1x2=str(row["result_1x2"]),
            btts_actual=int(row["btts_actual"]),
            over_15_actual=int(row["over_15_actual"]),
            over_25_actual=int(row["over_25_actual"]),
            over_35_actual=int(row["over_35_actual"]),
            corners_total=row["corners_total"],
            ht_home_goals=row["ht_home_goals"],
            ht_away_goals=row["ht_away_goals"],
        )
        if won is None:
            continue
        state.evaluable_rows += 1

        if closing_only:
            odds = row.get("closing_odds")
            odds = float(odds) if odds and float(odds) >= 1.0 else None
        else:
            odds = _pick_odds(row, closing_only=False, opening_only=False)

        if odds is None:
            continue

        for strategy in STRATEGIES_AD:
            if not _strategy_filters(strategy, odds):
                continue
            state.record(
                strategy=strategy,
                won=bool(won),
                odds=odds,
                market=str(row["market"]),
                league=row.get("league"),
                season=row.get("season"),
            )
    return state


def summarize_ad_backtest(state: AdBacktestState) -> dict[str, Any]:
    def nested(bucket: dict[str, dict[str, BetAccumulator]]) -> dict[str, Any]:
        return {k: {s: acc.to_metrics() for s, acc in v.items()} for k, v in bucket.items()}

    return {
        "label": state.label,
        "dataset_rows": state.dataset_rows,
        "evaluable_rows": state.evaluable_rows,
        "strategies": {s: state.strategies[s].to_metrics() for s in STRATEGIES_AD},
        "by_market": nested(state.by_market),
        "by_league_top20": dict(
            sorted(
                ((k, {s: v[s].to_metrics() for s in STRATEGIES_AD}) for k, v in state.by_league.items()),
                key=lambda x: x[1].get("A_all_selections", {}).get("bets", 0),
                reverse=True,
            )[:20]
        ),
        "by_season": nested(state.by_season),
        "by_odds_band": nested(state.by_odds_band),
    }


def audit_clean_table(conn: sqlite3.Connection) -> dict[str, Any]:
    total = conn.execute("SELECT COUNT(1) AS c FROM historical_csv_odds_prematch_clean").fetchone()["c"]
    violations = conn.execute(
        """
        SELECT COUNT(1) AS c FROM historical_csv_odds_prematch_clean
        WHERE closing_unix > kickoff_unix
        """
    ).fetchone()["c"]
    source_count = conn.execute("SELECT COUNT(1) AS c FROM historical_csv_odds_imports").fetchone()["c"]
    return {
        "clean_rows": int(total),
        "source_rows_unchanged": int(source_count),
        "closing_after_kickoff_violations": int(violations),
    }


__all__ = [
    "build_prematch_clean_dataset",
    "run_ad_backtest",
    "summarize_ad_backtest",
    "audit_clean_table",
    "ensure_prematch_clean_table",
    "is_prematch_row",
    "kickoff_to_unix",
    "CLEAN_JOIN_SQL",
    "RAW_JOIN_SQL",
    "STRATEGIES_AD",
]

"""Immutable autonomous prediction snapshot store — Phase 61."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.migrations import ensure_schema_compat
from worldcup_predictor.database.repository import FootballIntelligenceRepository


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class AutonomousStore:
    """Append-only store for autonomous prediction snapshots and evaluations."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._repo = FootballIntelligenceRepository(self.settings.sqlite_path or None)
        self._conn = self._repo._conn  # noqa: SLF001
        ensure_schema_compat(self._conn)

    def has_recent_snapshot(
        self,
        fixture_id: int,
        engine: str,
        *,
        freshness_hours: int,
        market_id: str | None = None,
    ) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=freshness_hours)).replace(tzinfo=None).isoformat()
        query = """
            SELECT 1 FROM autonomous_prediction_snapshots
            WHERE fixture_id = ? AND engine = ? AND created_at >= ?
        """
        params: list[Any] = [int(fixture_id), engine, cutoff]
        if market_id:
            query += " AND market_id = ?"
            params.append(market_id)
        query += " LIMIT 1"
        row = self._conn.execute(query, params).fetchone()
        return row is not None

    def insert_snapshot(
        self,
        *,
        fixture_id: int,
        competition_key: str,
        engine: str,
        market_id: str,
        prediction: dict[str, Any],
        season: int | None = None,
        league_id: int | None = None,
        home_team: str | None = None,
        away_team: str | None = None,
        kickoff_utc: str | None = None,
        fixture_status: str | None = None,
        confidence: float | None = None,
        tier: str | None = None,
        odds_decimal: float | None = None,
        generated_by: str = "autonomous_scheduler",
        source: str = "production",
        is_user_visible: bool = False,
    ) -> tuple[int | None, str]:
        created_at = _utc_now()
        pred_json = json.dumps(prediction, default=str)
        phash = _payload_hash(prediction)
        snapshot_key = f"{fixture_id}:{engine}:{market_id}:{created_at}:{phash[:8]}"
        try:
            cur = self._conn.execute(
                """
                INSERT INTO autonomous_prediction_snapshots (
                    snapshot_key, fixture_id, competition_key, season, league_id,
                    home_team, away_team, kickoff_utc, fixture_status,
                    engine, market_id, prediction_json, confidence, tier, odds_decimal,
                    generated_by, source, is_user_visible, is_immutable, created_at, payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    snapshot_key,
                    int(fixture_id),
                    competition_key,
                    season,
                    league_id,
                    home_team,
                    away_team,
                    kickoff_utc,
                    fixture_status,
                    engine,
                    market_id,
                    pred_json,
                    confidence,
                    tier,
                    odds_decimal,
                    generated_by,
                    source,
                    1 if is_user_visible else 0,
                    created_at,
                    phash,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid), "inserted"
        except sqlite3.IntegrityError:
            return None, "duplicate_snapshot_key"

    def list_snapshots(
        self,
        *,
        fixture_id: int | None = None,
        engine: str | None = None,
        market_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM autonomous_prediction_snapshots WHERE 1=1"
        params: list[Any] = []
        if fixture_id is not None:
            query += " AND fixture_id = ?"
            params.append(int(fixture_id))
        if engine:
            query += " AND engine = ?"
            params.append(engine)
        if market_id:
            query += " AND market_id = ?"
            params.append(market_id)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
        rows = self._conn.execute(query, params).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["prediction"] = json.loads(item.pop("prediction_json"))
            except (json.JSONDecodeError, TypeError):
                item["prediction"] = {}
            out.append(item)
        return out

    def list_snapshots_needing_evaluation(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT s.*
            FROM autonomous_prediction_snapshots s
            LEFT JOIN autonomous_snapshot_evaluations e ON e.snapshot_id = s.id
            WHERE e.id IS NULL
            ORDER BY s.created_at ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["prediction"] = json.loads(item.pop("prediction_json"))
            except (json.JSONDecodeError, TypeError):
                item["prediction"] = {}
            out.append(item)
        return out

    def upsert_evaluation(
        self,
        *,
        snapshot_id: int,
        fixture_id: int,
        engine: str,
        market_id: str,
        status: str,
        evaluation_reason: str | None = None,
        actual: dict[str, Any] | None = None,
    ) -> bool:
        try:
            self._conn.execute(
                """
                INSERT INTO autonomous_snapshot_evaluations (
                    snapshot_id, fixture_id, engine, market_id, status,
                    evaluation_reason, actual_json, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(snapshot_id),
                    int(fixture_id),
                    engine,
                    market_id,
                    status,
                    evaluation_reason,
                    json.dumps(actual or {}, default=str),
                    _utc_now(),
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def save_certification_report(self, report: dict[str, Any]) -> int:
        cur = self._conn.execute(
            "INSERT INTO autonomous_certification_runs (run_at, report_json) VALUES (?, ?)",
            (_utc_now(), json.dumps(report, default=str)),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def latest_certification_report(self) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM autonomous_certification_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        try:
            item["report"] = json.loads(item.pop("report_json"))
        except (json.JSONDecodeError, TypeError):
            item["report"] = {}
        return item

    def start_cycle_run(self) -> int:
        cur = self._conn.execute(
            "INSERT INTO autonomous_cycle_runs (started_at, status) VALUES (?, ?)",
            (_utc_now(), "running"),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def finish_cycle_run(self, cycle_id: int, *, status: str, report: dict[str, Any]) -> None:
        self._conn.execute(
            """
            UPDATE autonomous_cycle_runs
            SET finished_at = ?, status = ?, report_json = ?
            WHERE id = ?
            """,
            (_utc_now(), status, json.dumps(report, default=str), int(cycle_id)),
        )
        self._conn.commit()

    def aggregate_performance(
        self,
        *,
        engine: str | None = None,
        market_id: str | None = None,
        competition_key: str | None = None,
        rolling_days: int | None = None,
    ) -> dict[str, Any]:
        query = """
            SELECT e.status, COUNT(*) AS c
            FROM autonomous_snapshot_evaluations e
            JOIN autonomous_prediction_snapshots s ON s.id = e.snapshot_id
            WHERE 1=1
        """
        params: list[Any] = []
        if engine:
            query += " AND e.engine = ?"
            params.append(engine)
        if market_id:
            query += " AND e.market_id = ?"
            params.append(market_id)
        if competition_key:
            query += " AND s.competition_key = ?"
            params.append(competition_key)
        if rolling_days:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=rolling_days)).replace(tzinfo=None).isoformat()
            query += " AND e.evaluated_at >= ?"
            params.append(cutoff)
        query += " GROUP BY e.status"
        rows = self._conn.execute(query, params).fetchall()
        counts = {str(r["status"]): int(r["c"]) for r in rows}
        correct = counts.get("correct", 0)
        wrong = counts.get("wrong", 0)
        pending = counts.get("pending", 0)
        evaluated = correct + wrong
        winrate = (correct / evaluated) if evaluated else None
        return {
            "counts": counts,
            "correct": correct,
            "wrong": wrong,
            "pending": pending,
            "evaluated": evaluated,
            "winrate": winrate,
        }

"""Phase A23 — append-only lifecycle SQLite store."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.migrations import ensure_schema_compat
from worldcup_predictor.database.repository import FootballIntelligenceRepository


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


class LifecycleStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._repo = FootballIntelligenceRepository(self.settings.sqlite_path or None)
        self._conn: sqlite3.Connection = self._repo._conn  # noqa: SLF001
        ensure_schema_compat(self._conn)

    def close(self) -> None:
        self._repo.close()

    def insert_record(
        self,
        *,
        record_key: str,
        fixture_id: int,
        payload: dict[str, Any],
        lifecycle_state: str,
        prediction_at: str,
        prediction_source: str,
        competition_key: str | None = None,
        season: int | None = None,
        home_team: str | None = None,
        away_team: str | None = None,
        kickoff_utc: str | None = None,
        prediction_version: str | None = None,
        model_version: str | None = None,
        engine: str | None = None,
        snapshot_id: str | None = None,
        confidence: float | None = None,
        bet_quality_score: float | None = None,
        tier: str | None = None,
        best_pick: str | None = None,
        best_value: str | None = None,
        publication_overlay: dict[str, Any] | None = None,
        predops_snapshot: dict[str, Any] | None = None,
        egie_snapshot: dict[str, Any] | None = None,
        paper_betting_flag: bool = False,
        combo_recommended_flag: bool = False,
        owner_notes: str | None = None,
        audit: dict[str, Any] | None = None,
        shadow_fixture_ref: int | None = None,
    ) -> int | None:
        """Append-only insert; returns record id or None if duplicate record_key."""
        now = _utc_now()
        try:
            cur = self._conn.execute(
                """
                INSERT INTO prediction_lifecycle_records (
                    record_key, fixture_id, competition_key, season,
                    home_team, away_team, kickoff_utc, lifecycle_state,
                    prediction_at, prediction_version, prediction_source,
                    model_version, engine, snapshot_id, confidence,
                    bet_quality_score, tier, best_pick, best_value,
                    payload_json, publication_overlay_json, predops_snapshot_json,
                    egie_snapshot_json, paper_betting_flag, combo_recommended_flag,
                    owner_notes, audit_json, shadow_fixture_ref, created_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    record_key,
                    fixture_id,
                    competition_key,
                    season,
                    home_team,
                    away_team,
                    kickoff_utc,
                    lifecycle_state,
                    prediction_at,
                    prediction_version,
                    prediction_source,
                    model_version,
                    engine,
                    snapshot_id,
                    confidence,
                    bet_quality_score,
                    tier,
                    best_pick,
                    best_value,
                    json.dumps(payload, separators=(",", ":"), default=str),
                    json.dumps(publication_overlay or {}, separators=(",", ":"), default=str)
                    if publication_overlay
                    else None,
                    json.dumps(predops_snapshot or {}, separators=(",", ":"), default=str)
                    if predops_snapshot
                    else None,
                    json.dumps(egie_snapshot or {}, separators=(",", ":"), default=str)
                    if egie_snapshot
                    else None,
                    1 if paper_betting_flag else 0,
                    1 if combo_recommended_flag else 0,
                    owner_notes,
                    json.dumps(audit or {}, separators=(",", ":"), default=str) if audit else None,
                    shadow_fixture_ref,
                    now,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def add_event(
        self,
        *,
        fixture_id: int,
        event_type: str,
        lifecycle_state: str,
        event_at: str | None = None,
        summary: str | None = None,
        pick_snapshot: str | None = None,
        record_id: int | None = None,
        meta: dict[str, Any] | None = None,
    ) -> int:
        now = _utc_now()
        cur = self._conn.execute(
            """
            INSERT INTO prediction_lifecycle_events (
                fixture_id, record_id, event_at, event_type, lifecycle_state,
                summary, pick_snapshot, meta_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fixture_id,
                record_id,
                event_at or now,
                event_type,
                lifecycle_state,
                summary,
                pick_snapshot,
                json.dumps(meta or {}, separators=(",", ":"), default=str) if meta else None,
                now,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_latest_record(self, fixture_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT * FROM prediction_lifecycle_records
            WHERE fixture_id = ?
            ORDER BY prediction_at DESC, id DESC
            LIMIT 1
            """,
            (fixture_id,),
        ).fetchone()
        return self._row_to_record(row) if row else None

    def list_records_for_fixture(self, fixture_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM prediction_lifecycle_records
            WHERE fixture_id = ?
            ORDER BY prediction_at ASC, id ASC
            LIMIT ?
            """,
            (fixture_id, limit),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_events_for_fixture(self, fixture_id: int, *, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM prediction_lifecycle_events
            WHERE fixture_id = ?
            ORDER BY event_at ASC, id ASC
            LIMIT ?
            """,
            (fixture_id, limit),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            if item.get("meta_json"):
                try:
                    item["meta"] = json.loads(item["meta_json"])
                except json.JSONDecodeError:
                    item["meta"] = {}
            out.append(item)
        return out

    def upsert_fixture_results(
        self,
        fixture_id: int,
        *,
        competition_key: str | None,
        ft_score: str | None,
        ht_score: str | None,
        winner: str | None,
        btts_result: str | None,
        over_under_result: str | None,
        correct_score_result: str | None,
        goal_timing_result: str | None,
        first_goal_team_result: str | None,
        goalscorer_results: dict[str, Any] | None,
        markets: dict[str, Any],
    ) -> None:
        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO prediction_fixture_results (
                fixture_id, competition_key, ft_score, ht_score, winner,
                btts_result, over_under_result, correct_score_result,
                goal_timing_result, first_goal_team_result, goalscorer_results_json,
                markets_json, captured_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id) DO UPDATE SET
                competition_key = excluded.competition_key,
                ft_score = excluded.ft_score,
                ht_score = excluded.ht_score,
                winner = excluded.winner,
                btts_result = excluded.btts_result,
                over_under_result = excluded.over_under_result,
                correct_score_result = excluded.correct_score_result,
                goal_timing_result = excluded.goal_timing_result,
                first_goal_team_result = excluded.first_goal_team_result,
                goalscorer_results_json = excluded.goalscorer_results_json,
                markets_json = excluded.markets_json,
                updated_at = excluded.updated_at
            """,
            (
                fixture_id,
                competition_key,
                ft_score,
                ht_score,
                winner,
                btts_result,
                over_under_result,
                correct_score_result,
                goal_timing_result,
                first_goal_team_result,
                json.dumps(goalscorer_results or {}, separators=(",", ":"), default=str),
                json.dumps(markets, separators=(",", ":"), default=str),
                now,
                now,
            ),
        )
        self._conn.commit()

    def insert_market_evaluation(
        self,
        *,
        eval_key: str,
        record_id: int,
        fixture_id: int,
        market_id: str,
        prediction: str | None,
        actual: str | None,
        result: str,
        color: str,
        confidence: float | None = None,
        bet_quality_score: float | None = None,
        odds: float | None = None,
        evaluated_at: str | None = None,
    ) -> int | None:
        now = evaluated_at or _utc_now()
        try:
            cur = self._conn.execute(
                """
                INSERT INTO prediction_market_evaluations (
                    eval_key, record_id, fixture_id, market_id, prediction, actual,
                    result, color, confidence, bet_quality_score, odds, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eval_key,
                    record_id,
                    fixture_id,
                    market_id,
                    prediction,
                    actual,
                    result,
                    color,
                    confidence,
                    bet_quality_score,
                    odds,
                    now,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            self._conn.execute(
                """
                UPDATE prediction_market_evaluations SET
                    prediction = ?, actual = ?, result = ?, color = ?,
                    confidence = ?, bet_quality_score = ?, odds = ?, evaluated_at = ?
                WHERE eval_key = ?
                """,
                (
                    prediction,
                    actual,
                    result,
                    color,
                    confidence,
                    bet_quality_score,
                    odds,
                    now,
                    eval_key,
                ),
            )
            self._conn.commit()
            return None

    def upsert_accuracy_rollup(
        self,
        *,
        market_id: str,
        window_key: str,
        predictions: int,
        correct: int,
        wrong: int,
        pending: int,
        push_count: int,
        void_count: int,
        accuracy: float | None,
        roi: float | None,
        avg_confidence: float | None,
        avg_bet_quality: float | None,
        avg_odds: float | None,
    ) -> None:
        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO prediction_market_accuracy_rollup (
                market_id, window_key, predictions, correct, wrong, pending,
                push_count, void_count, accuracy, roi, avg_confidence,
                avg_bet_quality, avg_odds, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_id, window_key) DO UPDATE SET
                predictions = excluded.predictions,
                correct = excluded.correct,
                wrong = excluded.wrong,
                pending = excluded.pending,
                push_count = excluded.push_count,
                void_count = excluded.void_count,
                accuracy = excluded.accuracy,
                roi = excluded.roi,
                avg_confidence = excluded.avg_confidence,
                avg_bet_quality = excluded.avg_bet_quality,
                avg_odds = excluded.avg_odds,
                updated_at = excluded.updated_at
            """,
            (
                market_id,
                window_key,
                predictions,
                correct,
                wrong,
                pending,
                push_count,
                void_count,
                accuracy,
                roi,
                avg_confidence,
                avg_bet_quality,
                avg_odds,
                now,
            ),
        )
        self._conn.commit()

    def insert_model_registry(
        self,
        *,
        record_id: int,
        fixture_id: int,
        model_role: str,
        model_version: str | None = None,
        publication_version: str | None = None,
        promotion_version: str | None = None,
        engine: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO prediction_model_registry (
                record_id, fixture_id, model_role, model_version,
                publication_version, promotion_version, engine, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                fixture_id,
                model_role,
                model_version,
                publication_version,
                promotion_version,
                engine,
                _utc_now(),
            ),
        )
        self._conn.commit()

    def insert_best_value_history(
        self,
        *,
        record_id: int,
        fixture_id: int,
        pick_type: str,
        pick_value: str | None,
        reason: str | None = None,
        quality_score: float | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO prediction_best_value_history (
                record_id, fixture_id, pick_type, pick_value, reason,
                quality_score, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (record_id, fixture_id, pick_type, pick_value, reason, quality_score, _utc_now()),
        )
        self._conn.commit()

    def insert_combo_history(
        self,
        *,
        combo_key: str,
        combo_type: str,
        legs: list[dict[str, Any]],
        quality: float | None = None,
        combined_odds: float | None = None,
        result: str | None = None,
        profit: float | None = None,
        status: str = "pending",
    ) -> int | None:
        now = _utc_now()
        try:
            cur = self._conn.execute(
                """
                INSERT INTO prediction_combo_history (
                    combo_key, combo_type, legs_json, quality, combined_odds,
                    result, profit, status, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    combo_key,
                    combo_type,
                    json.dumps(legs, separators=(",", ":"), default=str),
                    quality,
                    combined_odds,
                    result,
                    profit,
                    status,
                    now,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def insert_knowledge_record(
        self,
        *,
        knowledge_key: str,
        fixture_id: int,
        record_id: int | None,
        market_id: str | None,
        outcome: str,
        reason: str | None,
        confidence: float | None,
        quality_score: float | None,
        engine: str | None,
        knowledge: dict[str, Any],
    ) -> int | None:
        try:
            cur = self._conn.execute(
                """
                INSERT INTO prediction_knowledge_records (
                    knowledge_key, fixture_id, record_id, market_id, outcome,
                    reason, confidence, quality_score, engine, knowledge_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    knowledge_key,
                    fixture_id,
                    record_id,
                    market_id,
                    outcome,
                    reason,
                    confidence,
                    quality_score,
                    engine,
                    json.dumps(knowledge, separators=(",", ":"), default=str),
                    _utc_now(),
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def update_record_state(self, record_id: int, lifecycle_state: str) -> None:
        self._conn.execute(
            "UPDATE prediction_lifecycle_records SET lifecycle_state = ? WHERE id = ?",
            (lifecycle_state, record_id),
        )
        self._conn.commit()

    def count_records(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM prediction_lifecycle_records").fetchone()
        return int(row["c"]) if row else 0

    def count_market_evaluations(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM prediction_market_evaluations").fetchone()
        return int(row["c"]) if row else 0

    def list_accuracy_rollups(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM prediction_market_accuracy_rollup ORDER BY market_id, window_key"
        ).fetchall()
        return [dict(r) for r in rows]

    def search_records(
        self,
        *,
        team: str | None = None,
        competition_key: str | None = None,
        season: int | None = None,
        market: str | None = None,
        lifecycle_state: str | None = None,
        tier: str | None = None,
        model_version: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        min_confidence: float | None = None,
        min_bet_quality: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if team:
            clauses.append("(home_team LIKE ? OR away_team LIKE ?)")
            params.extend([f"%{team}%", f"%{team}%"])
        if competition_key:
            clauses.append("competition_key = ?")
            params.append(competition_key)
        if season is not None:
            clauses.append("season = ?")
            params.append(season)
        if lifecycle_state:
            clauses.append("lifecycle_state = ?")
            params.append(lifecycle_state)
        if tier:
            clauses.append("tier = ?")
            params.append(tier)
        if model_version:
            clauses.append("model_version = ?")
            params.append(model_version)
        if date_from:
            clauses.append("kickoff_utc >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("kickoff_utc <= ?")
            params.append(date_to)
        if min_confidence is not None:
            clauses.append("confidence >= ?")
            params.append(min_confidence)
        if min_bet_quality is not None:
            clauses.append("bet_quality_score >= ?")
            params.append(min_bet_quality)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT * FROM prediction_lifecycle_records
            {where}
            ORDER BY kickoff_utc DESC, prediction_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = self._conn.execute(sql, params).fetchall()
        records = [self._row_to_record(r) for r in rows]

        if market:
            filtered = []
            for rec in records:
                payload = rec.get("payload") or {}
                markets = payload.get("detailed_markets") or payload.get("probabilities") or {}
                if market.lower() in json.dumps(markets, default=str).lower():
                    filtered.append(rec)
            return filtered
        return records

    def get_fixture_results(self, fixture_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM prediction_fixture_results WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        for key in ("markets_json", "goalscorer_results_json"):
            if item.get(key):
                try:
                    item[key.replace("_json", "")] = json.loads(item[key])
                except json.JSONDecodeError:
                    pass
        return item

    def list_market_evaluations_for_fixture(self, fixture_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM prediction_market_evaluations
            WHERE fixture_id = ?
            ORDER BY market_id
            """,
            (fixture_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_pending_fixture_ids(self, *, limit: int = 200) -> list[int]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT fixture_id FROM prediction_lifecycle_records
            WHERE lifecycle_state NOT IN ('evaluated', 'archived')
            ORDER BY fixture_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [int(r["fixture_id"]) for r in rows]

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for key, target in (
            ("payload_json", "payload"),
            ("publication_overlay_json", "publication_overlay"),
            ("predops_snapshot_json", "predops_snapshot"),
            ("egie_snapshot_json", "egie_snapshot"),
            ("audit_json", "audit"),
        ):
            if item.get(key):
                try:
                    item[target] = json.loads(item[key])
                except json.JSONDecodeError:
                    item[target] = {}
        return item

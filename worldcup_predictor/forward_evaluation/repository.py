"""Forward evaluation freeze repository — insert, fetch, immutability guards."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.forward_evaluation.constants import EVAL_PENDING

FREEZE_SERVICE_BATCH = "FREEZE-SERVICE-v2"

_MUTABLE_COLUMNS = frozenset(
    {
        "evaluation_status",
        "quarantine_reason",
        "freeze_status",
    }
)

_INSERT_COLUMNS = (
    "prediction_id",
    "batch_id",
    "fixture_id",
    "match_name",
    "competition",
    "tier",
    "kickoff",
    "generated_at",
    "frozen_at",
    "prediction_mode",
    "odds_timestamp",
    "odds_home",
    "odds_draw",
    "odds_away",
    "bookmaker_count",
    "odds_freshness",
    "wde_decision",
    "ft_marginal_direction",
    "home_probability",
    "draw_probability",
    "away_probability",
    "wde_confidence",
    "effective_1x2",
    "btts_prediction",
    "btts_probability",
    "ou25_prediction",
    "over_probability",
    "under_probability",
    "top3_mass",
    "top5_mass",
    "top10_mass",
    "entropy",
    "lambda_home",
    "lambda_away",
    "total_lambda",
    "market_direction",
    "consensus",
    "data_quality",
    "warning_summary",
    "wde_model_version",
    "ecse_model_version",
    "ecse_top5_complete",
    "payload_hash",
    "evaluation_status",
    "validation_tier",
    "display_status",
    "competition_family",
    "domain_type",
    "validation_note",
    "provider_fixture_id",
    "league_id",
    "season",
    "home_team_name",
    "away_team_name",
    "prediction_scope",
    "public_visible",
    "worldcup_stored_prediction_id",
    "ecse_snapshot_id",
    "source_job_id",
    "odds_snapshot_id",
    "source_commit_sha",
    "source_payload_hash",
    "content_hash",
    "odds_fetched_at_utc",
    "last_valid_prematch_time_utc",
    "prediction_engine_version",
    "btts_model_version",
    "ou_model_version",
    "odds_freshness_status",
    "wde_payload_json",
    "btts_payload_json",
    "ou_payload_json",
    "ecse_payload_json",
    "complete_payload_json",
    "immutable",
    "freeze_version",
    "supersedes_freeze_id",
    "freeze_status",
    "wde_execution_status",
    "btts_execution_status",
    "ou_execution_status",
    "unavailable_fields_json",
    "quarantine_reason",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


class ForwardEvalRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def fetch_by_id(self, freeze_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM frozen_predictions WHERE prediction_id = ?",
            (freeze_id,),
        ).fetchone()
        return dict(row) if row else None

    def fetch_by_content_hash(self, content_hash: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM frozen_predictions WHERE content_hash = ? OR payload_hash = ? LIMIT 1",
            (content_hash, content_hash),
        ).fetchone()
        return dict(row) if row else None

    def fetch_by_fixture_and_hash(
        self, fixture_id: int, payload_hash: str
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM frozen_predictions WHERE fixture_id = ? AND payload_hash = ?",
            (int(fixture_id), payload_hash),
        ).fetchone()
        return dict(row) if row else None

    def list_by_fixture(self, fixture_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM frozen_predictions WHERE fixture_id = ? ORDER BY generated_at DESC, frozen_at DESC",
            (int(fixture_id),),
        ).fetchall()
        return [dict(r) for r in rows]

    def fetch_canonical_freeze(
        self,
        fixture_id: int,
        *,
        prediction_scope: str | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM frozen_predictions
            WHERE fixture_id = ?
              AND (freeze_status IS NULL OR freeze_status = 'ACTIVE')
              AND (quarantine_reason IS NULL OR quarantine_reason = '')
        """
        params: list[Any] = [int(fixture_id)]
        if prediction_scope:
            query += " AND prediction_scope = ?"
            params.append(prediction_scope)
        query += " ORDER BY generated_at DESC, frozen_at ASC LIMIT 1"
        row = self._conn.execute(query, params).fetchone()
        return dict(row) if row else None

    def detect_source_conflict(
        self,
        fixture_id: int,
        *,
        worldcup_stored_prediction_id: int,
        ecse_snapshot_id: int,
        source_payload_hash: str,
        content_hash: str,
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT * FROM frozen_predictions
            WHERE fixture_id = ?
              AND worldcup_stored_prediction_id = ?
              AND ecse_snapshot_id = ?
              AND source_payload_hash = ?
            ORDER BY frozen_at DESC
            LIMIT 1
            """,
            (
                int(fixture_id),
                int(worldcup_stored_prediction_id),
                int(ecse_snapshot_id),
                source_payload_hash,
            ),
        ).fetchone()
        if not row:
            return None
        existing = dict(row)
        existing_hash = existing.get("content_hash") or existing.get("payload_hash")
        if existing_hash and existing_hash != content_hash:
            return existing
        return None

    def insert_freeze(
        self,
        envelope: dict[str, Any],
        *,
        rank_rows: list[dict[str, Any]] | None = None,
    ) -> str:
        prediction_id = str(envelope.get("prediction_id") or uuid.uuid4())
        envelope = {**envelope, "prediction_id": prediction_id}
        if not envelope.get("batch_id"):
            envelope["batch_id"] = FREEZE_SERVICE_BATCH
        if envelope.get("immutable") is None:
            envelope["immutable"] = 1
        if not envelope.get("freeze_version"):
            envelope["freeze_version"] = "FORWARD-FREEZE-v2"
        if not envelope.get("freeze_status"):
            envelope["freeze_status"] = "ACTIVE"
        if not envelope.get("evaluation_status"):
            envelope["evaluation_status"] = EVAL_PENDING
        if not envelope.get("frozen_at"):
            envelope["frozen_at"] = _utc_now()

        content = envelope.get("content_hash") or envelope.get("payload_hash")
        if content:
            envelope["content_hash"] = content
            envelope["payload_hash"] = content

        cols_present = {c for c in _INSERT_COLUMNS if c in envelope}
        ordered = [c for c in _INSERT_COLUMNS if c in cols_present]
        placeholders = ",".join("?" for _ in ordered)
        col_sql = ",".join(ordered)
        values = [envelope[c] for c in ordered]
        self._conn.execute(
            f"INSERT INTO frozen_predictions ({col_sql}) VALUES ({placeholders})",
            values,
        )
        for row in rank_rows or envelope.get("rank_rows") or []:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO exact_score_rankings (prediction_id, fixture_id, rank, score, probability)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    prediction_id,
                    int(envelope["fixture_id"]),
                    int(row.get("rank") or 0),
                    str(row.get("score") or ""),
                    row.get("probability"),
                ),
            )
        self._conn.commit()
        return prediction_id

    def mark_quarantined(
        self,
        fixture_id: int,
        reason: str,
        *,
        prediction_scope: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        now = _utc_now()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO freeze_quarantine (fixture_id, prediction_scope, reason, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(fixture_id),
                prediction_scope,
                reason,
                json.dumps(detail or {}, default=str),
                now,
            ),
        )
        self._conn.commit()

    def update_evaluation_status(
        self,
        freeze_id: str,
        evaluation_status: str,
        *,
        quarantine_reason: str | None = None,
    ) -> bool:
        row = self.fetch_by_id(freeze_id)
        if not row:
            return False
        if int(row.get("immutable") or 0) == 1:
            self._conn.execute(
                "UPDATE frozen_predictions SET evaluation_status = ?, quarantine_reason = COALESCE(?, quarantine_reason) WHERE prediction_id = ?",
                (evaluation_status, quarantine_reason, freeze_id),
            )
            self._conn.commit()
            return True
        return False

    def update_mutable_fields(self, freeze_id: str, fields: dict[str, Any]) -> None:
        illegal = set(fields) - _MUTABLE_COLUMNS
        if illegal:
            raise ValueError(f"immutable_payload_update_blocked:{','.join(sorted(illegal))}")
        if not fields:
            return
        row = self.fetch_by_id(freeze_id)
        if not row:
            raise KeyError(freeze_id)
        if int(row.get("immutable") or 0) != 1:
            raise ValueError("freeze_not_marked_immutable")
        sets = ", ".join(f"{k} = ?" for k in fields)
        self._conn.execute(
            f"UPDATE frozen_predictions SET {sets} WHERE prediction_id = ?",
            [*fields.values(), freeze_id],
        )
        self._conn.commit()

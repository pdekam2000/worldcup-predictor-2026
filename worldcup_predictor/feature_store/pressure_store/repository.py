"""PostgreSQL persistence for Sportmonks Pressure feature store."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.session import postgres_configured, session_scope
from worldcup_predictor.feature_store.pressure_store.models import FixturePressureSummary, SportmonksPressureRecord

logger = logging.getLogger(__name__)


class SportmonksPressureRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return postgres_configured(self.settings)

    def upsert_records(self, records: list[SportmonksPressureRecord]) -> int:
        if not records:
            return 0
        if not self.configured:
            logger.warning("PostgreSQL not configured — skipping pressure record upsert")
            return 0

        written = 0
        with session_scope(self.settings) as session:
            for rec in records:
                session.execute(
                    text(
                        """
                        INSERT INTO fs_sportmonks_pressure_records (
                            id, sportmonks_fixture_id, fixture_id, league_id, season_id,
                            participant_id, team_id, minute, pressure_value, pressure_row_id,
                            captured_at, source, raw_reference, metadata
                        ) VALUES (
                            :id, :sportmonks_fixture_id, :fixture_id, :league_id, :season_id,
                            :participant_id, :team_id, :minute, :pressure_value, :pressure_row_id,
                            :captured_at, :source, :raw_reference, CAST(:metadata AS jsonb)
                        )
                        ON CONFLICT (sportmonks_fixture_id, pressure_row_id)
                        DO UPDATE SET
                            pressure_value = EXCLUDED.pressure_value,
                            minute = EXCLUDED.minute,
                            participant_id = EXCLUDED.participant_id,
                            team_id = EXCLUDED.team_id,
                            captured_at = EXCLUDED.captured_at,
                            source = EXCLUDED.source,
                            raw_reference = EXCLUDED.raw_reference,
                            metadata = EXCLUDED.metadata
                        """
                    ),
                    {
                        "id": uuid.uuid4(),
                        "sportmonks_fixture_id": rec.sportmonks_fixture_id,
                        "fixture_id": rec.fixture_id,
                        "league_id": rec.league_id,
                        "season_id": rec.season_id,
                        "participant_id": rec.participant_id,
                        "team_id": rec.team_id,
                        "minute": rec.minute,
                        "pressure_value": rec.pressure_value,
                        "pressure_row_id": rec.pressure_row_id,
                        "captured_at": rec.captured_at,
                        "source": rec.source,
                        "raw_reference": rec.raw_reference,
                        "metadata": json.dumps(rec.metadata or {}, default=str),
                    },
                )
                written += 1
        return written

    def upsert_fixture_summary(self, summary: FixturePressureSummary | dict[str, Any]) -> bool:
        if not self.configured:
            return False
        data = summary if isinstance(summary, dict) else summary.to_dict()
        now = datetime.now(timezone.utc)
        with session_scope(self.settings) as session:
            session.execute(
                text(
                    """
                    INSERT INTO fs_sportmonks_pressure_fixture_summary (
                        sportmonks_fixture_id, fixture_id, league_id, season_id,
                        home_team_id, away_team_id, match_started_at,
                        pressure_row_count, unique_minutes, first_goal_minute,
                        features_json, captured_at, updated_at, source
                    ) VALUES (
                        :sportmonks_fixture_id, :fixture_id, :league_id, :season_id,
                        :home_team_id, :away_team_id, :match_started_at,
                        :pressure_row_count, :unique_minutes, :first_goal_minute,
                        CAST(:features_json AS jsonb), :captured_at, :updated_at, :source
                    )
                    ON CONFLICT (sportmonks_fixture_id) DO UPDATE SET
                        fixture_id = EXCLUDED.fixture_id,
                        league_id = EXCLUDED.league_id,
                        season_id = EXCLUDED.season_id,
                        home_team_id = EXCLUDED.home_team_id,
                        away_team_id = EXCLUDED.away_team_id,
                        match_started_at = EXCLUDED.match_started_at,
                        pressure_row_count = EXCLUDED.pressure_row_count,
                        unique_minutes = EXCLUDED.unique_minutes,
                        first_goal_minute = EXCLUDED.first_goal_minute,
                        features_json = EXCLUDED.features_json,
                        captured_at = EXCLUDED.captured_at,
                        updated_at = EXCLUDED.updated_at,
                        source = EXCLUDED.source
                    """
                ),
                {
                    **data,
                    "features_json": json.dumps(data.get("features_json") or {}, default=str),
                    "updated_at": now,
                },
            )
        return True

    def delete_fixture_records(self, sportmonks_fixture_id: int) -> int:
        if not self.configured:
            return 0
        with session_scope(self.settings) as session:
            result = session.execute(
                text("DELETE FROM fs_sportmonks_pressure_records WHERE sportmonks_fixture_id = :fid"),
                {"fid": sportmonks_fixture_id},
            )
        return int(result.rowcount or 0)

    def delete_fixture_summary(self, sportmonks_fixture_id: int) -> bool:
        if not self.configured:
            return False
        with session_scope(self.settings) as session:
            session.execute(
                text("DELETE FROM fs_sportmonks_pressure_fixture_summary WHERE sportmonks_fixture_id = :fid"),
                {"fid": sportmonks_fixture_id},
            )
        return True

    def count_records_for_fixture(self, sportmonks_fixture_id: int) -> int:
        if not self.configured:
            return 0
        with session_scope(self.settings) as session:
            row = session.execute(
                text("SELECT COUNT(*) FROM fs_sportmonks_pressure_records WHERE sportmonks_fixture_id = :fid"),
                {"fid": sportmonks_fixture_id},
            ).scalar()
        return int(row or 0)

    def get_records_for_fixture(self, sportmonks_fixture_id: int) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        with session_scope(self.settings) as session:
            rows = session.execute(
                text(
                    """
                    SELECT * FROM fs_sportmonks_pressure_records
                    WHERE sportmonks_fixture_id = :fid
                    ORDER BY minute, participant_id
                    """
                ),
                {"fid": sportmonks_fixture_id},
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_fixture_summary(self, sportmonks_fixture_id: int) -> dict[str, Any] | None:
        if not self.configured:
            return None
        with session_scope(self.settings) as session:
            row = session.execute(
                text("SELECT * FROM fs_sportmonks_pressure_fixture_summary WHERE sportmonks_fixture_id = :fid"),
                {"fid": sportmonks_fixture_id},
            ).mappings().first()
        return dict(row) if row else None

    def list_fixture_summaries(
        self,
        *,
        league_id: int | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        clauses = ["pressure_row_count > 0"]
        params: dict[str, Any] = {"limit": limit}
        if league_id is not None:
            clauses.append("league_id = :league_id")
            params["league_id"] = league_id
        where = " AND ".join(clauses)
        with session_scope(self.settings) as session:
            rows = session.execute(
                text(
                    f"""
                    SELECT * FROM fs_sportmonks_pressure_fixture_summary
                    WHERE {where}
                    ORDER BY match_started_at NULLS LAST, sportmonks_fixture_id
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        return [dict(r) for r in rows]

    def imported_pressure_fixture_ids(self) -> set[int]:
        if not self.configured:
            return set()
        with session_scope(self.settings) as session:
            rows = session.execute(
                text(
                    """
                    SELECT sportmonks_fixture_id
                    FROM fs_sportmonks_pressure_fixture_summary
                    WHERE pressure_row_count > 0
                    """
                )
            ).all()
        return {int(r[0]) for r in rows}

    def manifest_job_stats(self, job_key_prefix: str = "phase54h4") -> list[dict[str, Any]]:
        if not self.configured:
            return []
        with session_scope(self.settings) as session:
            rows = session.execute(
                text(
                    """
                    SELECT job_key, status, COUNT(*) AS n
                    FROM fs_sportmonks_pressure_ingest_manifest
                    WHERE job_key LIKE :prefix
                    GROUP BY job_key, status
                    ORDER BY job_key, status
                    """
                ),
                {"prefix": f"{job_key_prefix}%"},
            ).mappings().all()
        return [dict(r) for r in rows]

    def manifest_status(self, job_key: str, sportmonks_fixture_id: int) -> str | None:
        if not self.configured:
            return None
        with session_scope(self.settings) as session:
            row = session.execute(
                text(
                    """
                    SELECT status FROM fs_sportmonks_pressure_ingest_manifest
                    WHERE job_key = :job_key AND sportmonks_fixture_id = :fid
                    """
                ),
                {"job_key": job_key, "fid": sportmonks_fixture_id},
            ).first()
        return str(row[0]) if row else None

    def write_manifest(
        self,
        *,
        job_key: str,
        sportmonks_fixture_id: int,
        status: str,
        league_id: int | None = None,
        season_id: int | None = None,
        api_calls: int = 0,
        records_written: int = 0,
        error: str | None = None,
    ) -> None:
        if not self.configured:
            return
        with session_scope(self.settings) as session:
            session.execute(
                text(
                    """
                    INSERT INTO fs_sportmonks_pressure_ingest_manifest (
                        id, job_key, league_id, season_id, sportmonks_fixture_id,
                        status, api_calls, records_written, error, processed_at
                    ) VALUES (
                        :id, :job_key, :league_id, :season_id, :sportmonks_fixture_id,
                        :status, :api_calls, :records_written, :error, :processed_at
                    )
                    ON CONFLICT (job_key, sportmonks_fixture_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        api_calls = EXCLUDED.api_calls,
                        records_written = EXCLUDED.records_written,
                        error = EXCLUDED.error,
                        processed_at = EXCLUDED.processed_at
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "job_key": job_key,
                    "league_id": league_id,
                    "season_id": season_id,
                    "sportmonks_fixture_id": sportmonks_fixture_id,
                    "status": status,
                    "api_calls": api_calls,
                    "records_written": records_written,
                    "error": error,
                    "processed_at": datetime.now(timezone.utc),
                },
            )

    def audit_coverage(self) -> dict[str, Any]:
        if not self.configured:
            return {"configured": False}
        try:
            with session_scope(self.settings) as session:
                stats = session.execute(
                    text(
                        """
                        SELECT
                            COUNT(*) AS record_count,
                            COUNT(DISTINCT sportmonks_fixture_id) AS fixture_count,
                            COUNT(DISTINCT league_id) AS league_count,
                            COUNT(DISTINCT season_id) AS season_count,
                            COUNT(DISTINCT participant_id) AS team_count,
                            AVG(minute) AS avg_minute,
                            MAX(minute) AS max_minute
                        FROM fs_sportmonks_pressure_records
                        """
                    )
                ).mappings().first()
                summary_stats = session.execute(
                    text(
                        """
                        SELECT
                            COUNT(*) AS summary_count,
                            AVG(pressure_row_count) AS avg_rows_per_fixture,
                            AVG(unique_minutes) AS avg_minutes_per_fixture
                        FROM fs_sportmonks_pressure_fixture_summary
                        """
                    )
                ).mappings().first()
                dupes = session.execute(
                    text(
                        """
                        SELECT sportmonks_fixture_id, pressure_row_id, COUNT(*) AS n
                        FROM fs_sportmonks_pressure_records
                        GROUP BY 1, 2
                        HAVING COUNT(*) > 1
                        LIMIT 5
                        """
                    )
                ).mappings().all()
            return {
                "configured": True,
                "tables_ready": True,
                "records": dict(stats) if stats else {},
                "summaries": dict(summary_stats) if summary_stats else {},
                "duplicate_groups_sample": [dict(d) for d in dupes],
            }
        except Exception as exc:
            logger.warning("Pressure feature store audit failed: %s", exc)
            return {"configured": True, "tables_ready": False, "error": str(exc)}

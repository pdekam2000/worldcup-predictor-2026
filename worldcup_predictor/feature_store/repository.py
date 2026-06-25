"""PostgreSQL persistence for Sportmonks xG feature store."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.session import postgres_configured, session_scope
from worldcup_predictor.feature_store.models import FixtureXgSummary, SportmonksXgRecord

logger = logging.getLogger(__name__)


class SportmonksXgRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return postgres_configured(self.settings)

    def upsert_records(self, records: list[SportmonksXgRecord]) -> int:
        if not records:
            return 0
        if not self.configured:
            logger.warning("PostgreSQL not configured — skipping xG record upsert")
            return 0

        written = 0
        with session_scope(self.settings) as session:
            for rec in records:
                session.execute(
                    text(
                        """
                        INSERT INTO fs_sportmonks_xg_records (
                            id, sportmonks_fixture_id, fixture_id, league_id, season_id,
                            home_team_id, away_team_id, participant_id, player_id,
                            record_type, metric_key, type_id, type_name, location,
                            xg_value, captured_at, source, raw_reference, metadata
                        ) VALUES (
                            :id, :sportmonks_fixture_id, :fixture_id, :league_id, :season_id,
                            :home_team_id, :away_team_id, :participant_id, :player_id,
                            :record_type, :metric_key, :type_id, :type_name, :location,
                            :xg_value, :captured_at, :source, :raw_reference, CAST(:metadata AS jsonb)
                        )
                        ON CONFLICT (sportmonks_fixture_id, record_type, metric_key, participant_id, player_id)
                        DO UPDATE SET
                            xg_value = EXCLUDED.xg_value,
                            captured_at = EXCLUDED.captured_at,
                            source = EXCLUDED.source,
                            raw_reference = EXCLUDED.raw_reference,
                            metadata = EXCLUDED.metadata,
                            type_id = EXCLUDED.type_id,
                            type_name = EXCLUDED.type_name,
                            location = EXCLUDED.location
                        """
                    ),
                    {
                        "id": uuid.uuid4(),
                        "sportmonks_fixture_id": rec.sportmonks_fixture_id,
                        "fixture_id": rec.fixture_id,
                        "league_id": rec.league_id,
                        "season_id": rec.season_id,
                        "home_team_id": rec.home_team_id,
                        "away_team_id": rec.away_team_id,
                        "participant_id": rec.participant_id,
                        "player_id": rec.player_id,
                        "record_type": rec.record_type,
                        "metric_key": rec.metric_key,
                        "type_id": rec.type_id,
                        "type_name": rec.type_name,
                        "location": rec.location,
                        "xg_value": rec.xg_value,
                        "captured_at": rec.captured_at,
                        "source": rec.source,
                        "raw_reference": rec.raw_reference,
                        "metadata": json.dumps(rec.metadata or {}, default=str),
                    },
                )
                written += 1
        return written

    def upsert_fixture_summary(self, summary: FixtureXgSummary | dict[str, Any]) -> bool:
        if not self.configured:
            return False
        data = summary if isinstance(summary, dict) else summary.to_dict()
        now = datetime.now(timezone.utc)
        with session_scope(self.settings) as session:
            session.execute(
                text(
                    """
                    INSERT INTO fs_sportmonks_xg_fixture_summary (
                        sportmonks_fixture_id, fixture_id, league_id, season_id,
                        home_team_id, away_team_id, match_started_at,
                        home_xg, away_xg, home_xga, away_xga, home_npxg, away_npxg,
                        xg_total, xg_difference,
                        home_team_recent_xg, away_team_recent_xg,
                        home_team_recent_xga, away_team_recent_xga,
                        attack_difference, defense_difference, momentum_difference,
                        aggregation_window, features_json, captured_at, updated_at, source
                    ) VALUES (
                        :sportmonks_fixture_id, :fixture_id, :league_id, :season_id,
                        :home_team_id, :away_team_id, :match_started_at,
                        :home_xg, :away_xg, :home_xga, :away_xga, :home_npxg, :away_npxg,
                        :xg_total, :xg_difference,
                        :home_team_recent_xg, :away_team_recent_xg,
                        :home_team_recent_xga, :away_team_recent_xga,
                        :attack_difference, :defense_difference, :momentum_difference,
                        :aggregation_window, CAST(:features_json AS jsonb), :captured_at, :updated_at, :source
                    )
                    ON CONFLICT (sportmonks_fixture_id) DO UPDATE SET
                        fixture_id = EXCLUDED.fixture_id,
                        home_xg = EXCLUDED.home_xg,
                        away_xg = EXCLUDED.away_xg,
                        home_xga = EXCLUDED.home_xga,
                        away_xga = EXCLUDED.away_xga,
                        home_npxg = EXCLUDED.home_npxg,
                        away_npxg = EXCLUDED.away_npxg,
                        xg_total = EXCLUDED.xg_total,
                        xg_difference = EXCLUDED.xg_difference,
                        home_team_recent_xg = EXCLUDED.home_team_recent_xg,
                        away_team_recent_xg = EXCLUDED.away_team_recent_xg,
                        home_team_recent_xga = EXCLUDED.home_team_recent_xga,
                        away_team_recent_xga = EXCLUDED.away_team_recent_xga,
                        attack_difference = EXCLUDED.attack_difference,
                        defense_difference = EXCLUDED.defense_difference,
                        momentum_difference = EXCLUDED.momentum_difference,
                        aggregation_window = EXCLUDED.aggregation_window,
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
        """Remove all xG records for a fixture (used on force re-import)."""
        if not self.configured:
            return 0
        with session_scope(self.settings) as session:
            result = session.execute(
                text("DELETE FROM fs_sportmonks_xg_records WHERE sportmonks_fixture_id = :fid"),
                {"fid": sportmonks_fixture_id},
            )
        return int(result.rowcount or 0)

    def delete_fixture_summary(self, sportmonks_fixture_id: int) -> bool:
        if not self.configured:
            return False
        with session_scope(self.settings) as session:
            session.execute(
                text("DELETE FROM fs_sportmonks_xg_fixture_summary WHERE sportmonks_fixture_id = :fid"),
                {"fid": sportmonks_fixture_id},
            )
        return True

    def count_records_by_metric(self) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        with session_scope(self.settings) as session:
            rows = session.execute(
                text(
                    """
                    SELECT metric_key, record_type, COUNT(*) AS n
                    FROM fs_sportmonks_xg_records
                    GROUP BY metric_key, record_type
                    ORDER BY n DESC
                    """
                )
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_records_for_fixture(self, sportmonks_fixture_id: int) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        with session_scope(self.settings) as session:
            rows = session.execute(
                text(
                    """
                    SELECT * FROM fs_sportmonks_xg_records
                    WHERE sportmonks_fixture_id = :fid
                    ORDER BY record_type, metric_key
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
                text("SELECT * FROM fs_sportmonks_xg_fixture_summary WHERE sportmonks_fixture_id = :fid"),
                {"fid": sportmonks_fixture_id},
            ).mappings().first()
        return dict(row) if row else None

    def get_team_match_history(
        self,
        team_id: int,
        *,
        league_id: int | None = None,
        limit: int = 20,
        before_started_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return prior fixture summaries where team participated, ordered by match date."""
        if not self.configured:
            return []
        clauses = ["(home_team_id = :team_id OR away_team_id = :team_id)"]
        params: dict[str, Any] = {"team_id": team_id, "limit": limit}
        if league_id is not None:
            clauses.append("league_id = :league_id")
            params["league_id"] = league_id
        if before_started_at is not None:
            clauses.append("(match_started_at IS NULL OR match_started_at < :before)")
            params["before"] = before_started_at
        where = " AND ".join(clauses)
        with session_scope(self.settings) as session:
            rows = session.execute(
                text(
                    f"""
                    SELECT * FROM fs_sportmonks_xg_fixture_summary
                    WHERE {where}
                    ORDER BY match_started_at NULLS LAST, sportmonks_fixture_id
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        return [dict(r) for r in rows]

    def manifest_status(self, job_key: str, sportmonks_fixture_id: int) -> str | None:
        if not self.configured:
            return None
        with session_scope(self.settings) as session:
            row = session.execute(
                text(
                    """
                    SELECT status FROM fs_sportmonks_xg_ingest_manifest
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
                    INSERT INTO fs_sportmonks_xg_ingest_manifest (
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

    def list_fixture_summaries(
        self,
        *,
        league_id: int | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        clauses = ["1=1"]
        params: dict[str, Any] = {"limit": limit}
        if league_id is not None:
            clauses.append("league_id = :league_id")
            params["league_id"] = league_id
        where = " AND ".join(clauses)
        with session_scope(self.settings) as session:
            rows = session.execute(
                text(
                    f"""
                    SELECT * FROM fs_sportmonks_xg_fixture_summary
                    WHERE {where}
                    ORDER BY match_started_at NULLS LAST, sportmonks_fixture_id
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        return [dict(r) for r in rows]

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
                            COUNT(DISTINCT participant_id) FILTER (WHERE participant_id IS NOT NULL) AS team_count,
                            COUNT(*) FILTER (WHERE record_type = 'player_xg') AS player_record_count
                        FROM fs_sportmonks_xg_records
                        """
                    )
                ).mappings().first()
                summary_stats = session.execute(
                    text(
                        """
                        SELECT
                            COUNT(*) AS summary_count,
                            COUNT(*) FILTER (WHERE home_team_recent_xg IS NOT NULL) AS with_rolling_xg
                        FROM fs_sportmonks_xg_fixture_summary
                        """
                    )
                ).mappings().first()
                dupes = session.execute(
                    text(
                        """
                        SELECT sportmonks_fixture_id, record_type, metric_key, participant_id, player_id, COUNT(*) AS n
                        FROM fs_sportmonks_xg_records
                        GROUP BY 1,2,3,4,5
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
            logger.warning("xG feature store audit failed: %s", exc)
            return {"configured": True, "tables_ready": False, "error": str(exc)}

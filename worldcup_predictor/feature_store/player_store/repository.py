"""PostgreSQL persistence for lineup / player feature store."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.session import postgres_configured, session_scope
from worldcup_predictor.feature_store.player_store.models import PlayerMatchStatRecord, PlayerRollingFeatureRecord

logger = logging.getLogger(__name__)


class PlayerFeatureRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return postgres_configured(self.settings)

    def upsert_match_stats(self, records: list[PlayerMatchStatRecord]) -> int:
        if not records or not self.configured:
            return 0
        written = 0
        with session_scope(self.settings) as session:
            for rec in records:
                session.execute(
                    text(
                        """
                        INSERT INTO fs_player_match_stats (
                            id, sportmonks_fixture_id, fixture_id, player_id, player_name,
                            team_id, position, starter, captain, minutes, goals, assists,
                            shots, shots_on_target, rating, xg, xa, yellow_cards, red_cards,
                            season_id, league_id, match_date, source, raw_reference,
                            metadata, captured_at
                        ) VALUES (
                            :id, :sportmonks_fixture_id, :fixture_id, :player_id, :player_name,
                            :team_id, :position, :starter, :captain, :minutes, :goals, :assists,
                            :shots, :shots_on_target, :rating, :xg, :xa, :yellow_cards, :red_cards,
                            :season_id, :league_id, :match_date, :source, :raw_reference,
                            CAST(:metadata AS jsonb), :captured_at
                        )
                        ON CONFLICT (sportmonks_fixture_id, player_id) DO UPDATE SET
                            player_name = EXCLUDED.player_name,
                            team_id = EXCLUDED.team_id,
                            position = EXCLUDED.position,
                            starter = EXCLUDED.starter,
                            captain = EXCLUDED.captain,
                            minutes = EXCLUDED.minutes,
                            goals = EXCLUDED.goals,
                            assists = EXCLUDED.assists,
                            shots = EXCLUDED.shots,
                            shots_on_target = EXCLUDED.shots_on_target,
                            rating = EXCLUDED.rating,
                            xg = EXCLUDED.xg,
                            xa = EXCLUDED.xa,
                            yellow_cards = EXCLUDED.yellow_cards,
                            red_cards = EXCLUDED.red_cards,
                            season_id = EXCLUDED.season_id,
                            league_id = EXCLUDED.league_id,
                            match_date = EXCLUDED.match_date,
                            source = EXCLUDED.source,
                            raw_reference = EXCLUDED.raw_reference,
                            metadata = EXCLUDED.metadata,
                            captured_at = EXCLUDED.captured_at
                        """
                    ),
                    {
                        "id": uuid.uuid4(),
                        "sportmonks_fixture_id": rec.sportmonks_fixture_id,
                        "fixture_id": rec.fixture_id,
                        "player_id": rec.player_id,
                        "player_name": rec.player_name,
                        "team_id": rec.team_id,
                        "position": rec.position,
                        "starter": rec.starter,
                        "captain": rec.captain,
                        "minutes": rec.minutes,
                        "goals": rec.goals,
                        "assists": rec.assists,
                        "shots": rec.shots,
                        "shots_on_target": rec.shots_on_target,
                        "rating": rec.rating,
                        "xg": rec.xg,
                        "xa": rec.xa,
                        "yellow_cards": rec.yellow_cards,
                        "red_cards": rec.red_cards,
                        "season_id": rec.season_id,
                        "league_id": rec.league_id,
                        "match_date": rec.match_date,
                        "source": rec.source,
                        "raw_reference": rec.raw_reference,
                        "metadata": json.dumps(rec.metadata or {}, default=str),
                        "captured_at": rec.captured_at,
                    },
                )
                written += 1
        return written

    def upsert_rolling_features(self, records: list[PlayerRollingFeatureRecord]) -> int:
        if not records or not self.configured:
            return 0
        written = 0
        with session_scope(self.settings) as session:
            for rec in records:
                session.execute(
                    text(
                        """
                        INSERT INTO fs_player_rolling_features (
                            id, sportmonks_fixture_id, fixture_id, player_id, team_id,
                            league_id, season_id, match_date,
                            goals_last_3, goals_last_5, goals_last_10, assists_last_5,
                            minutes_last_5, starts_last_5, shots_last_5, shots_on_target_last_5,
                            xg_last_5, xg_last_10, goals_per_90, xg_per_90,
                            starter_probability, recent_form_score,
                            starter, captain, position, position_group, formation,
                            goalkeeper_player_id, captain_player_id,
                            lineup_available, lineup_quality_score,
                            starting_xi_json, bench_json, metadata, source, captured_at
                        ) VALUES (
                            :id, :sportmonks_fixture_id, :fixture_id, :player_id, :team_id,
                            :league_id, :season_id, :match_date,
                            :goals_last_3, :goals_last_5, :goals_last_10, :assists_last_5,
                            :minutes_last_5, :starts_last_5, :shots_last_5, :shots_on_target_last_5,
                            :xg_last_5, :xg_last_10, :goals_per_90, :xg_per_90,
                            :starter_probability, :recent_form_score,
                            :starter, :captain, :position, :position_group, :formation,
                            :goalkeeper_player_id, :captain_player_id,
                            :lineup_available, :lineup_quality_score,
                            CAST(:starting_xi_json AS jsonb), CAST(:bench_json AS jsonb),
                            CAST(:metadata AS jsonb), :source, :captured_at
                        )
                        ON CONFLICT (sportmonks_fixture_id, player_id) DO UPDATE SET
                            team_id = EXCLUDED.team_id,
                            league_id = EXCLUDED.league_id,
                            season_id = EXCLUDED.season_id,
                            match_date = EXCLUDED.match_date,
                            goals_last_3 = EXCLUDED.goals_last_3,
                            goals_last_5 = EXCLUDED.goals_last_5,
                            goals_last_10 = EXCLUDED.goals_last_10,
                            assists_last_5 = EXCLUDED.assists_last_5,
                            minutes_last_5 = EXCLUDED.minutes_last_5,
                            starts_last_5 = EXCLUDED.starts_last_5,
                            shots_last_5 = EXCLUDED.shots_last_5,
                            shots_on_target_last_5 = EXCLUDED.shots_on_target_last_5,
                            xg_last_5 = EXCLUDED.xg_last_5,
                            xg_last_10 = EXCLUDED.xg_last_10,
                            goals_per_90 = EXCLUDED.goals_per_90,
                            xg_per_90 = EXCLUDED.xg_per_90,
                            starter_probability = EXCLUDED.starter_probability,
                            recent_form_score = EXCLUDED.recent_form_score,
                            starter = EXCLUDED.starter,
                            captain = EXCLUDED.captain,
                            position = EXCLUDED.position,
                            position_group = EXCLUDED.position_group,
                            formation = EXCLUDED.formation,
                            goalkeeper_player_id = EXCLUDED.goalkeeper_player_id,
                            captain_player_id = EXCLUDED.captain_player_id,
                            lineup_available = EXCLUDED.lineup_available,
                            lineup_quality_score = EXCLUDED.lineup_quality_score,
                            starting_xi_json = EXCLUDED.starting_xi_json,
                            bench_json = EXCLUDED.bench_json,
                            metadata = EXCLUDED.metadata,
                            source = EXCLUDED.source,
                            captured_at = EXCLUDED.captured_at
                        """
                    ),
                    {
                        "id": uuid.uuid4(),
                        "sportmonks_fixture_id": rec.sportmonks_fixture_id,
                        "fixture_id": rec.fixture_id,
                        "player_id": rec.player_id,
                        "team_id": rec.team_id,
                        "league_id": rec.league_id,
                        "season_id": rec.season_id,
                        "match_date": rec.match_date,
                        "goals_last_3": rec.goals_last_3,
                        "goals_last_5": rec.goals_last_5,
                        "goals_last_10": rec.goals_last_10,
                        "assists_last_5": rec.assists_last_5,
                        "minutes_last_5": rec.minutes_last_5,
                        "starts_last_5": rec.starts_last_5,
                        "shots_last_5": rec.shots_last_5,
                        "shots_on_target_last_5": rec.shots_on_target_last_5,
                        "xg_last_5": rec.xg_last_5,
                        "xg_last_10": rec.xg_last_10,
                        "goals_per_90": rec.goals_per_90,
                        "xg_per_90": rec.xg_per_90,
                        "starter_probability": rec.starter_probability,
                        "recent_form_score": rec.recent_form_score,
                        "starter": rec.starter,
                        "captain": rec.captain,
                        "position": rec.position,
                        "position_group": rec.position_group,
                        "formation": rec.formation,
                        "goalkeeper_player_id": rec.goalkeeper_player_id,
                        "captain_player_id": rec.captain_player_id,
                        "lineup_available": rec.lineup_available,
                        "lineup_quality_score": rec.lineup_quality_score,
                        "starting_xi_json": json.dumps(rec.starting_xi or []),
                        "bench_json": json.dumps(rec.bench or []),
                        "metadata": json.dumps(rec.metadata or {}, default=str),
                        "source": rec.source,
                        "captured_at": rec.captured_at,
                    },
                )
                written += 1
        return written

    def delete_fixture(self, sportmonks_fixture_id: int) -> None:
        if not self.configured:
            return
        with session_scope(self.settings) as session:
            session.execute(
                text("DELETE FROM fs_player_match_stats WHERE sportmonks_fixture_id = :fid"),
                {"fid": sportmonks_fixture_id},
            )
            session.execute(
                text("DELETE FROM fs_player_rolling_features WHERE sportmonks_fixture_id = :fid"),
                {"fid": sportmonks_fixture_id},
            )

    def imported_fixture_ids(self) -> set[int]:
        if not self.configured:
            return set()
        with session_scope(self.settings) as session:
            rows = session.execute(
                text(
                    """
                    SELECT DISTINCT sportmonks_fixture_id
                    FROM fs_player_match_stats
                    """
                )
            ).all()
        return {int(r[0]) for r in rows}

    def manifest_status(self, job_key: str, sportmonks_fixture_id: int) -> str | None:
        if not self.configured:
            return None
        with session_scope(self.settings) as session:
            row = session.execute(
                text(
                    """
                    SELECT status FROM fs_player_ingest_manifest
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
        player_rows: int = 0,
        rolling_rows: int = 0,
        error: str | None = None,
    ) -> None:
        if not self.configured:
            return
        with session_scope(self.settings) as session:
            session.execute(
                text(
                    """
                    INSERT INTO fs_player_ingest_manifest (
                        id, job_key, league_id, season_id, sportmonks_fixture_id,
                        status, player_rows, rolling_rows, error, processed_at
                    ) VALUES (
                        :id, :job_key, :league_id, :season_id, :sportmonks_fixture_id,
                        :status, :player_rows, :rolling_rows, :error, :processed_at
                    )
                    ON CONFLICT (job_key, sportmonks_fixture_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        player_rows = EXCLUDED.player_rows,
                        rolling_rows = EXCLUDED.rolling_rows,
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
                    "player_rows": player_rows,
                    "rolling_rows": rolling_rows,
                    "error": error,
                    "processed_at": datetime.now(timezone.utc),
                },
            )

    def load_player_history(
        self,
        player_id: int,
        *,
        before_date: datetime | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        clauses = ["player_id = :player_id"]
        params: dict[str, Any] = {"player_id": player_id, "limit": limit}
        if before_date is not None:
            clauses.append("match_date < :before_date")
            params["before_date"] = before_date
        where = " AND ".join(clauses)
        with session_scope(self.settings) as session:
            rows = session.execute(
                text(
                    f"""
                    SELECT * FROM fs_player_match_stats
                    WHERE {where}
                    ORDER BY match_date DESC NULLS LAST
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
                            COUNT(*) AS player_rows,
                            COUNT(DISTINCT player_id) AS unique_players,
                            COUNT(DISTINCT sportmonks_fixture_id) AS fixture_count,
                            COUNT(DISTINCT league_id) AS league_count,
                            COUNT(DISTINCT season_id) AS season_count,
                            SUM(CASE WHEN starter THEN 1 ELSE 0 END) AS starter_rows,
                            SUM(CASE WHEN xg IS NOT NULL THEN 1 ELSE 0 END) AS xg_rows,
                            SUM(CASE WHEN minutes > 0 THEN 1 ELSE 0 END) AS minutes_rows
                        FROM fs_player_match_stats
                        """
                    )
                ).mappings().first()
                rolling = session.execute(
                    text(
                        """
                        SELECT
                            COUNT(*) AS rolling_rows,
                            COUNT(DISTINCT sportmonks_fixture_id) AS rolling_fixtures,
                            SUM(CASE WHEN lineup_available THEN 1 ELSE 0 END) AS lineup_available_rows,
                            SUM(CASE WHEN formation IS NOT NULL THEN 1 ELSE 0 END) AS formation_rows,
                            SUM(CASE WHEN goals_last_5 > 0 OR minutes_last_5 > 0 THEN 1 ELSE 0 END) AS rolling_signal_rows
                        FROM fs_player_rolling_features
                        """
                    )
                ).mappings().first()
                by_league = session.execute(
                    text(
                        """
                        SELECT league_id,
                               COUNT(DISTINCT sportmonks_fixture_id) AS fixtures,
                               COUNT(DISTINCT player_id) AS players,
                               SUM(CASE WHEN xg IS NOT NULL THEN 1 ELSE 0 END) AS xg_rows
                        FROM fs_player_match_stats
                        GROUP BY league_id
                        ORDER BY fixtures DESC
                        """
                    )
                ).mappings().all()
                by_season = session.execute(
                    text(
                        """
                        SELECT season_id,
                               COUNT(DISTINCT sportmonks_fixture_id) AS fixtures,
                               COUNT(DISTINCT player_id) AS players
                        FROM fs_player_match_stats
                        GROUP BY season_id
                        ORDER BY fixtures DESC
                        LIMIT 20
                        """
                    )
                ).mappings().all()
                dupes = session.execute(
                    text(
                        """
                        SELECT sportmonks_fixture_id, player_id, COUNT(*) AS n
                        FROM fs_player_match_stats
                        GROUP BY 1, 2
                        HAVING COUNT(*) > 1
                        LIMIT 5
                        """
                    )
                ).mappings().all()
            return {
                "configured": True,
                "tables_ready": True,
                "match_stats": dict(stats) if stats else {},
                "rolling_features": dict(rolling) if rolling else {},
                "by_league": [dict(r) for r in by_league],
                "by_season": [dict(r) for r in by_season],
                "duplicate_groups_sample": [dict(d) for d in dupes],
            }
        except Exception as exc:
            logger.warning("Player feature store audit failed: %s", exc)
            return {"configured": True, "tables_ready": False, "error": str(exc)}

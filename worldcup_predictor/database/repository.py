"""SQLite repository for football intelligence data."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.competitions import CompetitionConfig, list_competition_keys
from worldcup_predictor.database.connection import connect, get_db_path, init_database
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.schedule.match_center import classify_status


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


@dataclass
class DatabaseStatus:
    connected: bool
    path: str
    schema_version: int
    table_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "path": self.path,
            "schema_version": self.schema_version,
            "table_counts": self.table_counts,
        }


class FootballIntelligenceRepository:
    """Primary data access layer — DB is source of truth; JSONL remains for export."""

    TABLE_NAMES = (
        "competitions",
        "teams",
        "fixtures",
        "fixture_results",
        "predictions",
        "prediction_markets",
        "verification_results",
        "team_form_snapshots",
        "odds_snapshots",
        "xg_snapshots",
        "player_stats_snapshots",
        "agent_signals",
        "model_coach_reports",
        "selection_decisions",
        "learning_records_v2",
        "api_response_cache",
        "api_quota_stats",
    )

    def __init__(self, path: str | None = None) -> None:
        self._path = get_db_path(path)
        init_database(self._path)
        self._conn = connect(self._path)

    @property
    def path(self) -> str:
        return str(self._path)

    def close(self) -> None:
        self._conn.close()

    def status(self) -> DatabaseStatus:
        counts: dict[str, int] = {}
        for table in self.TABLE_NAMES:
            try:
                row = self._conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
                counts[table] = int(row["c"]) if row else 0
            except sqlite3.Error:
                counts[table] = 0
        version_row = self._conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        version = int(version_row["value"]) if version_row else 0
        return DatabaseStatus(
            connected=True,
            path=self.path,
            schema_version=version,
            table_counts=counts,
        )

    def upsert_competition(self, comp: CompetitionConfig) -> None:
        self._conn.execute(
            """
            INSERT INTO competitions(key, name, league_id, season, competition_type,
                supports_groups, supports_table, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                name=excluded.name,
                league_id=excluded.league_id,
                season=excluded.season,
                competition_type=excluded.competition_type,
                supports_groups=excluded.supports_groups,
                supports_table=excluded.supports_table,
                updated_at=excluded.updated_at
            """,
            (
                comp.key,
                comp.name,
                comp.league_id,
                comp.season,
                comp.compensation_type,
                int(comp.supports_groups),
                int(comp.supports_table),
                _utc_now(),
            ),
        )
        self._conn.commit()

    def upsert_fixture(
        self,
        fixture: TournamentFixture,
        *,
        competition_key: str,
        league_id: int | None = None,
        season: int | None = None,
    ) -> bool:
        if fixture.is_placeholder or fixture.source == "placeholder":
            return False
        kickoff = fixture.kickoff_time.isoformat() if fixture.kickoff_time else None
        resolved_league_id = league_id if league_id is not None else fixture.league_id
        resolved_season = season if season is not None else fixture.season
        self._conn.execute(
            """
            INSERT INTO fixtures(
                fixture_id, competition_key, home_team, away_team, home_team_id, away_team_id,
                kickoff_utc, status, round_name, group_name, venue, city, source, is_placeholder,
                league_id, season, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id) DO UPDATE SET
                competition_key=excluded.competition_key,
                home_team=excluded.home_team,
                away_team=excluded.away_team,
                home_team_id=COALESCE(excluded.home_team_id, fixtures.home_team_id),
                away_team_id=COALESCE(excluded.away_team_id, fixtures.away_team_id),
                kickoff_utc=excluded.kickoff_utc,
                status=excluded.status,
                round_name=excluded.round_name,
                group_name=excluded.group_name,
                venue=excluded.venue,
                city=excluded.city,
                source=excluded.source,
                is_placeholder=excluded.is_placeholder,
                league_id=COALESCE(excluded.league_id, fixtures.league_id),
                season=COALESCE(excluded.season, fixtures.season),
                updated_at=excluded.updated_at
            """,
            (
                fixture.fixture_id,
                competition_key,
                fixture.home_team,
                fixture.away_team,
                fixture.home_team_id,
                fixture.away_team_id,
                kickoff,
                fixture.status,
                fixture.round,
                fixture.group,
                fixture.venue,
                fixture.city,
                fixture.source,
                int(fixture.is_placeholder),
                resolved_league_id,
                resolved_season,
                _utc_now(),
            ),
        )
        self._conn.commit()
        return True

    def update_fixture_identity(
        self,
        fixture_id: int,
        *,
        home_team_id: int | None = None,
        away_team_id: int | None = None,
        league_id: int | None = None,
        season: int | None = None,
    ) -> bool:
        """Patch team/league identity fields after live fixture resolution."""
        if not self.fixture_exists(fixture_id):
            return False
        self._conn.execute(
            """
            UPDATE fixtures SET
                home_team_id = COALESCE(?, home_team_id),
                away_team_id = COALESCE(?, away_team_id),
                league_id = COALESCE(?, league_id),
                season = COALESCE(?, season),
                updated_at = ?
            WHERE fixture_id = ?
            """,
            (
                home_team_id,
                away_team_id,
                league_id,
                season,
                _utc_now(),
                fixture_id,
            ),
        )
        self._conn.commit()
        return True

    def upsert_fixture_result(self, fixture: TournamentFixture, *, competition_key: str) -> bool:
        if fixture.home_goals is None or fixture.away_goals is None:
            return False
        if classify_status(fixture.status) != "finished":
            return False
        total = fixture.home_goals + fixture.away_goals
        ou = "over_2_5" if total > 2 else "under_2_5"
        if fixture.home_goals > fixture.away_goals:
            winner = fixture.home_team
        elif fixture.home_goals < fixture.away_goals:
            winner = fixture.away_team
        else:
            winner = "draw"
        ht = None
        if fixture.halftime_home_goals is not None and fixture.halftime_away_goals is not None:
            ht = f"{fixture.halftime_home_goals}-{fixture.halftime_away_goals}"
        self._conn.execute(
            """
            INSERT INTO fixture_results(
                fixture_id, competition_key, final_score, halftime_score,
                home_goals, away_goals, winner, over_under_2_5, total_goals,
                finished_at, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id) DO UPDATE SET
                final_score=excluded.final_score,
                halftime_score=excluded.halftime_score,
                home_goals=excluded.home_goals,
                away_goals=excluded.away_goals,
                winner=excluded.winner,
                over_under_2_5=excluded.over_under_2_5,
                total_goals=excluded.total_goals,
                finished_at=excluded.finished_at,
                source=excluded.source
            """,
            (
                fixture.fixture_id,
                competition_key,
                f"{fixture.home_goals}-{fixture.away_goals}",
                ht,
                fixture.home_goals,
                fixture.away_goals,
                winner,
                ou,
                total,
                _utc_now(),
                fixture.source,
            ),
        )
        self._conn.commit()
        return True

    def upsert_prediction(
        self,
        *,
        prediction_id: str,
        fixture_id: int,
        competition_key: str,
        home_team: str,
        away_team: str,
        prediction_version: str,
        created_at: str,
        data_quality: float,
        prediction_quality: float,
        confidence: float,
        no_bet_flag: bool,
        selected_by_engine: bool = False,
        reason_selected: str | None = None,
        source: str = "live",
        lineups_available: bool = False,
        is_preliminary: bool = True,
        markets: dict[str, str] | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO predictions(
                prediction_id, fixture_id, competition_key, home_team, away_team,
                prediction_version, created_at, data_quality, prediction_quality,
                confidence, no_bet_flag, selected_by_engine, reason_selected,
                source, lineups_available, is_preliminary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(prediction_id) DO UPDATE SET
                data_quality=excluded.data_quality,
                prediction_quality=excluded.prediction_quality,
                confidence=excluded.confidence,
                no_bet_flag=excluded.no_bet_flag,
                selected_by_engine=excluded.selected_by_engine,
                reason_selected=excluded.reason_selected,
                lineups_available=excluded.lineups_available,
                is_preliminary=excluded.is_preliminary
            """,
            (
                prediction_id,
                fixture_id,
                competition_key,
                home_team,
                away_team,
                prediction_version,
                created_at,
                data_quality,
                prediction_quality,
                confidence,
                int(no_bet_flag),
                int(selected_by_engine),
                reason_selected,
                source,
                int(lineups_available),
                int(is_preliminary),
            ),
        )
        if markets:
            for market, value in markets.items():
                self._conn.execute(
                    """
                    INSERT INTO prediction_markets(prediction_id, market, predicted_value)
                    VALUES (?, ?, ?)
                    ON CONFLICT(prediction_id, market) DO UPDATE SET
                        predicted_value=excluded.predicted_value
                    """,
                    (prediction_id, market, value),
                )
        self._conn.commit()

    def upsert_verification(
        self,
        *,
        fixture_id: int,
        prediction_id: str,
        competition_key: str | None,
        market: str,
        predicted: str,
        actual: str,
        result: str,
        color: str,
        verified_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO verification_results(
                fixture_id, prediction_id, competition_key, market, predicted, actual,
                result, color, verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id, prediction_id, market) DO UPDATE SET
                predicted=excluded.predicted,
                actual=excluded.actual,
                result=excluded.result,
                color=excluded.color,
                verified_at=excluded.verified_at
            """,
            (
                fixture_id,
                prediction_id,
                competition_key,
                market,
                predicted,
                actual,
                result,
                color,
                verified_at,
            ),
        )
        self._conn.commit()

    def save_snapshot(
        self,
        table: str,
        *,
        fixture_id: int,
        competition_key: str,
        payload: dict[str, Any],
        snapshot_at: str | None = None,
        team_name: str | None = None,
        agent_name: str | None = None,
    ) -> None:
        stamp = snapshot_at or _utc_now()
        payload_json = json.dumps(payload, ensure_ascii=False)
        if table == "odds_snapshots":
            self._conn.execute(
                "INSERT INTO odds_snapshots(fixture_id, competition_key, snapshot_at, payload_json) VALUES (?, ?, ?, ?)",
                (fixture_id, competition_key, stamp, payload_json),
            )
        elif table == "xg_snapshots":
            self._conn.execute(
                "INSERT INTO xg_snapshots(fixture_id, competition_key, snapshot_at, payload_json) VALUES (?, ?, ?, ?)",
                (fixture_id, competition_key, stamp, payload_json),
            )
        elif table == "player_stats_snapshots":
            self._conn.execute(
                "INSERT INTO player_stats_snapshots(fixture_id, competition_key, snapshot_at, payload_json) VALUES (?, ?, ?, ?)",
                (fixture_id, competition_key, stamp, payload_json),
            )
        elif table == "agent_signals":
            self._conn.execute(
                "INSERT INTO agent_signals(fixture_id, competition_key, agent_name, signal_at, payload_json) VALUES (?, ?, ?, ?, ?)",
                (fixture_id, competition_key, agent_name or "unknown", stamp, payload_json),
            )
        self._conn.commit()

    def save_coach_report(self, report: dict[str, Any], *, competition_key: str | None = None) -> None:
        self._conn.execute(
            "INSERT INTO model_coach_reports(competition_key, generated_at, report_json) VALUES (?, ?, ?)",
            (competition_key, report.get("generated_at_utc") or _utc_now(), json.dumps(report, ensure_ascii=False)),
        )
        self._conn.commit()

    def save_selection_decision(
        self,
        *,
        fixture_id: int,
        competition_key: str,
        selection_level: str,
        total_score: float,
        scores: dict[str, float],
        reason: str,
        expected_improvement: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO selection_decisions(
                fixture_id, competition_key, selection_level, total_score,
                scores_json, reason, expected_improvement, decided_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fixture_id,
                competition_key,
                selection_level,
                total_score,
                json.dumps(scores),
                reason,
                expected_improvement,
                _utc_now(),
            ),
        )
        self._conn.commit()

    def list_fixtures(
        self,
        *,
        competition_key: str | None = None,
        status_class: str | None = None,
        limit: int | None = None,
    ) -> list[sqlite3.Row]:
        query = "SELECT * FROM fixtures WHERE is_placeholder = 0"
        params: list[Any] = []
        if competition_key:
            query += " AND competition_key = ?"
            params.append(competition_key)
        if status_class == "upcoming":
            query += " AND status IN ('NS', 'TBD', 'SCHEDULED', 'TIMED')"
        elif status_class == "live":
            query += " AND status IN ('1H', '2H', 'HT', 'ET', 'LIVE', 'BT', 'P')"
        elif status_class == "finished":
            query += " AND status IN ('FT', 'AET', 'PEN', 'FINISHED')"
        query += " ORDER BY kickoff_utc ASC"
        if limit:
            query += f" LIMIT {int(limit)}"
        return list(self._conn.execute(query, params).fetchall())

    def has_odds_snapshot(self, fixture_id: int) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM odds_snapshots WHERE fixture_id = ? LIMIT 1", (fixture_id,)
        ).fetchone() is not None

    def has_xg_snapshot(self, fixture_id: int) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM xg_snapshots WHERE fixture_id = ? LIMIT 1", (fixture_id,)
        ).fetchone() is not None

    def performance_by_competition(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT COALESCE(v.competition_key, p.competition_key, 'unknown') AS competition_key,
                   v.market,
                   SUM(CASE WHEN v.result = 'correct' THEN 1 ELSE 0 END) AS correct,
                   COUNT(*) AS total
            FROM verification_results v
            LEFT JOIN predictions p ON p.prediction_id = v.prediction_id
            GROUP BY COALESCE(v.competition_key, p.competition_key, 'unknown'), v.market
            """
        ).fetchall()
        return [
            {
                "competition_key": row["competition_key"],
                "market": row["market"],
                "winrate": round(row["correct"] / row["total"], 4) if row["total"] else None,
                "total": row["total"],
            }
            for row in rows
        ]

    def performance_by_version(self, *, competition_key: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT p.prediction_version, v.market,
                   SUM(CASE WHEN v.result = 'correct' THEN 1 ELSE 0 END) AS correct,
                   COUNT(*) AS total
            FROM verification_results v
            JOIN predictions p ON p.prediction_id = v.prediction_id
        """
        params: list[Any] = []
        if competition_key:
            query += " WHERE p.competition_key = ?"
            params.append(competition_key)
        query += " GROUP BY p.prediction_version, v.market"
        rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "prediction_version": row["prediction_version"],
                "market": row["market"],
                "winrate": round(row["correct"] / row["total"], 4) if row["total"] else None,
                "total": row["total"],
            }
            for row in rows
        ]

    def seed_competitions(self) -> None:
        from worldcup_predictor.config.competitions import get_competition

        for key in list_competition_keys():
            self.upsert_competition(get_competition(key))

    def latest_coach_report(self, *, competition_key: str | None = None) -> dict[str, Any] | None:
        if competition_key:
            row = self._conn.execute(
                "SELECT report_json FROM model_coach_reports WHERE competition_key = ? ORDER BY id DESC LIMIT 1",
                (competition_key,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT report_json FROM model_coach_reports ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return json.loads(row["report_json"])

    def fetch_training_rows(self, *, competition_key: str | None = None) -> list[sqlite3.Row]:
        query = """
            SELECT p.prediction_id, p.fixture_id, p.competition_key, p.data_quality,
                   p.prediction_quality, p.confidence, p.lineups_available, p.no_bet_flag,
                   p.is_preliminary, v.market, v.result
            FROM predictions p
            JOIN verification_results v ON v.prediction_id = p.prediction_id
        """
        params: list[Any] = []
        if competition_key:
            query += " WHERE p.competition_key = ?"
            params.append(competition_key)
        return list(self._conn.execute(query, params).fetchall())

    def fetch_pattern_analysis_rows(self, *, competition_key: str | None = None) -> list[sqlite3.Row]:
        """Verified prediction rows enriched for pattern discovery (SQLite primary source)."""
        query = """
            SELECT
                p.prediction_id,
                p.fixture_id,
                COALESCE(v.competition_key, p.competition_key, 'unknown') AS competition_key,
                v.market,
                v.result,
                p.data_quality,
                p.prediction_quality,
                p.confidence,
                p.lineups_available,
                p.is_preliminary,
                p.no_bet_flag,
                p.selected_by_engine,
                CASE WHEN EXISTS (
                    SELECT 1 FROM odds_snapshots o WHERE o.fixture_id = p.fixture_id LIMIT 1
                ) THEN 1 ELSE 0 END AS has_odds,
                CASE WHEN EXISTS (
                    SELECT 1 FROM xg_snapshots x WHERE x.fixture_id = p.fixture_id LIMIT 1
                ) THEN 1 ELSE 0 END AS has_xg,
                CASE WHEN EXISTS (
                    SELECT 1 FROM agent_signals a
                    WHERE a.fixture_id = p.fixture_id
                      AND (
                        LOWER(a.payload_json) LIKE '%disagreement%'
                        OR LOWER(a.payload_json) LIKE '%strong_disagreement%'
                      )
                    LIMIT 1
                ) THEN 1 ELSE 0 END AS odds_disagreement,
                CASE WHEN EXISTS (
                    SELECT 1 FROM fixture_results fr WHERE fr.fixture_id = p.fixture_id LIMIT 1
                ) THEN 1 ELSE 0 END AS has_fixture_result,
                (
                    SELECT sd.selection_level FROM selection_decisions sd
                    WHERE sd.fixture_id = p.fixture_id
                    ORDER BY sd.decided_at DESC LIMIT 1
                ) AS selection_level
            FROM verification_results v
            JOIN predictions p ON p.prediction_id = v.prediction_id
            WHERE v.result IN ('correct', 'wrong')
        """
        params: list[Any] = []
        if competition_key:
            query += " AND p.competition_key = ?"
            params.append(competition_key)
        return list(self._conn.execute(query, params).fetchall())

    def fetch_odds_snapshots(self, fixture_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return odds snapshots oldest-first for movement analysis."""
        rows = self._conn.execute(
            """
            SELECT snapshot_at, payload_json, competition_key
            FROM odds_snapshots
            WHERE fixture_id = ?
            ORDER BY snapshot_at ASC
            LIMIT ?
            """,
            (int(fixture_id), int(limit)),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (json.JSONDecodeError, TypeError):
                payload = {}
            result.append(
                {
                    "snapshot_at": row["snapshot_at"],
                    "competition_key": row["competition_key"],
                    "payload": payload,
                }
            )
        return result

    def latest_prediction_for_fixture(self, fixture_id: int) -> dict[str, Any] | None:
        """Return latest stored prediction row with markets and verification (read-only)."""
        row = self._conn.execute(
            """
            SELECT * FROM predictions
            WHERE fixture_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (int(fixture_id),),
        ).fetchone()
        if not row:
            return None
        prediction_id = row["prediction_id"]
        market_rows = self._conn.execute(
            "SELECT market, predicted_value FROM prediction_markets WHERE prediction_id = ?",
            (prediction_id,),
        ).fetchall()
        verification_rows = self._conn.execute(
            """
            SELECT market, predicted, actual, result, color
            FROM verification_results
            WHERE prediction_id = ?
            ORDER BY market
            """,
            (prediction_id,),
        ).fetchall()
        return {
            "prediction": dict(row),
            "markets": {str(m["market"]): str(m["predicted_value"]) for m in market_rows},
            "verifications": [dict(v) for v in verification_rows],
        }

    def append_learning_record_v2(
        self,
        *,
        record_id: str,
        fixture_id: int,
        prediction_id: str,
        competition_key: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> bool:
        """Append-only learning record — returns False if record_id already exists."""
        try:
            self._conn.execute(
                """
                INSERT INTO learning_records_v2
                (record_id, fixture_id, prediction_id, competition_key, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    int(fixture_id),
                    prediction_id,
                    competition_key,
                    json.dumps(payload, ensure_ascii=False),
                    created_at,
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def fetch_learning_records_v2(
        self,
        *,
        competition_key: str | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT record_id, fixture_id, prediction_id, competition_key,
                   payload_json, created_at, verified_at
            FROM learning_records_v2
        """
        params: list[Any] = []
        if competition_key:
            query += " WHERE competition_key = ?"
            params.append(competition_key)
        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(int(limit))
        rows = self._conn.execute(query, params).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (json.JSONDecodeError, TypeError):
                payload = {}
            out.append(
                {
                    "record_id": row["record_id"],
                    "fixture_id": row["fixture_id"],
                    "prediction_id": row["prediction_id"],
                    "competition_key": row["competition_key"],
                    "payload": payload,
                    "created_at": row["created_at"],
                    "verified_at": row["verified_at"],
                }
            )
        return out

    def mark_learning_record_verified(
        self,
        record_id: str,
        *,
        outcome_payload: dict[str, Any],
        verified_at: str,
    ) -> bool:
        row = self._conn.execute(
            "SELECT payload_json FROM learning_records_v2 WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if not row:
            return False
        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            payload = {}
        payload.update(outcome_payload)
        self._conn.execute(
            """
            UPDATE learning_records_v2
            SET payload_json = ?, verified_at = ?
            WHERE record_id = ?
            """,
            (json.dumps(payload, ensure_ascii=False), verified_at, record_id),
        )
        self._conn.commit()
        return True

    def fixture_exists(self, fixture_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM fixtures WHERE fixture_id = ? AND is_placeholder = 0 LIMIT 1",
            (fixture_id,),
        ).fetchone()
        return row is not None

    def get_fixture_row(self, fixture_id: int) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM fixtures WHERE fixture_id = ?", (fixture_id,)).fetchone()
        return dict(row) if row else None

    def get_fixture_result_row(self, fixture_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM fixture_results WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_fixture_enrichment_row(self, fixture_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM fixture_enrichment WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_upcoming_fixtures(
        self,
        competition_key: str,
        *,
        season: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        query = """
            SELECT *
            FROM fixtures
            WHERE competition_key = ?
              AND is_placeholder = 0
              AND status IN ('NS', 'TBD', 'SCHEDULED', 'TIMED')
              AND kickoff_utc > ?
        """
        params: list[Any] = [competition_key, now_utc]
        if season is not None:
            query += " AND (season = ? OR season IS NULL)"
            params.append(season)
        query += " ORDER BY kickoff_utc ASC LIMIT ?"
        params.append(int(limit))
        rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_sportmonks_fixture_enrichment_cache(
        self,
        sportmonks_fixture_id: int,
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM sportmonks_fixture_enrichment
            WHERE sportmonks_fixture_id = ?
              AND status = 'ok'
              AND expires_at_utc > ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (sportmonks_fixture_id, _utc_now()),
        ).fetchone()
        return dict(row) if row else None

    def get_sportmonks_fixture_enrichment_by_api_fixture_id(
        self,
        fixture_id_api_football: int,
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM sportmonks_fixture_enrichment
            WHERE fixture_id_api_football = ?
              AND status = 'ok'
              AND expires_at_utc > ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(fixture_id_api_football), _utc_now()),
        ).fetchone()
        return dict(row) if row else None

    def save_sportmonks_fixture_enrichment(
        self,
        *,
        sportmonks_fixture_id: int,
        fixture_id_api_football: int | None,
        league_id: int,
        season_id: int,
        endpoint: str,
        include_params: str,
        raw_json: str,
        fetched_at_utc: str,
        expires_at_utc: str,
        status: str = "ok",
        base_enrichment_available: bool = False,
        premium_odds_available: bool = False,
        premium_predictions_available: bool = False,
        premium_xg_available: bool = False,
        premium_odds_access_denied: bool = False,
        premium_predictions_access_denied: bool = False,
        premium_xg_access_denied: bool = False,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO sportmonks_fixture_enrichment (
                fixture_id_api_football,
                sportmonks_fixture_id,
                league_id,
                season_id,
                endpoint,
                include_params,
                raw_json,
                fetched_at_utc,
                expires_at_utc,
                status,
                base_enrichment_available,
                premium_odds_available,
                premium_predictions_available,
                premium_xg_available,
                premium_odds_access_denied,
                premium_predictions_access_denied,
                premium_xg_access_denied
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sportmonks_fixture_id) DO UPDATE SET
                fixture_id_api_football = excluded.fixture_id_api_football,
                league_id = excluded.league_id,
                season_id = excluded.season_id,
                endpoint = excluded.endpoint,
                include_params = excluded.include_params,
                raw_json = excluded.raw_json,
                fetched_at_utc = excluded.fetched_at_utc,
                expires_at_utc = excluded.expires_at_utc,
                status = excluded.status,
                base_enrichment_available = excluded.base_enrichment_available,
                premium_odds_available = excluded.premium_odds_available,
                premium_predictions_available = excluded.premium_predictions_available,
                premium_xg_available = excluded.premium_xg_available,
                premium_odds_access_denied = excluded.premium_odds_access_denied,
                premium_predictions_access_denied = excluded.premium_predictions_access_denied,
                premium_xg_access_denied = excluded.premium_xg_access_denied
            """,
            (
                fixture_id_api_football,
                sportmonks_fixture_id,
                league_id,
                season_id,
                endpoint,
                include_params,
                raw_json,
                fetched_at_utc,
                expires_at_utc,
                status,
                int(base_enrichment_available),
                int(premium_odds_available),
                int(premium_predictions_available),
                int(premium_xg_available),
                int(premium_odds_access_denied),
                int(premium_predictions_access_denied),
                int(premium_xg_access_denied),
            ),
        )
        self._conn.commit()

    def get_api_cache_payload(self, cache_key: str) -> Any | None:
        row = self._conn.execute(
            """
            SELECT payload_json, expires_at
            FROM api_response_cache
            WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        if str(row["expires_at"]) <= _utc_now():
            self._conn.execute(
                "DELETE FROM api_response_cache WHERE cache_key = ?",
                (cache_key,),
            )
            self._conn.commit()
            return None
        try:
            return json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            return None

    def set_api_cache_payload(
        self,
        *,
        cache_key: str,
        endpoint: str,
        params: dict[str, Any],
        payload: Any,
        expires_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO api_response_cache (
                cache_key, endpoint, params_json, payload_json, cached_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                endpoint = excluded.endpoint,
                params_json = excluded.params_json,
                payload_json = excluded.payload_json,
                cached_at = excluded.cached_at,
                expires_at = excluded.expires_at
            """,
            (
                cache_key,
                endpoint,
                json.dumps(params, sort_keys=True, default=str),
                json.dumps(payload, ensure_ascii=False),
                _utc_now(),
                expires_at,
            ),
        )
        self._conn.commit()

    def get_api_quota_stats(self, stat_date: str | None = None) -> dict[str, Any] | None:
        date_key = stat_date or datetime.now(timezone.utc).date().isoformat()
        row = self._conn.execute(
            "SELECT * FROM api_quota_stats WHERE stat_date = ?",
            (date_key,),
        ).fetchone()
        return dict(row) if row else None

    def upsert_api_quota_stats(self, stats: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO api_quota_stats (
                stat_date, live_requests, cache_hits, local_hits,
                calls_saved, rate_limit_retries, last_sync_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stat_date) DO UPDATE SET
                live_requests = excluded.live_requests,
                cache_hits = excluded.cache_hits,
                local_hits = excluded.local_hits,
                calls_saved = excluded.calls_saved,
                rate_limit_retries = excluded.rate_limit_retries,
                last_sync_at = excluded.last_sync_at,
                updated_at = excluded.updated_at
            """,
            (
                stats.get("stat_date", datetime.now(timezone.utc).date().isoformat()),
                int(stats.get("live_requests", 0)),
                int(stats.get("cache_hits", 0)),
                int(stats.get("local_hits", 0)),
                int(stats.get("calls_saved", 0)),
                int(stats.get("rate_limit_retries", 0)),
                stats.get("last_sync_at"),
                _utc_now(),
            ),
        )
        self._conn.commit()

    def list_fixture_goal_events(self, fixture_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT sort_index, minute, extra_minute, team, team_id, player, assist,
                   is_penalty, is_own_goal, detail
            FROM fixture_goal_events
            WHERE fixture_id = ?
            ORDER BY sort_index ASC
            """,
            (int(fixture_id),),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_fixture_goal_events(self, fixture_id: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM fixture_goal_events WHERE fixture_id = ?",
            (int(fixture_id),),
        ).fetchone()
        return int(row[0]) if row else 0

    def update_fixture_outcome_detail(
        self,
        fixture_id: int,
        *,
        competition_key: str = "world_cup_2026",
        ht_home_goals: int | None = None,
        ht_away_goals: int | None = None,
        ht_result: str | None = None,
        first_goal_team: str | None = None,
        first_goal_player: str | None = None,
        first_goal_minute: int | None = None,
        first_goal_extra_minute: int | None = None,
        match_outcome_type: str | None = None,
        outcome_persisted_at: str | None = None,
        outcome_source: str | None = None,
    ) -> bool:
        ht_score = None
        if ht_home_goals is not None and ht_away_goals is not None:
            ht_score = f"{ht_home_goals}-{ht_away_goals}"
        self._conn.execute(
            """
            UPDATE fixture_results SET
                ht_home_goals = COALESCE(?, ht_home_goals),
                ht_away_goals = COALESCE(?, ht_away_goals),
                ht_result = COALESCE(?, ht_result),
                halftime_score = COALESCE(?, halftime_score),
                first_goal_team = COALESCE(?, first_goal_team),
                first_goal_player = COALESCE(?, first_goal_player),
                first_goal_minute = COALESCE(?, first_goal_minute),
                first_goal_extra_minute = COALESCE(?, first_goal_extra_minute),
                match_outcome_type = COALESCE(?, match_outcome_type),
                outcome_persisted_at = COALESCE(?, outcome_persisted_at),
                outcome_source = COALESCE(?, outcome_source)
            WHERE fixture_id = ?
            """,
            (
                ht_home_goals,
                ht_away_goals,
                ht_result,
                ht_score,
                first_goal_team,
                first_goal_player,
                first_goal_minute,
                first_goal_extra_minute,
                match_outcome_type,
                outcome_persisted_at,
                outcome_source,
                int(fixture_id),
            ),
        )
        self._conn.commit()
        return self._conn.total_changes > 0

    def replace_fixture_goal_events(self, fixture_id: int, events: list[Any]) -> bool:
        from worldcup_predictor.outcomes.models import GoalEvent

        fid = int(fixture_id)
        self._conn.execute("DELETE FROM fixture_goal_events WHERE fixture_id = ?", (fid,))
        for idx, event in enumerate(events):
            if isinstance(event, GoalEvent):
                row = event
            elif isinstance(event, dict):
                row = GoalEvent.from_row({**event, "sort_index": event.get("sort_index", idx)})
            else:
                continue
            self._conn.execute(
                """
                INSERT INTO fixture_goal_events (
                    fixture_id, sort_index, minute, extra_minute, team, team_id,
                    player, assist, is_penalty, is_own_goal, detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fid,
                    int(row.sort_index),
                    row.minute,
                    row.extra_minute,
                    row.team,
                    row.team_id,
                    row.player,
                    row.assist,
                    1 if row.is_penalty else 0,
                    1 if row.is_own_goal else 0,
                    row.detail,
                ),
            )
        self._conn.commit()
        return True

    # --- Phase 51C goal timing queries (read-only, leakage-safe filters) ---

    def list_finished_fixtures_before(
        self,
        *,
        before_kickoff: str,
        competition_keys: list[str],
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if not competition_keys:
            return []
        placeholders = ",".join("?" for _ in competition_keys)
        query = f"""
            SELECT f.*, r.home_goals, r.away_goals, r.first_goal_team, r.first_goal_minute,
                   r.first_goal_extra_minute
            FROM fixtures f
            LEFT JOIN fixture_results r ON r.fixture_id = f.fixture_id
            WHERE f.is_placeholder = 0
              AND f.competition_key IN ({placeholders})
              AND f.kickoff_utc IS NOT NULL
              AND f.kickoff_utc < ?
              AND f.status IN ('FT', 'AET', 'PEN', 'FINISHED')
            ORDER BY f.kickoff_utc DESC
        """
        params: list[Any] = [*competition_keys, before_kickoff]
        if limit:
            query += " LIMIT ?"
            params.append(int(limit))
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def list_team_finished_fixtures_before(
        self,
        *,
        team_name: str,
        before_kickoff: str,
        competition_keys: list[str],
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        if not competition_keys or not team_name:
            return []
        placeholders = ",".join("?" for _ in competition_keys)
        query = f"""
            SELECT f.*, r.home_goals, r.away_goals, r.first_goal_team, r.first_goal_minute,
                   r.first_goal_extra_minute
            FROM fixtures f
            LEFT JOIN fixture_results r ON r.fixture_id = f.fixture_id
            WHERE f.is_placeholder = 0
              AND f.competition_key IN ({placeholders})
              AND f.kickoff_utc IS NOT NULL
              AND f.kickoff_utc < ?
              AND f.status IN ('FT', 'AET', 'PEN', 'FINISHED')
              AND (f.home_team = ? OR f.away_team = ?)
            ORDER BY f.kickoff_utc DESC
            LIMIT ?
        """
        params: list[Any] = [*competition_keys, before_kickoff, team_name, team_name, int(limit)]
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def goal_timing_league_coverage(self, competition_keys: list[str]) -> list[dict[str, Any]]:
        if not competition_keys:
            return []
        placeholders = ",".join("?" for _ in competition_keys)
        rows = self._conn.execute(
            f"""
            SELECT f.competition_key AS competition_key,
                   COUNT(*) AS finished_matches,
                   SUM(CASE WHEN g.c > 0 THEN 1 ELSE 0 END) AS with_goal_events,
                   SUM(CASE WHEN r.first_goal_minute IS NOT NULL THEN 1 ELSE 0 END) AS with_first_goal_minute
            FROM fixtures f
            LEFT JOIN fixture_results r ON r.fixture_id = f.fixture_id
            LEFT JOIN (
                SELECT fixture_id, COUNT(*) AS c
                FROM fixture_goal_events
                GROUP BY fixture_id
            ) g ON g.fixture_id = f.fixture_id
            WHERE f.is_placeholder = 0
              AND f.competition_key IN ({placeholders})
              AND f.status IN ('FT', 'AET', 'PEN', 'FINISHED')
            GROUP BY f.competition_key
            ORDER BY f.competition_key
            """,
            competition_keys,
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Phase 33: World Cup stored predictions ---

    def upsert_worldcup_stored_prediction(
        self,
        *,
        fixture_id: int,
        payload: dict[str, Any],
        kickoff_utc: str | None = None,
        source: str = "background",
        predicted_at: str | None = None,
        competition_key: str = "world_cup_2026",
        superseded_from: int | None = None,
    ) -> None:
        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO worldcup_stored_predictions (
                fixture_id, competition_key, kickoff_utc, payload_json,
                source, predicted_at, updated_at,
                is_active, invalidated_at, invalidated_reason, superseded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, NULL, NULL, ?)
            ON CONFLICT(fixture_id) DO UPDATE SET
                kickoff_utc = excluded.kickoff_utc,
                payload_json = excluded.payload_json,
                source = excluded.source,
                predicted_at = excluded.predicted_at,
                updated_at = excluded.updated_at,
                is_active = 1,
                invalidated_at = NULL,
                invalidated_reason = NULL,
                superseded_by = excluded.superseded_by
            """,
            (
                int(fixture_id),
                competition_key,
                kickoff_utc,
                json.dumps(payload, ensure_ascii=False, default=str),
                source,
                predicted_at or now,
                now,
                superseded_from,
            ),
        )
        self._conn.commit()

    def get_worldcup_stored_prediction(
        self,
        fixture_id: int,
        *,
        include_inactive: bool = False,
    ) -> dict[str, Any] | None:
        if include_inactive:
            row = self._conn.execute(
                "SELECT * FROM worldcup_stored_predictions WHERE fixture_id = ?",
                (int(fixture_id),),
            ).fetchone()
            return dict(row) if row else None
        row = self._conn.execute(
            """
            SELECT * FROM worldcup_stored_predictions
            WHERE fixture_id = ?
              AND (is_active IS NULL OR is_active = 1)
            """,
            (int(fixture_id),),
        ).fetchone()
        return dict(row) if row else None

    def count_worldcup_stored_predictions(
        self, *, competition_key: str = "world_cup_2026", include_quarantined: bool = True
    ) -> int:
        query = "SELECT COUNT(*) AS c FROM worldcup_stored_predictions WHERE competition_key = ?"
        params: list[Any] = [competition_key]
        if not include_quarantined:
            query += " AND (is_quarantined IS NULL OR is_quarantined = 0)"
        row = self._conn.execute(query, params).fetchone()
        return int(row["c"]) if row else 0

    def list_worldcup_stored_prediction_competition_keys(self) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT competition_key FROM worldcup_stored_predictions
            WHERE competition_key IS NOT NULL AND competition_key != ''
              AND (is_active IS NULL OR is_active = 1)
            ORDER BY competition_key
            """
        ).fetchall()
        return [str(r["competition_key"]) for r in rows if r["competition_key"]]

    def list_worldcup_stored_predictions(
        self,
        *,
        competition_key: str = "world_cup_2026",
        limit: int = 100,
        offset: int = 0,
        include_quarantined: bool = True,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM worldcup_stored_predictions
            WHERE competition_key = ?
              AND (is_active IS NULL OR is_active = 1)
        """
        params: list[Any] = [competition_key]
        if not include_quarantined:
            query += " AND (is_quarantined IS NULL OR is_quarantined = 0)"
        query += " ORDER BY predicted_at DESC LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def list_worldcup_stored_prediction_rows(
        self,
        *,
        competition_key: str = "world_cup_2026",
        limit: int = 100,
        offset: int = 0,
        include_quarantined: bool = True,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        """Backward-compatible alias used by evaluation scheduler and smoke scripts."""
        _ = include_inactive  # inactive rows excluded by list_worldcup_stored_predictions
        return self.list_worldcup_stored_predictions(
            competition_key=competition_key,
            limit=limit,
            offset=offset,
            include_quarantined=include_quarantined,
        )

    def get_worldcup_prediction_evaluation(self, fixture_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM worldcup_prediction_evaluations WHERE fixture_id = ?",
            (int(fixture_id),),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["no_bet"] = bool(d.get("no_bet"))
        return d

    def upsert_worldcup_prediction_evaluation(
        self,
        *,
        fixture_id: int,
        evaluation: dict[str, Any],
        outcome: dict[str, Any],
        competition_key: str = "world_cup_2026",
    ) -> None:
        markets = evaluation.get("markets") or {}
        advanced = evaluation.get("advanced_markets") or {}
        goal_minute = advanced.get("goal_minute") if isinstance(advanced.get("goal_minute"), dict) else {}

        def _adv_status(key: str) -> str | None:
            block = advanced.get(key)
            if isinstance(block, dict) and block.get("status"):
                return str(block["status"])
            return None

        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO worldcup_prediction_evaluations (
                fixture_id, competition_key, overall_status, no_bet,
                actual_result, final_score,
                safe_pick_status, value_pick_status, aggressive_pick_status,
                market_1x2_status, market_ou_status, market_btts_status, market_dc_status,
                market_ht_status, market_cs_status, market_fg_team_status,
                market_goalscorer_status, market_goal_minute_status,
                market_goal_minute_actual, market_goal_minute_predicted,
                detail_json, evaluated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id) DO UPDATE SET
                overall_status = excluded.overall_status,
                no_bet = excluded.no_bet,
                actual_result = excluded.actual_result,
                final_score = excluded.final_score,
                safe_pick_status = excluded.safe_pick_status,
                value_pick_status = excluded.value_pick_status,
                aggressive_pick_status = excluded.aggressive_pick_status,
                market_1x2_status = excluded.market_1x2_status,
                market_ou_status = excluded.market_ou_status,
                market_btts_status = excluded.market_btts_status,
                market_dc_status = excluded.market_dc_status,
                market_ht_status = excluded.market_ht_status,
                market_cs_status = excluded.market_cs_status,
                market_fg_team_status = excluded.market_fg_team_status,
                market_goalscorer_status = excluded.market_goalscorer_status,
                market_goal_minute_status = excluded.market_goal_minute_status,
                market_goal_minute_actual = excluded.market_goal_minute_actual,
                market_goal_minute_predicted = excluded.market_goal_minute_predicted,
                detail_json = excluded.detail_json,
                evaluated_at = excluded.evaluated_at
            """,
            (
                int(fixture_id),
                competition_key,
                str(evaluation.get("status") or "pending"),
                1 if evaluation.get("no_bet") else 0,
                outcome.get("actual_result"),
                outcome.get("final_score"),
                markets.get("safe_pick"),
                markets.get("value_pick"),
                markets.get("aggressive_pick"),
                markets.get("1x2"),
                markets.get("over_under_2_5"),
                markets.get("btts"),
                markets.get("double_chance"),
                _adv_status("ht_result"),
                _adv_status("correct_score"),
                _adv_status("first_goal_team"),
                _adv_status("goalscorer"),
                _adv_status("goal_minute") or markets.get("goal_minute"),
                goal_minute.get("actual"),
                goal_minute.get("predicted"),
                json.dumps(evaluation, ensure_ascii=False, default=str),
                now,
            ),
        )
        self._conn.commit()

    def list_worldcup_prediction_evaluations(
        self,
        *,
        competition_key: str = "world_cup_2026",
        include_quarantined: bool = False,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM worldcup_prediction_evaluations WHERE competition_key = ?"
        params: list[Any] = [competition_key]
        if not include_quarantined:
            query += " AND (is_quarantined IS NULL OR is_quarantined = 0)"
        rows = self._conn.execute(query, params).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            d["no_bet"] = bool(d.get("no_bet"))
            out.append(d)
        return out

    def list_all_worldcup_prediction_evaluations(
        self,
        *,
        include_quarantined: bool = False,
    ) -> list[dict[str, Any]]:
        """All competitions — used by Results page and finished-tab supplement."""
        query = "SELECT * FROM worldcup_prediction_evaluations WHERE 1=1"
        if not include_quarantined:
            query += " AND (is_quarantined IS NULL OR is_quarantined = 0)"
        query += " ORDER BY evaluated_at DESC"
        rows = self._conn.execute(query).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            d["no_bet"] = bool(d.get("no_bet"))
            out.append(d)
        return out

    def count_worldcup_prediction_evaluations(
        self,
        *,
        competition_key: str = "world_cup_2026",
        include_quarantined: bool = False,
    ) -> int:
        query = "SELECT COUNT(*) AS c FROM worldcup_prediction_evaluations WHERE competition_key = ?"
        params: list[Any] = [competition_key]
        if not include_quarantined:
            query += " AND (is_quarantined IS NULL OR is_quarantined = 0)"
        row = self._conn.execute(query, params).fetchone()
        return int(row["c"]) if row else 0

    def upsert_worldcup_accuracy_summary(
        self,
        *,
        competition_key: str,
        summary: dict[str, Any],
    ) -> None:
        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO worldcup_accuracy_summary (competition_key, summary_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(competition_key) DO UPDATE SET
                summary_json = excluded.summary_json,
                updated_at = excluded.updated_at
            """,
            (competition_key, json.dumps(summary, ensure_ascii=False, default=str), now),
        )
        self._conn.commit()

    def get_worldcup_accuracy_summary(self, *, competition_key: str = "world_cup_2026") -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT summary_json FROM worldcup_accuracy_summary WHERE competition_key = ?",
            (competition_key,),
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["summary_json"])
        except (json.JSONDecodeError, TypeError):
            return None

    def insert_performance_snapshot(
        self,
        *,
        competition_key: str,
        snapshot_at: str,
        evaluated_count: int,
        correct_count: int,
        wrong_count: int,
        pending_count: int,
        overall_winrate: float | None,
        markets_json: str,
        rule_a_json: str | None = None,
        agent_contribution_json: str | None = None,
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO performance_snapshots (
                competition_key, snapshot_at, evaluated_count, correct_count,
                wrong_count, pending_count, overall_winrate,
                markets_json, rule_a_json, agent_contribution_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                competition_key,
                snapshot_at,
                int(evaluated_count),
                int(correct_count),
                int(wrong_count),
                int(pending_count),
                overall_winrate,
                markets_json,
                rule_a_json,
                agent_contribution_json,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_performance_snapshots(
        self,
        *,
        competition_key: str = "world_cup_2026",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM performance_snapshots
            WHERE competition_key = ?
            ORDER BY snapshot_at ASC
            LIMIT ?
            """,
            (competition_key, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_fixtures_in_kickoff_window(
        self,
        competition_key: str,
        *,
        window_days: int = 3,
        season: int | None = None,
    ) -> list[dict[str, Any]]:
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        end = now + timedelta(days=int(window_days))
        query = """
            SELECT *
            FROM fixtures
            WHERE competition_key = ?
              AND is_placeholder = 0
              AND status IN ('NS', 'TBD', 'SCHEDULED', 'TIMED')
              AND kickoff_utc >= ?
              AND kickoff_utc <= ?
        """
        params: list[Any] = [competition_key, now.isoformat(), end.isoformat()]
        if season is not None:
            query += " AND (season = ? OR season IS NULL)"
            params.append(season)
        query += " ORDER BY kickoff_utc ASC"
        return [dict(r) for r in self._conn.execute(query, params).fetchall()]

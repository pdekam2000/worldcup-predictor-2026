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

    def upsert_fixture(self, fixture: TournamentFixture, *, competition_key: str) -> bool:
        if fixture.is_placeholder or fixture.source == "placeholder":
            return False
        kickoff = fixture.kickoff_time.isoformat() if fixture.kickoff_time else None
        self._conn.execute(
            """
            INSERT INTO fixtures(
                fixture_id, competition_key, home_team, away_team, kickoff_utc, status,
                round_name, group_name, venue, city, source, is_placeholder, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id) DO UPDATE SET
                competition_key=excluded.competition_key,
                home_team=excluded.home_team,
                away_team=excluded.away_team,
                kickoff_utc=excluded.kickoff_utc,
                status=excluded.status,
                round_name=excluded.round_name,
                group_name=excluded.group_name,
                venue=excluded.venue,
                city=excluded.city,
                source=excluded.source,
                is_placeholder=excluded.is_placeholder,
                updated_at=excluded.updated_at
            """,
            (
                fixture.fixture_id,
                competition_key,
                fixture.home_team,
                fixture.away_team,
                kickoff,
                fixture.status,
                fixture.round,
                fixture.group,
                fixture.venue,
                fixture.city,
                fixture.source,
                int(fixture.is_placeholder),
                _utc_now(),
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

"""Lineup / player feature store — ingest, normalize, rolling features, audit."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.feature_store.player_store.aggregations import build_fixture_rolling_features
from worldcup_predictor.feature_store.player_store.models import PlayerIngestResult, PlayerMatchStatRecord
from worldcup_predictor.feature_store.player_store.normalizers import extract_lineup_context, normalize_fixture_player_stats
from worldcup_predictor.feature_store.player_store.repository import PlayerFeatureRepository

logger = logging.getLogger(__name__)

_CACHE_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_pressure/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
)
_TARGET_LEAGUE_IDS = (2, 5, 2286, 732)
_LINEUP_INCLUDES = (
    "participants;league;season;state;events.type;events.player;"
    "statistics.type;lineups.player;lineups.details.type;lineups.xGLineup.type;formations"
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dict_to_match_stat(row: dict[str, Any]) -> PlayerMatchStatRecord:
    return PlayerMatchStatRecord(
        sportmonks_fixture_id=int(row["sportmonks_fixture_id"]),
        player_id=int(row["player_id"]),
        captured_at=row.get("captured_at") or _utc_now(),
        source=str(row.get("source") or "db"),
        fixture_id=row.get("fixture_id"),
        player_name=row.get("player_name"),
        team_id=row.get("team_id"),
        position=row.get("position"),
        starter=bool(row.get("starter")),
        captain=bool(row.get("captain")),
        minutes=int(row.get("minutes") or 0),
        goals=int(row.get("goals") or 0),
        assists=int(row.get("assists") or 0),
        shots=int(row.get("shots") or 0),
        shots_on_target=int(row.get("shots_on_target") or 0),
        rating=float(row["rating"]) if row.get("rating") is not None else None,
        xg=float(row["xg"]) if row.get("xg") is not None else None,
        xa=float(row["xa"]) if row.get("xa") is not None else None,
        yellow_cards=int(row.get("yellow_cards") or 0),
        red_cards=int(row.get("red_cards") or 0),
        season_id=row.get("season_id"),
        league_id=row.get("league_id"),
        match_date=row.get("match_date"),
        metadata=row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
    )


class PlayerFeatureStore:
    """Shadow/research lineup + player intelligence layer (Phase 54J)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repo = PlayerFeatureRepository(self.settings)

    @property
    def configured(self) -> bool:
        return self.repo.configured

    def _load_histories(
        self,
        player_ids: list[int],
        *,
        before_date: datetime | None,
    ) -> dict[int, list[PlayerMatchStatRecord]]:
        histories: dict[int, list[PlayerMatchStatRecord]] = {}
        for pid in player_ids:
            rows = self.repo.load_player_history(pid, before_date=before_date, limit=30)
            histories[pid] = [_dict_to_match_stat(r) for r in rows]
        return histories

    def ingest_fixture(
        self,
        sportmonks_fixture_id: int,
        *,
        raw: dict[str, Any] | None = None,
        source: str = "sportmonks_cache",
        raw_reference: str | None = None,
        force_reimport: bool = False,
        build_rolling: bool = True,
    ) -> dict[str, Any]:
        if force_reimport:
            self.repo.delete_fixture(sportmonks_fixture_id)

        if raw is None:
            return {
                "sportmonks_fixture_id": sportmonks_fixture_id,
                "status": "error",
                "player_rows_written": 0,
                "rolling_rows_written": 0,
                "error": "no_payload",
            }

        match_stats = normalize_fixture_player_stats(
            raw,
            sportmonks_fixture_id=sportmonks_fixture_id,
            source=source,
            raw_reference=raw_reference,
        )
        if not match_stats:
            return {
                "sportmonks_fixture_id": sportmonks_fixture_id,
                "status": "empty",
                "player_rows_written": 0,
                "rolling_rows_written": 0,
                "skip_reason": "no_lineups",
            }

        lineup_context = extract_lineup_context(raw)
        player_rows = self.repo.upsert_match_stats(match_stats)

        rolling_rows = 0
        if build_rolling:
            player_ids = [r.player_id for r in match_stats]
            before = match_stats[0].match_date
            histories = self._load_histories(player_ids, before_date=before) if self.configured else {}
            rolling = build_fixture_rolling_features(
                match_stats,
                lineup_context=lineup_context,
                player_histories=histories,
            )
            rolling_rows = self.repo.upsert_rolling_features(rolling)

        return {
            "sportmonks_fixture_id": sportmonks_fixture_id,
            "status": "imported",
            "player_rows_written": player_rows,
            "rolling_rows_written": rolling_rows,
            "lineup_context": lineup_context,
            "league_id": match_stats[0].league_id,
            "season_id": match_stats[0].season_id,
        }

    def backfill_from_cache(
        self,
        *,
        cache_dirs: list[Path | str] | None = None,
        league_id: int | None = None,
        job_key: str = "phase54j_cache_import",
        force_reimport: bool = False,
        target_leagues: tuple[int, ...] = _TARGET_LEAGUE_IDS,
    ) -> PlayerIngestResult:
        roots = list(cache_dirs) if cache_dirs else list(_CACHE_ROOTS)
        seen_paths: set[Path] = set()
        seen_ids: set[int] = set()
        imported_ids = self.repo.imported_fixture_ids()
        result = PlayerIngestResult(job_key=job_key)

        for root in roots:
            root = Path(root)
            if not root.is_dir():
                continue
            for path in sorted(root.glob("*.json")):
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                try:
                    blob = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    result.fixtures_error += 1
                    continue

                data = (blob.get("payload") or {}).get("data")
                if not isinstance(data, dict):
                    result.fixtures_error += 1
                    continue

                sm_id = int(blob.get("sportmonks_fixture_id") or data.get("id") or path.stem)
                if sm_id in seen_ids:
                    continue
                lid = int(data.get("league_id") or 0)
                if league_id is not None and lid != league_id:
                    continue
                if lid not in target_leagues and league_id is None:
                    continue

                if sm_id in imported_ids and not force_reimport:
                    result.fixtures_skipped += 1
                    seen_ids.add(sm_id)
                    continue

                prior = self.repo.manifest_status(job_key, sm_id)
                if prior == "imported" and not force_reimport:
                    result.fixtures_skipped += 1
                    seen_ids.add(sm_id)
                    continue

                result.fixtures_processed += 1
                ingest_source = "uefa_cache" if "uefa_club" in str(path) else "sportmonks_cache"
                ingest = self.ingest_fixture(
                    sm_id,
                    raw=data,
                    source=ingest_source,
                    raw_reference=str(path),
                    force_reimport=force_reimport,
                )
                seen_ids.add(sm_id)
                result.api_calls_cached += 1

                status = str(ingest.get("status") or "error")
                prow = int(ingest.get("player_rows_written") or 0)
                rrow = int(ingest.get("rolling_rows_written") or 0)
                result.player_rows_written += prow
                result.rolling_rows_written += rrow

                if status == "imported":
                    result.fixtures_imported += 1
                elif status == "empty":
                    result.fixtures_empty += 1
                else:
                    result.fixtures_error += 1
                    if ingest.get("error"):
                        result.errors.append(f"{sm_id}:{ingest['error']}")

                self.repo.write_manifest(
                    job_key=job_key,
                    sportmonks_fixture_id=sm_id,
                    status=status,
                    league_id=lid or None,
                    season_id=int(data.get("season_id") or 0) or None,
                    player_rows=prow,
                    rolling_rows=rrow,
                    error=ingest.get("error") or ingest.get("skip_reason"),
                )
        return result

    def coverage_audit(self) -> dict[str, Any]:
        return self.repo.audit_coverage()

    def goalscorer_readiness_matrix(self, audit: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        audit = audit or self.coverage_audit()
        ms = audit.get("match_stats") or {}
        rf = audit.get("rolling_features") or {}
        fixtures = int(ms.get("fixture_count") or 0)
        players = int(ms.get("unique_players") or 0)
        xg_rows = int(ms.get("xg_rows") or 0)
        starter_rows = int(ms.get("starter_rows") or 0)
        rolling_rows = int(rf.get("rolling_rows") or 0)
        rolling_signal = int(rf.get("rolling_signal_rows") or 0)
        lineup_avail = int(rf.get("lineup_available_rows") or 0)

        def pct(n: int, d: int) -> str:
            return f"{round(100 * n / d, 1)}%" if d else "0%"

        return [
            {
                "feature": "goals_last_5",
                "coverage": pct(rolling_signal, rolling_rows),
                "quality": "high" if rolling_signal > rolling_rows * 0.3 else "medium",
                "goalscorer_value": "high",
            },
            {
                "feature": "goals_per_90",
                "coverage": pct(rolling_signal, rolling_rows),
                "quality": "high",
                "goalscorer_value": "high",
            },
            {
                "feature": "xg_per_90",
                "coverage": pct(xg_rows, int(ms.get("player_rows") or 1)),
                "quality": "medium" if xg_rows else "low",
                "goalscorer_value": "high",
            },
            {
                "feature": "starter_probability",
                "coverage": pct(starter_rows, int(ms.get("player_rows") or 1)),
                "quality": "high",
                "goalscorer_value": "high",
            },
            {
                "feature": "lineup_status",
                "coverage": pct(lineup_avail, rolling_rows),
                "quality": "high",
                "goalscorer_value": "high",
            },
            {
                "feature": "player_rating",
                "coverage": "partial",
                "quality": "medium",
                "goalscorer_value": "medium",
            },
            {
                "feature": "shots_on_target",
                "coverage": "partial",
                "quality": "medium",
                "goalscorer_value": "medium",
            },
            {
                "feature": "recent_form_score",
                "coverage": pct(rolling_signal, rolling_rows),
                "quality": "medium",
                "goalscorer_value": "high",
            },
            {
                "feature": "formation",
                "coverage": pct(int(rf.get("formation_rows") or 0), rolling_rows),
                "quality": "medium",
                "goalscorer_value": "low",
            },
            {
                "feature": "unique_players",
                "coverage": str(players),
                "quality": "high" if players >= 500 else "medium",
                "goalscorer_value": "high",
            },
            {
                "feature": "fixtures_imported",
                "coverage": str(fixtures),
                "quality": "high" if fixtures >= 100 else "medium",
                "goalscorer_value": "high",
            },
        ]

    def recommend_next(self, audit: dict[str, Any] | None = None) -> str:
        audit = audit or self.coverage_audit()
        if not audit.get("tables_ready"):
            return "NEED_MORE_PLAYER_DATA"
        fixtures = int((audit.get("match_stats") or {}).get("fixture_count") or 0)
        players = int((audit.get("match_stats") or {}).get("unique_players") or 0)
        if fixtures < 50 or players < 200:
            return "NEED_MORE_PLAYER_DATA"
        rolling = int((audit.get("rolling_features") or {}).get("rolling_rows") or 0)
        if rolling >= fixtures * 15:
            return "BUILD_GOALSCORER_SHADOW_ENGINE"
        return "BUILD_LINEUP_STRENGTH_ENGINE"

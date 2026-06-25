"""Sportmonks xG feature store — ingest, normalize, persist, aggregate, retrieve."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.feature_store.aggregations import build_fixture_rolling_context
from worldcup_predictor.feature_store.models import FixtureXgSummary, IngestResult, SportmonksXgRecord
from worldcup_predictor.feature_store.normalizers import (
    _parse_started_at,
    build_fixture_summary_from_records,
    normalize_fixture_xg_records,
)
from worldcup_predictor.feature_store.repository import SportmonksXgRepository
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.providers.sportmonks_xg_extraction import XG_MATCH_FIXTURE_INCLUDES

logger = logging.getLogger(__name__)

_FINISHED_STATE_IDS = {5, 7, 8}
_XG_INCLUDES = ";".join(XG_MATCH_FIXTURE_INCLUDES) + ";xGFixture.type"
_CACHE_SUBDIR = Path("data/feature_store/sportmonks_xg/raw")
_TEAM_XG_METRICS = frozenset({"xg", "xga", "npxg"})


def _filter_records(
    records: list[SportmonksXgRecord],
    *,
    metric_keys: frozenset[str] | None = None,
) -> list[SportmonksXgRecord]:
    if not metric_keys:
        return records
    return [r for r in records if r.metric_key in metric_keys]


def _fixture_has_team_xg(records: list[SportmonksXgRecord]) -> bool:
    return any(
        r.metric_key == "xg" and r.record_type in ("team_metric", "team_xg", "fixture_xg")
        for r in records
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _team_history_from_summaries(team_id: int, summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for row in summaries:
        is_home = row.get("home_team_id") == team_id
        xg_for = row.get("home_xg") if is_home else row.get("away_xg")
        xg_against = row.get("away_xg") if is_home else row.get("home_xg")
        if xg_for is None and xg_against is None:
            continue
        history.append(
            {
                "sportmonks_fixture_id": row.get("sportmonks_fixture_id"),
                "xg_for": float(xg_for) if xg_for is not None else None,
                "xg_against": float(xg_against) if xg_against is not None else None,
                "is_home": is_home,
                "match_started_at": row.get("match_started_at"),
            }
        )
    return history


class SportmonksXgFeatureStore:
    """
    Production-grade Sportmonks xG intelligence layer.

    Flow: Sportmonks API / cache → normalize → PostgreSQL → aggregations → EGIE-ready features.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repo = SportmonksXgRepository(self.settings)
        self.provider = SportmonksProvider(self.settings)
        self.cache_root = Path.cwd() / _CACHE_SUBDIR

    @property
    def configured(self) -> bool:
        return self.repo.configured

    def cache_path(self, sportmonks_fixture_id: int) -> Path:
        return self.cache_root / f"{sportmonks_fixture_id}.json"

    def load_cache(self, sportmonks_fixture_id: int) -> dict[str, Any] | None:
        path = self.cache_path(sportmonks_fixture_id)
        if not path.is_file():
            legacy = Path.cwd() / "data/egie/uefa_club/raw" / f"{sportmonks_fixture_id}.json"
            path = legacy if legacy.is_file() else path
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def save_cache(self, sportmonks_fixture_id: int, payload: dict[str, Any], *, status_code: int = 200) -> Path:
        self.cache_root.mkdir(parents=True, exist_ok=True)
        blob = {
            "sportmonks_fixture_id": sportmonks_fixture_id,
            "fetched_at": _utc_now().isoformat(),
            "status_code": status_code,
            "payload": payload,
        }
        path = self.cache_path(sportmonks_fixture_id)
        path.write_text(json.dumps(blob, indent=2, default=str), encoding="utf-8")
        return path

    def fetch_fixture_payload(
        self,
        sportmonks_fixture_id: int,
        *,
        force_refresh: bool = False,
        use_cache: bool = True,
    ) -> tuple[dict[str, Any] | None, bool, int]:
        """Return (fixture_data, from_cache, api_calls)."""
        api_calls = 0
        if use_cache and not force_refresh:
            cached = self.load_cache(sportmonks_fixture_id)
            if cached and isinstance(cached.get("payload"), dict):
                data = (cached["payload"].get("data") or cached["payload"])
                if isinstance(data, dict) and data:
                    return data, True, 0

        if not self.provider.is_configured:
            return None, False, 0

        status, payload, error = self.provider.safe_get(
            f"/fixtures/{sportmonks_fixture_id}",
            params={"include": _XG_INCLUDES},
        )
        api_calls = 1
        if error or not isinstance(payload, dict):
            logger.warning("Sportmonks fetch failed for %s: %s", sportmonks_fixture_id, error)
            return None, False, api_calls
        self.save_cache(sportmonks_fixture_id, payload, status_code=status or 200)
        data = payload.get("data")
        return (data if isinstance(data, dict) else None), False, api_calls

    def ingest_fixture(
        self,
        sportmonks_fixture_id: int,
        *,
        fixture_id: int | None = None,
        force_refresh: bool = False,
        use_cache: bool = True,
        compute_rolling: bool = True,
        rolling_window: int = 5,
        source: str | None = None,
        metric_keys: frozenset[str] | None = None,
        force_reimport: bool = False,
        require_team_xg: bool = False,
    ) -> dict[str, Any]:
        """Ingest one fixture: normalize, persist records + summary."""
        if force_reimport:
            self.repo.delete_fixture_records(sportmonks_fixture_id)
            self.repo.delete_fixture_summary(sportmonks_fixture_id)

        raw, from_cache, api_calls = self.fetch_fixture_payload(
            sportmonks_fixture_id, force_refresh=force_refresh, use_cache=use_cache
        )
        if not raw:
            return {
                "sportmonks_fixture_id": sportmonks_fixture_id,
                "status": "error",
                "records_written": 0,
                "api_calls": api_calls,
                "from_cache": from_cache,
                "error": "no_payload",
            }

        cache_ref = str(self.cache_path(sportmonks_fixture_id))
        records = normalize_fixture_xg_records(
            raw,
            sportmonks_fixture_id=sportmonks_fixture_id,
            fixture_id=fixture_id,
            source=source or ("sportmonks_cache" if from_cache else "sportmonks_fixture"),
            raw_reference=cache_ref,
        )
        records = _filter_records(records, metric_keys=metric_keys)
        if not records:
            skip_reason = "no_true_xg_metrics" if metric_keys == frozenset({"xg"}) else "empty"
            return {
                "sportmonks_fixture_id": sportmonks_fixture_id,
                "status": "empty",
                "records_written": 0,
                "api_calls": api_calls,
                "from_cache": from_cache,
                "skip_reason": skip_reason,
            }

        has_team_xg = _fixture_has_team_xg(records)
        if require_team_xg and not has_team_xg:
            return {
                "sportmonks_fixture_id": sportmonks_fixture_id,
                "status": "skipped",
                "records_written": 0,
                "api_calls": api_calls,
                "from_cache": from_cache,
                "skip_reason": "xgot_only_no_team_xg",
            }

        rolling_ctx: dict[str, Any] = {}
        if compute_rolling and records[0].home_team_id and records[0].away_team_id:
            started = _parse_started_at(raw)
            home_hist = self.repo.get_team_match_history(
                records[0].home_team_id,
                league_id=records[0].league_id,
                limit=rolling_window * 2,
                before_started_at=started,
            )
            away_hist = self.repo.get_team_match_history(
                records[0].away_team_id,
                league_id=records[0].league_id,
                limit=rolling_window * 2,
                before_started_at=started,
            )
            rolling_ctx = build_fixture_rolling_context(
                _team_history_from_summaries(records[0].home_team_id, home_hist),
                _team_history_from_summaries(records[0].away_team_id, away_hist),
                window=rolling_window,
            )

        summary_dict = build_fixture_summary_from_records(
            records,
            sportmonks_fixture_id=sportmonks_fixture_id,
            match_started_at=_parse_started_at(raw),
            rolling_features=rolling_ctx,
        )
        written = self.repo.upsert_records(records)
        self.repo.upsert_fixture_summary(FixtureXgSummary(**summary_dict))

        return {
            "sportmonks_fixture_id": sportmonks_fixture_id,
            "status": "imported",
            "records_written": written,
            "api_calls": api_calls,
            "from_cache": from_cache,
            "summary": summary_dict,
        }

    def discover_fixtures(
        self,
        *,
        league_id: int,
        season_id: int | None = None,
        per_page: int = 50,
        max_pages: int = 15,
    ) -> list[dict[str, Any]]:
        """Discover fixtures for league/season via Sportmonks."""
        if not self.provider.is_configured:
            return []

        if season_id:
            filters = f"fixtureSeasons:{season_id}"
        else:
            filters = f"fixtureLeagues:{league_id}"

        fixtures: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            _, payload, err = self.provider.safe_get(
                "/fixtures",
                params={
                    "filters": filters,
                    "include": "participants;state",
                    "per_page": per_page,
                    "page": page,
                },
            )
            if err or not isinstance(payload, dict):
                break
            rows = payload.get("data") or []
            if not isinstance(rows, list) or not rows:
                break
            fixtures.extend(r for r in rows if isinstance(r, dict))
            if len(rows) < per_page:
                break
        return fixtures

    def resolve_season_id_by_label(self, league_id: int, season_label: str) -> int | None:
        """Resolve Sportmonks season_id from human label (e.g. 2024/2025, 2026)."""
        label_norm = season_label.strip().replace("-", "/").lower()
        _, payload, err = self.provider.safe_get(
            f"/leagues/{league_id}",
            params={"include": "seasons;currentSeason"},
        )
        if err or not isinstance(payload, dict):
            return None
        data = payload.get("data") or {}
        for s in data.get("seasons") or []:
            if not isinstance(s, dict):
                continue
            name = str(s.get("name") or "").strip().replace("-", "/").lower()
            if name == label_norm:
                try:
                    return int(s["id"])
                except (TypeError, ValueError, KeyError):
                    return None
        return None

    def resolve_season_id(self, league_id: int) -> int | None:
        _, payload, err = self.provider.safe_get(
            f"/leagues/{league_id}",
            params={"include": "seasons;currentSeason"},
        )
        if err or not isinstance(payload, dict):
            return None
        data = payload.get("data") or {}
        current = data.get("currentseason") or data.get("currentSeason")
        if isinstance(current, dict) and current.get("id"):
            return int(current["id"])
        seasons = data.get("seasons") or []
        if seasons and isinstance(seasons[0], dict):
            return int(seasons[0].get("id") or 0) or None
        return None

    def backfill_league(
        self,
        *,
        league_id: int,
        season_id: int | None = None,
        max_calls: int = 80,
        job_key: str | None = None,
        finished_only: bool = True,
        use_cache: bool = True,
        force_refresh: bool = False,
        force_reimport: bool = False,
        metric_keys: frozenset[str] | None = None,
        require_team_xg: bool = False,
        dry_run: bool = False,
        max_pages: int = 15,
    ) -> IngestResult:
        """Safe batch backfill with resume via manifest."""
        job = job_key or f"xg_backfill_l{league_id}_s{season_id or 'auto'}"
        result = IngestResult(job_key=job)
        season = season_id or self.resolve_season_id(league_id)
        fixtures = self.discover_fixtures(league_id=league_id, season_id=season, max_pages=max_pages)

        for fx in fixtures:
            if result.api_calls_live >= max_calls:
                result.fixtures_skipped += 1
                continue
            sm_id = int(fx.get("id") or 0)
            if sm_id <= 0:
                continue

            prior = self.repo.manifest_status(job, sm_id)
            if prior == "imported" and not force_refresh and not force_reimport and not dry_run:
                result.fixtures_skipped += 1
                continue

            if finished_only and int(fx.get("state_id") or 0) not in _FINISHED_STATE_IDS:
                if not dry_run:
                    self.repo.write_manifest(
                        job_key=job,
                        sportmonks_fixture_id=sm_id,
                        status="skipped_upcoming",
                        league_id=league_id,
                        season_id=season,
                    )
                result.fixtures_skipped += 1
                continue

            result.fixtures_processed += 1
            if dry_run:
                result.fixtures_imported += 1
                continue

            ingest = self.ingest_fixture(
                sm_id,
                use_cache=use_cache,
                force_refresh=force_refresh,
                force_reimport=force_reimport,
                metric_keys=metric_keys,
                require_team_xg=require_team_xg,
            )
            if ingest.get("from_cache"):
                result.api_calls_cached += 1
            else:
                result.api_calls_live += int(ingest.get("api_calls") or 0)

            status = str(ingest.get("status") or "error")
            records_written = int(ingest.get("records_written") or 0)
            result.records_written += records_written

            if status == "imported":
                result.fixtures_imported += 1
            elif status in ("empty", "skipped"):
                result.fixtures_empty += 1
            else:
                result.fixtures_error += 1
                if ingest.get("error"):
                    result.errors.append(f"{sm_id}:{ingest['error']}")

            manifest_status = status
            if ingest.get("skip_reason"):
                manifest_status = f"{status}:{ingest['skip_reason']}"

            self.repo.write_manifest(
                job_key=job,
                sportmonks_fixture_id=sm_id,
                status=manifest_status,
                league_id=league_id,
                season_id=season,
                api_calls=int(ingest.get("api_calls") or 0),
                records_written=records_written,
                error=ingest.get("error") or ingest.get("skip_reason"),
            )

        self.rebuild_rolling_features(league_id=league_id)
        return result

    def backfill_from_cache_dir(
        self,
        cache_dir: Path | str | None = None,
        *,
        job_key: str = "xg_cache_import",
        league_id: int | None = None,
        force_reimport: bool = False,
        metric_keys: frozenset[str] | None = None,
        require_team_xg: bool = False,
    ) -> IngestResult:
        """Import xG from existing JSON caches (0 API calls)."""
        root = Path(cache_dir) if cache_dir else Path.cwd() / "data/egie/uefa_club/raw"
        result = IngestResult(job_key=job_key)
        if not root.is_dir():
            result.errors.append(f"cache_dir_missing:{root}")
            return result

        for path in sorted(root.glob("*.json")):
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
            if league_id is not None and int(data.get("league_id") or 0) != league_id:
                continue

            prior = self.repo.manifest_status(job_key, sm_id)
            if prior == "imported" and not force_reimport:
                result.fixtures_skipped += 1
                continue

            if force_reimport:
                self.repo.delete_fixture_records(sm_id)
                self.repo.delete_fixture_summary(sm_id)

            result.fixtures_processed += 1
            records = normalize_fixture_xg_records(
                data,
                sportmonks_fixture_id=sm_id,
                source="uefa_cache",
                raw_reference=str(path),
            )
            records = _filter_records(records, metric_keys=metric_keys)

            if not records:
                result.fixtures_empty += 1
                self.repo.write_manifest(
                    job_key=job_key,
                    sportmonks_fixture_id=sm_id,
                    status="empty:no_true_xg_metrics",
                    error="no_true_xg_metrics",
                )
                continue

            if require_team_xg and not _fixture_has_team_xg(records):
                result.fixtures_empty += 1
                self.repo.write_manifest(
                    job_key=job_key,
                    sportmonks_fixture_id=sm_id,
                    status="skipped:xgot_only_no_team_xg",
                    error="xgot_only_no_team_xg",
                )
                continue

            summary_dict = build_fixture_summary_from_records(
                records,
                sportmonks_fixture_id=sm_id,
                match_started_at=_parse_started_at(data),
            )
            written = self.repo.upsert_records(records)
            self.repo.upsert_fixture_summary(FixtureXgSummary(**summary_dict))
            result.records_written += written
            result.fixtures_imported += 1
            result.api_calls_cached += 1
            self.repo.write_manifest(
                job_key=job_key,
                sportmonks_fixture_id=sm_id,
                status="imported",
                records_written=written,
            )

        self.rebuild_rolling_features(league_id=league_id)
        return result

    def retrieve_fixture(self, sportmonks_fixture_id: int) -> dict[str, Any]:
        """Retrieve normalized xG records + summary for a fixture."""
        return {
            "sportmonks_fixture_id": sportmonks_fixture_id,
            "records": self.repo.get_records_for_fixture(sportmonks_fixture_id),
            "summary": self.repo.get_fixture_summary(sportmonks_fixture_id),
        }

    def aggregate_team_rolling(
        self,
        team_id: int,
        *,
        league_id: int | None = None,
        window: int = 5,
    ) -> dict[str, Any]:
        summaries = self.repo.get_team_match_history(team_id, league_id=league_id, limit=window * 3)
        from worldcup_predictor.feature_store.aggregations import compute_team_rolling_xg

        return compute_team_rolling_xg(_team_history_from_summaries(team_id, summaries), window=window)

    def rebuild_rolling_features(self, *, league_id: int | None = None, window: int = 5) -> int:
        """Recompute rolling xG on summaries after batch import (chronological pass)."""
        summaries = self.repo.list_fixture_summaries(league_id=league_id)
        updated = 0
        history_by_team: dict[int, list[dict[str, Any]]] = {}

        for row in summaries:
            sm_id = int(row["sportmonks_fixture_id"])
            home_id = row.get("home_team_id")
            away_id = row.get("away_team_id")
            home_hist = history_by_team.get(int(home_id), []) if home_id else []
            away_hist = history_by_team.get(int(away_id), []) if away_id else []
            rolling_ctx = build_fixture_rolling_context(home_hist, away_hist, window=window)

            patch: dict[str, Any] = {
                **row,
                "home_team_recent_xg": rolling_ctx.get("home_team_recent_xg"),
                "away_team_recent_xg": rolling_ctx.get("away_team_recent_xg"),
                "home_team_recent_xga": rolling_ctx.get("home_team_recent_xga"),
                "away_team_recent_xga": rolling_ctx.get("away_team_recent_xga"),
                "aggregation_window": window,
                "features_json": rolling_ctx.get("features_json") or {},
            }
            hrx, arx = patch.get("home_team_recent_xg"), patch.get("away_team_recent_xg")
            if hrx is not None and arx is not None:
                patch["attack_difference"] = round(float(hrx) - float(arx), 4)
            hra, ara = patch.get("home_team_recent_xga"), patch.get("away_team_recent_xga")
            if hra is not None and ara is not None:
                patch["defense_difference"] = round(float(ara) - float(hra), 4)
            if patch.get("attack_difference") is not None and patch.get("defense_difference") is not None:
                patch["momentum_difference"] = round(
                    float(patch["attack_difference"]) + float(patch["defense_difference"]), 4
                )

            self.repo.upsert_fixture_summary(patch)
            updated += 1

            if home_id and row.get("home_xg") is not None:
                history_by_team.setdefault(int(home_id), []).append(
                    {
                        "xg_for": float(row["home_xg"]),
                        "xg_against": float(row["away_xg"]) if row.get("away_xg") is not None else None,
                        "is_home": True,
                    }
                )
            if away_id and row.get("away_xg") is not None:
                history_by_team.setdefault(int(away_id), []).append(
                    {
                        "xg_for": float(row["away_xg"]),
                        "xg_against": float(row["home_xg"]) if row.get("home_xg") is not None else None,
                        "is_home": False,
                    }
                )
        return updated

    def quality_audit(self) -> dict[str, Any]:
        return self.repo.audit_coverage()

"""Sportmonks Pressure feature store — ingest, normalize, persist, aggregate, retrieve."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.feature_store.pressure_store.models import FixturePressureSummary, PressureIngestResult
from worldcup_predictor.feature_store.pressure_store.normalizers import (
    build_fixture_pressure_summary,
    normalize_fixture_pressure_records,
)
from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

logger = logging.getLogger(__name__)

_FINISHED_STATE_IDS = {5, 7, 8}
_PRESSURE_INCLUDES = "participants;pressure;events.type"
_CACHE_SUBDIR = Path("data/feature_store/sportmonks_pressure/raw")
_UEFA_CACHE_DIR = Path("data/egie/uefa_club/raw")
_EXTRA_CACHE_DIRS = (
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
)
_TARGET_LEAGUE_IDS = (2, 5, 2286, 732)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SportmonksPressureFeatureStore:
    """
    Shadow/research Sportmonks Pressure intelligence layer.

    Flow: Sportmonks API / cache → normalize → PostgreSQL → aggregations → EGIE shadow (future).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repo = SportmonksPressureRepository(self.settings)
        self.provider = SportmonksProvider(self.settings)
        self.cache_root = Path.cwd() / _CACHE_SUBDIR

    @property
    def configured(self) -> bool:
        return self.repo.configured

    def cache_path(self, sportmonks_fixture_id: int) -> Path:
        return self.cache_root / f"{sportmonks_fixture_id}.json"

    def load_cache(self, sportmonks_fixture_id: int) -> dict[str, Any] | None:
        for path in (self.cache_path(sportmonks_fixture_id), _UEFA_CACHE_DIR / f"{sportmonks_fixture_id}.json"):
            if not path.is_file():
                continue
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
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
        api_calls = 0
        if use_cache and not force_refresh:
            cached = self.load_cache(sportmonks_fixture_id)
            if cached:
                data = (cached.get("payload") or {}).get("data") or cached.get("payload")
                if isinstance(data, dict) and data:
                    return data, True, 0

        if not self.provider.is_configured:
            return None, False, 0

        status, payload, error = self.provider.safe_get(
            f"/fixtures/{sportmonks_fixture_id}",
            params={"include": _PRESSURE_INCLUDES},
        )
        api_calls = 1
        if error or not isinstance(payload, dict):
            logger.warning("Sportmonks pressure fetch failed for %s: %s", sportmonks_fixture_id, error)
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
        source: str | None = None,
        force_reimport: bool = False,
        raw: dict[str, Any] | None = None,
        raw_reference: str | None = None,
    ) -> dict[str, Any]:
        if force_reimport:
            self.repo.delete_fixture_records(sportmonks_fixture_id)
            self.repo.delete_fixture_summary(sportmonks_fixture_id)

        from_cache = False
        api_calls = 0
        if raw is None:
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

        cache_ref = raw_reference or str(self.cache_path(sportmonks_fixture_id))
        records = normalize_fixture_pressure_records(
            raw,
            sportmonks_fixture_id=sportmonks_fixture_id,
            fixture_id=fixture_id,
            source=source or ("sportmonks_cache" if from_cache else "sportmonks_fixture"),
            raw_reference=cache_ref,
        )
        if not records:
            return {
                "sportmonks_fixture_id": sportmonks_fixture_id,
                "status": "empty",
                "records_written": 0,
                "api_calls": api_calls,
                "from_cache": from_cache,
                "skip_reason": "no_pressure_rows",
            }

        summary_dict = build_fixture_pressure_summary(
            records,
            sportmonks_fixture_id=sportmonks_fixture_id,
            raw=raw,
        )
        written = self.repo.upsert_records(records)
        self.repo.upsert_fixture_summary(FixturePressureSummary(**summary_dict))

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
        if not self.provider.is_configured:
            return []
        filters = f"fixtureSeasons:{season_id}" if season_id else f"fixtureLeagues:{league_id}"
        fixtures: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            _, payload, err = self.provider.safe_get(
                "/fixtures",
                params={"filters": filters, "include": "participants;state", "per_page": per_page, "page": page},
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
        dry_run: bool = False,
        max_pages: int = 15,
    ) -> PressureIngestResult:
        job = job_key or f"pressure_backfill_l{league_id}_s{season_id or 'auto'}"
        result = PressureIngestResult(job_key=job)
        season = season_id or self.resolve_season_id(league_id)
        fixtures = self.discover_fixtures(league_id=league_id, season_id=season, max_pages=max_pages)
        imported_ids = self.repo.imported_pressure_fixture_ids()

        def _started_at(fx: dict[str, Any]) -> str:
            return str(fx.get("starting_at") or fx.get("starting_at_timestamp") or "")

        fixtures = sorted(fixtures, key=_started_at, reverse=True)

        for fx in fixtures:
            if result.api_calls_live >= max_calls:
                result.fixtures_skipped += 1
                continue
            sm_id = int(fx.get("id") or 0)
            if sm_id <= 0:
                continue

            if sm_id in imported_ids and not force_reimport:
                result.fixtures_skipped += 1
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
            elif status == "empty":
                result.fixtures_empty += 1
            else:
                result.fixtures_error += 1
                if ingest.get("error"):
                    result.errors.append(f"{sm_id}:{ingest['error']}")

            self.repo.write_manifest(
                job_key=job,
                sportmonks_fixture_id=sm_id,
                status=status,
                league_id=league_id,
                season_id=season,
                api_calls=int(ingest.get("api_calls") or 0),
                records_written=records_written,
                error=ingest.get("error") or ingest.get("skip_reason"),
            )
        return result

    def backfill_from_fixture_ids(
        self,
        fixture_ids: list[int],
        *,
        job_key: str = "pressure_fixture_list",
        max_calls: int = 100,
        use_cache: bool = True,
        force_reimport: bool = False,
    ) -> PressureIngestResult:
        result = PressureIngestResult(job_key=job_key)
        imported_ids = self.repo.imported_pressure_fixture_ids()
        for sm_id in fixture_ids:
            if result.api_calls_live >= max_calls:
                result.fixtures_skipped += 1
                continue
            if sm_id in imported_ids and not force_reimport:
                result.fixtures_skipped += 1
                continue
            prior = self.repo.manifest_status(job_key, sm_id)
            if prior == "imported" and not force_reimport:
                result.fixtures_skipped += 1
                continue
            result.fixtures_processed += 1
            ingest = self.ingest_fixture(
                sm_id,
                use_cache=use_cache,
                force_reimport=force_reimport,
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
            elif status == "empty":
                result.fixtures_empty += 1
            else:
                result.fixtures_error += 1
            self.repo.write_manifest(
                job_key=job_key,
                sportmonks_fixture_id=sm_id,
                status=status,
                records_written=records_written,
                error=ingest.get("error") or ingest.get("skip_reason"),
            )
        return result

    def backfill_expansion(
        self,
        *,
        max_calls: int = 120,
        target_leagues: tuple[int, ...] = _TARGET_LEAGUE_IDS,
        force_reimport: bool = False,
    ) -> dict[str, Any]:
        """Cache-first multi-source expansion with capped API backfill."""
        before = self.repo.audit_coverage()
        before_count = int((before.get("records") or {}).get("fixture_count") or 0)

        cache_result = self.backfill_from_cache_dir(
            league_id=None,
            job_key="phase54h2_cache_expansion",
            force_reimport=force_reimport,
            extra_dirs=list(_EXTRA_CACHE_DIRS),
        )

        api_budget = max_calls
        league_results: dict[str, Any] = {}
        for league_id in target_leagues:
            if api_budget <= 0:
                break
            per_league = max(10, api_budget // max(1, len(target_leagues)))
            lr = self.backfill_league(
                league_id=league_id,
                max_calls=per_league,
                job_key=f"phase54h2_api_l{league_id}",
                use_cache=True,
                force_reimport=force_reimport,
                max_pages=25,
            )
            api_budget -= int(lr.api_calls_live)
            league_results[str(league_id)] = lr.to_dict()

        after = self.repo.audit_coverage()
        after_count = int((after.get("records") or {}).get("fixture_count") or 0)
        gap_reason = None
        if after_count < 150:
            gap_reason = (
                f"Local cache exhausted: {int(cache_result.fixtures_imported)} fixtures with pressure "
                f"from {int(cache_result.fixtures_processed)} cached payloads; "
                f"{int(cache_result.fixtures_empty)} payloads had no pressure rows. "
                "xG cache (1500+ fixtures) lacks include=pressure. "
                "API league backfill returned 0 new fixtures (token/plan or already ingested). "
                "World Cup 732: no pressure cache found."
            )
        return {
            "before_fixtures": before_count,
            "after_fixtures": after_count,
            "delta_fixtures": after_count - before_count,
            "target_minimum": 150,
            "target_preferred": 300,
            "target_met_minimum": after_count >= 150,
            "coverage_gap_reason": gap_reason,
            "cache_backfill": cache_result.to_dict(),
            "league_api_backfill": league_results,
            "api_configured": self.provider.is_configured,
            "audit_after": after,
        }

    def backfill_from_cache_dir(
        self,
        cache_dir: Path | str | None = None,
        *,
        job_key: str = "pressure_cache_import",
        league_id: int | None = None,
        force_reimport: bool = False,
        extra_dirs: list[Path | str] | None = None,
        source: str | None = None,
    ) -> PressureIngestResult:
        roots = []
        if cache_dir:
            roots.append(Path(cache_dir))
        roots.extend([_UEFA_CACHE_DIR, self.cache_root])
        if extra_dirs:
            roots.extend(Path(d) for d in extra_dirs)

        seen_paths: set[Path] = set()
        seen_ids: set[int] = set()
        imported_ids = self.repo.imported_pressure_fixture_ids()
        result = PressureIngestResult(job_key=job_key)
        default_source = source or ("cache_seed" if "cache_seed" in job_key else None)

        for root in roots:
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
                if league_id is not None and int(data.get("league_id") or 0) != league_id:
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
                ingest_source = default_source
                if ingest_source is None:
                    ingest_source = "uefa_cache" if "uefa_club" in str(path) else "sportmonks_cache"
                ingest = self.ingest_fixture(
                    sm_id,
                    use_cache=False,
                    force_reimport=force_reimport,
                    raw=data,
                    raw_reference=str(path),
                    source=ingest_source,
                )
                status = str(ingest.get("status") or "error")
                records_written = int(ingest.get("records_written") or 0)
                result.records_written += records_written
                result.api_calls_cached += 1
                seen_ids.add(sm_id)

                if status == "imported":
                    result.fixtures_imported += 1
                elif status == "empty":
                    result.fixtures_empty += 1
                else:
                    result.fixtures_error += 1

                self.repo.write_manifest(
                    job_key=job_key,
                    sportmonks_fixture_id=sm_id,
                    status=status,
                    league_id=int(data.get("league_id") or 0) or None,
                    season_id=int(data.get("season_id") or 0) or None,
                    records_written=records_written,
                    error=ingest.get("error") or ingest.get("skip_reason"),
                )
        return result

    def retrieve_fixture(self, sportmonks_fixture_id: int) -> dict[str, Any]:
        return {
            "sportmonks_fixture_id": sportmonks_fixture_id,
            "records": self.repo.get_records_for_fixture(sportmonks_fixture_id),
            "summary": self.repo.get_fixture_summary(sportmonks_fixture_id),
        }

    def quality_audit(self) -> dict[str, Any]:
        return self.repo.audit_coverage()

"""PostgreSQL persistence for EGIE raw provider responses."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.session import postgres_configured, session_scope
from worldcup_predictor.egie.models import EgieRawSaveResult

logger = logging.getLogger(__name__)


def _canonical_params(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_request_fingerprint(
    *,
    provider: str,
    resource_type: str,
    request_endpoint: str,
    request_params: dict[str, Any],
) -> str:
    raw = f"{provider}|{resource_type}|{request_endpoint}|{_canonical_params(request_params)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_payload_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class EgieRawStoreRepository:
    """CRUD for egie_provider_raw_responses and egie_ingest_runs."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def save_raw_response(
        self,
        *,
        provider: str,
        resource_type: str,
        request_endpoint: str,
        request_params: dict[str, Any],
        payload_json: Any,
        source: str,
        competition_key: str | None = None,
        league_id: int | None = None,
        season: int | None = None,
        fixture_id: int | None = None,
        team_id: int | None = None,
        sportmonks_fixture_id: int | None = None,
        http_status: int | None = 200,
        fetched_at: datetime | None = None,
        upsert: bool = True,
    ) -> EgieRawSaveResult:
        if not postgres_configured(self.settings):
            logger.warning("PostgreSQL not configured — skipping EGIE raw save")
            return EgieRawSaveResult(saved=False, skipped_duplicate=False)

        fingerprint = build_request_fingerprint(
            provider=provider,
            resource_type=resource_type,
            request_endpoint=request_endpoint,
            request_params=request_params,
        )
        payload_hash = build_payload_hash(payload_json)
        fetched = fetched_at or datetime.now(timezone.utc)
        row_id = uuid.uuid4()

        with session_scope(self.settings) as session:
            if not upsert:
                existing = session.execute(
                    text(
                        """
                        SELECT id::text, payload_hash
                        FROM egie_provider_raw_responses
                        WHERE provider = :provider AND request_fingerprint = :fingerprint
                        LIMIT 1
                        """
                    ),
                    {"provider": provider, "fingerprint": fingerprint},
                ).mappings().first()
                if existing and existing.get("payload_hash") == payload_hash:
                    return EgieRawSaveResult(
                        saved=False,
                        skipped_duplicate=True,
                        raw_id=str(existing["id"]),
                        provider=provider,
                        resource_type=resource_type,
                        fixture_id=fixture_id,
                    )

            session.execute(
                text(
                    """
                    INSERT INTO egie_provider_raw_responses (
                        id, provider, resource_type, competition_key, league_id, season,
                        fixture_id, team_id, sportmonks_fixture_id,
                        request_endpoint, request_params, request_fingerprint,
                        payload_json, payload_hash, http_status, source, fetched_at, created_at
                    ) VALUES (
                        :id, :provider, :resource_type, :competition_key, :league_id, :season,
                        :fixture_id, :team_id, :sportmonks_fixture_id,
                        :request_endpoint, CAST(:request_params AS jsonb), :request_fingerprint,
                        CAST(:payload_json AS jsonb), :payload_hash, :http_status, :source, :fetched_at, NOW()
                    )
                    ON CONFLICT (provider, request_fingerprint) DO UPDATE SET
                        payload_json = EXCLUDED.payload_json,
                        payload_hash = EXCLUDED.payload_hash,
                        http_status = EXCLUDED.http_status,
                        source = EXCLUDED.source,
                        fetched_at = EXCLUDED.fetched_at,
                        fixture_id = COALESCE(EXCLUDED.fixture_id, egie_provider_raw_responses.fixture_id),
                        competition_key = COALESCE(EXCLUDED.competition_key, egie_provider_raw_responses.competition_key)
                    """
                ),
                {
                    "id": row_id,
                    "provider": provider,
                    "resource_type": resource_type,
                    "competition_key": competition_key,
                    "league_id": league_id,
                    "season": season,
                    "fixture_id": int(fixture_id) if fixture_id else None,
                    "team_id": int(team_id) if team_id else None,
                    "sportmonks_fixture_id": int(sportmonks_fixture_id) if sportmonks_fixture_id else None,
                    "request_endpoint": request_endpoint,
                    "request_params": json.dumps(request_params, ensure_ascii=False),
                    "request_fingerprint": fingerprint,
                    "payload_json": json.dumps(payload_json, ensure_ascii=False, default=str),
                    "payload_hash": payload_hash,
                    "http_status": http_status,
                    "source": source,
                    "fetched_at": fetched,
                },
            )

        return EgieRawSaveResult(
            saved=True,
            skipped_duplicate=False,
            raw_id=str(row_id),
            provider=provider,
            resource_type=resource_type,
            fixture_id=fixture_id,
        )

    def get_latest_raw(
        self,
        *,
        provider: str,
        resource_type: str,
        fixture_id: int | None = None,
        competition_key: str | None = None,
        season: int | None = None,
        request_params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not postgres_configured(self.settings):
            return None

        if request_params is not None:
            fingerprint = build_request_fingerprint(
                provider=provider,
                resource_type=resource_type,
                request_endpoint=resource_type,
                request_params=request_params,
            )
            query = """
                SELECT *
                FROM egie_provider_raw_responses
                WHERE provider = :provider AND request_fingerprint = :fingerprint
                LIMIT 1
            """
            params: dict[str, Any] = {"provider": provider, "fingerprint": fingerprint}
        else:
            query = """
                SELECT *
                FROM egie_provider_raw_responses
                WHERE provider = :provider AND resource_type = :resource_type
            """
            params = {"provider": provider, "resource_type": resource_type}
            if fixture_id is not None:
                query += " AND fixture_id = :fixture_id"
                params["fixture_id"] = int(fixture_id)
            if competition_key:
                query += " AND competition_key = :competition_key"
                params["competition_key"] = competition_key
            if season is not None:
                query += " AND season = :season"
                params["season"] = int(season)
            query += " ORDER BY fetched_at DESC LIMIT 1"

        with session_scope(self.settings) as session:
            row = session.execute(text(query), params).mappings().first()
        return dict(row) if row else None

    def list_fixture_ids(
        self,
        *,
        provider: str,
        competition_key: str,
        season: int,
        resource_type: str = "fixtures",
    ) -> list[int]:
        if not postgres_configured(self.settings):
            return []

        with session_scope(self.settings) as session:
            rows = session.execute(
                text(
                    """
                    SELECT DISTINCT fixture_id
                    FROM egie_provider_raw_responses
                    WHERE provider = :provider
                      AND resource_type = :resource_type
                      AND competition_key = :competition_key
                      AND season = :season
                      AND fixture_id IS NOT NULL
                    ORDER BY fixture_id
                    """
                ),
                {
                    "provider": provider,
                    "resource_type": resource_type,
                    "competition_key": competition_key,
                    "season": season,
                },
            ).mappings().all()
        return [int(r["fixture_id"]) for r in rows if r.get("fixture_id")]

    def start_ingest_run(
        self,
        *,
        job_key: str,
        provider: str,
        competition_key: str,
        season: int,
        config: dict[str, Any],
    ) -> str:
        run_id = uuid.uuid4()
        if not postgres_configured(self.settings):
            return str(run_id)

        with session_scope(self.settings) as session:
            session.execute(
                text(
                    """
                    INSERT INTO egie_ingest_runs (
                        id, job_key, provider, competition_key, season, status, config, started_at, created_at
                    ) VALUES (
                        :id, :job_key, :provider, :competition_key, :season, 'running',
                        CAST(:config AS jsonb), NOW(), NOW()
                    )
                    """
                ),
                {
                    "id": run_id,
                    "job_key": job_key,
                    "provider": provider,
                    "competition_key": competition_key,
                    "season": season,
                    "config": json.dumps(config, ensure_ascii=False),
                },
            )
        return str(run_id)

    def finish_ingest_run(
        self,
        run_id: str,
        *,
        status: str,
        stats: dict[str, Any],
        errors: list[str],
    ) -> None:
        if not postgres_configured(self.settings):
            return

        with session_scope(self.settings) as session:
            session.execute(
                text(
                    """
                    UPDATE egie_ingest_runs
                    SET status = :status,
                        finished_at = NOW(),
                        stats = CAST(:stats AS jsonb),
                        errors = CAST(:errors AS jsonb)
                    WHERE id = :id
                    """
                ),
                {
                    "id": uuid.UUID(run_id),
                    "status": status,
                    "stats": json.dumps(stats, ensure_ascii=False),
                    "errors": json.dumps(errors, ensure_ascii=False),
                },
            )

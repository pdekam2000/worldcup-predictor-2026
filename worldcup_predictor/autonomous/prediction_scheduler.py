"""Autonomous prediction generation — Phase 61."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from worldcup_predictor.autonomous.fixture_discovery import DiscoveredFixture
from worldcup_predictor.autonomous.market_extract import (
    extract_markets_from_elite_bundle,
    extract_markets_from_production_payload,
)
from worldcup_predictor.autonomous.store import AutonomousStore
from worldcup_predictor.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

ELITE_JSONL = Path(__file__).resolve().parents[2] / "data" / "shadow" / "elite_orchestrator_predictions.jsonl"


@dataclass
class PredictionSchedulerResult:
    fixtures_processed: int = 0
    production_snapshots: int = 0
    elite_snapshots: int = 0
    skipped_cache: int = 0
    skipped_dry_run: int = 0
    errors: int = 0
    api_calls_used: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixtures_processed": self.fixtures_processed,
            "production_snapshots": self.production_snapshots,
            "elite_snapshots": self.elite_snapshots,
            "skipped_cache": self.skipped_cache,
            "skipped_dry_run": self.skipped_dry_run,
            "errors": self.errors,
            "api_calls_used": self.api_calls_used,
            "details": self.details[:50],
        }


def _load_elite_bundles() -> dict[int, dict[str, Any]]:
    if not ELITE_JSONL.is_file():
        return {}
    out: dict[int, dict[str, Any]] = {}
    for line in ELITE_JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            fid = int(row.get("fixture_id") or 0)
            if fid:
                out[fid] = row
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return out


def _get_production_payload(
    fixture: DiscoveredFixture,
    *,
    settings: Settings,
    result: PredictionSchedulerResult,
) -> dict[str, Any] | None:
    from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore

    store = WorldcupPredictionStore(settings)
    cached = store.get(
        fixture.fixture_id,
        competition_key=fixture.competition_key,
        season=fixture.season or 2026,
        locale="en",
    )
    if cached:
        result.skipped_cache += 1
        return cached

    if settings.autonomous_dry_run:
        return None

    from worldcup_predictor.automation.worldcup_background.prediction_runner import (
        build_api_payload,
    )
    from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline

    pipeline = PredictPipeline(settings, competition_key=fixture.competition_key, locale="en")
    pipe_result = pipeline.run(fixture.fixture_id, record_history=False)
    result.api_calls_used += 1
    if not pipe_result.success:
        return None
    return build_api_payload(
        pipe_result,
        intelligence_report=pipe_result.intelligence_report,
        specialist_report=pipe_result.specialist_report,
    )


def _store_market_snapshots(
    store: AutonomousStore,
    *,
    fixture: DiscoveredFixture,
    engine: str,
    source: str,
    markets: list[dict[str, Any]],
    is_user_visible: bool,
) -> int:
    count = 0
    for m in markets:
        sid, reason = store.insert_snapshot(
            fixture_id=fixture.fixture_id,
            competition_key=fixture.competition_key,
            season=fixture.season,
            league_id=fixture.league_id,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            kickoff_utc=fixture.kickoff_utc,
            fixture_status=fixture.status,
            engine=engine,
            market_id=m["market_id"],
            prediction=m["prediction"],
            confidence=m.get("confidence"),
            tier=m.get("tier"),
            generated_by="autonomous_scheduler",
            source=source,
            is_user_visible=is_user_visible,
        )
        if sid:
            count += 1
        elif reason != "duplicate_snapshot_key":
            logger.debug("snapshot_skip fixture=%s market=%s %s", fixture.fixture_id, m["market_id"], reason)
    return count


def run_autonomous_predictions(
    fixtures: list[DiscoveredFixture],
    *,
    settings: Settings | None = None,
) -> PredictionSchedulerResult:
    settings = settings or get_settings()
    store = AutonomousStore(settings)
    result = PredictionSchedulerResult()
    elite_index = _load_elite_bundles()

    for fixture in fixtures:
        result.fixtures_processed += 1
        try:
            if not store.has_recent_snapshot(
                fixture.fixture_id, "production", freshness_hours=settings.autonomous_snapshot_freshness_hours
            ):
                if settings.autonomous_dry_run:
                    result.skipped_dry_run += 1
                else:
                    payload = _get_production_payload(fixture, settings=settings, result=result)
                    if payload:
                        markets = extract_markets_from_production_payload(payload)
                        result.production_snapshots += _store_market_snapshots(
                            store,
                            fixture=fixture,
                            engine="production",
                            source="production",
                            markets=markets,
                            is_user_visible=False,
                        )

            if not store.has_recent_snapshot(
                fixture.fixture_id, "elite_shadow", freshness_hours=settings.autonomous_snapshot_freshness_hours
            ):
                bundle = elite_index.get(fixture.fixture_id)
                if bundle and not settings.autonomous_dry_run:
                    markets = extract_markets_from_elite_bundle(bundle)
                    result.elite_snapshots += _store_market_snapshots(
                        store,
                        fixture=fixture,
                        engine="elite_shadow",
                        source="elite_shadow",
                        markets=markets,
                        is_user_visible=False,
                    )
        except Exception as exc:
            result.errors += 1
            result.details.append({"fixture_id": fixture.fixture_id, "error": str(exc)})
            logger.warning("autonomous_predict_failed fixture=%s: %s", fixture.fixture_id, exc)

    return result

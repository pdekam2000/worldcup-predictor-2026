"""Multi-competition prefetch cycle — Phase A14."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.automation.prediction_prefetch.coverage import collect_upcoming_fixtures
from worldcup_predictor.automation.prediction_prefetch.priority import sort_fixtures_by_priority
from worldcup_predictor.automation.prediction_prefetch.smart_refresh import (
    build_prefetch_signals,
    should_refresh_for_signals,
)
from worldcup_predictor.automation.worldcup_background.freshness import _parse_dt, is_prediction_fresh, should_refresh_prediction
from worldcup_predictor.automation.worldcup_background.prediction_runner import run_and_store_prediction
from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.quota.prediction_cache import kickoff_from_payload

logger = logging.getLogger(__name__)

PREFETCH_COMPETITIONS: tuple[str, ...] = (
    "world_cup_2026",
    "champions_league",
    "europa_league",
    "conference_league",
    "premier_league",
    "la_liga",
    "serie_a",
    "bundesliga",
    "ligue_1",
)


@dataclass
class PrefetchCycleResult:
    scanned: int = 0
    predicted: int = 0
    skipped_fresh: int = 0
    skipped_cap: int = 0
    errors: int = 0
    window_days: int = 7
    max_per_cycle: int = 0
    elapsed_ms: float = 0.0
    details: list[dict[str, Any]] = field(default_factory=list)


def _load_stored_payload(repo: FootballIntelligenceRepository, fixture_id: int) -> dict[str, Any] | None:
    row = repo.get_worldcup_stored_prediction(fixture_id, include_inactive=True)
    if not row or not row.get("payload_json"):
        return None
    try:
        return json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return None


def _needs_generation(
    *,
    fixture: dict[str, Any],
    payload: dict[str, Any] | None,
    force_refresh: bool,
) -> tuple[bool, str]:
    kick = _parse_dt(fixture.get("kickoff_utc"))
    has_stored = payload is not None
    fresh = False
    if payload:
        fresh, _ = is_prediction_fresh(payload, kickoff_utc=kick)

    do_run, reason = should_refresh_prediction(
        kickoff_utc=kick,
        has_stored=has_stored,
        is_fresh=fresh,
        force_refresh=force_refresh,
    )
    if do_run:
        return True, reason

    signal_refresh, sig_reason = should_refresh_for_signals(payload, kickoff_utc=kick)
    if signal_refresh:
        return True, sig_reason

    return False, "fresh_skip"


def run_prefetch_cycle(
    *,
    settings: Settings | None = None,
    window_days: int | None = None,
    max_per_cycle: int | None = None,
    competition_keys: list[str] | None = None,
    force_refresh: bool = False,
    locale: str = "en",
) -> PrefetchCycleResult:
    """Run one prefetch pass across enabled competitions (orchestration only)."""
    settings = settings or get_settings()
    if not settings.worldcup_background_prediction_enabled:
        return PrefetchCycleResult(window_days=window_days or 7, max_per_cycle=0)

    window_days = window_days if window_days is not None else getattr(
        settings, "prediction_prefetch_window_days", settings.worldcup_prediction_window_days
    )
    max_per_cycle = max_per_cycle if max_per_cycle is not None else getattr(
        settings, "prediction_prefetch_max_per_cycle", 24
    )
    throttle = float(getattr(settings, "api_throttle_delay_seconds", 1.0) or 1.0)
    keys = set(competition_keys or PREFETCH_COMPETITIONS)

    started = time.perf_counter()
    fixtures = [
        f
        for f in collect_upcoming_fixtures(settings=settings, window_days=window_days)
        if f["competition_key"] in keys
    ]
    fixtures = sort_fixtures_by_priority(fixtures)

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    store = WorldcupPredictionStore(settings)
    result = PrefetchCycleResult(
        scanned=len(fixtures),
        window_days=window_days,
        max_per_cycle=max_per_cycle,
    )

    for fixture in fixtures:
        if result.predicted >= max_per_cycle:
            result.skipped_cap += 1
            continue

        fid = int(fixture["fixture_id"])
        ck = str(fixture["competition_key"])
        existing = _load_stored_payload(repo, fid)
        do_run, reason = _needs_generation(fixture=fixture, payload=existing, force_refresh=force_refresh)
        if not do_run:
            result.skipped_fresh += 1
            result.details.append({"fixture_id": fid, "competition_key": ck, "action": "skip", "reason": reason})
            continue

        try:
            t0 = time.perf_counter()
            payload = run_and_store_prediction(
                fid,
                settings=settings,
                competition_key=ck,
                locale=locale,
                record_history=False,
                source="prefetch_a14",
            )
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            if payload.get("status") == "ok":
                payload["_prefetch_signals"] = build_prefetch_signals(payload)
                store.upsert(
                    fid,
                    payload,
                    kickoff_utc=fixture.get("kickoff_utc"),
                    source="prefetch_a14",
                )
                result.predicted += 1
                result.details.append(
                    {
                        "fixture_id": fid,
                        "competition_key": ck,
                        "action": "predicted",
                        "reason": reason,
                        "latency_ms": latency_ms,
                        "no_bet": payload.get("no_bet"),
                        "priority": fixture.get("priority_label"),
                    }
                )
            else:
                result.errors += 1
                result.details.append(
                    {
                        "fixture_id": fid,
                        "competition_key": ck,
                        "action": "error",
                        "reason": payload.get("message"),
                        "latency_ms": latency_ms,
                    }
                )
            if throttle > 0:
                time.sleep(throttle)
        except Exception as exc:
            logger.exception("Prefetch failed fixture %s", fid)
            result.errors += 1
            result.details.append({"fixture_id": fid, "competition_key": ck, "action": "error", "reason": str(exc)})

    result.elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return result

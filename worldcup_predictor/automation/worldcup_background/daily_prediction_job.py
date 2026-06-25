"""Daily background World Cup prediction job — Phase 33."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.automation.worldcup_background.freshness import (
    is_prediction_fresh,
    should_refresh_prediction,
)
from worldcup_predictor.automation.worldcup_background.prediction_runner import run_and_store_prediction
from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.quota.prediction_cache import kickoff_from_payload

logger = logging.getLogger(__name__)


@dataclass
class DailyPredictionJobResult:
    scanned: int = 0
    predicted: int = 0
    skipped_fresh: int = 0
    skipped_post_kickoff: int = 0
    errors: int = 0
    fixture_ids: list[int] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)


def run_daily_worldcup_prediction(
    *,
    settings: Settings | None = None,
    window_days: int | None = None,
    force_refresh: bool = False,
    limit: int | None = None,
    competition_key: str = "world_cup_2026",
    locale: str = "en",
) -> DailyPredictionJobResult:
    settings = settings or get_settings()
    window_days = window_days if window_days is not None else settings.worldcup_prediction_window_days
    store = WorldcupPredictionStore(settings)
    fixtures = store.list_in_window(competition_key=competition_key, window_days=window_days)
    if limit is not None:
        fixtures = fixtures[: int(limit)]

    result = DailyPredictionJobResult(scanned=len(fixtures))
    for row in fixtures:
        fid = int(row["fixture_id"])
        result.fixture_ids.append(fid)
        kickoff_raw = row.get("kickoff_utc")
        existing = store.get(fid, competition_key=competition_key, locale=locale)
        kick = kickoff_from_payload(existing) if existing else None
        if kick is None and kickoff_raw:
            try:
                kick = datetime.fromisoformat(str(kickoff_raw).replace("Z", "+00:00")).replace(tzinfo=None)
            except (TypeError, ValueError):
                kick = None

        fresh = False
        if existing:
            fresh, _ = is_prediction_fresh(existing, kickoff_utc=kick)

        do_run, reason = should_refresh_prediction(
            kickoff_utc=kick,
            has_stored=existing is not None,
            is_fresh=fresh,
            force_refresh=force_refresh,
        )
        if not do_run:
            if reason == "post_kickoff_no_refresh":
                result.skipped_post_kickoff += 1
            else:
                result.skipped_fresh += 1
            result.details.append({"fixture_id": fid, "action": "skip", "reason": reason})
            continue

        try:
            payload = run_and_store_prediction(
                fid,
                settings=settings,
                competition_key=competition_key,
                locale=locale,
                record_history=False,
                source="background_daily",
            )
            if payload.get("status") == "ok":
                result.predicted += 1
                result.details.append({
                    "fixture_id": fid,
                    "action": "predicted",
                    "confidence": payload.get("confidence"),
                    "no_bet": payload.get("no_bet"),
                })
            else:
                result.errors += 1
                result.details.append({"fixture_id": fid, "action": "error", "reason": payload.get("message")})
        except Exception as exc:
            logger.exception("Background predict failed fixture %s", fid)
            result.errors += 1
            result.details.append({"fixture_id": fid, "action": "error", "reason": str(exc)})

    return result

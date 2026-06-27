"""Phase A23 — archive search & detail service."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.lifecycle.store import LifecycleStore


def search_archive(
    *,
    team: str | None = None,
    competition_key: str | None = None,
    season: int | None = None,
    market: str | None = None,
    lifecycle_state: str | None = None,
    tier: str | None = None,
    model_version: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_confidence: float | None = None,
    min_bet_quality: float | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    store = LifecycleStore()
    try:
        records = store.search_records(
            team=team,
            competition_key=competition_key,
            season=season,
            market=market,
            lifecycle_state=lifecycle_state,
            tier=tier,
            model_version=model_version,
            date_from=date_from,
            date_to=date_to,
            min_confidence=min_confidence,
            min_bet_quality=min_bet_quality,
            limit=limit,
            offset=offset,
        )
        return {"status": "ok", "count": len(records), "records": records}
    finally:
        store.close()


def get_fixture_lifecycle_detail(fixture_id: int) -> dict[str, Any]:
    store = LifecycleStore()
    try:
        records = store.list_records_for_fixture(fixture_id)
        timeline = store.list_events_for_fixture(fixture_id)
        results = store.get_fixture_results(fixture_id)
        market_evals = store.list_market_evaluations_for_fixture(fixture_id)
        return {
            "status": "ok",
            "fixture_id": fixture_id,
            "records": records,
            "timeline": timeline,
            "results": results,
            "market_evaluations": market_evals,
        }
    finally:
        store.close()


def get_market_accuracy_stats() -> dict[str, Any]:
    store = LifecycleStore()
    try:
        rollups = store.list_accuracy_rollups()
        return {"status": "ok", "markets": rollups, "total_records": store.count_records()}
    finally:
        store.close()

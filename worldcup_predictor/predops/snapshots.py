"""PredOps snapshot creation — Phase A15."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.predops.egie_snapshot import build_egie_snapshot
from worldcup_predictor.predops.markets import build_market_snapshot, compute_snapshot_deltas
from worldcup_predictor.predops.store import PredOpsStore
from worldcup_predictor.prediction.engine_versions import PREDICTION_ENGINE_VERSION


def coverage_state_from_payload(payload: dict[str, Any]) -> str:
    if not payload or payload.get("status") != "ok":
        return "failed"
    if payload.get("no_bet"):
        return "no_bet"
    return "completed"


def create_snapshot_from_payload(
    store: PredOpsStore,
    *,
    fixture_id: int,
    competition_key: str,
    kickoff_utc: str | None,
    payload: dict[str, Any],
    trigger_reason: str,
) -> str:
    previous = store.get_latest_snapshot(fixture_id)
    prev_id = previous.get("snapshot_id") if previous else None
    prev_markets_doc = None
    if previous:
        prev_markets_doc = {
            "markets": previous.get("markets"),
            "payload": previous.get("payload"),
        }

    markets_doc = build_market_snapshot(payload)
    egie = build_egie_snapshot(payload)
    deltas = compute_snapshot_deltas(prev_markets_doc, markets_doc.get("markets") or {}, current_payload=payload)
    state = coverage_state_from_payload(payload)

    payload_out = dict(payload)
    payload_out["_predops_signals"] = {
        "engine_version": payload.get("prediction_engine_version") or PREDICTION_ENGINE_VERSION,
        "snapshot_trigger": trigger_reason,
        "coverage_state": state,
    }

    snap_id = store.insert_snapshot(
        fixture_id=fixture_id,
        competition_key=competition_key,
        kickoff_utc=kickoff_utc,
        trigger_reason=trigger_reason,
        payload=payload_out,
        markets=markets_doc,
        egie=egie,
        deltas=deltas,
        coverage_state=state,
        engine_version=payload.get("prediction_engine_version") or PREDICTION_ENGINE_VERSION,
        previous_snapshot_id=prev_id,
    )
    _enqueue_elite_shadow_analysis(
        fixture_id=fixture_id,
        competition_key=competition_key,
        snapshot_id=snap_id,
    )
    _capture_lifecycle_snapshot(
        fixture_id=fixture_id,
        snapshot_id=snap_id,
        payload=payload_out,
        predops_snapshot=markets_doc,
        egie_snapshot=egie,
    )
    return snap_id


def _capture_lifecycle_snapshot(
    *,
    fixture_id: int,
    snapshot_id: str,
    payload: dict[str, Any],
    predops_snapshot: dict[str, Any] | None,
    egie_snapshot: dict[str, Any] | None,
) -> None:
    """Phase A23 — non-blocking lifecycle capture after PredOps snapshot."""
    try:
        from worldcup_predictor.lifecycle.hooks import hook_after_predops_snapshot

        hook_after_predops_snapshot(
            fixture_id=fixture_id,
            snapshot_id=snapshot_id,
            payload=payload,
            predops_snapshot=predops_snapshot,
            egie_snapshot=egie_snapshot,
        )
    except Exception:
        return


def _enqueue_elite_shadow_analysis(
    *,
    fixture_id: int,
    competition_key: str,
    snapshot_id: str,
) -> None:
    """Phase A22 — non-blocking shadow queue hook after PredOps snapshot."""
    try:
        from worldcup_predictor.elite_orchestrator.shadow_queue import enqueue_shadow_fixture

        enqueue_shadow_fixture(
            fixture_id,
            competition_key=competition_key,
            source="predops_snapshot",
            snapshot_id=snapshot_id,
        )
    except Exception:
        return

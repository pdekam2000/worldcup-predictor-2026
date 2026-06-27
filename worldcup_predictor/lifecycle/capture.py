"""Phase A23 — capture predictions into append-only lifecycle store."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.lifecycle.store import LifecycleStore

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _payload_fingerprint(payload: dict[str, Any]) -> str:
    slim = {
        "fixture_id": payload.get("fixture_id"),
        "prediction": payload.get("prediction"),
        "probabilities": payload.get("probabilities"),
        "safe_pick": payload.get("safe_pick"),
        "value_pick": payload.get("value_pick"),
        "best_available_pick": payload.get("best_available_pick"),
        "predicted_at": payload.get("predicted_at"),
        "prediction_engine_version": payload.get("prediction_engine_version"),
    }
    raw = json.dumps(slim, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _record_key(
    fixture_id: int,
    *,
    source: str,
    prediction_at: str,
    fingerprint: str,
) -> str:
    return f"{fixture_id}:{source}:{prediction_at}:{fingerprint}"


def _extract_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    tracking = payload.get("accuracy_tracking") or {}
    pub = payload.get("publication_overlay") or payload.get("public_overlay") or {}
    bq = payload.get("bet_quality") or {}
    if isinstance(bq, dict):
        bq_score = bq.get("score") or bq.get("bet_quality_score")
        bq_tier = bq.get("tier") or bq.get("bet_quality_tier")
    else:
        bq_score = payload.get("bet_quality_score")
        bq_tier = payload.get("bet_quality_tier")

    best_pick = payload.get("prediction") or payload.get("public_best_pick")
    if isinstance(best_pick, dict):
        best_pick = best_pick.get("selection") or best_pick.get("pick") or str(best_pick)

    best_value = payload.get("value_pick") or payload.get("best_value_pick")
    if isinstance(best_value, dict):
        best_value = best_value.get("selection") or best_value.get("pick") or str(best_value)

    confidence = payload.get("confidence")
    if confidence is None and isinstance(payload.get("probabilities"), dict):
        probs = payload["probabilities"]
        pred = str(payload.get("prediction") or "").lower()
        mapping = {"home": "home_win", "away": "away_win", "draw": "draw"}
        key = mapping.get(pred, pred)
        try:
            confidence = float(probs.get(key) or 0)
        except (TypeError, ValueError):
            confidence = None

    return {
        "competition_key": payload.get("competition_key") or payload.get("competition"),
        "season": payload.get("season"),
        "home_team": payload.get("home_team"),
        "away_team": payload.get("away_team"),
        "kickoff_utc": payload.get("kickoff_utc"),
        "prediction_version": payload.get("prediction_engine_version") or payload.get("engine_version"),
        "model_version": payload.get("model_version") or payload.get("prediction_engine_version"),
        "engine": payload.get("engine") or payload.get("prediction_engine") or "production",
        "confidence": confidence,
        "bet_quality_score": bq_score,
        "tier": bq_tier or tracking.get("pick_tier"),
        "best_pick": str(best_pick) if best_pick is not None else None,
        "best_value": str(best_value) if best_value is not None else None,
        "publication_overlay": pub if isinstance(pub, dict) else {},
        "paper_betting_flag": bool(payload.get("paper_betting_enabled") or payload.get("paper_bet")),
        "combo_recommended_flag": bool(payload.get("combo_recommended") or payload.get("recommended_combo")),
        "audit": {
            "cache_source": payload.get("cache_source"),
            "no_bet": payload.get("no_bet"),
            "official_recommended": tracking.get("official_recommended"),
        },
    }


def _pick_types_from_payload(payload: dict[str, Any]) -> list[tuple[str, Any]]:
    pairs: list[tuple[str, Any]] = []
    for key, label in (
        ("safe_pick", "safe_pick"),
        ("balanced_pick", "balanced_pick"),
        ("value_pick", "value_pick"),
        ("aggressive_pick", "high_odds_pick"),
        ("caution_pick", "caution_pick"),
        ("best_available_pick", "best_pick"),
        ("public_best_pick", "best_pick"),
    ):
        val = payload.get(key)
        if val:
            pairs.append((label, val))
    return pairs


def _resolve_lifecycle_state(store: LifecycleStore, fixture_id: int, kickoff_utc: str | None) -> str:
    prior = store.get_latest_record(fixture_id)
    if prior is None:
        return "generated"
    if kickoff_utc:
        try:
            kick = datetime.fromisoformat(str(kickoff_utc).replace("Z", ""))
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if now >= kick:
                return "kickoff"
        except ValueError:
            pass
    return "updated"


def capture_prediction_from_payload(
    payload: dict[str, Any],
    *,
    fixture_id: int | None = None,
    source: str = "production",
    snapshot_id: str | None = None,
    predops_snapshot: dict[str, Any] | None = None,
    egie_snapshot: dict[str, Any] | None = None,
    shadow_fixture_ref: int | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Non-blocking capture hook — append-only lifecycle record."""
    settings = settings or get_settings()
    if not getattr(settings, "prediction_lifecycle_enabled", True):
        return {"status": "disabled"}

    fid = int(fixture_id or payload.get("fixture_id") or 0)
    if fid <= 0:
        return {"status": "skipped", "reason": "missing_fixture_id"}

    meta = _extract_metadata(payload)
    prediction_at = str(payload.get("predicted_at") or payload.get("cached_at") or _utc_now())
    if isinstance(prediction_at, (int, float)):
        prediction_at = datetime.fromtimestamp(float(prediction_at), tz=timezone.utc).replace(tzinfo=None).isoformat()

    fingerprint = _payload_fingerprint(payload)
    record_key = _record_key(fid, source=source, prediction_at=prediction_at, fingerprint=fingerprint)

    store = LifecycleStore(settings)
    try:
        lifecycle_state = _resolve_lifecycle_state(store, fid, meta.get("kickoff_utc"))
        prior = store.get_latest_record(fid)
        prior_pick = None
        if prior:
            prior_pick = prior.get("best_pick")

        record_id = store.insert_record(
            record_key=record_key,
            fixture_id=fid,
            payload=payload,
            lifecycle_state=lifecycle_state,
            prediction_at=prediction_at,
            prediction_source=source,
            competition_key=meta.get("competition_key"),
            season=int(meta["season"]) if meta.get("season") is not None else None,
            home_team=meta.get("home_team"),
            away_team=meta.get("away_team"),
            kickoff_utc=meta.get("kickoff_utc"),
            prediction_version=meta.get("prediction_version"),
            model_version=meta.get("model_version"),
            engine=meta.get("engine"),
            snapshot_id=snapshot_id,
            confidence=float(meta["confidence"]) if meta.get("confidence") is not None else None,
            bet_quality_score=float(meta["bet_quality_score"]) if meta.get("bet_quality_score") is not None else None,
            tier=meta.get("tier"),
            best_pick=meta.get("best_pick"),
            best_value=meta.get("best_value"),
            publication_overlay=meta.get("publication_overlay"),
            predops_snapshot=predops_snapshot,
            egie_snapshot=egie_snapshot,
            paper_betting_flag=bool(meta.get("paper_betting_flag")),
            combo_recommended_flag=bool(meta.get("combo_recommended_flag")),
            audit=meta.get("audit"),
            shadow_fixture_ref=shadow_fixture_ref,
        )

        if record_id is None:
            return {"status": "duplicate", "record_key": record_key}

        event_type = "generated" if lifecycle_state == "generated" else "updated"
        summary = f"Prediction: {meta.get('best_pick') or 'n/a'}"
        if prior_pick and prior_pick != meta.get("best_pick"):
            summary = f"Updated: {meta.get('best_pick') or 'n/a'} (was {prior_pick})"

        store.add_event(
            fixture_id=fid,
            record_id=record_id,
            event_type=event_type,
            lifecycle_state=lifecycle_state,
            event_at=prediction_at,
            summary=summary,
            pick_snapshot=meta.get("best_pick"),
        )

        store.insert_model_registry(
            record_id=record_id,
            fixture_id=fid,
            model_role="production_a",
            model_version=meta.get("model_version"),
            publication_version=str(meta.get("publication_overlay", {}).get("version") or ""),
            promotion_version=payload.get("promotion_version"),
            engine=meta.get("engine"),
        )
        if shadow_fixture_ref:
            store.insert_model_registry(
                record_id=record_id,
                fixture_id=fid,
                model_role="shadow_b",
                model_version="elite_shadow",
                engine="elite_shadow",
            )

        for pick_type, pick_val in _pick_types_from_payload(payload):
            pick_str = pick_val
            reason = None
            quality = None
            if isinstance(pick_val, dict):
                pick_str = pick_val.get("selection") or pick_val.get("pick") or json.dumps(pick_val, default=str)
                reason = pick_val.get("reason")
                quality = pick_val.get("quality_score") or pick_val.get("bet_quality_score")
            store.insert_best_value_history(
                record_id=record_id,
                fixture_id=fid,
                pick_type=pick_type,
                pick_value=str(pick_str) if pick_str is not None else None,
                reason=str(reason) if reason else None,
                quality_score=float(quality) if quality is not None else None,
            )

        return {
            "status": "ok",
            "record_id": record_id,
            "record_key": record_key,
            "lifecycle_state": lifecycle_state,
        }
    except Exception as exc:
        logger.warning("lifecycle_capture_failed fixture_id=%s: %s", fid, exc)
        return {"status": "error", "reason": str(exc)}
    finally:
        store.close()


def capture_combo(
    *,
    combo_type: str,
    legs: list[dict[str, Any]],
    quality: float | None = None,
    combined_odds: float | None = None,
    combo_key: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    if not getattr(settings, "prediction_lifecycle_enabled", True):
        return {"status": "disabled"}

    raw = json.dumps({"type": combo_type, "legs": legs, "odds": combined_odds}, sort_keys=True, default=str)
    key = combo_key or hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    store = LifecycleStore(settings)
    try:
        combo_id = store.insert_combo_history(
            combo_key=key,
            combo_type=combo_type,
            legs=legs,
            quality=quality,
            combined_odds=combined_odds,
        )
        return {"status": "ok" if combo_id else "duplicate", "combo_id": combo_id, "combo_key": key}
    finally:
        store.close()

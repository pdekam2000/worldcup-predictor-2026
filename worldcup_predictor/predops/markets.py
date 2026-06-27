"""Full market snapshot extraction from stored payloads — Phase A15 (read-only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.predops.constants import (
    ALL_MARKET_IDS,
    MARKET_STATUS_NO_PICK,
    MARKET_STATUS_PREDICTION,
    MARKET_STATUS_UNAVAILABLE,
)
from worldcup_predictor.prediction.engine_versions import PREDICTION_ENGINE_VERSION


def _confidence_tier(conf: float | None) -> str | None:
    if conf is None:
        return None
    try:
        c = float(conf)
        if c <= 1:
            c *= 100
    except (TypeError, ValueError):
        return None
    if c >= 75:
        return "high"
    if c >= 55:
        return "medium"
    return "low"


def _model_meta(payload: dict[str, Any], *, tier: str) -> dict[str, Any]:
    tracking = payload.get("accuracy_tracking") or {}
    return {
        "model_tier": tier,
        "model_family": payload.get("model_family") or tracking.get("model_family") or "production",
        "model_name": payload.get("model_name") or tracking.get("model_name") or "wde_pipeline",
        "model_version": payload.get("model_version") or tracking.get("model_version"),
        "engine_version": payload.get("prediction_engine_version") or PREDICTION_ENGINE_VERSION,
        "prediction_source": payload.get("generated_by") or payload.get("cache_source") or "stored",
        "generated_by": payload.get("generated_by") or "predops",
        "generated_at": payload.get("generated_at") or payload.get("predicted_at"),
        "data_sources_used": payload.get("data_sources_used") or tracking.get("data_sources_used") or [],
        "confidence_version": payload.get("adaptive_confidence_version"),
        "calibration_version": tracking.get("calibration_version"),
        "confidence_tier": tracking.get("confidence_tier") or _confidence_tier(
            payload.get("confidence")
        ),
        "reliability_tier": tracking.get("reliability_tier"),
    }


def _pick_block(
    selection: Any,
    *,
    probability: float | None = None,
    confidence: float | None = None,
    source: str,
) -> dict[str, Any] | None:
    if selection is None or selection == "":
        return None
    return {
        "prediction": selection,
        "probability": probability,
        "confidence": confidence,
        "source": source,
    }


def _tier_from_pick_tier(payload: dict[str, Any]) -> str:
    pt = payload.get("pick_tier") or (payload.get("accuracy_tracking") or {}).get("pick_tier")
    if pt in ("elite", "official", "production_ready", "A"):
        return "A"
    if pt in ("legacy", "B", "research_only"):
        return "B"
    return "A" if not payload.get("no_bet") else "B"


def _extract_1x2(payload: dict[str, Any]) -> dict[str, Any]:
    meta = _model_meta(payload, tier=_tier_from_pick_tier(payload))
    no_bet = bool(payload.get("no_bet"))
    probs = payload.get("probabilities") or {}
    mw = probs.get("match_winner") if isinstance(probs, dict) else None
    dm = payload.get("detailed_markets") or {}
    dm_mw = dm.get("match_winner") if isinstance(dm, dict) else None

    tier_b_sel = None
    tier_b_conf = None
    if isinstance(dm_mw, dict):
        tier_b_sel = dm_mw.get("selection") or dm_mw.get("pick")
        tier_b_conf = dm_mw.get("confidence") or dm_mw.get("probability")
    tier_a_sel = payload.get("prediction") if not no_bet else None
    tier_a_conf = payload.get("confidence")

    final_pick = payload.get("best_available_pick") or payload.get("user_visible_pick") or payload.get("safe_pick")
    final_sel = tier_a_sel
    final_conf = tier_a_conf
    if isinstance(final_pick, dict):
        final_sel = final_pick.get("pick") or final_pick.get("selection") or final_sel
        final_conf = final_pick.get("confidence") or final_pick.get("probability") or final_conf

    tier_a = _pick_block(tier_a_sel, confidence=tier_a_conf, source="elite_pipeline")
    tier_b = _pick_block(tier_b_sel, confidence=tier_b_conf, source="legacy_detailed_markets")

    if no_bet and not tier_b_sel:
        return {
            **meta,
            "market_id": "1x2",
            "market_status": MARKET_STATUS_NO_PICK,
            "reason": payload.get("caution_reason") or "no_bet_flag",
            "tier_a_prediction": tier_a,
            "tier_b_prediction": tier_b,
            "final_selected_prediction": None,
            "agreement_status": "no_pick",
        }

    if not tier_a_sel and not tier_b_sel:
        return {**meta, "market_id": "1x2", "market_status": MARKET_STATUS_UNAVAILABLE, "reason": "no_data"}

    agree = "disagree"
    if tier_a and tier_b and str(tier_a.get("prediction")).lower() == str(tier_b.get("prediction")).lower():
        agree = "agree"
    elif tier_a and not tier_b:
        agree = "no_legacy"
    elif tier_b and not tier_a:
        agree = "no_elite"

    selected_tier = "A" if tier_a_sel else "B"
    return {
        **meta,
        "market_id": "1x2",
        "market_status": MARKET_STATUS_PREDICTION,
        "reason": None,
        "tier_a_prediction": tier_a,
        "tier_b_prediction": tier_b,
        "final_selected_prediction": {
            "selected_tier": selected_tier,
            "prediction": final_sel,
            "confidence": final_conf,
            "selection_reason": (final_pick or {}).get("reason") if isinstance(final_pick, dict) else "primary",
            "agreement_status": agree,
        },
        "probabilities": mw if isinstance(mw, dict) else None,
    }


def _extract_prob_market(
    payload: dict[str, Any],
    market_id: str,
    *,
    prob_key: str,
    dm_key: str | None = None,
) -> dict[str, Any]:
    meta = _model_meta(payload, tier=_tier_from_pick_tier(payload))
    probs = payload.get("probabilities") or {}
    dm = payload.get("detailed_markets") or {}
    block = probs.get(prob_key) if isinstance(probs, dict) else None
    if not block and dm_key and isinstance(dm, dict):
        block = dm.get(dm_key)
    if not isinstance(block, dict) or not block:
        return {
            **meta,
            "market_id": market_id,
            "market_status": MARKET_STATUS_UNAVAILABLE,
            "reason": "not_in_payload",
        }
    sel = block.get("selection") or block.get("pick")
    if not sel:
        return {
            **meta,
            "market_id": market_id,
            "market_status": MARKET_STATUS_NO_PICK,
            "reason": "no_selection",
            "raw": block,
        }
    conf = block.get("confidence") or block.get("probability")
    pick = _pick_block(sel, probability=conf, confidence=conf, source="production")
    return {
        **meta,
        "market_id": market_id,
        "market_status": MARKET_STATUS_PREDICTION,
        "tier_a_prediction": pick,
        "tier_b_prediction": None,
        "final_selected_prediction": {
            "selected_tier": "A",
            "prediction": sel,
            "confidence": conf,
            "selection_reason": "probabilities_block",
            "agreement_status": "no_legacy",
        },
        "raw": block,
    }


def _extract_correct_score(payload: dict[str, Any]) -> dict[str, Any]:
    meta = _model_meta(payload, tier=_tier_from_pick_tier(payload))
    dm = payload.get("detailed_markets") or {}
    cs = dm.get("correct_score") if isinstance(dm, dict) else None
    if not cs:
        sc = payload.get("scoreline") or payload.get("scoreline_candidates")
        if sc:
            cs = sc
    if not cs:
        return {**meta, "market_id": "correct_score", "market_status": MARKET_STATUS_UNAVAILABLE, "reason": "not_in_payload"}
    return {
        **meta,
        "market_id": "correct_score",
        "market_status": MARKET_STATUS_PREDICTION,
        "final_selected_prediction": {"selected_tier": "A", "prediction": cs, "agreement_status": "no_legacy"},
        "raw": cs,
    }


def _extract_ht(payload: dict[str, Any], market_id: str, dm_key: str) -> dict[str, Any]:
    meta = _model_meta(payload, tier=_tier_from_pick_tier(payload))
    dm = payload.get("detailed_markets") or {}
    block = dm.get(dm_key) if isinstance(dm, dict) else None
    if not block:
        return {**meta, "market_id": market_id, "market_status": MARKET_STATUS_UNAVAILABLE, "reason": "not_in_payload"}
    sel = block.get("selection") if isinstance(block, dict) else block
    if not sel:
        return {**meta, "market_id": market_id, "market_status": MARKET_STATUS_NO_PICK, "reason": "no_selection"}
    return {
        **meta,
        "market_id": market_id,
        "market_status": MARKET_STATUS_PREDICTION,
        "final_selected_prediction": {"selected_tier": "A", "prediction": sel, "agreement_status": "no_legacy"},
        "raw": block,
    }


def _extract_player_market(payload: dict[str, Any], market_id: str, keys: tuple[str, ...]) -> dict[str, Any]:
    meta = _model_meta(payload, tier="A")
    dm = payload.get("detailed_markets") or {}
    val = None
    for k in keys:
        if isinstance(dm, dict) and dm.get(k):
            val = dm[k]
            break
        if payload.get(k):
            val = payload[k]
            break
    if not val:
        return {**meta, "market_id": market_id, "market_status": MARKET_STATUS_UNAVAILABLE, "reason": "not_in_payload"}
    if isinstance(val, dict) and not val.get("selection") and not val.get("player") and not val.get("candidates"):
        return {**meta, "market_id": market_id, "market_status": MARKET_STATUS_NO_PICK, "reason": "empty_block"}
    return {
        **meta,
        "market_id": market_id,
        "market_status": MARKET_STATUS_PREDICTION,
        "final_selected_prediction": {"selected_tier": "A", "prediction": val, "agreement_status": "no_legacy"},
    }


def build_market_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Build full market snapshot document from existing prediction payload."""
    if not payload or payload.get("status") != "ok":
        return {
            "markets": {},
            "summary": {"total": len(ALL_MARKET_IDS), "prediction": 0, "no_pick": 0, "unavailable": len(ALL_MARKET_IDS)},
        }

    markets: dict[str, Any] = {}
    markets["1x2"] = _extract_1x2(payload)
    markets["double_chance"] = _extract_prob_market(payload, "double_chance", prob_key="double_chance", dm_key="double_chance")
    markets["btts"] = _extract_prob_market(payload, "btts", prob_key="btts", dm_key="btts")
    for mid, pk, dk in (
        ("over_under_0_5", "over_under_0_5", "over_under_0_5"),
        ("over_under_1_5", "over_under_1_5", "over_under_1_5"),
        ("over_under_2_5", "over_under_2_5", "over_under_2_5"),
        ("over_under_3_5", "over_under_3_5", "over_under_3_5"),
    ):
        markets[mid] = _extract_prob_market(payload, mid, prob_key=pk, dm_key=dk)
    markets["correct_score"] = _extract_correct_score(payload)
    markets["ht_result"] = _extract_ht(payload, "ht_result", "ht_result")
    markets["ht_ft"] = _extract_ht(payload, "ht_ft", "ht_ft")

    gt = payload.get("goal_timing") or payload.get("egie") or {}
    if isinstance(gt, dict):
        for mid, key in (
            ("first_goal_team", "first_goal_team"),
            ("first_goal_time_range", "first_goal_time_range"),
            ("estimated_first_goal_minute", "estimated_first_goal_minute"),
            ("next_goal_team", "next_goal_team"),
            ("team_goals_home", "team_goals_home"),
            ("team_goals_away", "team_goals_away"),
            ("goal_timing_confidence", "confidence"),
            ("goal_timing_tier", "tier"),
        ):
            val = gt.get(key)
            if val is not None:
                markets[mid] = {
                    **_model_meta(payload, tier="A"),
                    "market_id": mid,
                    "market_status": MARKET_STATUS_PREDICTION,
                    "final_selected_prediction": {"selected_tier": "A", "prediction": val, "agreement_status": "no_legacy"},
                }
            else:
                markets[mid] = {
                    **_model_meta(payload, tier="A"),
                    "market_id": mid,
                    "market_status": MARKET_STATUS_UNAVAILABLE,
                    "reason": "egie_not_in_payload",
                }
    else:
        for mid in (
            "first_goal_team",
            "first_goal_time_range",
            "estimated_first_goal_minute",
            "next_goal_team",
            "team_goals_home",
            "team_goals_away",
            "goal_timing_confidence",
            "goal_timing_tier",
        ):
            markets[mid] = {
                **_model_meta(payload, tier="A"),
                "market_id": mid,
                "market_status": MARKET_STATUS_UNAVAILABLE,
                "reason": "egie_block_missing",
            }

    markets["anytime_goalscorer"] = _extract_player_market(
        payload, "anytime_goalscorer", ("anytime_goalscorer", "anytime_goalscorer_candidates", "goalscorer")
    )
    markets["first_goalscorer"] = _extract_player_market(
        payload, "first_goalscorer", ("first_goalscorer", "first_goalscorer_candidates")
    )
    markets["player_most_likely_to_score"] = _extract_player_market(
        payload, "player_most_likely_to_score", ("player_most_likely_to_score", "most_likely_scorer")
    )

    pred = sum(1 for m in markets.values() if m.get("market_status") == MARKET_STATUS_PREDICTION)
    no_pick = sum(1 for m in markets.values() if m.get("market_status") == MARKET_STATUS_NO_PICK)
    unavail = sum(1 for m in markets.values() if m.get("market_status") == MARKET_STATUS_UNAVAILABLE)
    return {
        "markets": markets,
        "summary": {
            "total": len(markets),
            "prediction": pred,
            "no_pick": no_pick,
            "unavailable": unavail,
        },
    }


def compute_snapshot_deltas(
    previous: dict[str, Any] | None,
    current_markets: dict[str, Any],
    *,
    current_payload: dict[str, Any],
) -> dict[str, Any]:
    if not previous:
        return {
            "changed_markets": list(current_markets.keys()),
            "confidence_delta": None,
            "data_delta": {"first_snapshot": True},
            "odds_delta": None,
            "lineup_delta": None,
            "weather_delta": None,
        }
    prev_markets = (previous.get("markets") or {}) if isinstance(previous.get("markets"), dict) else previous
    if isinstance(prev_markets, dict) and "markets" in prev_markets:
        prev_markets = prev_markets["markets"]
    changed: list[str] = []
    for mid, block in current_markets.items():
        prev = prev_markets.get(mid) if isinstance(prev_markets, dict) else None
        if not prev:
            changed.append(mid)
            continue
        cur_final = (block.get("final_selected_prediction") or {}).get("prediction")
        prev_final = (prev.get("final_selected_prediction") or {}).get("prediction")
        if str(cur_final) != str(prev_final):
            changed.append(mid)
    prev_payload = previous.get("payload") or {}
    conf_delta = None
    try:
        c0 = float(prev_payload.get("confidence") or 0)
        c1 = float(current_payload.get("confidence") or 0)
        conf_delta = round(c1 - c0, 2)
    except (TypeError, ValueError):
        pass
    return {
        "changed_markets": changed,
        "confidence_delta": conf_delta,
        "data_delta": {"markets_changed": len(changed)},
        "odds_delta": None,
        "lineup_delta": None,
        "weather_delta": None,
    }

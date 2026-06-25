"""Extract market-level predictions from production API payloads — Phase 61."""

from __future__ import annotations

from typing import Any


def _pick_tier(payload: dict[str, Any]) -> str | None:
    tracking = payload.get("accuracy_tracking") or {}
    return tracking.get("pick_tier") or tracking.get("confidence_tier")


def _pick_confidence(payload: dict[str, Any]) -> float | None:
    probs = payload.get("probabilities") or {}
    if isinstance(probs.get("match_winner"), dict):
        mw = probs["match_winner"]
        try:
            return max(float(mw.get("home") or 0), float(mw.get("draw") or 0), float(mw.get("away") or 0))
        except (TypeError, ValueError):
            pass
    conf = payload.get("confidence")
    try:
        return float(conf) if conf is not None else None
    except (TypeError, ValueError):
        return None


def extract_markets_from_production_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not payload:
        return []
    tier = _pick_tier(payload)
    confidence = _pick_confidence(payload)
    markets: list[dict[str, Any]] = []

    pred = payload.get("prediction")
    if pred:
        markets.append(
            {
                "market_id": "1x2",
                "prediction": {"selection": pred, "raw": pred},
                "confidence": confidence,
                "tier": tier,
            }
        )

    probs = payload.get("probabilities") or {}
    dm = payload.get("detailed_markets") or {}

    ou = probs.get("over_under_2_5")
    if isinstance(ou, dict) and ou.get("selection"):
        markets.append(
            {
                "market_id": "over_under_2_5",
                "prediction": ou,
                "confidence": float(ou.get("probability") or ou.get("confidence") or 0) or confidence,
                "tier": tier,
            }
        )

    btts = probs.get("btts")
    if isinstance(btts, dict) and btts.get("selection"):
        markets.append(
            {
                "market_id": "btts",
                "prediction": btts,
                "confidence": float(btts.get("probability") or btts.get("confidence") or 0) or confidence,
                "tier": tier,
            }
        )

    dc = dm.get("double_chance") if isinstance(dm, dict) else None
    if isinstance(dc, dict) and dc:
        best_key = max(dc, key=lambda k: float(dc.get(k) or 0))
        markets.append(
            {
                "market_id": "double_chance",
                "prediction": {"selection": best_key, "probabilities": dc},
                "confidence": float(dc.get(best_key) or 0) or confidence,
                "tier": tier,
            }
        )

    cs = dm.get("correct_score") if isinstance(dm, dict) else None
    if isinstance(cs, dict) and cs:
        markets.append({"market_id": "correct_score", "prediction": cs, "confidence": confidence, "tier": tier})

    for key, mid in (
        ("goal_timing", "goal_timing"),
        ("first_goal_team", "first_goal_team"),
        ("team_to_score_first", "team_to_score_first"),
        ("goalscorer", "goalscorer"),
    ):
        val = dm.get(key) if isinstance(dm, dict) else None
        val = val or probs.get(key) or payload.get(key)
        if val:
            markets.append(
                {
                    "market_id": mid,
                    "prediction": val if isinstance(val, dict) else {"selection": val},
                    "confidence": confidence,
                    "tier": tier,
                }
            )

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for m in markets:
        mid = m["market_id"]
        if mid in seen:
            continue
        seen.add(mid)
        deduped.append(m)
    return deduped


def extract_markets_from_elite_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    markets: list[dict[str, Any]] = []
    for m in bundle.get("markets") or []:
        market_id = str(m.get("market_id") or "").lower()
        if not market_id:
            continue
        mp = m.get("market_predictions") or {}
        markets.append(
            {
                "market_id": market_id,
                "prediction": {
                    "selection": m.get("prediction") or mp.get("prediction"),
                    "raw": m.get("prediction") or mp.get("prediction"),
                },
                "confidence": m.get("confidence") or mp.get("confidence"),
                "tier": m.get("tier") or mp.get("tier"),
            }
        )
    return markets

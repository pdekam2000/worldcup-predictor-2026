"""Bet Quality publication overlay — Phase A16 (orchestration only)."""

from __future__ import annotations

from typing import Any

# Market keys aligned with PredOps + extended EGIE/player markets
OVERLAY_MARKET_KEYS: tuple[str, ...] = (
    "1x2",
    "double_chance",
    "btts",
    "over_under_0_5",
    "over_under_1_5",
    "over_under_2_5",
    "over_under_3_5",
    "correct_score",
    "ht_result",
    "ht_ft",
    "first_goal_team",
    "first_goal_time_range",
    "estimated_first_goal_minute",
    "next_goal_team",
    "team_goals_home",
    "team_goals_away",
    "anytime_goalscorer",
    "first_goalscorer",
    "player_most_likely_to_score",
)

QUALITY_TIERS: tuple[dict[str, Any], ...] = (
    {"min": 95, "tier": "Elite", "color": "dark_green"},
    {"min": 85, "tier": "Excellent", "color": "green"},
    {"min": 75, "tier": "Strong", "color": "light_green"},
    {"min": 60, "tier": "Good", "color": "yellow"},
    {"min": 45, "tier": "Medium Risk", "color": "orange"},
    {"min": 25, "tier": "High Risk", "color": "red"},
    {"min": 0, "tier": "Very Weak", "color": "dark_red"},
)


def _fixture_data_quality(payload: dict[str, Any]) -> float:
    dq = payload.get("data_quality")
    if isinstance(dq, dict):
        return _float(dq.get("completeness_score") or dq.get("score") or dq.get("overall_score"), 50.0)
    return _float(dq, 50.0)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        v = float(value)
        return v * 100 if 0 < v <= 1 else v
    except (TypeError, ValueError):
        return default


def quality_tier_from_score(score: float) -> dict[str, Any]:
    s = max(0.0, min(100.0, float(score)))
    for band in QUALITY_TIERS:
        if s >= band["min"]:
            return {"bet_quality_score": round(s, 1), "bet_quality_tier": band["tier"], "bet_quality_color": band["color"]}
    return {"bet_quality_score": round(s, 1), "bet_quality_tier": "Very Weak", "bet_quality_color": "dark_red"}


def _wde_reasons(payload: dict[str, Any]) -> list[str]:
    audit = payload.get("audit_trace") or {}
    return list((audit.get("confidence") or {}).get("no_bet_reasons") or [])


def _ranking_index(payload: dict[str, Any], market_key: str, selection: Any) -> int | None:
    ranking = payload.get("market_ranking") or []
    sel = str(selection or "").lower()
    for i, row in enumerate(ranking):
        if not isinstance(row, dict):
            continue
        mk = str(row.get("market_key") or row.get("market") or "").lower()
        if mk == market_key.lower() or market_key.lower() in mk:
            return i
        if sel and sel in str(row.get("selection") or row.get("pick") or "").lower():
            return i
    return None


def compute_market_quality_score(
    *,
    market_key: str,
    probability: float | None,
    market_confidence: float | None,
    fixture_confidence: float,
    data_quality: float,
    ranking_position: int | None,
    fixture_no_bet: bool,
    wde_reasons: list[str],
    model_agreement: float | None = None,
    odds_value_edge: float | None = None,
) -> tuple[float, dict[str, Any], str]:
    """
    Transparent read-only formula (not WDE, not model training).
    Returns (score 0-100, score_inputs, quality_reason).
    """
    prob = _float(probability, 50.0) if probability is not None else 50.0
    mconf = _float(market_confidence, prob)
    fconf = _float(fixture_confidence, 0.0)
    dq = _float(data_quality, 50.0)

    # Base: market probability (distinct from bet quality output field)
    score = prob * 0.42 + mconf * 0.28 + fconf * 0.12 + dq * 0.10

    rank_bonus = 0.0
    if ranking_position is not None:
        if ranking_position == 0:
            rank_bonus = 8.0
        elif ranking_position == 1:
            rank_bonus = 5.0
        elif ranking_position <= 3:
            rank_bonus = 2.0
    score += rank_bonus

    if model_agreement is not None:
        score += min(5.0, _float(model_agreement, 0) * 0.05)

    if odds_value_edge is not None and odds_value_edge > 0:
        score += min(6.0, odds_value_edge * 10)

    if fixture_no_bet:
        score -= 8.0
        if any("confidence" in r for r in wde_reasons):
            score -= 4.0

    score = max(0.0, min(100.0, score))

    inputs = {
        "market_probability": round(prob, 1),
        "market_confidence": round(mconf, 1),
        "fixture_confidence": round(fconf, 1),
        "data_quality": round(dq, 1),
        "ranking_position": ranking_position,
        "rank_bonus": rank_bonus,
        "fixture_no_bet_penalty": fixture_no_bet,
        "model_agreement": model_agreement,
        "odds_value_edge": odds_value_edge,
    }

    tier = quality_tier_from_score(score)
    reason = (
        f"Market prob {prob:.0f}% · fixture conf {fconf:.0f}% · DQ {dq:.0f}%"
        + (f" · rank #{ranking_position + 1}" if ranking_position is not None else "")
        + (" · caution fixture (WDE threshold)" if fixture_no_bet else "")
    )
    return score, inputs, reason


def _extract_market_block(payload: dict[str, Any], market_key: str) -> dict[str, Any]:
    """Read market data from payload without generating fake values."""
    dm = payload.get("detailed_markets") or {}
    probs = payload.get("probabilities") or {}
    ranking = payload.get("market_ranking") or []

    key_map = {
        "1x2": ("match_winner", "prediction", probs.get("match_winner")),
        "double_chance": ("double_chance", None, probs.get("double_chance")),
        "btts": ("btts", None, probs.get("btts")),
        "over_under_0_5": ("over_under_0_5", None, probs.get("over_under_0_5")),
        "over_under_1_5": ("over_under_1_5", None, probs.get("over_under_1_5")),
        "over_under_2_5": ("over_under_2_5", None, probs.get("over_under_2_5")),
        "over_under_3_5": ("over_under_3_5", None, probs.get("over_under_3_5")),
        "correct_score": ("correct_score", None, None),
        "ht_result": ("ht_result", None, None),
        "ht_ft": ("ht_ft", None, None),
    }

    if market_key in ("first_goal_team", "first_goal_time_range", "estimated_first_goal_minute", "next_goal_team"):
        gt = payload.get("goal_timing") or payload.get("egie") or {}
        if isinstance(gt, dict) and gt.get(market_key.replace("first_goal_", "").replace("estimated_", "")):
            pass
        fg = dm.get("first_goal") or dm.get("goal_timing") or {}
        if market_key == "first_goal_team" and isinstance(fg, dict):
            return {
                "prediction": fg.get("team"),
                "probability": fg.get("probability"),
                "confidence": fg.get("confidence"),
                "internal_status": "published" if fg.get("team") else "unavailable",
                "unavailable_reason": None if fg.get("team") else "not_in_payload",
            }

    dm_key, top_key, prob_block = key_map.get(market_key, (market_key, None, None))
    block = dm.get(dm_key) if isinstance(dm, dict) else None
    if not block and isinstance(prob_block, dict):
        block = prob_block
    if market_key == "1x2" and not block:
        sel = payload.get("prediction")
        if sel and not payload.get("no_bet"):
            return {
                "prediction": sel,
                "probability": payload.get("confidence"),
                "confidence": payload.get("confidence"),
                "internal_status": "published",
            }
        if sel:
            return {
                "prediction": sel,
                "probability": probs.get("home_win") if isinstance(probs, dict) else None,
                "confidence": payload.get("confidence"),
                "internal_status": "no_bet",
            }

    if not block:
        for row in ranking:
            if isinstance(row, dict) and str(row.get("market_key", "")).lower() == market_key:
                return {
                    "prediction": row.get("pick") or row.get("selection"),
                    "probability": row.get("probability"),
                    "confidence": row.get("confidence") or row.get("market_rank_score"),
                    "internal_status": "published",
                }
        return {"internal_status": "unavailable", "unavailable_reason": "not_in_payload"}

    if isinstance(block, dict):
        sel = block.get("selection") or block.get("pick") or block.get("team")
        if not sel:
            return {"internal_status": "no_bet", "unavailable_reason": "no_selection", "raw": block}
        return {
            "prediction": sel,
            "probability": block.get("probability") or block.get("confidence"),
            "confidence": block.get("confidence") or block.get("probability"),
            "internal_status": "published",
            "raw": block,
        }
    return {"internal_status": "unavailable", "unavailable_reason": "invalid_block"}


def _derive_public_best_pick(payload: dict[str, Any]) -> dict[str, Any] | None:
    pick = payload.get("best_available_pick") or payload.get("caution_pick")
    if isinstance(pick, dict) and (pick.get("pick") or pick.get("selection")):
        return pick
    ranking = payload.get("market_ranking") or []
    for row in ranking[:3]:
        if isinstance(row, dict) and (row.get("pick") or row.get("selection")):
            return row
    return None


def build_market_quality_map(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    fixture_no_bet = bool(payload.get("no_bet"))
    fconf = _float(payload.get("confidence"), 0)
    dq = _fixture_data_quality(payload)
    reasons = _wde_reasons(payload)
    agreement = None
    agents = (payload.get("specialist_summary") or {}).get("agents") or {}
    mc = agents.get("market_consensus_agent") if isinstance(agents, dict) else None
    if isinstance(mc, dict):
        agreement = _float((mc.get("signals") or {}).get("aggregated_score"), None)

    markets: dict[str, Any] = {}
    for mk in OVERLAY_MARKET_KEYS:
        raw = _extract_market_block(payload, mk)
        status = raw.get("internal_status") or "unavailable"
        if status == "unavailable":
            markets[mk] = {
                "market": mk,
                "internal_status": "unavailable",
                "quality_reason": raw.get("unavailable_reason") or "not_in_payload",
                **quality_tier_from_score(0),
            }
            continue
        if status == "no_bet" and not raw.get("prediction"):
            markets[mk] = {
                "market": mk,
                "internal_status": "no_bet",
                "quality_reason": raw.get("unavailable_reason") or "no_pick",
                **quality_tier_from_score(0),
            }
            continue

        pred = raw.get("prediction")
        prob = raw.get("probability")
        mconf = raw.get("confidence")
        rank_pos = _ranking_index(payload, mk, pred)
        score, inputs, qreason = compute_market_quality_score(
            market_key=mk,
            probability=prob,
            market_confidence=mconf,
            fixture_confidence=fconf,
            data_quality=dq,
            ranking_position=rank_pos,
            fixture_no_bet=fixture_no_bet,
            wde_reasons=reasons,
            model_agreement=agreement,
        )
        tier = quality_tier_from_score(score)
        markets[mk] = {
            "market": mk,
            "prediction": pred,
            "probability": round(_float(prob, 0), 1) if prob is not None else None,
            "confidence": round(_float(mconf, 0), 1) if mconf is not None else None,
            "internal_status": status,
            **tier,
            "quality_reason": qreason,
            "score_inputs": inputs,
        }
    return markets


def build_publication_overlay(payload: dict[str, Any], *, include_debug: bool = False) -> dict[str, Any]:
    """Build publication_overlay from existing snapshot/payload (read-time)."""
    if not payload or payload.get("status") not in (None, "ok"):
        return {
            "public_recommendation_status": "unavailable",
            "quality_reason": "prediction_not_available",
            "derived_from_no_bet_fixture": False,
            "market_quality": {},
        }

    internal_no_bet = bool(payload.get("no_bet"))
    markets = build_market_quality_map(payload)
    market_list = list(markets.values())

    # Best market by quality score among published/no_bet with prediction
    candidates = [
        m
        for m in market_list
        if m.get("prediction") and m.get("internal_status") in ("published", "no_bet")
    ]
    candidates.sort(key=lambda x: x.get("bet_quality_score") or 0, reverse=True)
    top_market = candidates[0] if candidates else None

    public_best = _derive_public_best_pick(payload)
    if public_best and top_market:
        # Align quality with top market or re-score public best pick
        pk = str(public_best.get("market_key") or public_best.get("market") or "").lower()
        for m in candidates:
            if m.get("market", "").lower() in pk or pk in m.get("market", "").lower():
                top_market = m
                break

    if internal_no_bet:
        if public_best or top_market:
            status = "caution_best_available"
            caution_label = "Caution — Best Available"
            derived = True
        else:
            status = "unavailable"
            caution_label = None
            derived = True
    else:
        status = "published"
        caution_label = None
        derived = False

    if top_market:
        bqs = top_market.get("bet_quality_score", 0)
        tier = quality_tier_from_score(bqs)
        source_market = top_market.get("market")
        quality_reason = top_market.get("quality_reason", "")
    elif public_best:
        bqs, inputs, quality_reason = compute_market_quality_score(
            market_key=str(public_best.get("market_key") or "unknown"),
            probability=public_best.get("probability"),
            market_confidence=public_best.get("confidence"),
            fixture_confidence=_float(payload.get("confidence"), 0),
            data_quality=_fixture_data_quality(payload),
            ranking_position=0,
            fixture_no_bet=internal_no_bet,
            wde_reasons=_wde_reasons(payload),
        )
        tier = quality_tier_from_score(bqs)
        source_market = public_best.get("market") or public_best.get("market_key")
    else:
        bqs = 0
        tier = quality_tier_from_score(0)
        source_market = None
        quality_reason = "No market-level recommendation available"

    public_best_pick_label = None
    if public_best and isinstance(public_best, dict):
        mkt = public_best.get("market") or source_market or "Market"
        sel = public_best.get("pick") or public_best.get("selection")
        if sel:
            public_best_pick_label = f"{mkt}: {sel}"

    overlay: dict[str, Any] = {
        "public_recommendation_status": status,
        "bet_quality_score": tier["bet_quality_score"],
        "bet_quality_tier": tier["bet_quality_tier"],
        "bet_quality_color": tier["bet_quality_color"],
        "caution_label": caution_label,
        "quality_reason": quality_reason,
        "source_market": source_market,
        "derived_from_no_bet_fixture": derived,
        "public_best_pick": public_best_pick_label,
        "public_probability": top_market.get("probability") if top_market else None,
        "market_quality": markets,
    }

    if include_debug:
        overlay["internal_no_bet"] = internal_no_bet
        overlay["wde_no_bet_reasons"] = _wde_reasons(payload)
        overlay["fixture_confidence"] = _float(payload.get("confidence"), 0)
        overlay["data_quality"] = _fixture_data_quality(payload)

    return overlay


def sanitize_public_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Strip internal WDE fields from public match summaries."""
    if not summary:
        return summary
    out = dict(summary)
    out.pop("no_bet", None)
    po = dict(out.get("publication_overlay") or {})
    po.pop("internal_no_bet", None)
    po.pop("wde_no_bet_reasons", None)
    out["publication_overlay"] = po
    return out


def apply_plan_gating(overlay: dict[str, Any], plan: str = "free") -> dict[str, Any]:
    """Display gating only — no billing changes."""
    out = dict(overlay)
    p = (plan or "free").lower()
    if p in ("pro", "enterprise", "owner", "admin"):
        return out
    if p == "starter":
        # hide score inputs per market
        mq = {}
        for k, v in (out.get("market_quality") or {}).items():
            mq[k] = {kk: vv for kk, vv in v.items() if kk != "score_inputs"}
        out["market_quality"] = mq
        return out
    # free
    out.pop("market_quality", None)
    if "score_inputs" in out:
        del out["score_inputs"]
    return out


def enrich_summary_with_overlay(summary: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge overlay into prediction_summary for Match Center."""
    out = dict(summary)
    status = overlay.get("public_recommendation_status")
    out["publication_overlay"] = {
        k: overlay.get(k)
        for k in (
            "public_recommendation_status",
            "bet_quality_score",
            "bet_quality_tier",
            "bet_quality_color",
            "caution_label",
            "quality_reason",
            "source_market",
            "derived_from_no_bet_fixture",
            "public_best_pick",
        )
        if k in overlay
    }
    out["bet_quality_score"] = overlay.get("bet_quality_score")
    out["bet_quality_tier"] = overlay.get("bet_quality_tier")
    out["bet_quality_color"] = overlay.get("bet_quality_color")

    if status == "published":
        pass  # keep existing best_pick
    elif status == "caution_best_available" and overlay.get("public_best_pick"):
        out["best_pick"] = overlay.get("public_best_pick")
        out["caution_label"] = overlay.get("caution_label")
        out["public_recommendation_status"] = status
        # Public: do not expose raw no_bet
        out["display_status"] = "caution_best_available"
    elif status == "unavailable":
        out["best_pick"] = None
        out["display_status"] = "unavailable"
        out["unavailable_reason"] = overlay.get("quality_reason")

    # Internal no_bet preserved on summary for owner paths
    return out

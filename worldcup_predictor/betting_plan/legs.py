"""Collect fixture legs from PredOps snapshots — Phase A17."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.automation.prediction_prefetch.coverage import collect_upcoming_fixtures
from worldcup_predictor.automation.worldcup_background.freshness import _parse_dt, is_prediction_fresh
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.predops.store import PredOpsStore
from worldcup_predictor.publication.bet_quality_overlay import build_publication_overlay


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _kickoff_date(kickoff_utc: Any) -> date | None:
    kick = _parse_dt(kickoff_utc)
    if kick is None:
        return None
    return kick.date()


def _parse_plan_date(value: str | None) -> date:
    if not value or value.lower() in ("today", ""):
        return _utc_now().date()
    if value.lower() == "tomorrow":
        return _utc_now().date() + timedelta(days=1)
    return date.fromisoformat(value[:10])


def _risk_from_score(score: float, payload_risk: str | None = None) -> str:
    if score >= 85:
        return "low"
    if score >= 65:
        return "medium"
    if payload_risk:
        return str(payload_risk).lower()
    return "high"


def _odds_decimal(payload: dict[str, Any], market_key: str) -> float | None:
    bi = payload.get("betting_intelligence") or {}
    for row in payload.get("market_ranking") or []:
        if not isinstance(row, dict):
            continue
        mk = str(row.get("market_key") or row.get("market") or "").lower()
        if mk == market_key.lower() or market_key.lower() in mk:
            o = row.get("odds_decimal") or row.get("odds")
            if o is not None:
                try:
                    v = float(o)
                    return v if v > 1 else None
                except (TypeError, ValueError):
                    pass
    fo = bi.get("fair_odds") or payload.get("expected_odds")
    if fo is not None:
        try:
            v = float(fo)
            return v if v > 1 else None
        except (TypeError, ValueError):
            pass
    return None


def _leg_from_market(
    *,
    fixture: dict[str, Any],
    payload: dict[str, Any],
    snap: dict[str, Any],
    market_key: str,
    market_block: dict[str, Any],
    overlay: dict[str, Any],
    include_debug: bool,
) -> dict[str, Any] | None:
    if market_block.get("internal_status") == "unavailable":
        return None
    pred = market_block.get("prediction")
    if not pred:
        return None
    score = float(market_block.get("bet_quality_score") or 0)
    leg = {
        "fixture_id": fixture["fixture_id"],
        "home_team": fixture.get("home_team"),
        "away_team": fixture.get("away_team"),
        "fixture_label": f"{fixture.get('home_team')} vs {fixture.get('away_team')}",
        "league": fixture.get("competition_name") or fixture.get("competition_key"),
        "competition_key": fixture.get("competition_key"),
        "kickoff_utc": fixture.get("kickoff_utc"),
        "market": market_key,
        "market_label": market_key.replace("_", " ").upper(),
        "prediction": str(pred),
        "bet_quality_score": score,
        "bet_quality_tier": market_block.get("bet_quality_tier"),
        "bet_quality_color": market_block.get("bet_quality_color"),
        "probability": market_block.get("probability"),
        "confidence": market_block.get("confidence"),
        "risk_level": _risk_from_score(score, payload.get("risk_level")),
        "reason": market_block.get("quality_reason") or overlay.get("quality_reason"),
        "caution": overlay.get("public_recommendation_status") == "caution_best_available",
        "snapshot_id": snap.get("snapshot_id"),
        "last_updated": snap.get("generated_at") or payload.get("generated_at"),
        "odds_decimal": _odds_decimal(payload, market_key),
        "odds_estimated": False,
    }
    if leg["odds_decimal"] is None and leg.get("probability"):
        try:
            p = float(leg["probability"])
            if p > 0:
                leg["odds_decimal"] = round(100 / p, 2)
                leg["odds_estimated"] = True
        except (TypeError, ValueError):
            pass
    if include_debug:
        leg["score_inputs"] = market_block.get("score_inputs")
        leg["internal_status"] = market_block.get("internal_status")
        leg["wde_caution"] = overlay.get("caution_label")
        leg["fixture_no_bet"] = bool(payload.get("no_bet"))
    return leg


def collect_legs_for_date(
    plan_date: date,
    *,
    settings: Settings | None = None,
    include_debug: bool = False,
    window_days: int = 14,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    store = PredOpsStore(settings)
    fixtures = collect_upcoming_fixtures(settings=settings, window_days=window_days)
    target_fixtures = [f for f in fixtures if _kickoff_date(f.get("kickoff_utc")) == plan_date]
    if not target_fixtures:
        return []

    fixture_ids = [int(f["fixture_id"]) for f in target_fixtures]
    snaps = store.latest_by_fixtures(fixture_ids)
    legs: list[dict[str, Any]] = []

    for fixture in target_fixtures:
        fid = int(fixture["fixture_id"])
        snap = snaps.get(fid) or {}
        payload = snap.get("payload") or {}
        if not payload or payload.get("status") not in (None, "ok"):
            continue
        kick = _parse_dt(fixture.get("kickoff_utc"))
        fresh, _ = is_prediction_fresh(payload, kickoff_utc=kick)
        if not fresh:
            continue
        overlay = build_publication_overlay(payload, include_debug=include_debug)
        mq = overlay.get("market_quality") or {}
        for market_key, block in mq.items():
            if not isinstance(block, dict):
                continue
            leg = _leg_from_market(
                fixture=fixture,
                payload=payload,
                snap=snap,
                market_key=market_key,
                market_block=block,
                overlay=overlay,
                include_debug=include_debug,
            )
            if leg:
                legs.append(leg)

    legs.sort(key=lambda x: x.get("bet_quality_score") or 0, reverse=True)
    return legs


def parse_plan_date(value: str | None) -> date:
    return _parse_plan_date(value)

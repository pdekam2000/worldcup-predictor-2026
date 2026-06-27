"""Evaluate stored prediction picks against finished match outcomes — Phase 33."""

from __future__ import annotations

from typing import Any, Literal

from worldcup_predictor.api.market_level_evaluation import (
    attach_market_evaluations_to_result,
    btts_selection_from_payload,
    canonical_1x2_selection,
    ou_selection_from_payload,
)
from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome
from worldcup_predictor.automation.worldcup_background.advanced_market_evaluator import (
    advanced_market_status_map,
    evaluate_advanced_markets,
)

ResultStatus = Literal["correct", "wrong", "pending", "unknown", "void", "unavailable"]


def _goals(outcome: FixtureOutcome) -> tuple[int | None, int | None]:
    if outcome.final_score and "-" in outcome.final_score:
        parts = outcome.final_score.split("-", 1)
        try:
            return int(parts[0].strip()), int(parts[1].strip())
        except ValueError:
            pass
    return None, None


def _actual_1x2(home: int, away: int) -> str:
    if home > away:
        return "home_win"
    if home < away:
        return "away_win"
    return "draw"


def _eval_1x2(selection: str | None, actual: str | None) -> ResultStatus:
    if actual is None:
        return "unknown"
    if not selection:
        return "void"
    mapping = {
        "home": "home_win",
        "home_win": "home_win",
        "draw": "draw",
        "away": "away_win",
        "away_win": "away_win",
    }
    pred = mapping.get(str(selection).lower())
    if pred is None:
        return "unknown"
    return "correct" if pred == actual else "wrong"


def _eval_ou(selection: str | None, total: float) -> ResultStatus:
    if selection is None:
        return "void"
    sel = str(selection).lower()
    if "over" in sel:
        return "correct" if total > 2.5 else "wrong"
    if "under" in sel:
        return "correct" if total <= 2.5 else "wrong"
    return "unknown"


def _eval_btts(selection: str | None, home: int, away: int) -> ResultStatus:
    if selection is None:
        return "void"
    both = home > 0 and away > 0
    sel = str(selection).lower()
    if sel in {"yes", "btts_yes"}:
        return "correct" if both else "wrong"
    if sel in {"no", "btts_no"}:
        return "correct" if not both else "wrong"
    return "unknown"


def _eval_double_chance(selection: str | None, actual: str) -> ResultStatus:
    if not selection:
        return "void"
    sel = str(selection).lower()
    if sel in {"home_or_draw", "1x"}:
        return "correct" if actual in {"home_win", "draw"} else "wrong"
    if sel in {"draw_or_away", "x2"}:
        return "correct" if actual in {"draw", "away_win"} else "wrong"
    if sel in {"home_or_away", "12"}:
        return "correct" if actual in {"home_win", "away_win"} else "wrong"
    return "unknown"


def _eval_pick_dict(pick: dict[str, Any] | None, outcome: FixtureOutcome) -> ResultStatus:
    if pick is None:
        return "void"
    if not outcome.is_finished:
        return "pending"
    home, away = _goals(outcome)
    if home is None or away is None or outcome.actual_result is None:
        return "unknown"
    actual = outcome.actual_result
    market = str(pick.get("market") or pick.get("market_key") or "").lower()
    selection = pick.get("selection") or pick.get("pick")
    sel = str(selection or "").lower()

    if "double chance" in market or sel in {"home_or_draw", "draw_or_away", "home_or_away", "1x", "x2", "12"}:
        return _eval_double_chance(sel or str(pick.get("pick") or ""), actual)
    if "btts" in market or sel in {"yes", "no", "btts_yes", "btts_no"}:
        return _eval_btts(sel, home, away)
    if "over" in market or "under" in market or "o/u" in market or "over_under" in sel:
        return _eval_ou(sel or str(pick.get("pick") or ""), float(home + away))
    if "match winner" in market or "1x2" in market or sel in {"home_win", "draw", "away_win", "home", "away"}:
        return _eval_1x2(sel or str(pick.get("pick") or ""), actual)
    return "unknown"


def evaluate_stored_prediction(
    payload: dict[str, Any],
    outcome: FixtureOutcome,
) -> dict[str, Any]:
    """Evaluate all tracked markets for one stored prediction."""
    if not outcome.is_finished:
        advanced = evaluate_advanced_markets(payload, outcome)
        return {
            "fixture_id": payload.get("fixture_id"),
            "status": "pending",
            "markets": advanced_market_status_map(advanced),
            "advanced_markets": advanced,
        }

    home, away = _goals(outcome)
    actual = outcome.actual_result
    total = float(home + away) if home is not None and away is not None else None

    markets: dict[str, ResultStatus] = {}
    markets["1x2"] = _eval_1x2(canonical_1x2_selection(payload), actual)

    ou_sel = ou_selection_from_payload(payload)
    markets["over_under_2_5"] = (
        _eval_ou(ou_sel, total if total is not None else -1) if total is not None else "unknown"
    )

    btts_sel = btts_selection_from_payload(payload)
    markets["btts"] = (
        _eval_btts(btts_sel, home or 0, away or 0)
        if home is not None and away is not None
        else "unknown"
    )

    dm = payload.get("detailed_markets") or {}
    dc = dm.get("double_chance") if isinstance(dm, dict) else None
    if isinstance(dc, dict):
        best = max(
            [("home_or_draw", dc.get("home_or_draw")), ("draw_or_away", dc.get("draw_or_away")), ("home_or_away", dc.get("home_or_away"))],
            key=lambda x: float(x[1] or 0),
        )[0]
        markets["double_chance"] = _eval_double_chance(best, actual or "") if actual else "unknown"

    markets["safe_pick"] = _eval_pick_dict(payload.get("safe_pick"), outcome)
    markets["value_pick"] = _eval_pick_dict(payload.get("value_pick"), outcome)
    markets["aggressive_pick"] = _eval_pick_dict(payload.get("aggressive_pick"), outcome)
    markets["caution_pick"] = _eval_pick_dict(payload.get("caution_pick"), outcome)
    markets["best_available_pick"] = _eval_pick_dict(payload.get("best_available_pick"), outcome)

    recs = payload.get("recommended_bets") or []
    for i, rec in enumerate(recs[:5]):
        if isinstance(rec, dict):
            markets[f"recommended_{i}"] = _eval_pick_dict(rec, outcome)

    no_bet = bool(payload.get("no_bet"))
    tracking = payload.get("accuracy_tracking") or {}
    official_recommended = bool(tracking.get("official_recommended")) and not no_bet
    pick_tier = str(tracking.get("pick_tier") or ("official" if official_recommended else "caution"))

    overall = "pending"
    if outcome.is_finished:
        if official_recommended:
            if markets.get("safe_pick") in {"correct", "wrong"}:
                overall = markets["safe_pick"]
            elif markets.get("1x2") in {"correct", "wrong"}:
                overall = markets["1x2"]
        elif no_bet or pick_tier == "caution":
            caution_status = markets.get("caution_pick") or markets.get("best_available_pick")
            if caution_status in {"correct", "wrong"}:
                overall = caution_status
            elif markets.get("1x2") in {"correct", "wrong"}:
                overall = markets["1x2"]
            else:
                overall = "unknown"
        elif markets.get("1x2") in {"correct", "wrong"}:
            overall = markets["1x2"]

    advanced_markets = evaluate_advanced_markets(payload, outcome)
    markets.update(advanced_market_status_map(advanced_markets))

    result = {
        "fixture_id": payload.get("fixture_id"),
        "status": overall,
        "actual_result": actual,
        "final_score": outcome.final_score,
        "no_bet": no_bet,
        "official_recommended": official_recommended,
        "pick_tier": pick_tier,
        "markets": markets,
        "advanced_markets": advanced_markets,
    }
    return attach_market_evaluations_to_result(result, payload, outcome)

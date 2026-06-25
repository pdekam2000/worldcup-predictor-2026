"""Advanced market evaluators — Phase 46C-2 (HT, Correct Score, First Goal, Goalscorer)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome

AdvancedStatus = Literal["correct", "wrong", "pending", "unavailable", "unknown", "void"]

_UNAVAILABLE_OUTCOME_TYPES = frozenset(
    {"POSTPONED", "CANCELLED", "CANC", "ABD", "ABANDONED", "SUSP", "SUSPENDED", "INT", "INTERRUPTED"}
)
_AET_PEN_OUTCOME_TYPES = frozenset({"AET", "PEN", "FT_PEN", "FTP"})


def _normalize_token(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_ht_selection(value: str | None) -> str | None:
    if not value:
        return None
    key = str(value).lower().strip()
    mapping = {
        "home": "home_win",
        "home_win": "home_win",
        "1": "home_win",
        "draw": "draw",
        "x": "draw",
        "away": "away_win",
        "away_win": "away_win",
        "2": "away_win",
    }
    return mapping.get(key)


def _parse_scoreline(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    text = str(value).strip().replace(":", "-")
    if "-" not in text:
        return None, None
    left, _, right = text.partition("-")
    try:
        return int(left.strip()), int(right.strip())
    except ValueError:
        return None, None


def _format_scoreline(home: int, away: int) -> str:
    return f"{home}-{away}"


def _match_outcome_unavailable(outcome: FixtureOutcome) -> bool:
    mot = str(outcome.match_outcome_type or "").upper()
    if mot in _UNAVAILABLE_OUTCOME_TYPES:
        return True
    status = str(outcome.fixture_status or "").upper()
    return status in _UNAVAILABLE_OUTCOME_TYPES


def _ht_predicted(payload: dict[str, Any]) -> tuple[str | None, float | None]:
    dm = payload.get("detailed_markets") or {}
    ht = dm.get("halftime") if isinstance(dm, dict) else None
    if not isinstance(ht, dict):
        return None, None
    sel = _normalize_ht_selection(ht.get("selection"))
    if sel:
        probs = ht.get("probabilities") if isinstance(ht.get("probabilities"), dict) else {}
        conf = probs.get(sel) or probs.get(sel.replace("_win", ""))
        try:
            conf_f = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            conf_f = None
        if conf_f is not None and conf_f > 1:
            conf_f = conf_f / 100.0
        return sel, conf_f
    probs = ht.get("probabilities") if isinstance(ht.get("probabilities"), dict) else {}
    if probs:
        best = max(probs, key=lambda k: float(probs.get(k) or 0))
        pred = _normalize_ht_selection(best) or _normalize_ht_selection(best.replace("_win", ""))
        try:
            conf_f = float(probs.get(best) or 0)
        except (TypeError, ValueError):
            conf_f = None
        if conf_f is not None and conf_f > 1:
            conf_f = conf_f / 100.0
        return pred, conf_f
    return None, None


def _correct_score_predicted(payload: dict[str, Any]) -> tuple[str | None, float | None]:
    dm = payload.get("detailed_markets") or {}
    raw = dm.get("correct_scores") if isinstance(dm, dict) else None
    if isinstance(raw, dict):
        sel = raw.get("selection") or raw.get("label") or raw.get("scoreline")
        return (str(sel).strip() if sel else None), None
    if not isinstance(raw, list) or not raw:
        return None, None
    best_row: dict[str, Any] | None = None
    best_prob = -1.0
    for row in raw:
        if not isinstance(row, dict):
            continue
        label = row.get("label") or row.get("scoreline") or row.get("selection")
        if not label:
            continue
        try:
            prob = float(row.get("probability") or 0)
        except (TypeError, ValueError):
            prob = 0.0
        if prob > 1:
            prob = prob / 100.0
        if prob >= best_prob:
            best_prob = prob
            best_row = row
    if best_row is None:
        return None, None
    label = best_row.get("label") or best_row.get("scoreline") or best_row.get("selection")
    conf = best_prob if best_prob >= 0 else None
    return (str(label).strip() if label else None), conf


def _first_goal_predicted(payload: dict[str, Any]) -> tuple[str | None, float | None, bool]:
    """Return (team_or_no_goal, confidence, explicit_no_goal)."""
    dm = payload.get("detailed_markets") or {}
    fg = dm.get("first_goal") if isinstance(dm, dict) else None
    if not isinstance(fg, dict):
        return None, None, False
    team = fg.get("team") or fg.get("selection")
    if team is None:
        return None, None, False
    team_s = str(team).strip()
    if not team_s:
        return None, None, False
    no_goal_tokens = {"no_goal", "no goal", "none", "no scorer", "0-0", "nil"}
    if team_s.lower() in no_goal_tokens:
        return "no_goal", None, True
    try:
        conf = float(fg.get("confidence")) if fg.get("confidence") is not None else None
    except (TypeError, ValueError):
        conf = None
    if conf is not None and conf > 1:
        conf = conf / 100.0
    return team_s, conf, False


def _goalscorer_predicted(payload: dict[str, Any]) -> tuple[str | None, float | None, bool]:
    dm = payload.get("detailed_markets") or {}
    gs = dm.get("goalscorer") if isinstance(dm, dict) else None
    fg = dm.get("first_goal") if isinstance(dm, dict) else None
    player: str | None = None
    conf: float | None = None
    available = True
    if isinstance(gs, dict):
        available = gs.get("available") is not False
        player = gs.get("player")
        try:
            conf = float(gs.get("confidence")) if gs.get("confidence") is not None else None
        except (TypeError, ValueError):
            conf = None
    if not player and isinstance(fg, dict):
        player = fg.get("player")
    if conf is not None and conf > 1:
        conf = conf / 100.0
    if not available and not player:
        return None, conf, False
    return (str(player).strip() if player else None), conf, available


def _team_side_match(
    predicted_team: str,
    *,
    home_team: str | None,
    away_team: str | None,
) -> str | None:
    pred = _normalize_token(predicted_team)
    home = _normalize_token(home_team)
    away = _normalize_token(away_team)
    if pred and home and (pred == home or pred in home or home in pred):
        return "home"
    if pred and away and (pred == away or pred in away or away in pred):
        return "away"
    return None


def _actual_first_goal_side(
    outcome: FixtureOutcome,
    *,
    home_team: str | None,
    away_team: str | None,
) -> str | None:
    if outcome.first_goal_team:
        side = _team_side_match(outcome.first_goal_team, home_team=home_team, away_team=away_team)
        if side:
            return side
    events = outcome.goal_events or ()
    if events:
        first = events[0] if isinstance(events[0], dict) else None
        if first and first.get("team"):
            return _team_side_match(str(first["team"]), home_team=home_team, away_team=away_team)
    return None


def _first_goal_event_meta(outcome: FixtureOutcome) -> dict[str, Any]:
    events = outcome.goal_events or ()
    if not events:
        return {}
    first = events[0]
    if not isinstance(first, dict):
        return {}
    return {
        "is_own_goal": bool(first.get("is_own_goal")),
        "is_penalty": bool(first.get("is_penalty")),
        "player": first.get("player"),
        "team": first.get("team"),
    }


def _player_match_confidence(predicted: str, actual: str) -> tuple[bool, float, str]:
    pred_norm = _normalize_token(predicted)
    actual_norm = _normalize_token(actual)
    if not pred_norm or not actual_norm:
        return False, 0.0, "missing_name"
    if pred_norm == actual_norm:
        return True, 1.0, "exact_match"
    pred_parts = pred_norm.split()
    actual_parts = actual_norm.split()
    if pred_parts and actual_parts and pred_parts[-1] == actual_parts[-1]:
        return True, 0.85, "surname_match"
    if pred_norm in actual_norm or actual_norm in pred_norm:
        return True, 0.7, "partial_match"
    return False, 0.0, "no_match"


def _market_result(
    *,
    market: str,
    predicted: str | None,
    actual: str | None,
    status: AdvancedStatus,
    confidence: float | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "market": market,
        "predicted": predicted,
        "actual": actual,
        "status": status,
        "confidence": confidence,
        "reason": reason,
    }


def evaluate_ht_result(payload: dict[str, Any], outcome: FixtureOutcome) -> dict[str, Any]:
    market = "ht_result"
    if not outcome.is_finished:
        return _market_result(market=market, predicted=None, actual=None, status="pending", reason="match_not_finished")
    if _match_outcome_unavailable(outcome):
        return _market_result(
            market=market,
            predicted=None,
            actual=None,
            status="unavailable",
            reason=f"match_outcome_type={outcome.match_outcome_type or outcome.fixture_status}",
        )
    predicted, conf = _ht_predicted(payload)
    actual = outcome.ht_result
    actual_display = outcome.ht_score
    if actual is None and outcome.ht_home_goals is not None and outcome.ht_away_goals is not None:
        actual = (
            "home_win"
            if outcome.ht_home_goals > outcome.ht_away_goals
            else ("away_win" if outcome.ht_home_goals < outcome.ht_away_goals else "draw")
        )
        actual_display = f"{outcome.ht_home_goals}-{outcome.ht_away_goals}"
    if actual is None:
        return _market_result(
            market=market,
            predicted=predicted,
            actual=None,
            status="unavailable",
            confidence=conf,
            reason="ht_outcome_missing",
        )
    if not predicted:
        return _market_result(
            market=market,
            predicted=None,
            actual=actual_display or actual,
            status="unavailable",
            reason="no_ht_prediction",
        )
    status: AdvancedStatus = "correct" if predicted == actual else "wrong"
    return _market_result(
        market=market,
        predicted=predicted,
        actual=actual_display or actual,
        status=status,
        confidence=conf,
        reason=None,
    )


def evaluate_correct_score(payload: dict[str, Any], outcome: FixtureOutcome) -> dict[str, Any]:
    market = "correct_score"
    if not outcome.is_finished:
        return _market_result(market=market, predicted=None, actual=None, status="pending", reason="match_not_finished")
    if _match_outcome_unavailable(outcome):
        return _market_result(
            market=market,
            predicted=None,
            actual=None,
            status="unavailable",
            reason=f"match_outcome_type={outcome.match_outcome_type or outcome.fixture_status}",
        )
    predicted, conf = _correct_score_predicted(payload)
    home, away = _parse_scoreline(outcome.final_score)
    if home is None or away is None:
        return _market_result(
            market=market,
            predicted=predicted,
            actual=outcome.final_score,
            status="unavailable",
            confidence=conf,
            reason="final_score_missing",
        )
    actual = _format_scoreline(home, away)
    mot = str(outcome.match_outcome_type or "").upper()
    reason_note = None
    if mot in _AET_PEN_OUTCOME_TYPES:
        reason_note = f"evaluated_on_persisted_score; match_outcome_type={mot}"
    if not predicted:
        return _market_result(
            market=market,
            predicted=None,
            actual=actual,
            status="unavailable",
            confidence=conf,
            reason="no_correct_score_prediction",
        )
    pred_h, pred_a = _parse_scoreline(predicted)
    if pred_h is None or pred_a is None:
        return _market_result(
            market=market,
            predicted=predicted,
            actual=actual,
            status="unavailable",
            confidence=conf,
            reason="invalid_predicted_scoreline",
        )
    status: AdvancedStatus = "correct" if pred_h == home and pred_a == away else "wrong"
    return _market_result(
        market=market,
        predicted=_format_scoreline(pred_h, pred_a),
        actual=actual,
        status=status,
        confidence=conf,
        reason=reason_note,
    )


def evaluate_first_goal_team(payload: dict[str, Any], outcome: FixtureOutcome) -> dict[str, Any]:
    market = "first_goal_team"
    home_team = payload.get("home_team")
    away_team = payload.get("away_team")
    if not outcome.is_finished:
        return _market_result(market=market, predicted=None, actual=None, status="pending", reason="match_not_finished")
    if _match_outcome_unavailable(outcome):
        return _market_result(
            market=market,
            predicted=None,
            actual=None,
            status="unavailable",
            reason=f"match_outcome_type={outcome.match_outcome_type or outcome.fixture_status}",
        )
    predicted, conf, explicit_no_goal = _first_goal_predicted(payload)
    home, away = _parse_scoreline(outcome.final_score)
    total_goals = (home or 0) + (away or 0) if home is not None and away is not None else None
    no_goals = total_goals == 0
    actual_team = outcome.first_goal_team
    if no_goals:
        if explicit_no_goal or (predicted and str(predicted).lower() in {"no_goal", "no goal", "none"}):
            return _market_result(
                market=market,
                predicted="no_goal",
                actual="no_goal",
                status="correct",
                confidence=conf,
                reason="zero_zero_no_first_goal",
            )
        if predicted:
            return _market_result(
                market=market,
                predicted=predicted,
                actual="no_goal",
                status="wrong",
                confidence=conf,
                reason="zero_zero_no_first_goal",
            )
        return _market_result(
            market=market,
            predicted=None,
            actual="no_goal",
            status="unavailable",
            reason="no_first_goal_prediction",
        )
    if not predicted:
        return _market_result(
            market=market,
            predicted=None,
            actual=actual_team,
            status="unavailable",
            reason="no_first_goal_prediction",
        )
    if not actual_team and not outcome.goal_events:
        return _market_result(
            market=market,
            predicted=predicted,
            actual=None,
            status="unavailable",
            confidence=conf,
            reason="first_goal_outcome_missing",
        )
    pred_side = _team_side_match(predicted, home_team=home_team, away_team=away_team)
    actual_side = _actual_first_goal_side(outcome, home_team=home_team, away_team=away_team)
    if pred_side and actual_side:
        status: AdvancedStatus = "correct" if pred_side == actual_side else "wrong"
        return _market_result(
            market=market,
            predicted=predicted,
            actual=actual_team,
            status=status,
            confidence=conf,
            reason=None,
        )
    if actual_team and _normalize_token(predicted) == _normalize_token(actual_team):
        return _market_result(
            market=market,
            predicted=predicted,
            actual=actual_team,
            status="correct",
            confidence=conf,
            reason="team_name_exact",
        )
    if actual_team:
        return _market_result(
            market=market,
            predicted=predicted,
            actual=actual_team,
            status="wrong",
            confidence=conf,
            reason="team_name_mismatch",
        )
    return _market_result(
        market=market,
        predicted=predicted,
        actual=None,
        status="unavailable",
        confidence=conf,
        reason="first_goal_team_unresolved",
    )


def evaluate_goalscorer(payload: dict[str, Any], outcome: FixtureOutcome) -> dict[str, Any]:
    market = "goalscorer"
    if not outcome.is_finished:
        return _market_result(market=market, predicted=None, actual=None, status="pending", reason="match_not_finished")
    if _match_outcome_unavailable(outcome):
        return _market_result(
            market=market,
            predicted=None,
            actual=None,
            status="unavailable",
            reason=f"match_outcome_type={outcome.match_outcome_type or outcome.fixture_status}",
        )
    predicted, conf, available = _goalscorer_predicted(payload)
    meta = _first_goal_event_meta(outcome)
    if meta.get("is_own_goal"):
        return _market_result(
            market=market,
            predicted=predicted,
            actual=meta.get("player") or outcome.first_goal_player,
            status="unavailable",
            confidence=conf,
            reason="first_goal_own_goal_void",
        )
    home, away = _parse_scoreline(outcome.final_score)
    no_goals = home == 0 and away == 0 if home is not None and away is not None else False
    if no_goals:
        if predicted:
            return _market_result(
                market=market,
                predicted=predicted,
                actual="no_goal",
                status="wrong",
                confidence=conf,
                reason="zero_zero_no_scorer",
            )
        return _market_result(
            market=market,
            predicted=None,
            actual="no_goal",
            status="unavailable",
            reason="no_goalscorer_prediction",
        )
    actual = outcome.first_goal_player or meta.get("player")
    if not actual:
        return _market_result(
            market=market,
            predicted=predicted,
            actual=None,
            status="unavailable",
            confidence=conf,
            reason="first_goal_player_missing",
        )
    if not predicted or not available:
        return _market_result(
            market=market,
            predicted=predicted,
            actual=actual,
            status="unavailable",
            confidence=conf,
            reason="no_goalscorer_prediction",
        )
    matched, match_conf, match_reason = _player_match_confidence(predicted, actual)
    pred_norm = _normalize_token(predicted)
    actual_norm = _normalize_token(actual)
    if match_reason == "partial_match":
        return _market_result(
            market=market,
            predicted=predicted,
            actual=actual,
            status="unavailable",
            confidence=conf,
            reason="low_identity_confidence:partial_match",
        )
    if matched and match_reason in {"exact_match", "surname_match"}:
        status: AdvancedStatus = "correct"
    elif pred_norm and actual_norm:
        status = "wrong"
        match_reason = match_reason or "no_match"
    else:
        return _market_result(
            market=market,
            predicted=predicted,
            actual=actual,
            status="unavailable",
            confidence=conf,
            reason=f"low_identity_confidence:{match_reason}",
        )
    penalty_note = "penalty_first_goal" if meta.get("is_penalty") else None
    return _market_result(
        market=market,
        predicted=predicted,
        actual=actual,
        status=status,
        confidence=conf or match_conf,
        reason=penalty_note or match_reason,
    )


def evaluate_advanced_markets(
    payload: dict[str, Any],
    outcome: FixtureOutcome,
) -> dict[str, Any]:
    """Evaluate HT, Correct Score, First Goal Team, Goalscorer, and Goal Minute markets."""
    from worldcup_predictor.automation.worldcup_background.goal_minute_evaluator import evaluate_goal_minute

    return {
        "ht_result": evaluate_ht_result(payload, outcome),
        "correct_score": evaluate_correct_score(payload, outcome),
        "first_goal_team": evaluate_first_goal_team(payload, outcome),
        "goalscorer": evaluate_goalscorer(payload, outcome),
        "goal_minute": evaluate_goal_minute(payload, outcome),
    }


def advanced_market_status_map(advanced: dict[str, Any]) -> dict[str, str]:
    """Flatten advanced market detail into simple status keys for persistence."""
    out: dict[str, str] = {}
    key_map = {
        "ht_result": "ht_result",
        "correct_score": "correct_score",
        "first_goal_team": "first_goal_team",
        "goalscorer": "goalscorer",
        "goal_minute": "goal_minute",
    }
    for detail_key, market_key in key_map.items():
        block = advanced.get(detail_key) or {}
        if isinstance(block, dict) and block.get("status"):
            out[market_key] = str(block["status"])
    return out

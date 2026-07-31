"""Pure market settlement with explicit WIN | LOSS | PUSH | UNSUPPORTED.

Imports BCO classification helpers only. Does not modify BCO settlement.
Adds Draw No Bet and explicit PUSH (BCO historically maps push → unsupported).
"""

from __future__ import annotations

from typing import Any, Literal

from worldcup_predictor.research.bet_coverage_optimizer.market_semantics import (
    classified_price_to_market,
    classify_raw_market,
    extract_line,
    human_label,
    market_key_from_parts,
    normalize_dc,
    normalize_result,
    parse_score,
)
from worldcup_predictor.research.bet_coverage_optimizer import score_mapping as bco_settle
from worldcup_predictor.research.top10_to_5_optimizer.constants import LOSS, PUSH, UNSUPPORTED, WIN

SettleLabel = Literal["WIN", "LOSS", "PUSH", "UNSUPPORTED"]


def _result(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    if away_goals > home_goals:
        return "away"
    return "draw"


def _total(home_goals: int, away_goals: int) -> int:
    return int(home_goals) + int(away_goals)


def _map_bco(outcome: bool | str) -> SettleLabel:
    if outcome is True:
        return WIN
    if outcome is False:
        return LOSS
    return UNSUPPORTED


def settles_as_win(
    market_type: str,
    market_parameters: dict[str, Any] | None,
    home_goals: int,
    away_goals: int,
) -> SettleLabel:
    """
    Pure deterministic settlement.

    Returns WIN | LOSS | PUSH | UNSUPPORTED.
    Never silently converts PUSH to WIN or LOSS.
    """
    params = dict(market_parameters or {})
    mt = str(market_type or "").strip().lower()
    hg, ag = int(home_goals), int(away_goals)
    result = _result(hg, ag)
    total = _total(hg, ag)

    if mt in {"draw_no_bet", "dnb"}:
        side = normalize_result(str(params.get("result") or params.get("side") or params.get("team") or ""))
        if side not in {"home", "away"}:
            return UNSUPPORTED
        if result == "draw":
            return PUSH
        return WIN if result == side else LOSS

    if mt == "over_under":
        try:
            line = float(params["line"])
        except (KeyError, TypeError, ValueError):
            return UNSUPPORTED
        direction = str(params.get("direction") or "").lower()
        if float(line).is_integer() and total == int(line):
            return PUSH
        if direction == "over":
            return WIN if total > line else LOSS
        if direction == "under":
            return WIN if total < line else LOSS
        return UNSUPPORTED

    if mt == "team_total":
        team = normalize_result(str(params.get("team") or ""))
        if team not in {"home", "away"}:
            return UNSUPPORTED
        goals = hg if team == "home" else ag
        try:
            line = float(params["line"])
        except (KeyError, TypeError, ValueError):
            return UNSUPPORTED
        direction = str(params.get("direction") or "").lower()
        if float(line).is_integer() and goals == int(line):
            return PUSH
        if direction == "over":
            return WIN if goals > line else LOSS
        if direction == "under":
            return WIN if goals < line else LOSS
        return UNSUPPORTED

    if mt == "asian_handicap":
        team = normalize_result(str(params.get("team") or ""))
        if team not in {"home", "away"}:
            return UNSUPPORTED
        try:
            line = float(params["line"])
        except (KeyError, TypeError, ValueError):
            return UNSUPPORTED
        if team == "home":
            adj = (hg + line) - ag
        else:
            adj = (ag + line) - hg
        if abs(adj) < 1e-9:
            return PUSH
        frac = abs(line) % 1.0
        if abs(frac - 0.25) < 1e-9 or abs(frac - 0.75) < 1e-9:
            # Half-settlement not fully supported — explicit UNSUPPORTED (not silent win/loss)
            return UNSUPPORTED
        if abs(frac - 0.5) < 1e-9:
            return WIN if adj > 0 else LOSS
        return WIN if adj > 0 else LOSS

    if mt in {"result_total", "dc_total"}:
        # Component O/U may push — surface PUSH when result/DC wins and O/U pushes
        if mt == "result_total":
            res = normalize_result(str(params.get("result") or ""))
            if res is None:
                return UNSUPPORTED
            if res != result:
                return LOSS
        else:
            dc = normalize_dc(str(params.get("side") or ""))
            mapping = {"1x": {"home", "draw"}, "12": {"home", "away"}, "x2": {"draw", "away"}}
            allowed = mapping.get(dc or "")
            if not allowed:
                return UNSUPPORTED
            if result not in allowed:
                return LOSS
        try:
            line = float(params["line"])
        except (KeyError, TypeError, ValueError):
            return UNSUPPORTED
        direction = str(params.get("direction") or "").lower()
        if float(line).is_integer() and total == int(line):
            return PUSH
        if direction == "over":
            return WIN if total > line else LOSS
        if direction == "under":
            return WIN if total < line else LOSS
        return UNSUPPORTED

    # Defer remaining families to BCO (True/False/unsupported) then map labels
    bco = bco_settle.settles_as_win(mt, params, hg, ag)
    return _map_bco(bco)


def covered_scores_for_market(
    market_type: str,
    market_parameters: dict[str, Any],
    target_scores: list[str],
    *,
    treat_push_as_cover: bool = False,
) -> list[str] | None:
    """Scores that WIN (and optionally PUSH). None if any score is UNSUPPORTED."""
    covered: list[str] = []
    for score in target_scores:
        parts = str(score).replace(" ", "").split("-")
        if len(parts) != 2:
            continue
        try:
            hg, ag = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        outcome = settles_as_win(market_type, market_parameters, hg, ag)
        if outcome == UNSUPPORTED:
            return None
        if outcome == WIN or (treat_push_as_cover and outcome == PUSH):
            covered.append(f"{hg}-{ag}")
    return covered


def score_attributes(score: str) -> dict[str, Any]:
    parts = str(score).replace(" ", "").split("-")
    if len(parts) != 2:
        return {"scoreline": score}
    try:
        hg, ag = int(parts[0]), int(parts[1])
    except ValueError:
        return {"scoreline": score}
    if hg > ag:
        direction = "home"
    elif ag > hg:
        direction = "away"
    else:
        direction = "draw"
    return {
        "scoreline": f"{hg}-{ag}",
        "implied_1x2_direction": direction,
        "total_goals": hg + ag,
        "btts_status": "yes" if hg > 0 and ag > 0 else "no",
        "clean_sheet_status": "home_cs" if ag == 0 else ("away_cs" if hg == 0 else "neither"),
        "home_goals": hg,
        "away_goals": ag,
    }


# Re-export BCO classifiers for odds bridging (read-only reuse)
__all__ = [
    "settles_as_win",
    "covered_scores_for_market",
    "score_attributes",
    "classified_price_to_market",
    "classify_raw_market",
    "human_label",
    "market_key_from_parts",
    "parse_score",
    "extract_line",
    "normalize_result",
    "normalize_dc",
]

"""Post-processing market consistency guard — display-safe predictions without changing model outputs."""

from __future__ import annotations

import copy
import math
import re
from typing import Any, Literal

from worldcup_predictor.prediction.market_consistency_config import (
    CONSISTENCY_BTTS_NO_THRESHOLD,
    CONSISTENCY_BTTS_YES_THRESHOLD,
    CONSISTENCY_BTTS_YES_CLEAN_SHEET_SCORE_PROB_WITHHOLD,
    CONSISTENCY_DRAW_SCORING_SHARE,
    CONSISTENCY_EARLY_EXPECTED_MINUTE_MAX,
    CONSISTENCY_EARLY_MINUTE_BANDS,
    CONSISTENCY_LOW_TEAM_SCORING_PROB_THRESHOLD,
    CONSISTENCY_POISSON_LAMBDA_FLOOR,
    CONSISTENCY_RULES_VERSION,
    CONSISTENCY_STRONG_GOALSCORER_CONFIDENCE,
    CONSISTENCY_UNDER25_THRESHOLD,
    CONSISTENCY_OVER25_THRESHOLD,
    WITHHELD_USER_MESSAGE,
    get_consistency_thresholds,
)
from worldcup_predictor.prediction.market_consistency_timing import (
    RULE_TIMING_RANGE_CONSISTENCY,
    band_for_expected_minute,
    expected_minute_in_band,
    normalize_minute_band,
)

RULE_OU_CORRECT_SCORE_CONSISTENCY = "OU_CORRECT_SCORE_CONSISTENCY"
RULE_FIRST_GOAL_SCORELESS_CONSISTENCY = "FIRST_GOAL_SCORELESS_CONSISTENCY"

ConsistencyStatus = Literal["ok", "warning", "withheld"]

_DC_INCLUDES: dict[str, frozenset[str]] = {
    "home_or_draw": frozenset({"home_win", "draw"}),
    "home_or_away": frozenset({"home_win", "away_win"}),
    "draw_or_away": frozenset({"draw", "away_win"}),
}

_BTTS_YES_CONFLICT_SCORES = frozenset(
    {
        (0, 0),
        (1, 0),
        (0, 1),
    }
)


def _norm_prob(value: float | None) -> float:
    if value is None:
        return 0.0
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0.0
    return num / 100.0 if num > 1.0 else num


def _pct(value: float | None) -> float:
    return round(_norm_prob(value) * 100, 1)


def _parse_scoreline(label: str) -> tuple[int | None, int | None]:
    text = str(label or "").strip().replace(" ", "")
    match = re.match(r"^(\d+)[:\-](\d+)$", text)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _winner_from_score(home: int, away: int) -> str:
    if home > away:
        return "home_win"
    if away > home:
        return "away_win"
    return "draw"


def _both_teams_score(home: int, away: int) -> bool:
    return home > 0 and away > 0


def _clean_sheet_score(home: int, away: int) -> bool:
    return home == 0 or away == 0


def _top_1x2_selection(ft_probs: dict[str, float], fallback: str | None = None) -> str:
    if ft_probs:
        return max(ft_probs, key=lambda k: float(ft_probs.get(k) or 0))
    return str(fallback or "home_win")


def _team_side(team: str | None, home_team: str, away_team: str) -> str | None:
    if not team:
        return None
    team_l = team.strip().lower()
    if team_l == home_team.strip().lower():
        return "home"
    if team_l == away_team.strip().lower():
        return "away"
    return None


def _poisson_scores_prob(lambda_goals: float) -> float:
    lam = max(CONSISTENCY_POISSON_LAMBDA_FLOOR, float(lambda_goals or 0))
    return 1.0 - math.exp(-lam)


def _team_scoring_probability(
    *,
    team: str | None,
    home_team: str,
    away_team: str,
    ft_probs: dict[str, float],
    sportmonks_xg: dict[str, Any] | None,
) -> float | None:
    side = _team_side(team, home_team, away_team)
    xg_block = sportmonks_xg or {}
    if side == "home":
        xg = xg_block.get("home_xg")
        if xg is not None:
            return _poisson_scores_prob(float(xg))
    elif side == "away":
        xg = xg_block.get("away_xg")
        if xg is not None:
            return _poisson_scores_prob(float(xg))

    h = _norm_prob(ft_probs.get("home_win"))
    d = _norm_prob(ft_probs.get("draw"))
    a = _norm_prob(ft_probs.get("away_win"))
    if side == "home":
        return min(1.0, h + d * CONSISTENCY_DRAW_SCORING_SHARE)
    if side == "away":
        return min(1.0, a + d * CONSISTENCY_DRAW_SCORING_SHARE)
    return None


def _stamp_market(
    block: dict[str, Any],
    *,
    status: ConsistencyStatus,
    display_allowed: bool,
    reason: str | None = None,
    messages: list[str] | None = None,
) -> dict[str, Any]:
    out = dict(block)
    out["consistency_status"] = status
    out["display_allowed"] = display_allowed
    out["withheld_reason"] = reason
    out["consistency_messages"] = list(messages or [])
    return out


def _default_stamp(block: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(block or {})
    if "consistency_status" not in base:
        return _stamp_market(base, status="ok", display_allowed=True)
    return base


def _withhold(
    block: dict[str, Any],
    *,
    reason: str,
    messages: list[str] | None = None,
) -> dict[str, Any]:
    return _stamp_market(
        block,
        status="withheld",
        display_allowed=False,
        reason=reason,
        messages=messages or [reason],
    )


def _warn(
    block: dict[str, Any],
    *,
    reason: str,
    messages: list[str] | None = None,
    display_allowed: bool = True,
) -> dict[str, Any]:
    return _stamp_market(
        block,
        status="warning",
        display_allowed=display_allowed,
        reason=reason,
        messages=messages or [reason],
    )


def _sanitize_pick(pick: dict[str, Any] | None, withheld_keys: set[str]) -> dict[str, Any] | None:
    if not pick:
        return pick
    key = str(pick.get("market_key") or "")
    if key not in withheld_keys:
        out = dict(pick)
        out.setdefault("display_allowed", True)
        out.setdefault("consistency_status", "ok")
        return out
    return {
        **pick,
        "display_allowed": False,
        "consistency_status": "withheld",
        "withheld_reason": WITHHELD_USER_MESSAGE,
        "display_text": WITHHELD_USER_MESSAGE,
        "pick": None,
        "status": "withheld",
    }


def _sanitize_pick_list(items: list[Any] | None, withheld_keys: set[str]) -> list[Any]:
    if not isinstance(items, list):
        return []
    out: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            sanitized = _sanitize_pick(item, withheld_keys)
            if sanitized is not None:
                out.append(sanitized)
        else:
            out.append(item)
    return out


def _apply_timing_range_consistency(first_goal: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """TIMING_RANGE_CONSISTENCY — expected minute must fall inside minute_range."""
    fg = dict(first_goal)
    minute_range = normalize_minute_band(str(fg.get("minute_range") or ""))
    expected_raw = fg.get("expected_minute")
    if expected_raw is None or not minute_range or minute_range in {"—", "-"}:
        return fg, []

    try:
        expected_minute = int(expected_raw)
    except (TypeError, ValueError):
        reason = f"{RULE_TIMING_RANGE_CONSISTENCY}: invalid expected_minute {expected_raw!r}."
        return _withhold(fg, reason=reason), [reason]

    if expected_minute_in_band(expected_minute, minute_range):
        fg["minute_range"] = minute_range
        return fg, []

    aligned_band = band_for_expected_minute(expected_minute)
    if aligned_band:
        reason = (
            f"{RULE_TIMING_RANGE_CONSISTENCY}: expected minute {expected_minute} was outside "
            f"range {minute_range}; aligned display range to {aligned_band}."
        )
        fg["minute_range"] = aligned_band
        fg["expected_minute"] = expected_minute
        fg["timing_range_aligned"] = True
        return _warn(fg, reason=reason), [reason]

    reason = (
        f"{RULE_TIMING_RANGE_CONSISTENCY}: expected minute {expected_minute} does not fit "
        f"minute range {minute_range} and could not be aligned."
    )
    return _withhold(fg, reason=reason), [reason]


def apply_market_consistency_guard(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Apply global cross-market consistency rules to an API prediction payload.

    Raw model values are preserved in ``consistency_guard.raw_markets_audit``.
    """
    if not payload or payload.get("status") != "ok":
        return payload

    out = copy.deepcopy(payload)
    home_team = str(out.get("home_team") or "Home")
    away_team = str(out.get("away_team") or "Away")

    detailed = dict(out.get("detailed_markets") or {})
    raw_audit = copy.deepcopy(detailed)

    warnings: list[str] = []
    applied_rules: list[str] = []
    withheld_markets: list[str] = []
    withheld_keys: set[str] = set()

    mw = _default_stamp(detailed.get("match_winner"))
    ft_probs = dict(mw.get("probabilities") or {})
    top_1x2 = _top_1x2_selection(ft_probs, mw.get("selection"))

    ou = _default_stamp(detailed.get("over_under_25"))
    ou_probs = dict(ou.get("probabilities") or {})
    under_pct = _norm_prob(ou_probs.get("under_2_5"))
    over_pct = _norm_prob(ou_probs.get("over_2_5"))
    if under_pct <= 0 and ou.get("selection") == "under_2_5":
        under_pct = _norm_prob(ou.get("probability"))
    if over_pct <= 0 and ou.get("selection") == "over_2_5":
        over_pct = _norm_prob(ou.get("probability"))

    btts = _default_stamp(detailed.get("btts"))
    btts_probs = dict(btts.get("probabilities") or {})
    btts_yes = _norm_prob(btts_probs.get("yes"))
    btts_no = _norm_prob(btts_probs.get("no"))
    if btts_yes <= 0 and btts_no <= 0:
        sel = str(btts.get("selection") or "")
        prob = _norm_prob(btts.get("probability"))
        if sel == "yes":
            btts_yes = prob
            btts_no = 1.0 - prob
        elif sel == "no":
            btts_no = prob
            btts_yes = 1.0 - prob

    sportmonks_xg = out.get("sportmonks_xg") if isinstance(out.get("sportmonks_xg"), dict) else {}

    # Rule 1 & 6 — BTTS No / team scoring vs goalscorer
    goalscorer = _default_stamp(detailed.get("goalscorer") or {})
    gs_player = goalscorer.get("player")
    gs_team = goalscorer.get("team")
    gs_conf = _norm_prob(goalscorer.get("confidence"))

    if gs_player and goalscorer.get("available", True):
        team_score_prob = _team_scoring_probability(
            team=str(gs_team) if gs_team else None,
            home_team=home_team,
            away_team=away_team,
            ft_probs=ft_probs,
            sportmonks_xg=sportmonks_xg,
        )
        if btts_no >= CONSISTENCY_BTTS_NO_THRESHOLD:
            if team_score_prob is not None and team_score_prob < CONSISTENCY_LOW_TEAM_SCORING_PROB_THRESHOLD:
                reason = (
                    f"BTTS No is {_pct(btts_no):.1f}% while {gs_team or 'selected team'} "
                    f"has low scoring probability ({_pct(team_score_prob):.1f}%)."
                )
                goalscorer = _withhold(goalscorer, reason=reason)
                withheld_markets.append("goalscorer")
                withheld_keys.add("goalscorer")
                warnings.append(reason)
            elif team_score_prob is None and gs_conf < CONSISTENCY_STRONG_GOALSCORER_CONFIDENCE:
                reason = (
                    "BTTS No is strong and team scoring probability is unavailable; "
                    "goalscorer confidence is not high enough to display safely."
                )
                goalscorer = _withhold(goalscorer, reason=reason)
                withheld_markets.append("goalscorer")
                withheld_keys.add("goalscorer")
                warnings.append(reason)
        elif team_score_prob is not None and team_score_prob < CONSISTENCY_LOW_TEAM_SCORING_PROB_THRESHOLD:
            if gs_conf < CONSISTENCY_STRONG_GOALSCORER_CONFIDENCE:
                reason = (
                    f"{gs_team or 'Selected team'} has low expected scoring probability "
                    f"({_pct(team_score_prob):.1f}%) for a goalscorer pick."
                )
                goalscorer = _withhold(goalscorer, reason=reason)
                withheld_markets.append("goalscorer")
                withheld_keys.add("goalscorer")
                warnings.append(reason)

    detailed["goalscorer"] = goalscorer

    # TIMING_RANGE_CONSISTENCY — expected minute must match minute_range
    first_goal = _default_stamp(detailed.get("first_goal") or {})
    first_goal, timing_msgs = _apply_timing_range_consistency(first_goal)
    warnings.extend(timing_msgs)
    if timing_msgs:
        applied_rules.append(RULE_TIMING_RANGE_CONSISTENCY)

    minute_range = str(first_goal.get("minute_range") or "")
    expected_minute = first_goal.get("expected_minute")
    under_high = under_pct >= CONSISTENCY_UNDER25_THRESHOLD

    aggressive_timing = False
    if minute_range.replace("_", "-") in CONSISTENCY_EARLY_MINUTE_BANDS:
        aggressive_timing = True
    if expected_minute is not None:
        try:
            aggressive_timing = aggressive_timing or int(expected_minute) <= CONSISTENCY_EARLY_EXPECTED_MINUTE_MAX
        except (TypeError, ValueError):
            pass

    if under_high and aggressive_timing and (minute_range or expected_minute is not None):
        reason = (
            f"Under 2.5 is {_pct(under_pct):.1f}% — early/multiple goal timing conflicts with low total goals."
        )
        first_goal = _withhold(first_goal, reason=reason)
        withheld_markets.append("first_goal")
        withheld_keys.update({"first_goal_minute", "first_goal_team"})
        warnings.append(reason)
    elif under_high and aggressive_timing:
        first_goal = _warn(first_goal, reason="Low total goals signal conflicts with goal timing confidence.")
        warnings.append(first_goal["withheld_reason"] or "")

    detailed["first_goal"] = first_goal

    # Rule 3 — Correct score vs 1X2
    scores_raw = list(detailed.get("correct_scores") or [])
    sanitized_scores: list[dict[str, Any]] = []
    for row in scores_raw:
        if not isinstance(row, dict):
            continue
        stamped = _default_stamp(row)
        label = str(stamped.get("label") or stamped.get("scoreline") or stamped.get("score") or "")
        home_g, away_g = _parse_scoreline(label)
        if home_g is None or away_g is None:
            sanitized_scores.append(stamped)
            continue
        score_winner = _winner_from_score(home_g, away_g)
        if score_winner != top_1x2:
            reason = f"Correct score {label} implies {score_winner.replace('_', ' ')} but 1X2 leader is {top_1x2.replace('_', ' ')}."
            stamped = _withhold(stamped, reason=reason)
            withheld_markets.append("correct_score")
            withheld_keys.add("correct_score")
            warnings.append(reason)
        sanitized_scores.append(stamped)

    if sanitized_scores:
        detailed["correct_scores"] = sanitized_scores
        if any(s.get("consistency_status") == "withheld" for s in sanitized_scores):
            detailed["correct_scores_meta"] = _withhold(
                _default_stamp(detailed.get("correct_scores_meta") or {}),
                reason="Top correct score conflicts with 1X2 leader.",
            )

    # Rule 4 — Double Chance vs 1X2
    dc = _default_stamp(detailed.get("double_chance") or {})
    if dc:
        dc_options = {
            "home_or_draw": float(dc.get("home_or_draw") or 0),
            "home_or_away": float(dc.get("home_or_away") or 0),
            "draw_or_away": float(dc.get("draw_or_away") or 0),
        }
        best_dc = max(dc_options, key=lambda k: dc_options[k])
        includes = _DC_INCLUDES.get(best_dc, frozenset())
        if top_1x2 not in includes:
            reason = (
                f"Double Chance leader ({best_dc.replace('_', ' ')}) excludes 1X2 leader "
                f"({top_1x2.replace('_', ' ')})."
            )
            dc = _warn(dc, reason=reason, display_allowed=True)
            withheld_markets.append("double_chance")
            withheld_keys.add("double_chance")
            warnings.append(reason)
        detailed["double_chance"] = dc

    # Rule 5 — BTTS vs correct score rows
    if sanitized_scores:
        adjusted_scores: list[dict[str, Any]] = []
        for row in sanitized_scores:
            if row.get("consistency_status") == "withheld":
                adjusted_scores.append(row)
                continue
            label = str(row.get("label") or row.get("scoreline") or row.get("score") or "")
            home_g, away_g = _parse_scoreline(label)
            if home_g is None or away_g is None:
                adjusted_scores.append(row)
                continue
            score_prob = _norm_prob(row.get("probability"))
            total_goals = home_g + away_g
            if under_pct >= CONSISTENCY_UNDER25_THRESHOLD and total_goals >= 3:
                reason = (
                    f"{RULE_OU_CORRECT_SCORE_CONSISTENCY}: Under 2.5 is {_pct(under_pct):.1f}% "
                    f"but correct score {label} implies {total_goals} goals."
                )
                row = _withhold(row, reason=reason)
                withheld_markets.append("correct_score")
                withheld_keys.add("correct_score")
                warnings.append(reason)
                applied_rules.append(RULE_OU_CORRECT_SCORE_CONSISTENCY)
            elif over_pct >= CONSISTENCY_OVER25_THRESHOLD and total_goals <= 2:
                reason = (
                    f"{RULE_OU_CORRECT_SCORE_CONSISTENCY}: Over 2.5 is {_pct(over_pct):.1f}% "
                    f"but correct score {label} implies {total_goals} goals."
                )
                row = _withhold(row, reason=reason)
                withheld_markets.append("correct_score")
                withheld_keys.add("correct_score")
                warnings.append(reason)
                applied_rules.append(RULE_OU_CORRECT_SCORE_CONSISTENCY)
            elif btts_no >= CONSISTENCY_BTTS_NO_THRESHOLD and _both_teams_score(home_g, away_g):
                reason = f"BTTS No is {_pct(btts_no):.1f}% but correct score {label} requires both teams to score."
                row = _withhold(row, reason=reason)
                withheld_markets.append("correct_score")
                withheld_keys.add("correct_score")
                warnings.append(reason)
            elif btts_yes >= CONSISTENCY_BTTS_YES_THRESHOLD and _clean_sheet_score(home_g, away_g):
                if score_prob >= CONSISTENCY_BTTS_YES_CLEAN_SHEET_SCORE_PROB_WITHHOLD:
                    reason = f"BTTS Yes is {_pct(btts_yes):.1f}% but correct score {label} has a clean sheet."
                    row = _withhold(row, reason=reason)
                    withheld_markets.append("correct_score")
                    withheld_keys.add("correct_score")
                    warnings.append(reason)
                else:
                    row = _warn(
                        row,
                        reason=f"Low-confidence correct score {label} may conflict with strong BTTS Yes.",
                        display_allowed=True,
                    )
            adjusted_scores.append(row)
        detailed["correct_scores"] = adjusted_scores

    # FIRST_GOAL_SCORELESS — 0-0 correct score vs first team to score
    final_scores = list(detailed.get("correct_scores") or [])
    if first_goal.get("team") and final_scores:
        for row in final_scores:
            if row.get("consistency_status") == "withheld" or row.get("display_allowed") is False:
                continue
            label = str(row.get("label") or row.get("scoreline") or row.get("score") or "")
            home_g, away_g = _parse_scoreline(label)
            if home_g == 0 and away_g == 0:
                reason = (
                    f"{RULE_FIRST_GOAL_SCORELESS_CONSISTENCY}: correct score 0-0 conflicts with "
                    f"first team to score ({first_goal.get('team')})."
                )
                first_goal = _withhold(first_goal, reason=reason)
                withheld_markets.append("first_goal")
                withheld_keys.update({"first_goal_minute", "first_goal_team"})
                warnings.append(reason)
                if RULE_FIRST_GOAL_SCORELESS_CONSISTENCY not in applied_rules:
                    applied_rules.append(RULE_FIRST_GOAL_SCORELESS_CONSISTENCY)
                detailed["first_goal"] = first_goal
                break

    # Stamp reference markets as ok
    detailed["match_winner"] = mw
    detailed["over_under_25"] = ou
    detailed["btts"] = btts
    if "halftime" in detailed:
        detailed["halftime"] = _default_stamp(detailed.get("halftime"))
    if "first_half_team_to_score" in detailed:
        detailed["first_half_team_to_score"] = _default_stamp(detailed.get("first_half_team_to_score"))

    out["detailed_markets"] = detailed

    # Sanitize ranked picks / recommendations
    for key in (
        "recommended_bets",
        "market_ranking",
    ):
        out[key] = _sanitize_pick_list(out.get(key), withheld_keys)

    for key in (
        "safe_pick",
        "value_pick",
        "aggressive_pick",
        "caution_pick",
        "best_available_pick",
        "primary_recommendation",
        "user_visible_pick",
    ):
        out[key] = _sanitize_pick(out.get(key), withheld_keys)

    out["consistency_guard"] = {
        "applied": True,
        "consistency_warnings": warnings,
        "withheld_markets": sorted(set(withheld_markets)),
        "raw_markets_audit": raw_audit,
        "rules_version": CONSISTENCY_RULES_VERSION,
        "thresholds": get_consistency_thresholds(),
        "applied_rules": sorted(set(applied_rules)),
    }
    return out

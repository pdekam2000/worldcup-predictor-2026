"""Deterministic score → market settlement mapping."""

from __future__ import annotations

from typing import Any, Literal

from worldcup_predictor.research.bet_coverage_optimizer.market_semantics import normalize_dc, normalize_result

Unsupported = Literal["unsupported"]
SettleResult = bool | Unsupported


def _result(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    if away_goals > home_goals:
        return "away"
    return "draw"


def _total(home_goals: int, away_goals: int) -> int:
    return int(home_goals) + int(away_goals)


def _ou_wins(direction: str, line: float, total: int) -> SettleResult:
    d = str(direction or "").lower()
    # Whole-number lines can push — treat push as unsupported for win mapping.
    if float(line).is_integer() and total == int(line):
        return "unsupported"
    if d == "over":
        return total > float(line)
    if d == "under":
        return total < float(line)
    return "unsupported"


def _team_ou_wins(direction: str, line: float, goals: int) -> SettleResult:
    d = str(direction or "").lower()
    if float(line).is_integer() and goals == int(line):
        return "unsupported"
    if d == "over":
        return goals > float(line)
    if d == "under":
        return goals < float(line)
    return "unsupported"


def _dc_wins(side: str, result: str) -> SettleResult:
    dc = normalize_dc(side) or str(side or "").lower()
    mapping = {"1x": {"home", "draw"}, "12": {"home", "away"}, "x2": {"draw", "away"}}
    allowed = mapping.get(dc)
    if not allowed:
        return "unsupported"
    return result in allowed


def _winning_margin(selection: str, home_goals: int, away_goals: int) -> SettleResult:
    sel = str(selection or "").strip().lower().replace(" ", "_").replace("+", "")
    diff = home_goals - away_goals
    abs_diff = abs(diff)
    if sel in {"draw", "draw_0", "margin_0", "draw_margin_0", "0"}:
        return diff == 0
    if sel in {"home_1", "home_by_1", "1_by_1", "home_+1"}:
        return diff == 1
    if sel in {"away_1", "away_by_1", "2_by_1", "away_+1"}:
        return diff == -1
    if sel in {"home_2", "home_by_2", "1_by_2", "home_+2"}:
        return diff == 2
    if sel in {"away_2", "away_by_2", "2_by_2", "away_+2"}:
        return diff == -2
    if sel in {"home_3", "home_by_3", "home_3_plus", "home_by_3_plus", "1_by_3", "1_by_4"}:
        return diff >= 3
    if sel in {"away_3", "away_by_3", "away_3_plus", "away_by_3_plus", "2_by_3", "2_by_4"}:
        return diff <= -3
    # Generic patterns home_by_N / away_by_N
    if sel.startswith("home_by_") or sel.startswith("1_by_"):
        try:
            n = int(sel.split("_")[-1].replace("plus", ""))
            return (diff == n) if "plus" not in sel else (diff >= n)
        except ValueError:
            return "unsupported"
    if sel.startswith("away_by_") or sel.startswith("2_by_"):
        try:
            n = int(sel.split("_")[-1].replace("plus", ""))
            return (diff == -n) if "plus" not in sel else (diff <= -n)
        except ValueError:
            return "unsupported"
    if abs_diff == 0 and "draw" in sel:
        return True
    return "unsupported"


def _asian_handicap(team: str, line: float, home_goals: int, away_goals: int) -> SettleResult:
    """Clear-win only; quarter/half pushes return unsupported."""
    t = normalize_result(team) or str(team or "").lower()
    if t not in {"home", "away"}:
        return "unsupported"
    # Handicap applied to selected team
    if t == "home":
        adj = (home_goals + float(line)) - away_goals
    else:
        adj = (away_goals + float(line)) - home_goals
    # Integer / .0 lines: adj==0 is push
    if abs(adj) < 1e-9:
        return "unsupported"
    # Quarter lines (.25/.75) can split — treat as unsupported unless decisive whole half
    frac = abs(float(line)) % 1.0
    if abs(frac - 0.25) < 1e-9 or abs(frac - 0.75) < 1e-9:
        # Require clear full win after both half-lines would win
        half_a = float(line) - 0.25 if frac > 0.5 else float(line) + 0.25
        half_b = float(line) + 0.25 if frac > 0.5 else float(line) - 0.25
        # Simpler policy: unsupported for quarter lines
        _ = (half_a, half_b)
        return "unsupported"
    return adj > 0


def _european_handicap(team: str, line: float, home_goals: int, away_goals: int) -> SettleResult:
    t = normalize_result(team) or str(team or "").lower()
    if t not in {"home", "away"}:
        return "unsupported"
    if t == "home":
        adj_h, adj_a = home_goals + float(line), away_goals
    else:
        adj_h, adj_a = home_goals, away_goals + float(line)
    if adj_h == adj_a:
        return False  # EH has no push; draw after handicap loses for win markets
    if t == "home":
        return adj_h > adj_a
    return adj_a > adj_h


def settles_as_win(
    market_type: str,
    market_parameters: dict[str, Any] | None,
    home_goals: int,
    away_goals: int,
) -> SettleResult:
    """
    Pure settlement evaluator.

    Returns:
      True — selection wins for this exact score
      False — selection loses
      "unsupported" — mapping incomplete / push / unknown semantics
    """
    params = dict(market_parameters or {})
    mt = str(market_type or "").strip().lower()
    hg, ag = int(home_goals), int(away_goals)
    result = _result(hg, ag)
    total = _total(hg, ag)

    if mt == "exact_score":
        score = str(params.get("score") or "").replace(" ", "")
        return score == f"{hg}-{ag}"

    if mt == "double_chance":
        return _dc_wins(str(params.get("side") or ""), result)

    if mt == "over_under":
        return _ou_wins(str(params.get("direction") or ""), float(params["line"]), total)

    if mt == "btts":
        side = str(params.get("side") or "").lower()
        both = hg > 0 and ag > 0
        if side == "yes":
            return both
        if side == "no":
            return not both
        return "unsupported"

    if mt == "result_total":
        res = normalize_result(str(params.get("result") or ""))
        if res is None or res != result:
            return False if res is not None else "unsupported"
        return _ou_wins(str(params.get("direction") or ""), float(params["line"]), total)

    if mt == "dc_total":
        dc = _dc_wins(str(params.get("side") or ""), result)
        if dc == "unsupported":
            return "unsupported"
        if dc is False:
            return False
        return _ou_wins(str(params.get("direction") or ""), float(params["line"]), total)

    if mt == "team_total":
        team = normalize_result(str(params.get("team") or ""))
        if team not in {"home", "away"}:
            return "unsupported"
        goals = hg if team == "home" else ag
        return _team_ou_wins(str(params.get("direction") or ""), float(params["line"]), goals)

    if mt == "win_to_nil":
        team = normalize_result(str(params.get("team") or ""))
        if team == "home":
            return hg > ag and ag == 0
        if team == "away":
            return ag > hg and hg == 0
        return "unsupported"

    if mt == "winning_margin":
        return _winning_margin(str(params.get("selection") or ""), hg, ag)

    if mt == "asian_handicap":
        return _asian_handicap(str(params.get("team") or ""), float(params["line"]), hg, ag)

    if mt == "european_handicap":
        return _european_handicap(str(params.get("team") or ""), float(params["line"]), hg, ag)

    if mt == "goal_parity":
        parity = str(params.get("parity") or "").lower()
        odd = total % 2 == 1
        if parity == "odd":
            return odd
        if parity == "even":
            return not odd
        return "unsupported"

    if mt == "exact_team_goals":
        team = normalize_result(str(params.get("team") or ""))
        try:
            n = int(params.get("goals"))
        except (TypeError, ValueError):
            return "unsupported"
        if team == "home":
            return hg == n
        if team == "away":
            return ag == n
        return "unsupported"

    if mt == "1x2":
        res = normalize_result(str(params.get("result") or params.get("side") or ""))
        if res is None:
            return "unsupported"
        return result == res

    return "unsupported"


def covered_scores_for_market(
    market_type: str,
    market_parameters: dict[str, Any],
    target_scores: list[str],
) -> list[str] | None:
    """Return target scores that settle as win, or None if market semantics unsupported."""
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
        if outcome == "unsupported":
            return None
        if outcome is True:
            covered.append(f"{hg}-{ag}")
    return covered

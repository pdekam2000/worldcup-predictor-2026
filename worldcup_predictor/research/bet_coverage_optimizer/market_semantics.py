"""Market type / parameter normalization for settlement mapping."""

from __future__ import annotations

import re
from typing import Any


def parse_score(label: str | None) -> tuple[int, int] | None:
    if label is None:
        return None
    m = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", str(label))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def normalize_dc(selection: str) -> str | None:
    s = str(selection or "").strip().lower().replace(" ", "").replace("-", "").replace("/", "")
    mapping = {
        "1x": "1x",
        "homedraw": "1x",
        "12": "12",
        "homeaway": "12",
        "x2": "x2",
        "drawaway": "x2",
    }
    return mapping.get(s)


def normalize_result(selection: str) -> str | None:
    s = str(selection or "").strip().lower()
    return {
        "home": "home",
        "1": "home",
        "h": "home",
        "draw": "draw",
        "x": "draw",
        "d": "draw",
        "away": "away",
        "2": "away",
        "a": "away",
    }.get(s)


def extract_line(text: str) -> float | None:
    s = str(text or "")
    # Prefer over/under goal lines (x.5 / x.0) over digits inside tokens like "X2"
    m = re.search(r"(?:over|under)\s*(\d+(?:\.\d+)?)", s, flags=re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    m = re.search(r"(\d+\.\d+)", s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    m = re.search(r"(-?\d+(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def market_key_from_parts(market_type: str, params: dict[str, Any]) -> str:
    parts = [market_type]
    for k in sorted(params.keys()):
        parts.append(f"{k}={params[k]}")
    return "|".join(parts)


def human_label(market_type: str, params: dict[str, Any]) -> str:
    if market_type == "exact_score":
        return f"Exact {params.get('score')}"
    if market_type == "double_chance":
        return f"Double Chance {str(params.get('side') or '').upper()}"
    if market_type == "over_under":
        return f"{str(params.get('direction') or '').title()} {params.get('line')}"
    if market_type == "btts":
        return f"BTTS {str(params.get('side') or '').title()}"
    if market_type == "result_total":
        return (
            f"{str(params.get('result') or '').title()} & "
            f"{str(params.get('direction') or '').title()} {params.get('line')}"
        )
    if market_type == "dc_total":
        return (
            f"{str(params.get('side') or '').upper()} & "
            f"{str(params.get('direction') or '').title()} {params.get('line')}"
        )
    if market_type == "team_total":
        return (
            f"{str(params.get('team') or '').title()} "
            f"{str(params.get('direction') or '').title()} {params.get('line')} Team Goals"
        )
    if market_type == "win_to_nil":
        return f"{str(params.get('team') or '').title()} Win to Nil"
    if market_type == "winning_margin":
        return f"Winning Margin {params.get('selection')}"
    if market_type == "asian_handicap":
        return f"AH {params.get('team')} {params.get('line')}"
    if market_type == "european_handicap":
        return f"EH {params.get('team')} {params.get('line')}"
    if market_type == "goal_parity":
        return f"Goals {str(params.get('parity') or '').title()}"
    if market_type == "exact_team_goals":
        return f"{str(params.get('team') or '').title()} Exact Goals {params.get('goals')}"
    return market_key_from_parts(market_type, params)


def classify_raw_market(market_name: str, selection: str) -> tuple[str, dict[str, Any]] | None:
    """Best-effort deterministic mapping from provider market name + selection."""
    name = str(market_name or "").strip().lower()
    sel = str(selection or "").strip()
    sel_l = sel.lower()

    if "correct score" in name or "exact score" in name:
        sc = parse_score(sel)
        if sc:
            return "exact_score", {"score": f"{sc[0]}-{sc[1]}"}

    if "double chance" in name and "under" not in name and "over" not in name:
        dc = normalize_dc(sel)
        if dc:
            return "double_chance", {"side": dc}

    if name in {"both teams score", "btts", "both teams to score"} or (
        "both teams" in name and "score" in name and "over" not in name
    ):
        if "yes" in sel_l:
            return "btts", {"side": "yes"}
        if "no" in sel_l:
            return "btts", {"side": "no"}

    # Double chance + total BEFORE plain result+total (avoid X2 → draw / line=2)
    if ("double chance" in name and ("under" in name or "over" in name or "total" in name)) or (
        any(tok in sel_l.replace(" ", "") for tok in ("1x", "x2", "12", "home/draw", "draw/away", "home/away"))
        and ("under" in sel_l or "over" in sel_l)
    ):
        dc = None
        compact = sel_l.replace(" ", "").replace("/", "")
        for cand, norm in (("1x", "1x"), ("x2", "x2"), ("12", "12"), ("homedraw", "1x"), ("drawaway", "x2"), ("homeaway", "12")):
            if cand in compact:
                dc = norm
                break
        direction = "under" if "under" in sel_l else ("over" if "over" in sel_l else None)
        line = extract_line(sel_l)
        if dc and direction and line is not None:
            return "dc_total", {"side": dc, "direction": direction, "line": line}

    # Result + total / win + under/over
    if any(
        tok in name
        for tok in (
            "result/total",
            "result / total",
            "match result and total",
            "result and total",
            "win and under",
            "win and over",
            "home/away & under",
            "home/away & over",
        )
    ) or (("&" in sel_l or "/" in sel_l) and ("under" in sel_l or "over" in sel_l) and any(
        x in sel_l for x in ("home", "away", "draw")
    )):
        line = extract_line(sel_l)
        direction = "under" if "under" in sel_l else ("over" if "over" in sel_l else None)
        result = None
        if "home" in sel_l:
            result = "home"
        elif "away" in sel_l:
            result = "away"
        elif "draw" in sel_l:
            result = "draw"
        if result and direction and line is not None:
            return "result_total", {"result": result, "direction": direction, "line": line}

    # Team totals
    if "team total" in name or "team goals" in name or "home team" in name or "away team" in name:
        team = "home" if "home" in name or "home" in sel_l else ("away" if "away" in name or "away" in sel_l else None)
        direction = "under" if "under" in sel_l else ("over" if "over" in sel_l else None)
        line = extract_line(sel_l)
        if team and direction and line is not None:
            return "team_total", {"team": team, "direction": direction, "line": line}

    # Plain O/U (exclude halves / corners / team)
    if not any(t in name for t in ("first half", "second half", "corner", "team total", "home team", "away team")):
        if "over/under" in name or "goals over" in name or name in {"totals", "total_goals", "goals"}:
            line = extract_line(sel_l)
            direction = "under" if "under" in sel_l else ("over" if "over" in sel_l else None)
            if direction and line is not None:
                return "over_under", {"direction": direction, "line": line}

    if "win to nil" in name or "to win to nil" in name or "clean sheet" in name and "win" in name:
        team = normalize_result(sel_l.split()[0] if sel_l else "") or (
            "home" if "home" in sel_l else ("away" if "away" in sel_l else None)
        )
        if team in {"home", "away"}:
            return "win_to_nil", {"team": team}

    if "winning margin" in name:
        return "winning_margin", {"selection": sel_l.replace(" ", "_")}

    if "odd/even" in name or "goal odd" in name or name in {"odd even", "goals odd/even"}:
        if "odd" in sel_l:
            return "goal_parity", {"parity": "odd"}
        if "even" in sel_l:
            return "goal_parity", {"parity": "even"}

    if "asian handicap" in name:
        team = "home" if "home" in sel_l or sel_l.startswith("-") or sel_l.startswith("+") else None
        # Prefer explicit home/away in selection
        if "home" in sel_l or sel_l.startswith("1"):
            team = "home"
        elif "away" in sel_l or sel_l.startswith("2"):
            team = "away"
        line = extract_line(sel_l)
        if team and line is not None:
            # If selection is like "-1.5" without team, treat as home line convention
            if team is None:
                team = "home"
            return "asian_handicap", {"team": team, "line": line}

    if "european handicap" in name or name.strip() == "handicap":
        team = "home" if "home" in sel_l else ("away" if "away" in sel_l else "home")
        line = extract_line(sel_l)
        if line is not None:
            return "european_handicap", {"team": team, "line": line}

    # Exact team goals
    m = re.search(r"(home|away).{0,20}(?:exact|goals?).{0,10}(\d+)", f"{name} {sel_l}")
    if m:
        return "exact_team_goals", {"team": m.group(1), "goals": int(m.group(2))}

    return None


def classified_price_to_market(family: str, selection: str) -> tuple[str, dict[str, Any]] | None:
    """Map MultiMarketBundle (family, selection) into settlement market_type/params."""
    fam = str(family or "").strip().lower()
    sel = str(selection or "").strip().lower()

    if fam == "exact_score":
        sc = parse_score(sel)
        if sc:
            return "exact_score", {"score": f"{sc[0]}-{sc[1]}"}
    if fam == "double_chance":
        dc = normalize_dc(sel)
        if dc:
            return "double_chance", {"side": dc}
    if fam == "btts":
        if sel in {"yes", "no"}:
            return "btts", {"side": sel}
    if fam == "over_under":
        direction = "over" if sel.startswith("over") else ("under" if sel.startswith("under") else None)
        line = extract_line(sel)
        if direction and line is not None:
            return "over_under", {"direction": direction, "line": line}
    if fam == "team_goals":
        team = "home" if "home" in sel else ("away" if "away" in sel else None)
        direction = "over" if "over" in sel else ("under" if "under" in sel else None)
        line = extract_line(sel)
        if team and direction and line is not None:
            return "team_total", {"team": team, "direction": direction, "line": line}
        m = re.search(r"(home|away).{0,12}(\d+)", sel)
        if m and ("exact" in sel or sel.endswith(m.group(2))):
            return "exact_team_goals", {"team": m.group(1), "goals": int(m.group(2))}
    if fam == "winning_margin":
        return "winning_margin", {"selection": sel}
    if fam == "asian_handicap":
        team = "home" if "home" in sel or sel.startswith("1") else ("away" if "away" in sel or sel.startswith("2") else "home")
        line = extract_line(sel)
        if line is not None:
            return "asian_handicap", {"team": team, "line": line}
    if fam == "european_handicap":
        team = "home" if "home" in sel else ("away" if "away" in sel else "home")
        line = extract_line(sel)
        if line is not None:
            return "european_handicap", {"team": team, "line": line}
    if fam == "clean_sheet":
        team = "home" if "home" in sel else ("away" if "away" in sel else None)
        if team:
            return "win_to_nil", {"team": team}
    if fam in {"result_total", "result_ou"}:
        return classify_raw_market("result/total goals", selection)
    if fam in {"double_chance_total", "dc_total"}:
        return classify_raw_market("double chance total", selection)
    if fam == "goal_parity":
        if "odd" in sel:
            return "goal_parity", {"parity": "odd"}
        if "even" in sel:
            return "goal_parity", {"parity": "even"}
    return None

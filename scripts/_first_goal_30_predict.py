#!/usr/bin/env python3
"""Fetch first-goal-under-30 predictions for 10 WC fixtures."""
import json
import re
import urllib.request

BASE = "https://footballpredictor.it.com"

TARGETS = [
    ("Cape Verde", "Saudi Arabia", ["kap", "cape", "saudi"]),
    ("Uruguay", "Spain", ["uruguay", "spain", "spanien"]),
    ("Egypt", "Iran", ["egypt", "ägypten", "iran"]),
    ("New Zealand", "Belgium", ["new zealand", "neuseeland", "belg"]),
    ("Croatia", "Ghana", ["croat", "kroat", "ghana"]),
    ("Panama", "England", ["panama", "england"]),
    ("Congo DR", "Uzbekistan", ["congo", "kongo", "uzbek"]),
    ("Colombia", "Portugal", ["colomb", "portugal"]),
    ("Jordan", "Argentina", ["jordan", "argent"]),
    ("Algeria", "Austria", ["alger", "austria", "österreich"]),
]


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "first-goal-30-predict/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def match_row(rows: list, home_hints: list, away_hints: list) -> dict | None:
    for row in rows:
        h = (row.get("home_team") or "").lower()
        a = (row.get("away_team") or "").lower()
        home_ok = any(x in h for x in home_hints)
        away_ok = any(x in a for x in away_hints)
        if home_ok and away_ok:
            return row
    return None


def first_goal_under_30(payload: dict) -> dict:
    dm = payload.get("detailed_markets") or {}
    fg = dm.get("first_goal") or {}
    gt = dm.get("goal_timing") or {}
    minute_range = str(fg.get("minute_range") or gt.get("minute_range") or "")
    expected = fg.get("expected_minute") or gt.get("expected_minute")
    team = fg.get("team") or gt.get("team")
    conf = fg.get("confidence") or gt.get("confidence") or payload.get("confidence")

    under_30 = False
    if minute_range:
        under_30 = any(x in minute_range for x in ("0-15", "16-30", "0-30", "1-30", "0-29"))
        if re.search(r"0\s*[-–]\s*30", minute_range):
            under_30 = True
    if expected is not None:
        try:
            under_30 = under_30 or float(expected) <= 30
        except (TypeError, ValueError):
            pass

    probs = fg.get("probabilities") or gt.get("probabilities") or {}
    early_home = early_away = None
    if isinstance(probs, dict):
        early_home = probs.get("home_first") or probs.get("home")
        early_away = probs.get("away_first") or probs.get("away")

    return {
        "team": team,
        "minute_range": minute_range or None,
        "expected_minute": expected,
        "under_30": under_30,
        "confidence": conf,
        "probs": probs,
        "early_home": early_home,
        "early_away": early_away,
        "fg_block": fg,
        "gt_block": gt,
    }


def main() -> None:
    data = get(f"{BASE}/api/matches?competition=world_cup_2026&page_size=80&include_summary=true")
    rows = data.get("matches") or []
    out = []
    for home, away, hints in TARGETS:
        home_hints = [hints[0]] + [h for h in hints if h in norm(home) or norm(home)[:4] in h]
        away_hints = [hints[1] if len(hints) > 1 else hints[-1]] + hints[2:]
        home_hints = list(dict.fromkeys([norm(home)[:5], home.split()[0].lower()] + hints[:2]))
        away_hints = list(dict.fromkeys([norm(away)[:5], away.split()[-1].lower()] + hints[2:]))
        row = match_row(rows, home_hints, away_hints)
        item = {"match": f"{home} vs {away}", "fixture_id": None, "kickoff": None}
        if not row:
            item["error"] = "fixture_not_found"
            out.append(item)
            continue
        fid = row["fixture_id"]
        item["fixture_id"] = fid
        item["kickoff"] = row.get("match_date") or row.get("date")
        item["teams_api"] = f"{row.get('home_team')} vs {row.get('away_team')}"
        try:
            pred = get(f"{BASE}/api/predict/{fid}?competition=world_cup_2026")
        except Exception as exc:
            item["error"] = str(exc)
            out.append(item)
            continue
        fg = first_goal_under_30(pred)
        item["prediction"] = fg
        item["no_bet"] = pred.get("no_bet")
        item["home_team"] = pred.get("home_team") or row.get("home_team")
        item["away_team"] = pred.get("away_team") or row.get("away_team")
        # Decide pick
        team = fg.get("team")
        if not team and fg.get("under_30"):
            eh, ea = fg.get("early_home"), fg.get("early_away")
            try:
                if eh is not None and ea is not None and float(eh) != float(ea):
                    team = item["home_team"] if float(eh) > float(ea) else item["away_team"]
            except (TypeError, ValueError):
                pass
        if not team and fg.get("minute_range"):
            # if only range under 30, use first_goal_team from match_winner lean
            mw = (pred.get("detailed_markets") or {}).get("match_winner") or {}
            sel = mw.get("selection")
            if sel in ("home", "home_win"):
                team = item["home_team"]
            elif sel in ("away", "away_win"):
                team = item["away_team"]
        item["first_goal_under_30_team"] = team
        item["verdict"] = (
            f"{team} (first goal ≤30')"
            if team and fg.get("under_30")
            else (f"{team} (first goal, minute unclear ≤30)" if team else "No early-goal pick / data limited")
        )
        out.append(item)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""First goal under 30' — EGIE timing profiles + production 1X2 context."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

BASE = "https://footballpredictor.it.com"
ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "data" / "egie" / "world_cup" / "team_timing_profiles.json"

MATCHES = [
    ("Cape Verde Islands", "Saudi Arabia", 1489413, "2026-06-27 02:00"),
    ("Uruguay", "Spain", 1489417, "2026-06-27 02:00"),
    ("Egypt", "Iran", 1489414, "2026-06-27 05:00"),
    ("New Zealand", "Belgium", 1489415, "2026-06-27 05:00"),
    ("Croatia", "Ghana", 1489420, "2026-06-27 23:00"),
    ("Panama", "England", 1489422, "2026-06-27 23:00"),
    ("Congo DR", "Uzbekistan", 1539013, "2026-06-28 01:30"),
    ("Colombia", "Portugal", 1489419, "2026-06-28 01:30"),
    ("Jordan", "Argentina", 1489421, "2026-06-28 04:00"),
    ("Algeria", "Austria", 1489418, "2026-06-28 04:00"),
]

ALIASES = {
    "Cape Verde Islands": ["Cape Verde", "Cape Verde Islands", "Kap Verde"],
    "Saudi Arabia": ["Saudi Arabia", "Saudi Arabien"],
    "Spain": ["Spain", "Spanien"],
    "Egypt": ["Egypt", "Ägypten"],
    "New Zealand": ["New Zealand", "Neuseeland"],
    "Congo DR": ["Congo DR", "DR Kongo", "Congo"],
    "Uzbekistan": ["Uzbekistan", "Usbekistan"],
    "Austria": ["Austria", "Österreich"],
    "Argentina": ["Argentina", "Argentinien"],
    "Algeria": ["Algeria", "Algerien"],
}


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "fg30/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def find_team(profiles: dict, name: str) -> dict | None:
    if name in profiles:
        return profiles[name]
    for alias in ALIASES.get(name, [name]):
        if alias in profiles:
            return profiles[alias]
    low = name.lower()
    for key in profiles:
        if key.lower() == low or low in key.lower() or key.lower() in low:
            return profiles[key]
    return None


def early_rate(profile: dict | None) -> float:
    if not profile:
        return 0.15
    dist = (profile.get("scoring_timing_profile") or {}).get("goal_timing_distribution") or {}
    return float(dist.get("0-15") or 0) + float(dist.get("16-30") or 0)


def checkpoint30(profile: dict | None) -> float:
    if not profile:
        return 0.35
    cp = (profile.get("scoring_timing_profile") or {}).get("checkpoint_goal_probability") or {}
    return float(cp.get("30") or 0.35)


def predict_match(home: str, away: str, fid: int, profiles: dict, pred: dict) -> dict:
    hp = find_team(profiles, home)
    ap = find_team(profiles, away)
    home_early = early_rate(hp)
    away_early = early_rate(ap)
    home_cp30 = checkpoint30(hp)
    away_cp30 = checkpoint30(ap)

    probs = pred.get("probabilities") or {}
    try:
        ph = float(probs.get("home_win") or 33)
        pd = float(probs.get("draw") or 33)
        pa = float(probs.get("away_win") or 33)
        if ph > 1:
            ph, pd, pa = ph / 100, pd / 100, pa / 100
    except (TypeError, ValueError):
        ph, pd, pa = 0.33, 0.33, 0.33

    # Strength-weighted early first-goal lean
    home_score_w = home_early * (ph + pd * 0.35) * (1.0 + home_cp30 * 0.5)
    away_score_w = away_early * (pa + pd * 0.35) * (1.0 + away_cp30 * 0.5)
    total_w = max(home_score_w + away_score_w, 1e-6)
    p_home_first = home_score_w / total_w
    p_away_first = away_score_w / total_w

    # Goal before 30' (any team) — blend checkpoints
    p_goal_before_30 = min(
        0.88,
        max(
            0.12,
            (home_early + away_early) * 0.55 + (home_cp30 + away_cp30) * 0.25 + (ph + pa) * 0.15,
        ),
    )

    pick_home = p_home_first >= p_away_first
    team = home if pick_home else away
    conf = round(max(p_home_first, p_away_first) * 100, 1)

    # Minute band from combined early rates
    early_share = home_early + away_early
    if early_share >= 0.55:
        minute_band = "0-15"
    elif early_share >= 0.35:
        minute_band = "16-30"
    else:
        minute_band = "16-30" if p_goal_before_30 >= 0.45 else "31-45+ (low U30)"

    samples_h = (hp or {}).get("scoring_timing_profile", {}).get("samples", 0)
    samples_a = (ap or {}).get("scoring_timing_profile", {}).get("samples", 0)
    data_note = "EGIE WC timing + production 1X2"
    if samples_h < 3 or samples_a < 3:
        data_note += " (limited historical samples)"

    return {
        "first_goal_team_under_30": team,
        "p_home_first": round(p_home_first * 100, 1),
        "p_away_first": round(p_away_first * 100, 1),
        "p_any_goal_before_30": round(p_goal_before_30 * 100, 1),
        "expected_minute_band": minute_band,
        "confidence": conf,
        "model_1x2": {
            "home": round(ph * 100, 1),
            "draw": round(pd * 100, 1),
            "away": round(pa * 100, 1),
        },
        "wc_samples": f"{samples_h}/{samples_a}",
        "note": data_note,
    }


def main() -> None:
    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    rows = []
    for home, away, fid, kickoff in MATCHES:
        try:
            pred = get_json(f"{BASE}/api/predict/{fid}?competition=world_cup_2026")
        except Exception as exc:
            pred = {"probabilities": {}}
            res = {"error": str(exc)}
        else:
            res = predict_match(home, away, fid, profiles, pred)
        rows.append({"home": home, "away": away, "kickoff": kickoff, "fixture_id": fid, **res})
    out_path = ROOT / "data" / "validation" / "_first_goal_30_predictions.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()

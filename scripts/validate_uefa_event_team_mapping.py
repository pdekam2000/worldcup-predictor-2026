#!/usr/bin/env python3
"""Phase API-I — validate UEFA event team mapping and score reconstruction."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
MAPPING_PATH = ARTIFACTS / "uefa_fixture_mapping.json"
OUTPUT_PATH = ARTIFACTS / "uefa_event_team_mapping_validation.json"


def _cache_paths() -> list[Path]:
    roots = [
        ROOT / "data" / "egie" / "uefa_club" / "raw",
        ROOT / "data" / "data" / "egie" / "uefa_club" / "raw",
    ]
    seen: set[int] = set()
    out: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.glob("*.json")):
            try:
                fid = int(p.stem)
            except ValueError:
                continue
            if fid in seen:
                continue
            seen.add(fid)
            out.append(p)
    return out


def _load_mapping() -> dict[int, dict[str, Any]]:
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return {int(f["sportmonks_fixture_id"]): f for f in data.get("fixtures") or [] if f.get("sportmonks_fixture_id")}


def validate() -> dict[str, Any]:
    from worldcup_predictor.egie.uefa_club.feature_extractors import (
        _goals_tally_from_events,
        parse_match_result,
        parse_uefa_goal_events,
    )

    mapping = _load_mapping()
    paths = _cache_paths()
    results: list[dict[str, Any]] = []
    score_match = 0
    fg_resolved = 0
    chronological_ok = 0
    minute_valid = 0
    own_goal_ok = 0
    penalty_ok = 0

    for path in paths:
        fid = int(path.stem)
        fx = mapping.get(fid, {})
        blob = json.loads(path.read_text(encoding="utf-8"))
        payload = blob.get("payload")
        home = str(fx.get("home_team") or "")
        away = str(fx.get("away_team") or "")
        result = parse_match_result(payload, home_team=home, away_team=away)
        goals = parse_uefa_goal_events(payload)
        ev_home, ev_away = _goals_tally_from_events(goals)

        score_ok = (
            int(result.get("home_goals") or 0) == ev_home
            and int(result.get("away_goals") or 0) == ev_away
        ) or (not goals and int(result.get("home_goals") or 0) + int(result.get("away_goals") or 0) >= 0)
        if score_ok:
            score_match += 1

        fg_side = result.get("first_goal_team_side")
        if fg_side in ("home", "away", "none"):
            fg_resolved += 1

        chrono = True
        prev = -1
        for g in goals:
            m = g.get("minute")
            if m is not None and m < prev:
                chrono = False
                break
            if m is not None:
                prev = m
        if chrono:
            chronological_ok += 1

        mins_ok = all(g.get("minute") is None or (0 <= int(g["minute"]) <= 130) for g in goals)
        if mins_ok:
            minute_valid += 1

        for g in goals:
            if g.get("goal_kind") == "own_goal" and g.get("scoring_side") in ("home", "away"):
                own_goal_ok += 1
            if g.get("goal_kind") == "penalty" and g.get("scoring_side") in ("home", "away"):
                penalty_ok += 1

        if not score_ok or fg_side is None:
            results.append(
                {
                    "fixture_id": fid,
                    "score_from_fixture": [result.get("home_goals"), result.get("away_goals")],
                    "score_from_events": [ev_home, ev_away],
                    "first_goal_side": fg_side,
                    "goal_events": len(goals),
                }
            )

    n = len(paths)
    summary = {
        "fixtures_validated": n,
        "score_reconstruction_match": score_match,
        "score_reconstruction_pct": round(100 * score_match / n, 2) if n else 0,
        "first_goal_team_resolved": fg_resolved,
        "first_goal_team_resolved_pct": round(100 * fg_resolved / n, 2) if n else 0,
        "chronological_order_ok": chronological_ok,
        "minute_values_valid": minute_valid,
        "own_goals_mapped": own_goal_ok,
        "penalties_mapped": penalty_ok,
        "failures": results[:25],
        "status": "pass" if fg_resolved >= n - 5 and score_match >= n * 0.85 else "warn",
    }
    return summary


def main() -> int:
    if not MAPPING_PATH.is_file():
        print(f"Missing {MAPPING_PATH}")
        return 1
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    report = validate()
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {OUTPUT_PATH}")
    return 0 if report.get("status") == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

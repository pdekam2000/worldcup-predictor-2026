#!/usr/bin/env python3
"""Live model first-goal predictions for 10 WC fixtures — production pipeline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline

FIXTURES = [
    (1489413, "Cape Verde Islands", "Saudi Arabia", "2026-06-27 02:00"),
    (1489417, "Uruguay", "Spain", "2026-06-27 02:00"),
    (1489414, "Egypt", "Iran", "2026-06-27 05:00"),
    (1489415, "New Zealand", "Belgium", "2026-06-27 05:00"),
    (1489420, "Croatia", "Ghana", "2026-06-27 23:00"),
    (1489422, "Panama", "England", "2026-06-27 23:00"),
    (1539013, "Congo DR", "Uzbekistan", "2026-06-28 01:30"),
    (1489419, "Colombia", "Portugal", "2026-06-28 01:30"),
    (1489421, "Jordan", "Argentina", "2026-06-28 04:00"),
    (1489418, "Algeria", "Austria", "2026-06-28 04:00"),
]


def under_30(minute_range: str | None, expected: int | float | None) -> bool | None:
    if minute_range:
        r = str(minute_range).lower()
        if any(x in r for x in ("0-15", "16-30", "0-30", "1-30")):
            return True
        if any(x in r for x in ("31-45", "46-60", "61-75", "76-90", "90")):
            return False
    if expected is not None:
        try:
            return float(expected) <= 30
        except (TypeError, ValueError):
            pass
    return None


def main() -> int:
    settings = get_settings()
    pipeline = PredictPipeline(settings, locale="en", competition_key="world_cup_2026")
    rows = []
    for fid, home, away, kickoff in FIXTURES:
        result = pipeline.run(fixture_id=fid)
        row = {
            "fixture_id": fid,
            "match": f"{home} vs {away}",
            "kickoff": kickoff,
            "pipeline_ok": result.success,
        }
        if not result.success:
            row["error"] = "; ".join(
                f"{a.agent_name}: {a.message}" for a in result.agent_results if not a.success
            )
            rows.append(row)
            continue
        p = result.prediction
        fg = p.first_goal
        minute_range = fg.minute_range
        u30 = under_30(minute_range, getattr(fg, "expected_minute", None))
        row.update(
            {
                "home_team": p.match_name.split(" vs ")[0] if " vs " in p.match_name else home,
                "away_team": p.match_name.split(" vs ")[1] if " vs " in p.match_name else away,
                "first_goal_team": fg.team,
                "first_goal_player": fg.player,
                "first_goal_minute_range": minute_range,
                "first_goal_under_30": u30,
                "prediction_1x2": p.one_x_two.selection,
                "confidence": round(float(p.confidence_score or 0), 1),
                "no_bet": bool(p.no_bet_flag),
                "scoreline": f"{p.scoreline.home_goals}-{p.scoreline.away_goals}" if p.scoreline else None,
                "engine": (p.metadata or {}).get("engine_version") or (p.metadata or {}).get("pipeline_version"),
                "source": "PredictPipeline_live",
            }
        )
        rows.append(row)
    out = ROOT / "data" / "validation" / "live_model_first_goal_10.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(out.as_posix())
    for r in rows:
        print(
            r.get("match"),
            "->",
            r.get("first_goal_team"),
            r.get("first_goal_minute_range"),
            "U30=",
            r.get("first_goal_under_30"),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

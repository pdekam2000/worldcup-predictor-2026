"""Phase 8 — Sportmonks consumption layer validation (no live API required)."""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    from dataclasses import replace

    from worldcup_predictor.domain.intelligence import InjuryReport, MatchIntelligenceReport, TeamIntelligence
    from worldcup_predictor.providers.sportmonks_consumption import (
        apply_sportmonks_consumption,
        map_sportmonks_payload_fields,
        normalize_sportmonks_fixture,
    )

    checks: list[tuple[str, bool]] = []

    sample = {
        "id": 999001,
        "participants": [
            {"id": 10, "name": "Mexico", "meta": {"location": "home"}},
            {"id": 11, "name": "South Korea", "meta": {"location": "away"}},
        ],
        "sidelined": [
            {
                "participant_id": 10,
                "sideline": {
                    "player_id": 501,
                    "player_name": "Test Striker",
                    "category": "injury",
                    "reason": "knee",
                    "player": {"name": "Test Striker"},
                },
            }
        ],
        "lineups": [
            {
                "team_id": 10,
                "player_id": 501,
                "player_name": "Test Striker",
                "position_id": 27,
                "type_id": 11,
                "jersey_number": 9,
            }
        ],
        "statistics": [
            {
                "participant_id": 10,
                "type": {"name": "Expected Goals"},
                "data": {"value": 1.35},
            }
        ],
        "scores": [{"description": "CURRENT", "score": {"goals": 0}}],
    }

    field_map = map_sportmonks_payload_fields(sample)
    checks.append(("field_map_participants", field_map["has_participants"]))
    checks.append(("field_map_sidelined", field_map["has_sidelined"]))

    normalized = normalize_sportmonks_fixture(
        sample,
        home_team_name="Mexico",
        away_team_name="South Korea",
    )
    checks.append(("normalized_home_injuries", len(normalized["home_injuries"]) == 1))
    checks.append(("normalized_lineups", len(normalized["lineups_api"]) >= 1))
    checks.append(("normalized_xg_home", normalized["xg"].get("home") == 1.35))

    base = MatchIntelligenceReport(
        fixture_id=1489388,
        fixture=None,
        home_team=TeamIntelligence(
            team_name="Mexico",
            team_id=10,
            injuries=InjuryReport(team_name="Mexico", team_id=10, players=[], available=False),
        ),
        away_team=TeamIntelligence(
            team_name="South Korea",
            team_id=11,
            injuries=InjuryReport(team_name="South Korea", team_id=11, players=[], available=False),
        ),
        missing_data=["injuries", "lineups"],
        provider_metadata={"sportmonks_fixture": sample},
    )

    consumed = apply_sportmonks_consumption(base)
    checks.append(("gap_fill_home_injuries", len(consumed.home_team.injuries.players) == 1))
    checks.append(("gap_fill_lineups", not consumed.missing_data or "lineups" not in consumed.missing_data))
    checks.append(
        ("supplemental_sportmonks",
         (consumed.supplemental_sources or {}).get("sportmonks", {}).get("consumed") is True),
    )

    # Never overwrite stronger API-Football injuries
    strong = replace(
        base,
        home_team=replace(
            base.home_team,
            injuries=InjuryReport(
                team_name="Mexico",
                team_id=10,
                players=[{"player": {"id": 1, "name": "API Player"}, "team": {"name": "Mexico"}}],
                available=True,
                source="live",
            ),
        ),
    )
    kept = apply_sportmonks_consumption(strong)
    checks.append(
        ("no_overwrite_injuries",
         kept.home_team.injuries.players[0]["player"]["name"] == "API Player"),
    )

    # Match Center still has no predict import in frontend (static grep)
    mc = Path(__file__).resolve().parents[1] / "base44-d" / "src" / "pages" / "MatchCenter.jsx"
    mc_text = mc.read_text(encoding="utf-8")
    checks.append(("match_center_no_predict", "runPrediction" not in mc_text and "fetchCachedPrediction" not in mc_text))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"\n{len(failed)} check(s) failed")
        return 1
    print(f"\nAll {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Product UX phase validation — home, group browser, first goal, access."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_modules_import() -> None:
    importlib.import_module("worldcup_predictor.ui.user_home_dashboard")
    importlib.import_module("worldcup_predictor.ui.worldcup_group_browser")
    importlib.import_module("worldcup_predictor.intelligence.first_goal_intelligence_v2")
    importlib.import_module("worldcup_predictor.ui.first_goal_display")


def test_user_nav_has_game_search() -> None:
    from worldcup_predictor.ui.app_shell import USER_MODE_V2_NAV_ITEMS

    keys = [k for k, _, _ in USER_MODE_V2_NAV_ITEMS]
    assert "team_search" in keys
    assert "match_center" in keys


def test_group_browser_constants() -> None:
    from worldcup_predictor.ui.worldcup_group_browser import GROUP_KEYS

    assert len(GROUP_KEYS) == 8
    assert GROUP_KEYS[0] == "Group A"


def test_first_goal_engine_fallback() -> None:
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport, TeamIntelligence
    from worldcup_predictor.intelligence.first_goal_intelligence_v2 import build_first_goal_intelligence_v2

    report = MatchIntelligenceReport(
        fixture_id=1,
        fixture=None,
        home_team=TeamIntelligence(team_name="Home FC"),
        away_team=TeamIntelligence(team_name="Away FC"),
    )
    result = build_first_goal_intelligence_v2(report)
    assert result.first_goal_team in {"home", "away", "no_goal", "unknown"}
    assert result.first_goal_minute_band in {
        "0-15", "16-30", "31-45", "46-60", "61-75", "76-90", "no_goal", "unknown"
    }
    assert result.player_data_unavailable is True or result.likely_first_goal_scorers == [] or all(
        c.position not in {"G", "GK"} for c in result.likely_first_goal_scorers
    )
    payload = result.to_dict()
    assert "likely_scorers" in payload
    assert "data_available" in payload


def test_fixture_header_fields() -> None:
    from worldcup_predictor.ui.fixture_display import format_group_stage

    class _Fx:
        group = "Group A"
        round = "Group Stage - 1"
        stage = "Group Stage - 1"
        home_team = "A"
        away_team = "B"
        city = "Miami"
        country = "USA"

    assert "Group" in format_group_stage(_Fx())


def test_developer_mode_hidden_from_public_nav() -> None:
    from worldcup_predictor.ui.app_shell import USER_MODE_V2_NAV_ITEMS, DEV_NAV_ITEMS

    user_keys = {k for k, _, _ in USER_MODE_V2_NAV_ITEMS}
    dev_keys = {k for k, _, _ in DEV_NAV_ITEMS}
    assert "admin_entitlements" not in user_keys
    assert "specialists" not in user_keys


def main() -> int:
    tests = [
        test_modules_import,
        test_user_nav_has_game_search,
        test_group_browser_constants,
        test_first_goal_engine_fallback,
        test_fixture_header_fields,
        test_developer_mode_hidden_from_public_nav,
    ]
    for fn in tests:
        fn()
        print(f"PASS: {fn.__name__}")
    print("\nProduct UX validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

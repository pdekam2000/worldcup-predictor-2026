from __future__ import annotations

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().with_name('bootstrap_path.py')))

import importlib
import sys
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE_ID = 1489374
REPORT_PATH = ROOT / "reports" / "api_sports_deep_integration_report.md"


def test_report_exists() -> None:
    assert REPORT_PATH.is_file()
    text = REPORT_PATH.read_text(encoding="utf-8")
    assert "players/topscorers" in text
    assert "fixtures?live=all" in text


def test_client_phase53_methods() -> None:
    from worldcup_predictor.clients.api_football import ApiFootballClient

    for name in (
        "get_top_scorers",
        "get_fixture_players",
        "get_team_squad",
        "get_live_fixtures",
        "get_predictions",
    ):
        assert hasattr(ApiFootballClient, name), f"Missing {name}"


def test_deep_integration_module() -> None:
    importlib.import_module("worldcup_predictor.integrations.api_sports_deep_data")
    from worldcup_predictor.integrations.api_sports_deep_data import (
        attach_api_sports_deep_data,
        normalize_top_scorers,
    )

    rows = normalize_top_scorers([])
    assert rows == []
    assert callable(attach_api_sports_deep_data)


def test_scorer_gk_excluded() -> None:
    from worldcup_predictor.prediction.player_position_utils import apply_position_score

    assert apply_position_score(60.0, "G") is None
    assert apply_position_score(60.0, "F") == 60.0


def test_live_schedule_method() -> None:
    from worldcup_predictor.schedule.worldcup_schedule_service import WorldCupScheduleService

    assert hasattr(WorldCupScheduleService, "get_live_fixtures_from_api")


def test_cli_first_goal() -> None:
    from worldcup_predictor.cli.commands import run_first_goal_command

    buf = StringIO()
    assert run_first_goal_command(fixture_id=FIXTURE_ID, locale="en", stream=buf) == 0
    out = buf.getvalue().lower()
    assert "manuel neuer" not in out or '"player_name": "manuel neuer"' not in out


def test_cli_predict_unchanged() -> None:
    from worldcup_predictor.cli.commands import run_predict_command

    buf = StringIO()
    assert run_predict_command(fixture_id=FIXTURE_ID, locale="en", stream=buf) == 0


def test_cli_export() -> None:
    from worldcup_predictor.cli.commands import run_export_report_command

    buf = StringIO()
    assert run_export_report_command(fixture_id=FIXTURE_ID, locale="en", stream=buf) == 0


def test_hall_of_fame() -> None:
    from worldcup_predictor.cli.commands import run_hall_of_fame_command

    buf = StringIO()
    assert run_hall_of_fame_command(locale="en", stream=buf) == 0


def main() -> int:
    tests = [
        test_report_exists,
        test_client_phase53_methods,
        test_deep_integration_module,
        test_scorer_gk_excluded,
        test_live_schedule_method,
        test_cli_first_goal,
        test_cli_predict_unchanged,
        test_cli_export,
        test_hall_of_fame,
    ]
    for fn in tests:
        fn()
        print(f"PASS: {fn.__name__}")
    print("\nPhase 53 validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

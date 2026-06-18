from __future__ import annotations

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().with_name('bootstrap_path.py')))

import importlib
import json
import sys
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_modules_import() -> None:
    importlib.import_module("worldcup_predictor.performance.hall_of_fame")
    importlib.import_module("worldcup_predictor.ui.hall_of_fame_page")


def test_user_nav_includes_hall_of_fame() -> None:
    from worldcup_predictor.ui.app_shell import USER_MODE_V2_NAV_ITEMS

    keys = [k for k, _, _ in USER_MODE_V2_NAV_ITEMS]
    assert "hall_of_fame" in keys
    assert "accuracy" not in keys  # dev-only


def test_report_schema() -> None:
    from worldcup_predictor.performance.hall_of_fame import build_hall_of_fame_report

    report = build_hall_of_fame_report()
    payload = report.to_dict()
    for key in (
        "total_predictions",
        "verified_predictions",
        "all_time",
        "last_30_days",
        "last_100",
        "calibration_buckets",
        "best_tournaments",
        "best_agents",
    ):
        assert key in payload


def test_cli_hall_of_fame() -> None:
    from worldcup_predictor.cli.commands import run_hall_of_fame_command

    buf = StringIO()
    code = run_hall_of_fame_command(locale="en", stream=buf)
    assert code == 0
    out = buf.getvalue()
    assert "Hall of Fame" in out
    assert '"all_time"' in out
    assert '"last_30_days"' in out
    assert '"last_100"' in out


def main() -> int:
    for fn in (
        test_modules_import,
        test_user_nav_includes_hall_of_fame,
        test_report_schema,
        test_cli_hall_of_fame,
    ):
        fn()
        print(f"PASS: {fn.__name__}")
    print("\nHall of Fame validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

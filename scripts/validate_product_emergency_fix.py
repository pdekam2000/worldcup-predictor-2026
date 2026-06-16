"""Emergency product fix validation — navigation, group browser, bias audit artifacts."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_nav_keys() -> None:
    from worldcup_predictor.ui.app_shell import USER_MODE_V2_NAV_ITEMS
    from worldcup_predictor.ui.gui_mode_v2 import pages_for_mode, primary_nav_for_mode

    keys = [k for k, _, _ in USER_MODE_V2_NAV_ITEMS]
    required = [
        "home",
        "predict",
        "team_search",
        "match_center",
        "finished_results",
        "professional_reports",
        "hall_of_fame",
        "upgrade",
        "settings",
    ]
    for key in required:
        assert key in keys, f"Missing nav key: {key}"
    user_pages = pages_for_mode(developer_mode=False)
    assert "finished_results" in user_pages
    assert "match_center" in user_pages
    primary = [k for k, _, _ in primary_nav_for_mode(developer_mode=False)]
    assert primary.count("match_center") == 1


def test_modules_import() -> None:
    importlib.import_module("worldcup_predictor.ui.finished_results_page")
    importlib.import_module("worldcup_predictor.ui.worldcup_group_browser")
    importlib.import_module("worldcup_predictor.ui.gui_mode_v2")


def test_group_browser_helpers() -> None:
    from worldcup_predictor.ui.worldcup_group_browser import GROUP_KEYS, _badge_html, _match_row_class

    assert len(GROUP_KEYS) == 8

    class _Fx:
        status = "FT"
        home_team = "A"
        away_team = "B"
        home_goals = 2
        away_goals = 1

    assert _match_row_class(_Fx()) == "match-row-finished"
    html = _badge_html(_Fx(), "en")
    assert "match-badge-finished" in html


def test_scoring_pick_over_under() -> None:
    from worldcup_predictor.prediction.scoring_engine import ScoringEngine

    engine = ScoringEngine()
    sel, prob = engine._pick_over_under(2.48, low_confidence=True)
    assert sel in {"over_2_5", "under_2_5"}
    assert prob <= 0.62
    _, prob_high = engine._pick_over_under(3.1, low_confidence=False)
    assert prob_high > prob


def test_audit_reports_exist() -> None:
    bias = ROOT / "reports" / "prediction_bias_audit.md"
    dist = ROOT / "reports" / "prediction_distribution_check.md"
    assert bias.is_file(), "Missing reports/prediction_bias_audit.md"
    assert dist.is_file(), "Missing reports/prediction_distribution_check.md"


def test_cli_smoke() -> None:
    for cmd in [
        [sys.executable, "main.py", "predict", "--fixture-id", "1489374", "--locale", "en"],
    ]:
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, result.stderr or result.stdout


def main() -> int:
    tests = [
        test_modules_import,
        test_nav_keys,
        test_group_browser_helpers,
        test_scoring_pick_over_under,
        test_audit_reports_exist,
        test_cli_smoke,
    ]
    failed = 0
    for test in tests:
        name = test.__name__
        try:
            test()
            print(f"PASS {name}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {name}: {exc}")
    print(json.dumps({"failed": failed, "total": len(tests)}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase 51 validation — Tournament UX V3 + First Goal Intelligence visibility."""

from __future__ import annotations

import importlib
import json
import sys
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE_ID = 1489374


def test_modules() -> None:
    importlib.import_module("worldcup_predictor.ui.user_home_dashboard")
    importlib.import_module("worldcup_predictor.ui.worldcup_group_browser")
    importlib.import_module("worldcup_predictor.intelligence.first_goal_intelligence_v2")
    importlib.import_module("worldcup_predictor.ui.first_goal_display")
    importlib.import_module("worldcup_predictor.ui.fixture_display")


def test_home_dashboard_today_only() -> None:
    src = (ROOT / "worldcup_predictor" / "ui" / "user_home_dashboard.py").read_text(encoding="utf-8")
    assert "_today_fixtures" in src
    assert "card.venue" in src or "card.venue" in src


def test_group_browser_standings() -> None:
    src = (ROOT / "worldcup_predictor" / "ui" / "worldcup_group_browser.py").read_text(encoding="utf-8")
    assert "_render_group_standings" in src
    assert "GROUP_KEYS" in src
    assert len(__import__("worldcup_predictor.ui.worldcup_group_browser", fromlist=["GROUP_KEYS"]).GROUP_KEYS) == 8


def test_manual_search_label() -> None:
    from worldcup_predictor.ui.gui_i18n import gui_t

    assert "manual" in gui_t("group_browser.manual_search", "en").lower()


def test_first_goal_phase51_schema() -> None:
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport, TeamIntelligence
    from worldcup_predictor.intelligence.first_goal_intelligence_v2 import build_first_goal_intelligence_v2

    report = MatchIntelligenceReport(
        fixture_id=1,
        fixture=None,
        home_team=TeamIntelligence(team_name="Home FC"),
        away_team=TeamIntelligence(team_name="Away FC"),
    )
    result = build_first_goal_intelligence_v2(report)
    payload = result.to_dict()
    required = {
        "first_goal_team",
        "first_goal_minute_band",
        "likely_scorers",
        "confidence",
        "data_available",
        "risk_flags",
        "summary",
    }
    assert required.issubset(payload.keys())
    assert isinstance(payload["likely_scorers"], list)


def test_developer_mode_gated() -> None:
    from worldcup_predictor.ui.app_shell import DEV_NAV_ITEMS, USER_MODE_V2_NAV_ITEMS

    user_keys = {k for k, _, _ in USER_MODE_V2_NAV_ITEMS}
    dev_keys = {k for k, _, _ in DEV_NAV_ITEMS}
    assert "admin_entitlements" not in user_keys
    assert "specialists" not in user_keys
    assert dev_keys  # dev nav exists but separate


def test_explainability_first_goal() -> None:
    src = (
        ROOT / "worldcup_predictor" / "explainability" / "prediction_explainability_engine.py"
    ).read_text(encoding="utf-8")
    assert "first_goal_intelligence_v2" in src


def test_fixture_header_render() -> None:
    from worldcup_predictor.ui.fixture_display import render_fixture_summary_panel

    assert callable(render_fixture_summary_panel)


def test_cli_first_goal_smoke() -> None:
    from worldcup_predictor.cli.commands import run_first_goal_command

    buf = StringIO()
    code = run_first_goal_command(fixture_id=FIXTURE_ID, locale="en", stream=buf)
    assert code == 0
    out = buf.getvalue()
    assert "First Goal Intelligence V2" in out
    assert "likely_scorers" in out or "first_goal_team" in out


def test_cli_predict_attaches_fg() -> None:
    from worldcup_predictor.cli.commands import run_predict_command

    buf = StringIO()
    code = run_predict_command(fixture_id=FIXTURE_ID, locale="en", stream=buf)
    assert code == 0


def test_cli_export_report_fg_section() -> None:
    from worldcup_predictor.cli.commands import run_export_report_command

    buf = StringIO()
    code = run_export_report_command(fixture_id=FIXTURE_ID, locale="en", stream=buf)
    assert code == 0
    out = buf.getvalue()
    assert ".json" in out
    json_line = next(line for line in out.splitlines() if "JSON:" in line)
    json_path = Path(json_line.split("JSON:", 1)[1].strip())
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    pred = payload.get("prediction") or {}
    assert pred.get("first_goal_team") or pred.get("first_goal_minute_band")
    assert pred.get("first_goal_confidence") is not None


def main() -> int:
    tests = [
        test_modules,
        test_home_dashboard_today_only,
        test_group_browser_standings,
        test_manual_search_label,
        test_first_goal_phase51_schema,
        test_developer_mode_gated,
        test_explainability_first_goal,
        test_fixture_header_render,
        test_cli_first_goal_smoke,
        test_cli_predict_attaches_fg,
        test_cli_export_report_fg_section,
    ]
    for fn in tests:
        fn()
        print(f"PASS: {fn.__name__}")
    print("\nPhase 51 validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

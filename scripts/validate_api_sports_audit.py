"""API-Sports usage audit + First Goal goalkeeper exclusion validation."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE_ID = 1489374
AUDIT_PATH = ROOT / "reports" / "api_sports_usage_audit.md"
GOALKEEPER_NAMES = {"manuel neuer", "neuer"}


def test_audit_report_exists() -> None:
    assert AUDIT_PATH.is_file(), f"Missing audit report: {AUDIT_PATH}"
    text = AUDIT_PATH.read_text(encoding="utf-8")
    assert "Fixtures by ID" in text or "fixtures?id" in text.lower()
    assert "Phase 52" in text
    assert "players/topscorers" in text or "top scorers" in text.lower()


def test_client_core_endpoints_implemented() -> None:
    from worldcup_predictor.clients.api_football import ApiFootballClient

    client = ApiFootballClient.__dict__
    required = [
        "get_fixture_by_id",
        "get_fixture_events",
        "get_fixture_statistics",
        "get_fixture_lineups",
        "get_injuries",
        "get_odds",
        "get_standings",
        "get_team_statistics",
        "get_head_to_head",
    ]
    for name in required:
        assert name in client, f"Missing client method: {name}"


def test_scorer_position_filter_unit() -> None:
    from worldcup_predictor.prediction.scorer_candidates import (
        _apply_position_score,
        _is_goalkeeper,
    )

    assert _is_goalkeeper("G")
    assert _is_goalkeeper("GK")
    assert _apply_position_score(60.0, "G") is None
    assert _apply_position_score(60.0, "F") == 60.0
    assert _apply_position_score(60.0, "D") is not None
    assert _apply_position_score(60.0, "") is not None


def test_first_goal_cli_no_goalkeeper() -> None:
    from worldcup_predictor.cli.commands import run_first_goal_command

    buf = StringIO()
    code = run_first_goal_command(fixture_id=FIXTURE_ID, locale="en", stream=buf)
    assert code == 0
    out = buf.getvalue().lower()
    for name in GOALKEEPER_NAMES:
        assert name not in out or "goalkeeper" in out, f"Goalkeeper {name} found in scorer output"
    # Explicit check: Neuer must not be a scorer candidate
    assert '"player_name": "manuel neuer"' not in out
    assert '"player": "manuel neuer"' not in out


def test_predict_cli_smoke() -> None:
    from worldcup_predictor.cli.commands import run_predict_command

    buf = StringIO()
    code = run_predict_command(fixture_id=FIXTURE_ID, locale="en", stream=buf)
    assert code == 0


def main() -> int:
    tests = [
        test_audit_report_exists,
        test_client_core_endpoints_implemented,
        test_scorer_position_filter_unit,
        test_first_goal_cli_no_goalkeeper,
        test_predict_cli_smoke,
    ]
    for fn in tests:
        fn()
        print(f"PASS: {fn.__name__}")
    print("\nAPI-Sports audit validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

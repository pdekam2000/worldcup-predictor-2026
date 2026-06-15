"""Priority stabilization validation — run: python scripts/validate_stabilization.py"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["PUBLIC_ACCESS_ENABLED"] = "true"
os.environ["PUBLIC_ACCESS_CODE"] = "stabilize-code"
os.environ["FREE_DAILY_PREDICTION_LIMIT"] = "2"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin-secret"
os.environ["THE_ODDS_API_KEY"] = "test-odds-key"


def test_shared_access_code_login() -> None:
    import streamlit as st

    from worldcup_predictor.access.identity import login_with_invite, logout_user
    from worldcup_predictor.access.public_guard import blocks_prediction_actions

    if hasattr(st.session_state, "clear"):
        st.session_state.clear()

    assert blocks_prediction_actions() is True

    user, err = login_with_invite(identity="alice", access_code="wrong")
    assert user is None and err == "access.invalid_access_code"

    user, err = login_with_invite(identity="alice", access_code="stabilize-code")
    assert user is not None and err is None
    assert blocks_prediction_actions() is False

    from worldcup_predictor.access.prediction_gate import preview_prediction_quota

    quota = preview_prediction_quota()
    assert quota.daily_limit == 2
    assert quota.remaining is not None
    logout_user()


def test_game_search_in_user_nav() -> None:
    from worldcup_predictor.access.admin_auth import developer_only_page_keys
    from worldcup_predictor.ui.app_shell import LEGACY_USER_NAV_ITEMS, USER_MODE_V2_NAV_ITEMS
    from worldcup_predictor.ui.gui_mode_v2 import pages_for_mode, primary_nav_for_mode

    user_keys = [k for k, _, _ in USER_MODE_V2_NAV_ITEMS]
    assert "team_search" in user_keys
    assert "team_search" not in [k for k, _, _ in LEGACY_USER_NAV_ITEMS]
    assert "team_search" not in developer_only_page_keys()
    assert "team_search" in pages_for_mode(developer_mode=False)
    assert "team_search" in [k for k, _, _ in primary_nav_for_mode(developer_mode=False)]


def test_fixture_summary_panel() -> None:
    from worldcup_predictor.ui.fixture_display import render_fixture_summary_panel

    assert callable(render_fixture_summary_panel)


def test_developer_mode_admin_only() -> None:
    import streamlit as st

    from worldcup_predictor.access.admin_auth import is_admin_session, login_admin, logout_admin
    from worldcup_predictor.ui.gui_mode_v2 import is_developer_mode

    if hasattr(st.session_state, "clear"):
        st.session_state.clear()
    st.session_state["gui_mode"] = "developer"
    assert is_developer_mode() is False

    assert login_admin("admin", "admin-secret")
    assert is_admin_session()
    st.session_state["gui_mode"] = "developer"
    assert is_developer_mode() is True
    logout_admin()
    assert is_developer_mode() is False


def test_odds_api_guard_blocks_force_at_daily_limit() -> None:
    """Refresh-style guard: hard daily limit blocks even admin force refresh."""
    from worldcup_predictor.providers.odds_api_credit import guard as guard_mod
    from worldcup_predictor.providers.odds_api_credit import repository as repo_mod
    from worldcup_predictor.config.settings import get_settings
    from datetime import datetime, timezone
    from worldcup_predictor.domain.fixture import Fixture
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport, TeamIntelligence

    db = Path(tempfile.gettempdir()) / f"stab_{uuid.uuid4().hex}.db"
    os.environ["FOOTBALL_DB_PATH"] = str(db)
    repo_mod._repo = None
    try:
        repo = repo_mod.get_odds_api_repository()
        for i in range(16):
            repo.record_usage(endpoint="sports/x/odds", fixture_id=i, credits_used=1, source="validation")

        home = TeamIntelligence(team_name="A", team_id=1)
        away = TeamIntelligence(team_name="B", team_id=2)
        report = MatchIntelligenceReport(fixture_id=1, fixture=None, home_team=home, away_team=away)
        fixture = Fixture(
            id=1,
            competition_key="world_cup_2026",
            home_team="A",
            away_team="B",
            kickoff_utc=datetime.now(timezone.utc),
            venue="TBD",
            stage="Group",
            league_id=1,
            season=2026,
        )
        decision = guard_mod.evaluate_odds_api_call(report, fixture, get_settings(), force=True)
        assert not decision.allowed
        assert decision.reason == "daily_hard_limit_exceeded"
    finally:
        repo_mod._repo = None
        try:
            db.unlink()
        except OSError:
            pass


def test_public_access_code_from_env() -> None:
    from worldcup_predictor.access.config import public_access_code, public_access_enabled

    assert public_access_enabled() is True
    assert public_access_code() == "stabilize-code"


def main() -> int:
    tests = [
        test_public_access_code_from_env,
        test_shared_access_code_login,
        test_game_search_in_user_nav,
        test_fixture_summary_panel,
        test_developer_mode_admin_only,
        test_odds_api_guard_blocks_force_at_daily_limit,
    ]
    for fn in tests:
        fn()
        print(f"PASS: {fn.__name__}")
    print("\nStabilization validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

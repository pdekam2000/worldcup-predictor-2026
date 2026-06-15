"""Validate Phase 49 access + User Mode UX fixes (A–E)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["PUBLIC_ACCESS_ENABLED"] = "true"
os.environ["PUBLIC_ACCESS_CODE"] = "test-invite-code"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "test123"


def test_config_reads_env() -> None:
    from worldcup_predictor.access.config import public_access_enabled, public_access_config_debug

    assert public_access_enabled() is True
    dbg = public_access_config_debug()
    assert "PUBLIC_ACCESS_ENABLED = true" in dbg


def test_user_nav_includes_game_search() -> None:
    from worldcup_predictor.ui.app_shell import LEGACY_USER_NAV_ITEMS, USER_MODE_V2_NAV_ITEMS

    user_keys = [k for k, _, _ in USER_MODE_V2_NAV_ITEMS]
    legacy_keys = [k for k, _, _ in LEGACY_USER_NAV_ITEMS]
    required = [
        "home",
        "predict",
        "team_search",
        "match_center",
        "professional_reports",
        "upgrade",
        "settings",
    ]
    for key in required:
        assert key in user_keys, f"{key} missing from USER_MODE_V2_NAV_ITEMS"
    assert "team_search" not in legacy_keys


def test_blocks_prediction_when_anonymous() -> None:
    from worldcup_predictor.access.public_guard import blocks_prediction_actions

    assert blocks_prediction_actions() is True


def test_registered_user_not_blocked() -> None:
    import streamlit as st

    from worldcup_predictor.access.identity import init_access_session, login_with_invite, logout_user
    from worldcup_predictor.access.public_guard import blocks_prediction_actions

    if not hasattr(st, "session_state"):
        st.session_state = {}  # type: ignore[attr-defined]
    elif hasattr(st.session_state, "clear"):
        st.session_state.clear()

    init_access_session()
    user, err = login_with_invite(email="phase49-test@example.com", access_code="test-invite-code")
    assert user is not None and err is None
    assert blocks_prediction_actions() is False
    logout_user()


def test_developer_only_excludes_team_search() -> None:
    from worldcup_predictor.access.admin_auth import developer_only_page_keys

    assert "team_search" not in developer_only_page_keys()


def test_fixture_summary_panel_import() -> None:
    from worldcup_predictor.ui.fixture_display import render_fixture_summary_panel

    assert callable(render_fixture_summary_panel)


def main() -> int:
    tests = [
        test_config_reads_env,
        test_user_nav_includes_game_search,
        test_blocks_prediction_when_anonymous,
        test_registered_user_not_blocked,
        test_developer_only_excludes_team_search,
        test_fixture_summary_panel_import,
    ]
    for fn in tests:
        fn()
        print(f"PASS: {fn.__name__}")
    print("\nAll Phase 49 UX/access checks PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

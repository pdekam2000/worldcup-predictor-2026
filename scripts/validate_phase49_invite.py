"""Validate Phase 49 shared invite-code login."""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["PUBLIC_ACCESS_ENABLED"] = "true"
os.environ["PUBLIC_ACCESS_CODE"] = "my-private-code"
os.environ["FREE_DAILY_PREDICTION_LIMIT"] = "2"
os.environ["ADMIN_USERNAME"] = "pedram"
os.environ["ADMIN_PASSWORD"] = "admin-secret"


def _fresh_repo():
    db = Path(tempfile.gettempdir()) / f"phase49_invite_{uuid.uuid4().hex}.db"
    os.environ["ACCESS_DB_PATH"] = str(db)
    import worldcup_predictor.access.repository as repo_mod

    repo_mod._repo_singleton = None
    return db, repo_mod


def test_no_access_code_blocked() -> None:
    import streamlit as st

    from worldcup_predictor.access.identity import login_with_invite

    if hasattr(st.session_state, "clear"):
        st.session_state.clear()
    user, err = login_with_invite(email="user@example.com", access_code="")
    assert user is None
    assert err == "access.access_code_required"


def test_wrong_access_code_blocked() -> None:
    import streamlit as st

    from worldcup_predictor.access.identity import login_with_invite

    if hasattr(st.session_state, "clear"):
        st.session_state.clear()
    user, err = login_with_invite(email="user@example.com", access_code="wrong-code")
    assert user is None
    assert err == "access.invalid_access_code"


def test_correct_access_code_login() -> None:
    import streamlit as st

    from worldcup_predictor.access.identity import is_registered_user, login_with_invite

    db, repo_mod = _fresh_repo()
    try:
        if hasattr(st.session_state, "clear"):
            st.session_state.clear()
        user, err = login_with_invite(email="user@example.com", access_code="my-private-code")
        assert err is None
        assert user is not None
        assert user.email == "user@example.com"
        assert is_registered_user()
    finally:
        repo_mod._repo_singleton = None
        try:
            db.unlink()
        except OSError:
            pass


def test_quota_after_login() -> None:
    import streamlit as st

    from worldcup_predictor.access.identity import login_with_invite
    from worldcup_predictor.access.prediction_gate import acquire_prediction_slot, preview_prediction_quota

    db, repo_mod = _fresh_repo()
    try:
        if hasattr(st.session_state, "clear"):
            st.session_state.clear()
        user, _ = login_with_invite(email="quota@example.com", access_code="my-private-code")
        assert user is not None
        preview = preview_prediction_quota()
        assert preview.allowed
        assert preview.daily_limit == 2
        assert preview.remaining == 2

        for i in range(2):
            gate = acquire_prediction_slot()
            assert gate.allowed, f"prediction {i + 1} should succeed"

        gate3 = acquire_prediction_slot()
        assert not gate3.allowed
        assert gate3.show_upgrade
    finally:
        repo_mod._repo_singleton = None
        try:
            db.unlink()
        except OSError:
            pass


def test_admin_login_still_works() -> None:
    from worldcup_predictor.access.admin_auth import (
        admin_credentials,
        login_admin,
        verify_admin_credentials,
    )

    creds = admin_credentials()
    assert creds == ("pedram", "admin-secret")
    assert verify_admin_credentials("pedram", "admin-secret")
    assert not verify_admin_credentials("pedram", "wrong")

    import streamlit as st

    if hasattr(st.session_state, "clear"):
        st.session_state.clear()
    assert login_admin("pedram", "admin-secret")


def main() -> int:
    tests = [
        test_no_access_code_blocked,
        test_wrong_access_code_blocked,
        test_correct_access_code_login,
        test_quota_after_login,
        test_admin_login_still_works,
    ]
    for fn in tests:
        fn()
        print(f"PASS: {fn.__name__}")
    print("\nPhase 49 invite-code validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

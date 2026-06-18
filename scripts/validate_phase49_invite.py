from __future__ import annotations

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().with_name('bootstrap_path.py')))

import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["PUBLIC_ACCESS_ENABLED"] = "true"
os.environ["PUBLIC_ACCESS_CODE"] = "your-shared-code"
os.environ["FREE_DAILY_PREDICTION_LIMIT"] = "2"
os.environ["ADMIN_USERNAME"] = "pedram"
os.environ["ADMIN_PASSWORD"] = "admin-secret"

SHARED_CODE = "your-shared-code"


def _fresh_repo():
    db = Path(tempfile.gettempdir()) / f"phase49_invite_{uuid.uuid4().hex}.db"
    os.environ["ACCESS_DB_PATH"] = str(db)
    import worldcup_predictor.access.repository as repo_mod

    repo_mod._repo_singleton = None
    return db, repo_mod


def _clear_session() -> None:
    import streamlit as st

    if hasattr(st.session_state, "clear"):
        st.session_state.clear()


def test_no_access_code_blocked() -> None:
    from worldcup_predictor.access.identity import login_with_invite

    _clear_session()
    user, err = login_with_invite(identity="user1", access_code="")
    assert user is None
    assert err == "access.access_code_required"


def test_wrong_access_code_blocked() -> None:
    from worldcup_predictor.access.identity import login_with_invite

    _clear_session()
    user, err = login_with_invite(identity="user1", access_code="wrong-code")
    assert user is None
    assert err == "access.invalid_access_code"


def test_user1_and_user2_same_code_login() -> None:
    from worldcup_predictor.access.identity import is_registered_user, login_with_invite

    db, repo_mod = _fresh_repo()
    try:
        _clear_session()
        user1, err1 = login_with_invite(identity="user1", access_code=SHARED_CODE)
        assert err1 is None and user1 is not None
        assert user1.email == "user1"
        assert is_registered_user()

        _clear_session()
        user2, err2 = login_with_invite(identity="user2", access_code=SHARED_CODE)
        assert err2 is None and user2 is not None
        assert user2.email == "user2"
        assert user1.user_id != user2.user_id
    finally:
        repo_mod._repo_singleton = None
        try:
            db.unlink()
        except OSError:
            pass


def test_separate_quota_per_user() -> None:
    from worldcup_predictor.access.identity import login_with_invite
    from worldcup_predictor.access.prediction_gate import acquire_prediction_slot, preview_prediction_quota

    db, repo_mod = _fresh_repo()
    try:
        _clear_session()
        user1, _ = login_with_invite(identity="user1", access_code=SHARED_CODE)
        assert user1 is not None
        uid1 = user1.user_id

        for _ in range(2):
            assert acquire_prediction_slot().allowed
        assert not acquire_prediction_slot().allowed

        preview1 = preview_prediction_quota(uid1)
        assert preview1.used_today == 2
        assert preview1.remaining == 0

        _clear_session()
        user2, _ = login_with_invite(identity="user2", access_code=SHARED_CODE)
        assert user2 is not None

        preview2 = preview_prediction_quota()
        assert preview2.used_today == 0
        assert preview2.remaining == 2
        assert acquire_prediction_slot().allowed
    finally:
        repo_mod._repo_singleton = None
        try:
            db.unlink()
        except OSError:
            pass


def test_username_without_at_works() -> None:
    from worldcup_predictor.access.identity import login_with_invite

    db, repo_mod = _fresh_repo()
    try:
        _clear_session()
        user, err = login_with_invite(identity="Pedram", access_code=SHARED_CODE)
        assert err is None
        assert user is not None
        assert user.email == "pedram"
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

    _clear_session()
    assert login_admin("pedram", "admin-secret")


def main() -> int:
    tests = [
        test_no_access_code_blocked,
        test_wrong_access_code_blocked,
        test_user1_and_user2_same_code_login,
        test_separate_quota_per_user,
        test_username_without_at_works,
        test_admin_login_still_works,
    ]
    for fn in tests:
        fn()
        print(f"PASS: {fn.__name__}")
    print("\nPhase 49 invite-code validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

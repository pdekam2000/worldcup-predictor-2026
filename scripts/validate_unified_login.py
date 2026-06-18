from __future__ import annotations

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().with_name('bootstrap_path.py')))

import os
import sys


def main() -> int:
    os.environ.setdefault("PUBLIC_ACCESS_ENABLED", "true")
    os.environ.setdefault("PUBLIC_ACCESS_CODE", "test-user-pass")
    os.environ.setdefault("ADMIN_USERNAME", "admin")
    os.environ.setdefault("ADMIN_PASSWORD", "test-admin-pass")

    checks: list[tuple[str, bool]] = []

    from worldcup_predictor.access.admin_auth import (
        ADMIN_ONLY_NAV_KEYS,
        acquire_admin_session_lock,
        admin_credentials,
        is_admin_only_nav_page,
        try_acquire_admin_session_lock,
        verify_admin_credentials,
    )
    from worldcup_predictor.access.unified_auth import is_admin_username, verify_gui_password

    creds = admin_credentials()
    checks.append(("admin_creds", creds is not None))
    checks.append(("verify_admin", verify_admin_credentials("admin", "test-admin-pass")))
    checks.append(("verify_user_pass", verify_gui_password("test-user-pass")))
    checks.append(("is_admin_name", is_admin_username("admin")))
    checks.append(("reports_admin_only", is_admin_only_nav_page("professional_reports")))
    checks.append(("predict_not_admin_only", not is_admin_only_nav_page("predict")))

    from worldcup_predictor.access.repository import get_access_repository

    repo = get_access_repository()
    repo.force_clear_admin_session_lock()
    checks.append(("lock_first", try_acquire_admin_session_lock("token-a", "admin")))
    checks.append(("lock_block_second", not try_acquire_admin_session_lock("token-b", "admin")))
    checks.append(("lock_reacquire", try_acquire_admin_session_lock("token-a", "admin")))
    acquire_admin_session_lock("token-a", "admin")
    checks.append(("lock_force_acquire", repo.get_admin_session_lock() is not None))
    repo.force_clear_admin_session_lock()

    from worldcup_predictor.ui.gui_mode_v2 import pages_for_mode, primary_nav_for_mode

    user_nav = primary_nav_for_mode(developer_mode=False)
    user_keys = {k for k, _, _ in user_nav}
    checks.append(("user_nav_hides_reports", "professional_reports" not in user_keys))
    checks.append(("user_nav_has_predict", "predict" in user_keys))
    allowed = pages_for_mode(developer_mode=False)
    checks.append(("user_pages_no_settings", "settings" not in allowed))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"\n{len(failed)} failed")
        return 1
    print(f"\nAll {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

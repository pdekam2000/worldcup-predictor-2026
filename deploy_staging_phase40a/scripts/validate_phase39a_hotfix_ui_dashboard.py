"""Phase 39A hotfix — Settings save, toast dismiss, dashboard 500, match cards."""

from __future__ import annotations

import json
import runpy
import uuid
from pathlib import Path
from unittest.mock import patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 39A hotfix validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    user_py = (root / "worldcup_predictor" / "api" / "routes" / "user.py").read_text(encoding="utf-8")
    use_toast = (root / "base44-d" / "src" / "components" / "ui" / "use-toast.jsx").read_text(encoding="utf-8")
    toaster = (root / "base44-d" / "src" / "components" / "ui" / "toaster.jsx").read_text(encoding="utf-8")
    settings_page = (root / "base44-d" / "src" / "pages" / "SettingsPage.jsx").read_text(encoding="utf-8")
    match_center = (root / "base44-d" / "src" / "pages" / "MatchCenter.jsx").read_text(encoding="utf-8")
    versus = (root / "base44-d" / "src" / "components" / "match" / "MatchVersusCenter.jsx").read_text(encoding="utf-8")

    record("dashboard_no_settings_shadow", "get_app_settings" in user_py and "def get_settings(" not in user_py)
    record("dashboard_empty_fallback", "_empty_dashboard_payload" in user_py)
    record("settings_route_renamed", "read_user_settings" in user_py and "update_user_settings" in user_py)
    record("toast_auto_dismiss", "TOAST_AUTO_DISMISS_MS" in use_toast and "1000000" not in use_toast)
    record("toast_close_wired", "dismiss(id)" in toaster)
    record("toast_limit_sane", "TOAST_LIMIT = 5" in use_toast)
    record("settings_reload_after_save", "await load()" in settings_page and "Settings saved" in settings_page)
    record("match_football_icon", "MatchVersusCenter" in match_center and "⚽" in versus)
    record("upgrade_unchanged", "Payment system coming soon" in (
        root / "base44-d" / "src" / "components" / "subscription" / "UpgradeComingSoonDialog.jsx"
    ).read_text(encoding="utf-8"))

    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()

    try:
        from fastapi.testclient import TestClient
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.web_auth import WebAuthUser, issue_access_token
        from worldcup_predictor.config.settings import get_settings as load_settings
        from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

        if not postgres_configured():
            record("api_smoke", True, "skipped_no_postgres")
        else:
            test_email = f"hotfix-{uuid.uuid4().hex[:8]}@test.local"
            with saas_uow() as uow:
                user_row = uow.users.create(email=test_email, full_name="Hotfix Test")
                user_id = user_row.id
            web_user = WebAuthUser(
                id=str(user_id),
                email=test_email,
                full_name="Hotfix Test",
                role="user",
            )
            token = issue_access_token(web_user, token_version=0)
            client = TestClient(app)

            r = client.get("/api/user/dashboard", headers={"Authorization": f"Bearer {token}"})
            record("dashboard_returns_200", r.status_code == 200, f"status={r.status_code}")
            if r.status_code == 200:
                body = r.json()
                record("dashboard_empty_user_safe", body.get("status") == "ok" and "stats" in body)
                record("dashboard_no_history_ok", isinstance(body.get("recent_predictions"), list))

            r2 = client.patch(
                "/api/user/settings",
                headers={"Authorization": f"Bearer {token}"},
                json={"language": "de", "timezone": "Europe/Berlin", "preferences": {"darkMode": False}},
            )
            record("settings_patch_200", r2.status_code == 200, f"status={r2.status_code}")

            r3 = client.get("/api/user/settings", headers={"Authorization": f"Bearer {token}"})
            if r3.status_code == 200:
                s = r3.json().get("settings", {})
                record(
                    "settings_persist",
                    s.get("language") == "de" and s.get("timezone") == "Europe/Berlin",
                    json.dumps({"language": s.get("language"), "timezone": s.get("timezone")}),
                )
                prefs = s.get("preferences") or {}
                record("settings_preferences_persist", prefs.get("darkMode") is False)
            else:
                record("settings_persist", False, f"get status={r3.status_code}")
                record("settings_preferences_persist", False)

            import worldcup_predictor.api.routes.user as user_routes

            record("config_get_settings_callable", callable(load_settings))
            record("route_not_shadowing_config", user_routes.get_app_settings is load_settings)
    except Exception as exc:
        record("api_smoke", False, str(exc))

    # Toast reducer smoke
    from worldcup_predictor.config.provider_readiness import provider_diagnostic

    diag = provider_diagnostic(get_settings())
    record("no_regression_env_diag", "API_FOOTBALL_KEY_present" in diag)

    import subprocess
    import sys

    for script, label in (
        ("validate_phase39a_commercial_readiness.py", "39A"),
        ("validate_phase38a_subscription_system.py", "38A"),
        ("validate_phase37a_admin_security.py", "37A"),
    ):
        proc = subprocess.run(
            [sys.executable, str(root / "scripts" / script)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        line = next((ln for ln in (proc.stdout or "").splitlines() if "validation:" in ln.lower()), "")
        record(f"regression_{label}", proc.returncode == 0, line.strip() or f"exit={proc.returncode}")

    _report(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

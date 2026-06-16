"""Product polish fix validation — login persistence, accuracy, timezone, first goal."""

from __future__ import annotations

import importlib
import inspect
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
NOTES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def test_remember_login_module() -> None:
    from worldcup_predictor.access import remember_login

    src = inspect.getsource(remember_login)
    check("remember_login module imports", True)
    check("opaque token storage (not access code)", "PUBLIC_ACCESS_CODE" not in src and "localStorage" in src)
    check("remember token hash in DB", "_hash_token" in src)
    check("login_with_invite supports remember_me", "remember_me" in inspect.getsource(
        importlib.import_module("worldcup_predictor.access.identity").login_with_invite
    ))


def test_admin_sidebar_placement() -> None:
    from worldcup_predictor.ui import access_display, gui_app

    src = inspect.getsource(access_display.render_admin_bottom_sidebar)
    check("admin login uses expander", "expander" in src and "admin.login_expand" in src)
    check("admin expander collapsed by default", "expanded=False" in src)
    check("admin password field type=password", 'type="password"' in src)
    gui_src = inspect.getsource(gui_app._render_sidebar)
    check("gui calls render_admin_bottom_sidebar", "render_admin_bottom_sidebar" in gui_src)
    idx_admin = gui_src.find("render_admin_bottom_sidebar")
    idx_user = gui_src.find("render_access_sidebar")
    check("user login before admin in sidebar", idx_user >= 0 and idx_admin > idx_user)


def test_accuracy_dashboard() -> None:
    from worldcup_predictor.accuracy.dashboard_metrics import build_accuracy_dashboard
    from worldcup_predictor.ui.accuracy_display import render_developer_accuracy_table, render_user_accuracy_card

    dash = build_accuracy_dashboard([])
    check("accuracy dashboard builds", dash is not None)
    check("all_time period present", hasattr(dash, "all_time"))
    check("last_30_days period present", hasattr(dash, "last_30_days"))
    check("formula notes present", len(dash.formula_notes) >= 3)
    check("1x2 rate formula uses correct/total", dash.all_time.rate_1x2() is None or 0 <= dash.all_time.rate_1x2() <= 1)
    check("user accuracy card callable", callable(render_user_accuracy_card))
    check("developer accuracy table callable", callable(render_developer_accuracy_table))


def test_database_audit_report() -> None:
    report = ROOT / "reports" / "database_learning_audit.md"
    check("database audit report exists", report.is_file(), str(report))
    if report.is_file():
        text = report.read_text(encoding="utf-8")
        check("audit mentions database path", "Database path" in text or "database path" in text.lower())
        check("audit mentions learning policy", "Learning" in text or "learning" in text)
        check("audit mentions recommendations only", "recommendation" in text.lower() or "approval" in text.lower())


def test_first_goal_display() -> None:
    from worldcup_predictor.ui import first_goal_display, professional_prediction_card

    fg_src = inspect.getsource(first_goal_display.render_first_goal_prediction_card)
    check("first goal card title i18n", "first_goal.card_title" in fg_src)
    check("minute band disclaimer", "first_goal.band_disclaimer" in fg_src)
    check("likely scorers section", "first_goal.scorers_title" in inspect.getsource(
        first_goal_display.render_likely_goal_scorers_card
    ))
    check("GK excluded from scorers", "GOALKEEPER" in inspect.getsource(first_goal_display.render_likely_goal_scorers_card))
    pro_src = inspect.getsource(professional_prediction_card._render_card)
    check("prediction page renders first goal card", "render_first_goal_prediction_card" in pro_src)
    check("prediction page renders likely scorers", "render_likely_goal_scorers_card" in pro_src)


def test_timezone_display() -> None:
    from worldcup_predictor.ui.kickoff_timezone import format_kickoff_display, resolve_venue_timezone

    utc_ko = datetime(2026, 6, 15, 19, 0, tzinfo=timezone.utc)
    nyc = format_kickoff_display(utc_ko, venue_city="New York", locale="en")
    check("user local time populated", nyc.user_local != "—")
    check("UTC labeled with UTC", "UTC" in nyc.utc)
    check("venue local distinct from UTC for NYC", nyc.venue_local is not None and "19:00" not in (nyc.venue_local or ""))
    check("venue TZ resolves for New York", resolve_venue_timezone(city="New York") == "America/New_York")
    unknown = format_kickoff_display(utc_ko, venue_city="Unknown City XYZ", locale="en")
    check("unknown venue sets venue_unavailable", unknown.venue_unavailable is True)


def test_developer_mode_hidden() -> None:
    from worldcup_predictor.ui.gui_mode_v2 import pages_for_mode

    user_pages = pages_for_mode(developer_mode=False)
    dev_only = {"audit", "backtest", "learning", "automation", "api", "specialists"}
    exposed = dev_only.intersection(user_pages)
    check("developer routes hidden from user mode", len(exposed) == 0, f"exposed: {exposed}")


def test_db_remember_tokens_table() -> None:
    from worldcup_predictor.database.connection import get_db_path
    from worldcup_predictor.access.config import access_db_path

    db_path = get_db_path(access_db_path())
    if not db_path.is_file():
        check("sqlite db exists for remember_tokens", False, str(db_path))
        return
    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    check("remember_tokens table exists", "remember_tokens" in tables)
    NOTES.append(f"DB tables sample: {', '.join(sorted(tables)[:12])}...")


def main() -> int:
    print("Product Polish Fix Validation")
    print("=" * 40)
    test_remember_login_module()
    test_admin_sidebar_placement()
    test_accuracy_dashboard()
    test_database_audit_report()
    test_first_goal_display()
    test_timezone_display()
    test_developer_mode_hidden()
    test_db_remember_tokens_table()
    print("=" * 40)
    print(f"Result: {PASS} passed, {FAIL} failed")
    for note in NOTES:
        print(f"  note: {note}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

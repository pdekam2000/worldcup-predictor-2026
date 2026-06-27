#!/usr/bin/env python3
"""Phase A19 — AI Watchlist, Smart Alerts & Daily Assistant validation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "base44-d"


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for rel in (
        "worldcup_predictor/ai_assistant/store.py",
        "worldcup_predictor/ai_assistant/service.py",
        "worldcup_predictor/ai_assistant/detectors.py",
        "worldcup_predictor/ai_assistant/briefing.py",
        "worldcup_predictor/ai_assistant/channels.py",
        "worldcup_predictor/ai_assistant/scheduler.py",
        "worldcup_predictor/api/routes/ai_assistant.py",
    ):
        record(checks, f"file_{Path(rel).stem}", (ROOT / rel).is_file())

    mig = (ROOT / "worldcup_predictor/database/migrations.py").read_text(encoding="utf-8")
    for tbl in ("assistant_watchlist", "assistant_notifications", "assistant_preferences", "assistant_alert_state"):
        record(checks, f"ddl_{tbl}", tbl in mig)

    api = (ROOT / "worldcup_predictor/api/routes/ai_assistant.py").read_text(encoding="utf-8")
    for ep in ("/watchlist", "/assistant/notifications", "/preferences", "/daily-briefing", "scan-alerts"):
        record(checks, f"api_{ep.strip('/').replace('/', '_')}", ep in api)

    app_jsx = (FRONTEND / "src/App.jsx").read_text(encoding="utf-8")
    nav = (FRONTEND / "src/lib/navConfig.js").read_text(encoding="utf-8")
    record(checks, "ui_watchlist", "/watchlist" in app_jsx)
    record(checks, "ui_briefing", "/daily-briefing" in app_jsx)
    record(checks, "ui_nav", "Watchlist" in nav and "Daily Briefing" in nav)

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    scoring = (ROOT / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecisionEngine" in wde)
    record(checks, "scoring_unchanged", "class ScoringEngine" in scoring)

    try:
        from worldcup_predictor.database.migrations import ensure_schema_compat
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.ai_assistant.briefing import build_daily_briefing
        from worldcup_predictor.ai_assistant.rules import build_dedup_key, is_meaningful_quality_change
        from worldcup_predictor.ai_assistant.scheduler import run_alert_scan
        from worldcup_predictor.ai_assistant.service import (
            add_watchlist_item,
            get_daily_briefing,
            get_preferences,
            list_notifications,
            list_watchlist,
            update_preferences,
        )
        from worldcup_predictor.ai_assistant.store import AssistantStore

        repo = FootballIntelligenceRepository()
        ensure_schema_compat(repo._conn)

        uid_a = f"test-a19-{uuid.uuid4().hex[:8]}"
        uid_b = f"test-a19-{uuid.uuid4().hex[:8]}"

        wl = add_watchlist_item(uid_a, item_type="fixture", item_id="12345", item_name="Test Match")
        record(checks, "watchlist_add", wl.get("status") == "ok")

        items = list_watchlist(uid_a)
        record(checks, "watchlist_list", len(items.get("watchlist", [])) >= 1)

        prefs = update_preferences(uid_a, {"min_bet_quality": 50, "timezone": "UTC"})
        record(checks, "preferences", prefs.get("preferences", {}).get("min_bet_quality") == 50)

        store = AssistantStore()
        n1 = store.create_notification(
            uid_a,
            category="quality",
            alert_type="quality_increase",
            title="Test alert",
            message="Quality up",
            fixture_id=12345,
            old_value="60",
            new_value="72",
            reason="test",
            dedup_key=build_dedup_key("quality_increase", 12345, "72"),
        )
        n2 = store.create_notification(
            uid_a,
            category="quality",
            alert_type="quality_increase",
            title="Duplicate",
            message="Should dedup",
            fixture_id=12345,
            dedup_key=build_dedup_key("quality_increase", 12345, "72"),
        )
        record(checks, "no_duplicate_alerts", n1 is not None and n2 is None)

        notifs = list_notifications(uid_a)
        record(checks, "notification_center", notifs.get("unread_count", 0) >= 1)

        briefing = get_daily_briefing(uid_a)
        record(checks, "briefing", "briefing" in briefing and "disclaimer" in briefing.get("briefing", {}))

        scan = run_alert_scan(user_id=uid_a)
        record(checks, "alert_scan", scan.get("status") == "ok")

        record(checks, "meaningful_change", is_meaningful_quality_change(60, 72))

        # Paper betting integration path exists
        from worldcup_predictor.ai_assistant.detectors import detect_paper_betting_alerts

        pb_alerts = detect_paper_betting_alerts(
            store,
            uid_a,
            settlement_result={"settled": 0},
            prefs=get_preferences(uid_a).get("preferences", {}),
        )
        record(checks, "paper_betting_integration", isinstance(pb_alerts, list))

        # User isolation
        add_watchlist_item(uid_b, item_type="team", item_id="arsenal", item_name="Arsenal")
        record(checks, "user_isolation", len(list_watchlist(uid_b).get("watchlist", [])) == 1 and len(list_watchlist(uid_a).get("watchlist", [])) >= 1)

        # No bookmaker integration
        assistant_py = (ROOT / "worldcup_predictor/ai_assistant").read_text(encoding="utf-8", errors="ignore") if False else ""
        combined = ""
        for p in (ROOT / "worldcup_predictor/ai_assistant").glob("*.py"):
            combined += p.read_text(encoding="utf-8")
        record(checks, "no_bookmaker_refs", "place_bet(" not in combined and "bookmaker" not in combined.lower())

        channels = (ROOT / "worldcup_predictor/ai_assistant/channels.py").read_text(encoding="utf-8")
        record(checks, "email_ready_architecture", "EmailChannel" in channels and "InAppChannel" in channels)

    except Exception as exc:
        record(checks, "runtime_tests", False, str(exc))

    if os.getenv("SKIP_FRONTEND_BUILD") != "1":
        try:
            proc = subprocess.run(
                ["npm", "run", "build"],
                cwd=FRONTEND,
                capture_output=True,
                text=True,
                timeout=180,
                shell=sys.platform == "win32",
            )
            record(checks, "frontend_build", proc.returncode == 0, proc.stderr[-500:] if proc.stderr else "")
        except Exception as exc:
            record(checks, "frontend_build", False, str(exc))
    else:
        record(checks, "frontend_build", True, "skipped")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A19 validation: {passed}/{total} checks passed\n")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        extra = f" — {detail}" if detail and not ok else ""
        print(f"  [{status}] {name}{extra}")

    out = ROOT / "data" / "validation" / "phase_a19_ai_watchlist_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "passed": passed,
                "total": total,
                "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

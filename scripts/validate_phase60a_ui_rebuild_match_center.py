#!/usr/bin/env python3
"""Phase 60A — UI rebuild + Match Center control panel validation."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "base44-d"
SRC = FRONTEND / "src"


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    # --- Static files ---
    record(checks, "nav_config", (SRC / "lib/navConfig.js").is_file())
    record(checks, "phase60a_theme", (SRC / "lib/phase60aTheme.js").is_file())
    record(checks, "saas_page_header", (SRC / "components/saas/SaasPageHeader.jsx").is_file())
    record(checks, "best_tips_page", (SRC / "pages/BestTipsPage.jsx").is_file())
    record(checks, "match_center_page", (SRC / "pages/MatchCenter.jsx").is_file())
    record(checks, "combo_tips_page", (SRC / "pages/ComboTipsPage.jsx").is_file())
    record(checks, "archive_status_lib", (SRC / "lib/archiveStatus.js").is_file())
    record(checks, "admin_learning_page", (SRC / "pages/AdminLearningDashboard.jsx").is_file())

    nav_text = (SRC / "lib/navConfig.js").read_text(encoding="utf-8")
    record(checks, "nav_main_section", "MAIN_NAV_SECTION" in nav_text and '"Main"' in nav_text)
    record(checks, "nav_predictions_section", "PREDICTIONS_NAV_SECTION" in nav_text)
    record(checks, "nav_data_section", "DATA_NAV_SECTION" in nav_text)
    record(checks, "nav_account_section", "ACCOUNT_NAV_SECTION" in nav_text)
    record(checks, "nav_best_tips", "/best-tips" in nav_text)
    record(checks, "nav_combo_builder", "/combo-builder" in nav_text)
    record(checks, "nav_classic_predictions", "Classic Predictions" in nav_text)
    record(checks, "nav_elite_goal_intelligence", "Elite Goal Intelligence" in nav_text)
    record(checks, "nav_admin_shadow", "/admin/elite-shadow" in nav_text and "Elite Shadow Preview" in nav_text)
    record(checks, "nav_admin_learning", "/admin/learning" in nav_text)
    record(checks, "nav_admin_roles", 'roles: ["super_admin"]' in nav_text)
    record(checks, "nav_no_public_shadow", "Shadow vs Production" not in nav_text)

    nav_icons = re.findall(r"icon:\s*(\w+)", nav_text)
    nav_imports = set(re.findall(r"\b(\w+)\b", nav_text.split('from "lucide-react"')[0]))
    missing_icons = [i for i in set(nav_icons) if i not in nav_imports]
    record(checks, "nav_icons_imported", not missing_icons, ", ".join(missing_icons) if missing_icons else "ok")

    layout_text = (SRC / "components/dashboard/DashboardLayout.jsx").read_text(encoding="utf-8")
    record(checks, "layout_saas_theme", "theme-saas" in layout_text or "SAAS_THEME_CLASS" in layout_text)
    record(checks, "layout_sidebar_saas", 'variant="saas"' in layout_text)

    app_text = (SRC / "App.jsx").read_text(encoding="utf-8")
    required_routes = [
        "/dashboard",
        "/matches",
        "/best-tips",
        "/combo-tips",
        "/combo-builder",
        "/goal-timing/dashboard",
        "/archive",
        "/accuracy",
        "/subscription",
        "/settings",
        "/login",
        "/register",
        "/admin/elite-shadow",
        "/admin/learning",
        "/api-settings",
        "/betting-plan",
        "/paper-betting",
        "/watchlist",
        "/daily-briefing",
        "/notifications",
        "/research/highlights",
    ]
    for route in required_routes:
        key = f"route_{route.strip('/').replace('/', '_') or 'root'}"
        record(checks, key, route in app_text, route)

    record(checks, "route_best_tips_component", "BestTipsPage" in app_text)
    record(checks, "route_admin_learning_component", "AdminLearningDashboard" in app_text)
    record(checks, "route_combo_builder_redirect", 'path="/combo-builder"' in app_text)

    match_center = (SRC / "pages/MatchCenter.jsx").read_text(encoding="utf-8")
    record(checks, "match_center_competition_filter", "LeagueSelector" in match_center or "competition" in match_center)
    record(checks, "match_center_status_filter", "statusTab" in match_center)
    record(checks, "match_center_elite_card", 'variant="saas"' in match_center)

    best_tips = (SRC / "pages/BestTipsPage.jsx").read_text(encoding="utf-8")
    record(checks, "best_tips_fetch", "fetchBestTips" in best_tips)
    record(checks, "best_tips_classic_source", "Classic" in best_tips)
    record(checks, "best_tips_no_shadow_public", "shadow" not in best_tips.lower() or "Elite Shadow Preview only" in best_tips)

    combo = (SRC / "pages/ComboTipsPage.jsx").read_text(encoding="utf-8")
    record(checks, "combo_builder_title", "Combo Builder" in combo)
    record(checks, "combo_risk_warning", "higher risk" in combo.lower() or "do not guarantee" in combo.lower())

    archive_status = (SRC / "lib/archiveStatus.js").read_text(encoding="utf-8")
    for status in ("correct", "wrong", "partial", "pending"):
        record(checks, f"archive_status_{status}", f"{status}:" in archive_status)

    accuracy = (SRC / "pages/AccuracyCenter.jsx").read_text(encoding="utf-8")
    record(checks, "accuracy_quarantine_excluded", "quarantine" in accuracy.lower())

    # --- Prediction engine unchanged (grep guards) ---
    scoring_engine = ROOT / "worldcup_predictor/prediction/scoring_engine.py"
    wde = ROOT / "worldcup_predictor/decision/weighted_decision_engine.py"
    record(checks, "scoring_engine_preserved", scoring_engine.is_file())
    record(checks, "wde_preserved", wde.is_file())

    # --- Frontend build ---
    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=240,
            shell=os.name == "nt",
        )
        record(checks, "npm_build", proc.returncode == 0, (proc.stderr or proc.stdout)[-500:])
    except Exception as exc:
        record(checks, "npm_build", False, str(exc))

    record(checks, "dist_index", (FRONTEND / "dist" / "index.html").is_file())

    # --- Backend smoke (optional) ---
    base_url = (os.environ.get("PHASE60A_BASE_URL") or os.environ.get("API_BASE_URL") or "").rstrip("/")
    if base_url:
        try:
            import urllib.request

            endpoints = [
                ("/api/health", (200,)),
                ("/api/best-tips", (200,)),
                ("/api/matches", (200, 401)),
                ("/api/performance/summary", (200,)),
                ("/api/admin/elite-shadow/predictions", (401, 403)),
            ]
            for path, expect in endpoints:
                req = urllib.request.Request(f"{base_url}{path}")
                try:
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        record(checks, f"api_{path.strip('/').replace('/', '_')}", resp.status in expect, str(resp.status))
                except Exception as exc:
                    code = getattr(exc, "code", None)
                    record(checks, f"api_{path.strip('/').replace('/', '_')}", code in expect, str(code or exc))
        except Exception as exc:
            record(checks, "api_smoke", False, str(exc))
    else:
        record(checks, "api_smoke_skipped", True, "set PHASE60A_BASE_URL for live smoke")

    # --- Backend unit import ---
    try:
        from worldcup_predictor.api.performance_center import build_best_tips

        tips = build_best_tips(limit=3)
        record(checks, "backend_best_tips", tips.get("status") == "ok" and "tips" in tips)
    except Exception as exc:
        record(checks, "backend_best_tips", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase 60A validation: {passed}/{total} passed\n")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail and not ok:
            line += f" — {detail[:200]}"
        print(line)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

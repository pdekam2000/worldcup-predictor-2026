#!/usr/bin/env python3
"""Phase 64 — product owner quality upgrade validation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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

    nav = (FRONTEND / "src/lib/navConfig.js").read_text(encoding="utf-8")
    owner_nav = (FRONTEND / "src/lib/ownerNavConfig.js").read_text(encoding="utf-8")
    app = (FRONTEND / "src/App.jsx").read_text(encoding="utf-8")

    record(checks, "nav_match_center", "Match Center" in nav and 'path: "/matches"' in nav)
    record(checks, "nav_world_cup", "World Cup" in nav and 'path: "/world-cup"' in nav)
    record(checks, "route_world_cup", 'path="/world-cup"' in app)
    record(checks, "owner_nav_match_center", "Match Center" in owner_nav)
    record(checks, "owner_nav_world_cup", "World Cup" in owner_nav)
    record(checks, "owner_model_center_page", (FRONTEND / "src/pages/owner/OwnerModelCenter.jsx").is_file())
    record(checks, "owner_research_lab_page", (FRONTEND / "src/pages/owner/OwnerResearchLab.jsx").is_file())
    record(checks, "route_owner_model_center", 'path="/owner/model-center"' in app)
    record(checks, "route_owner_research_lab", 'path="/owner/research-lab"' in app)

    owner_routes = (ROOT / "worldcup_predictor/api/routes/owner.py").read_text(encoding="utf-8")
    record(checks, "api_model_center", "/model-center" in owner_routes)
    record(checks, "api_research_lab", "/research-lab" in owner_routes)
    record(checks, "api_run_once_body", "AutonomousRunRequest" in owner_routes)

    record(checks, "value_intelligence_module", (ROOT / "worldcup_predictor/research/value_intelligence.py").is_file())

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged_marker", "WeightedDecisionEngine" in wde or "class WeightedDecision" in wde)

    try:
        from worldcup_predictor.research.value_intelligence import run_value_intelligence

        summary = run_value_intelligence(write_artifacts=True)
        record(checks, "value_intel_artifacts", (ROOT / "artifacts/value_intelligence/value_bucket_summary.json").is_file())
        record(checks, "value_intel_csv", (ROOT / "artifacts/value_intelligence/value_bucket_summary.csv").is_file())
        record(checks, "value_intel_sample", isinstance(summary.get("sample_size"), int))
    except Exception as exc:
        record(checks, "value_intelligence_run", False, str(exc))

    try:
        from worldcup_predictor.owner.platform_service import OwnerPlatformService

        svc = OwnerPlatformService()
        mc = svc.model_center()
        record(checks, "model_center_api_shape", "production_engine" in mc and "elite_engine" in mc)
        lab = svc.research_lab(refresh_value=False)
        record(checks, "research_lab_api_shape", "value_intelligence" in lab)
        status = svc.autonomous_status()
        record(checks, "autonomous_gated", status.get("required_for_scheduler") == 3)
    except Exception as exc:
        record(checks, "owner_platform_service", False, str(exc))

    autonomous_page = (FRONTEND / "src/pages/owner/OwnerAutonomousPage.jsx").read_text(encoding="utf-8")
    record(checks, "autonomous_dry_run_ui", "dryRun" in autonomous_page)
    record(checks, "autonomous_fixture_limit_ui", "fixtureLimit" in autonomous_page)

    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=180,
            shell=os.name == "nt",
        )
        record(checks, "npm_build", proc.returncode == 0, (proc.stderr or proc.stdout)[-400:])
    except Exception as exc:
        record(checks, "npm_build", False, str(exc))

    base = (os.environ.get("PHASE64_BASE_URL") or os.environ.get("PHASE63_BASE_URL") or "").rstrip("/")
    if base:
        import urllib.error
        import urllib.request

        def get(path: str) -> int:
            try:
                req = urllib.request.Request(f"{base}{path}", headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return resp.status
            except urllib.error.HTTPError as exc:
                return exc.code

        record(checks, "smoke_health", get("/api/health") == 200)
        record(checks, "smoke_owner_overview_unauth", get("/api/owner/overview") in (401, 403))
        record(checks, "smoke_login_page", get("/login") == 200)
        record(checks, "smoke_owner_page_shell", get("/owner") in (200, 401))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" ({detail})" if detail and not ok else ""))
    print(f"SUMMARY {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

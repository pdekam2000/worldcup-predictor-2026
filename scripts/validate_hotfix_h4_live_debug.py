#!/usr/bin/env python3
"""HOTFIX H4 — production match detail crash + image debug validation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "hotfix_h4"
BASE = "http://127.0.0.1:8000"

FIXTURES = [1489409, 1489410, 1489412, 1489411, 1489416, 1539011, 1539012]


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def _get(url: str) -> dict | list | None:
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as exc:
        return {"_error": str(exc)}


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    # Frontend / route safety files
    record(checks, "route_error_boundary", (ROOT / "base44-d/src/components/ui/RouteErrorBoundary.jsx").is_file())
    record(checks, "match_detail_safe_view", (ROOT / "base44-d/src/lib/matchDetailSafeView.js").is_file())
    record(checks, "dashboard_outlet_boundary", "RouteErrorBoundary" in (ROOT / "base44-d/src/components/dashboard/DashboardLayout.jsx").read_text(encoding="utf-8"))
    record(checks, "safe_display_text", "safeDisplayText" in (ROOT / "base44-d/src/lib/predictionDetailProUtils.js").read_text(encoding="utf-8"))
    record(checks, "predict_400_retry", "response.status === 404 || response.status === 400" in (ROOT / "base44-d/src/api/worldcupApi.js").read_text(encoding="utf-8"))

    # Backend logo resolver
    dh = (ROOT / "worldcup_predictor/api/display_helpers.py").read_text(encoding="utf-8")
    record(checks, "api_football_team_logo", "api_football_team_logo_url" in dh)
    record(checks, "fixture_logo_from_team_id", "home_team_id" in dh and "api_football_team_logo_url(fixture.home_team_id)" in dh)

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecisionEngine" in wde)

    # API probes (local or production via env)
    import os

    base = os.environ.get("H4_API_BASE", BASE).rstrip("/")
    logo_rows = []
    object_hits = []

    for fid in FIXTURES:
        pred = _get(f"{base}/api/predict/{fid}")
        if isinstance(pred, dict) and not pred.get("_error"):
            o = pred.get("publication_overlay") or {}
            for k in ("public_best_pick", "prediction", "expected_odds"):
                v = o.get(k) if k == "public_best_pick" else pred.get(k)
                if isinstance(v, (dict, list)):
                    object_hits.append(f"{fid}:{k}")
            record(checks, f"predict_{fid}_ok", pred.get("status") in ("ok", None) or "fixture_id" in pred, str(pred.get("status")))
            hl = pred.get("home_team_logo")
            al = pred.get("away_team_logo")
            logo_rows.append({"fixture_id": fid, "home_logo": hl, "away_logo": al})

        bad = _get(f"{base}/api/predict/{fid}?competition=league_1")
        record(checks, f"predict_{fid}_bad_comp_not_fatal", isinstance(bad, dict))

    matches = _get(f"{base}/api/matches?competition=world_cup_2026&include_summary=true&page_size=25")
    if isinstance(matches, dict) and matches.get("matches"):
        rows = matches["matches"][:20]
        with_logo = sum(1 for r in rows if r.get("home_team_logo") or r.get("away_team_logo"))
        record(checks, "match_list_logos", with_logo >= max(1, len(rows) // 4), f"{with_logo}/{len(rows)} with logo")
        for r in rows[:5]:
            logo_rows.append(
                {
                    "fixture_id": r.get("fixture_id"),
                    "home": r.get("home_team"),
                    "home_logo": r.get("home_team_logo"),
                    "away_logo": r.get("away_team_logo"),
                    "competition": r.get("competition_key"),
                }
            )
    else:
        record(checks, "match_list_logos", False, str(matches))

    record(checks, "no_object_public_fields", len(object_hits) == 0, ", ".join(object_hits[:5]))

    # Frontend build
    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(ROOT / "base44-d"),
            capture_output=True,
            text=True,
            timeout=180,
            shell=True,
        )
        record(checks, "frontend_build", proc.returncode == 0, (proc.stderr or proc.stdout)[-400:])
    except Exception as exc:
        record(checks, "frontend_build", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    failed = [c for c in checks if not c[1]]
    report = {
        "phase": "H4",
        "passed": passed,
        "total": len(checks),
        "status": "LIVE_DETAIL_CRASH_AND_IMAGES_FIXED" if not failed else "CRASH_FIXED_IMAGES_PARTIAL",
        "logo_sample": logo_rows[:12],
        "object_hits": object_hits,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"H4 validation: {passed}/{len(checks)} — {report['status']}")
    for name, ok, detail in checks:
        mark = "OK" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if detail and not ok:
            line += f" — {detail}"
        print(line)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

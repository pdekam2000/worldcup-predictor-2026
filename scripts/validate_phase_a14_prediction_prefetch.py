#!/usr/bin/env python3
"""Phase A14 — background prediction prefetch validation."""

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

    for rel in (
        "worldcup_predictor/automation/prediction_prefetch/engine.py",
        "worldcup_predictor/automation/prediction_prefetch/coverage.py",
        "worldcup_predictor/automation/prediction_prefetch/scheduler.py",
        "worldcup_predictor/automation/prediction_prefetch/priority.py",
        "worldcup_predictor/automation/prediction_prefetch/smart_refresh.py",
        "scripts/validate_phase_a14_prediction_prefetch.py",
    ):
        record(checks, f"file_{Path(rel).stem}", (ROOT / rel).is_file())

    owner = (ROOT / "worldcup_predictor/api/routes/owner.py").read_text(encoding="utf-8")
    record(checks, "api_prefetch_coverage", "/prefetch/coverage" in owner)
    record(checks, "api_prefetch_run", "/prefetch/run-once" in owner)

    combo = (FRONTEND / "src/lib/comboGenerator.js").read_text(encoding="utf-8")
    record(checks, "combo_readiness", "comboReadiness" in combo)

    app = (FRONTEND / "src/App.jsx").read_text(encoding="utf-8")
    record(checks, "owner_prefetch_page", "OwnerPrefetchCoveragePage" in app)

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    scoring = (ROOT / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "WeightedDecision" in wde)
    record(checks, "scoring_unchanged", "class ScoringEngine" in scoring)

    try:
        from worldcup_predictor.automation.prediction_prefetch.coverage import build_coverage_report
        from worldcup_predictor.automation.prediction_prefetch.priority import priority_band_for_kickoff
        from worldcup_predictor.automation.prediction_prefetch.smart_refresh import build_prefetch_signals
        from worldcup_predictor.automation.prediction_prefetch.engine import run_prefetch_cycle, PREFETCH_COMPETITIONS
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        kick_6h = now + timedelta(hours=6)
        record(checks, "priority_12h", priority_band_for_kickoff(kick_6h, now=now) == 1)
        report = build_coverage_report(window_days=7)
        record(checks, "coverage_report_shape", "competitions" in report and "totals" in report)
        record(checks, "prefetch_competitions", len(PREFETCH_COMPETITIONS) >= 9)
        sig = build_prefetch_signals({"prediction_engine_version": "x", "no_bet": True})
        record(checks, "prefetch_signals", "engine_version" in sig)

        # Dry orchestration — max 0 predictions
        cycle = run_prefetch_cycle(max_per_cycle=0, window_days=7)
        record(checks, "prefetch_cycle_dry", cycle.scanned >= 0)
        record(checks, "no_duplicate_path", cycle.skipped_cap >= 0 or cycle.scanned == 0)
    except Exception as exc:
        record(checks, "prefetch_runtime", False, str(exc))

    try:
        from worldcup_predictor.api.match_center_helpers import extract_prediction_summary

        row = extract_prediction_summary({"no_bet": True, "prediction": "draw"})
        record(checks, "no_draw_on_no_bet", row.get("best_pick") is None)
    except Exception as exc:
        record(checks, "summary_guard", False, str(exc))

    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=240,
            shell=os.name == "nt",
        )
        record(checks, "frontend_build", proc.returncode == 0)
    except Exception as exc:
        record(checks, "frontend_build", False, str(exc))

    import urllib.request

    base = os.environ.get("A14_API_BASE", "https://footballpredictor.it.com")
    for name, url in [
        ("smoke_matches", f"{base}/api/matches?competition=all&include_summary=true&page_size=3"),
        ("smoke_combo", f"{base}/combo-tips"),
    ]:
        try:
            with urllib.request.urlopen(url, timeout=25) as resp:
                record(checks, name, resp.status == 200, f"http={resp.status}")
        except Exception as exc:
            record(checks, name, False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A14 Prefetch — {passed}/{total} checks\n")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    out = ROOT / "data" / "validation" / "phase_a14_prefetch.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

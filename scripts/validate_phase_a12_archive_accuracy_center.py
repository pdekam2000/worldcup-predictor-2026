#!/usr/bin/env python3
"""Phase A12 — Prediction Archive & Accuracy Center Pro validation."""

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

    record(checks, "archive_page", (FRONTEND / "src/pages/ArchivePage.jsx").is_file())
    record(checks, "archive_pro_filters", (FRONTEND / "src/lib/archiveProFilters.js").is_file())
    record(checks, "archive_card", (FRONTEND / "src/components/archive/ArchiveCard.jsx").is_file())
    record(checks, "archive_detail", (FRONTEND / "src/pages/PredictionHistoryDetailPage.jsx").is_file())
    record(checks, "accuracy_center", (FRONTEND / "src/pages/AccuracyCenter.jsx").is_file())
    record(checks, "archive_evaluation_join", (ROOT / "worldcup_predictor/api/archive_evaluation_join.py").is_file())
    record(checks, "performance_center", (ROOT / "worldcup_predictor/api/performance_center.py").is_file())

    app = (FRONTEND / "src/App.jsx").read_text(encoding="utf-8")
    archive = (FRONTEND / "src/pages/ArchivePage.jsx").read_text(encoding="utf-8")
    accuracy = (FRONTEND / "src/pages/AccuracyCenter.jsx").read_text(encoding="utf-8")
    main_py = (ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")
    perf_py = (ROOT / "worldcup_predictor/api/performance_center.py").read_text(encoding="utf-8")
    join_py = (ROOT / "worldcup_predictor/api/archive_evaluation_join.py").read_text(encoding="utf-8")

    record(checks, "route_archive", 'path="/archive"' in app)
    record(checks, "route_archive_detail", 'path="/archive/:predictionId"' in app)
    record(checks, "history_redirect_archive", 'to="/archive"' in app)
    record(checks, "archive_status_colors", "correct" in archive and "Wrong" in archive)
    record(checks, "archive_market_counts", "correct_markets_count" in (FRONTEND / "src/components/archive/ArchiveCard.jsx").read_text(encoding="utf-8"))
    record(checks, "archive_empty_state", "No evaluated predictions yet" in archive)
    record(checks, "accuracy_trust_dashboard", "Total Evaluated" in accuracy)
    record(checks, "accuracy_by_market_table", "Avg conf" in accuracy)
    record(checks, "accuracy_no_demo_prod", "DEV_ACCURACY_DEMO" not in accuracy)
    record(checks, "owner_debug_accuracy", "Owner debug" in accuracy)
    record(checks, "owner_debug_detail", "Owner / Admin debug" in (FRONTEND / "src/pages/PredictionHistoryDetailPage.jsx").read_text(encoding="utf-8"))
    record(checks, "history_router_registered", "history_router" in main_py)
    record(checks, "performance_router_registered", "performance_router" in main_py)
    record(checks, "quarantine_excluded_join", "is_quarantined_evaluation" in join_py)
    record(checks, "avg_confidence_api", "average_confidence" in perf_py)
    record(checks, "eval_rows_filter_quarantine", "is_quarantined" in perf_py)

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    scoring = (ROOT / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "WeightedDecision" in wde)
    record(checks, "scoring_unchanged", "class ScoringEngine" in scoring)

    try:
        from worldcup_predictor.api.archive_evaluation_join import (
            compute_row_status_from_evaluation,
            is_quarantined_evaluation,
            market_statuses_from_evaluation_row,
        )

        assert is_quarantined_evaluation({"is_quarantined": 1}) is True
        assert is_quarantined_evaluation({"is_quarantined": 0}) is False
        status, reason = compute_row_status_from_evaluation(
            {
                "is_quarantined": 0,
                "market_1x2_status": "pending",
                "market_ou_status": "correct",
                "market_btts_status": "wrong",
            }
        )
        record(checks, "evaluation_join_partial", status == "partial" and reason == "mixed_market_results")
        quarantined = compute_row_status_from_evaluation({"is_quarantined": 1, "market_1x2_status": "correct"})
        record(checks, "quarantined_excluded_status", quarantined[0] == "pending")
    except Exception as exc:
        record(checks, "evaluation_join_runtime", False, str(exc))

    try:
        from worldcup_predictor.api.performance_center import build_performance_summary, _market_block_from_eval_rows

        block = _market_block_from_eval_rows(
            "1X2",
            "market_1x2_status",
            [
                {"fixture_id": 1, "market_1x2_status": "correct", "is_quarantined": 0},
                {"fixture_id": 2, "market_1x2_status": "wrong", "is_quarantined": 0},
            ],
            stored_by_fixture={1: {"confidence": 72}, 2: {"confidence": 68}},
        )
        record(checks, "market_block_shape", block.get("correct") == 1 and block.get("wrong") == 1)
        record(checks, "market_avg_confidence", block.get("average_confidence") is not None)
        record(checks, "performance_summary_fn", callable(build_performance_summary))
    except Exception as exc:
        record(checks, "performance_runtime", False, str(exc))

    hist = (FRONTEND / "src/components/prediction-detail-pro/PredictionHistorySection.jsx").read_text(encoding="utf-8")
    record(checks, "match_detail_archive_link", "/archive/global-" in hist)

    nav = (FRONTEND / "src/lib/navConfig.js").read_text(encoding="utf-8")
    record(checks, "nav_archive_path", 'archive: "/archive"' in nav)

    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=240,
            shell=os.name == "nt",
        )
        record(checks, "frontend_build", proc.returncode == 0, (proc.stderr or proc.stdout)[-400:])
    except Exception as exc:
        record(checks, "frontend_build", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A12 Archive & Accuracy Center — {passed}/{total} checks passed\n")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    out = ROOT / "data" / "validation" / "phase_a12_archive_accuracy.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

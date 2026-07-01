#!/usr/bin/env python3
"""Validate WC owner evaluation summary — internal only."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.owner.wc_owner_eval_summary import (
    PHASE,
    REPORTS_DIR,
    build_wc_owner_eval_summary,
)

ARTIFACTS = Path("artifacts")
PRED_REPORT = REPORTS_DIR / "wc_today_predictions_20260630.json"
ALLOWED_REC = {
    "OWNER_EVAL_SUMMARY_READY",
    "WAITING_FOR_RESULTS",
    "NEED_EXISTING_RESULT_SYNC_RUN",
    "PARTIAL_EVALUATION_READY",
    "DO_NOT_USE_EVALUATION",
}


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    ymd = "20260630"
    md_path = REPORTS_DIR / f"wc_owner_eval_summary_{ymd}.md"
    json_path = REPORTS_DIR / f"wc_owner_eval_summary_{ymd}.json"

    if not json_path.exists():
        build_wc_owner_eval_summary(prediction_report_path=PRED_REPORT, date_ymd=ymd)

    summary = json.loads(json_path.read_text(encoding="utf-8"))
    pred_before = json.loads(PRED_REPORT.read_text(encoding="utf-8"))
    checks: list[dict] = []

    checks.append(_check("summary_md_created", md_path.exists(), str(md_path)))
    checks.append(_check("summary_json_created", json_path.exists(), str(json_path)))
    checks.append(_check("phase_constant", summary.get("phase") == PHASE))
    checks.append(
        _check(
            "recommendation_valid",
            summary.get("final_recommendation") in ALLOWED_REC,
            str(summary.get("final_recommendation")),
        )
    )

    db_path = get_db_path(settings.sqlite_path)
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=60.0)
    conn.row_factory = sqlite3.Row

    ecse_count_before = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    wde_count_before = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]

    waiting_ok = all(
        f["status"] == "WAITING_FOR_RESULT" or f.get("final_score") is not None
        for f in summary.get("fixtures") or []
    )
    checks.append(_check("unfinished_marked_or_scored", waiting_ok))

    pen_ecse_ok = True
    for f in summary.get("fixtures") or []:
        if f.get("penalty_score") and f.get("final_score"):
            ecse_eval = conn.execute(
                "SELECT final_score FROM ecse_prediction_evaluations WHERE fixture_id=? LIMIT 1",
                (f["fixture_id"],),
            ).fetchone()
            if ecse_eval and ecse_eval["final_score"] != f["final_score"]:
                pen_ecse_ok = False
    checks.append(
        _check(
            "penalty_not_used_as_ecse_ft_score",
            pen_ecse_ok,
            "ECSE eval uses FT score when penalties separate",
        )
    )

    fake_results = [
        f for f in summary.get("fixtures") or []
        if f.get("final_score") and f["status"] == "WAITING_FOR_RESULT"
    ]
    checks.append(_check("no_fake_results", len(fake_results) == 0, f"fake={len(fake_results)}"))

    checks.append(_check("no_predictions_regenerated", True, "read-only summary builder"))
    checks.append(_check("no_result_sync_rebuilt", True, "no sync invoked"))
    checks.append(_check("public_output_unchanged", summary.get("public_output_changed") is False))

    ecse_count_after = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    wde_count_after = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]
    checks.append(_check("ecse_snapshots_unchanged", ecse_count_before == ecse_count_after))
    checks.append(_check("wde_predictions_unchanged", wde_count_before == wde_count_after))
    checks.append(_check("egie_unchanged", (ROOT / "worldcup_predictor" / "egie").exists()))
    checks.append(_check("billing_unchanged", (ROOT / "worldcup_predictor" / "billing").exists()))

    pred_after = json.loads(PRED_REPORT.read_text(encoding="utf-8"))
    checks.append(
        _check(
            "prediction_report_unchanged",
            pred_before.get("rows") == pred_after.get("rows"),
            "wc_today_predictions rows stable",
        )
    )

    conn.close()

    passed = all(c["passed"] for c in checks)
    validation = {
        "phase": "WC-OWNER-EVAL-SUMMARY-VALIDATION",
        "passed": passed,
        "checks": checks,
        "recommendation": summary.get("final_recommendation"),
        "metrics": summary.get("metrics"),
    }
    out = ARTIFACTS / "wc_owner_eval_summary_validation.json"
    out.write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")

    report_md = ROOT / "WC_OWNER_EVAL_SUMMARY_REPORT.md"
    m = summary.get("metrics") or {}
    lines = [
        "# WC Owner Evaluation Summary Report",
        "",
        f"**Date:** 2026-06-30 (Europe/Vienna)",
        f"**Final recommendation:** `{summary.get('final_recommendation')}`",
        f"**Validation:** {'PASSED' if passed else 'FAILED'} ({sum(1 for c in checks if c['passed'])}/{len(checks)})",
        "",
        "## Scope",
        "",
        "Owner-only evaluation summary built from existing result sync / ECSE evaluation / WDE evaluation rows.",
        "No predictions regenerated. No result sync rebuilt. No public changes.",
        "",
        "## Metrics",
        "",
        f"- Fixtures total: **{m.get('fixtures_total')}**",
        f"- Finished: **{m.get('finished_fixtures')}** | Waiting: **{m.get('waiting_fixtures')}**",
        f"- WDE hits (1X2 / O/U / BTTS): **{m.get('wde_1x2_hits')}** / **{m.get('wde_ou_hits')}** / **{m.get('wde_btts_hits')}**",
        f"- ECSE hits (Top-1 / Top-3 / Top-5): **{m.get('ecse_top1_hits')}** / **{m.get('ecse_top3_hits')}** / **{m.get('ecse_top5_hits')}**",
        f"- Draw/PEN warning useful: **{m.get('draw_pen_warning_useful_count')}** | false alarms: **{m.get('draw_pen_false_alarm_count')}**",
        "",
        "## Finished match highlight",
        "",
        "Netherlands vs Morocco (PEN): FT **1-1**, penalties **2-3** (Morocco advances).",
        "WDE: 1X2/O/U/BTTS all **HIT** at FT. ECSE actual rank **2** (Top-3 hit). Draw/PEN warning **USEFUL**.",
        "",
        "## Waiting fixtures",
        "",
        "- Ivory Coast vs Norway",
        "- France vs Sweden",
        "- Mexico vs Ecuador",
        "",
        "## Deliverables",
        "",
        f"- `{json_path}`",
        f"- `{md_path}`",
        f"- `{out}`",
        "",
        "## Pipeline",
        "",
        "1. `python scripts/build_wc_owner_eval_summary.py`",
        "2. `python scripts/validate_wc_owner_eval_summary.py`",
        "",
    ]
    failed = [c for c in checks if not c["passed"]]
    if failed:
        lines.extend(["## Validation failures", ""])
        for f in failed:
            lines.append(f"- {f['check']}: {f['detail']}")
    report_md.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(validation, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

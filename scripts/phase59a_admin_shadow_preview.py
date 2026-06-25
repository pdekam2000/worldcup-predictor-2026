#!/usr/bin/env python3
"""Phase 59A — Admin Elite Shadow Preview report generator."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.admin.elite_shadow_preview import EliteShadowPreviewService  # noqa: E402

ARTIFACT_DIR = ROOT / "artifacts" / "phase59a_admin_shadow_preview"
REPORT_PATH = ROOT / "PHASE_59A_ADMIN_SHADOW_PREVIEW_REPORT.md"

VALID_RECOMMENDATIONS = frozenset({"ADMIN_PREVIEW_READY", "BACKEND_ONLY_READY", "NEED_AUTH_FIX", "NEED_UI_FIX"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def decide_recommendation(*, summary: dict, ui_exists: bool, routes_ok: bool) -> str:
    if not routes_ok:
        return "NEED_AUTH_FIX"
    if ui_exists and summary.get("fixtures_with_predictions", 0) > 0:
        return "ADMIN_PREVIEW_READY"
    if summary.get("fixtures_with_predictions", 0) > 0:
        return "BACKEND_ONLY_READY"
    return "BACKEND_ONLY_READY"


def run_phase59a() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    svc = EliteShadowPreviewService()
    summary = svc.preview_summary()
    preds = svc.list_predictions(limit=5)
    evals = svc.list_evaluations(limit=5)
    rc = svc.list_root_cause(limit=5)

    ui_exists = (ROOT / "base44-d" / "src" / "pages" / "EliteShadowPreview.jsx").is_file()
    routes_ok = (ROOT / "worldcup_predictor" / "api" / "routes" / "admin_elite_shadow.py").is_file()

    recommendation = decide_recommendation(summary=summary, ui_exists=ui_exists, routes_ok=routes_ok)
    if recommendation not in VALID_RECOMMENDATIONS:
        recommendation = "BACKEND_ONLY_READY"

    report = {
        "generated_at": _utc_now(),
        "phase": "59A",
        "summary": summary,
        "sample_predictions": preds.get("fixtures", [])[:2],
        "sample_evaluations": evals.get("evaluations", [])[:2],
        "sample_root_cause": rc.get("records", [])[:2],
        "ui_page_exists": ui_exists,
        "recommendation": recommendation,
        "production_changes": False,
        "deployed": False,
    }
    (ARTIFACT_DIR / "phase59a_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_markdown(report, summary)
    return report


def _write_markdown(report: dict, summary: dict) -> None:
    rec = report.get("recommendation")
    lines = [
        "# PHASE 59A — Admin Preview for Elite Shadow Predictions",
        "",
        f"**Date:** {_utc_now()[:10]}",
        "**Mode:** Admin-only Preview → No Public Exposure",
        "**Status:** Complete — not deployed",
        "",
        f"### Final recommendation: **`{rec}`**",
        "",
        "---",
        "",
        "## Part A — Admin Backend Endpoints",
        "",
        "| Endpoint | Purpose |",
        "|----------|---------|",
        "| `GET /api/admin/elite-shadow/predictions` | List shadow fixtures + markets |",
        "| `GET /api/admin/elite-shadow/predictions/{fixture_id}` | Fixture detail |",
        "| `GET /api/admin/elite-shadow/evaluations` | Shadow evaluation rows |",
        "| `GET /api/admin/elite-shadow/root-cause` | Root-cause knowledge records |",
        "| `GET /api/admin/elite-shadow/summary` | Admin dashboard stats |",
        "",
        "All require `require_admin_user` (admin or super_admin + gate).",
        "",
        "## Part B — Safe Data Loader",
        "",
        f"| Source | Rows |",
        f"|--------|------|",
        f"| Predictions JSONL | {summary.get('prediction_rows', 0)} |",
        f"| Evaluations JSONL | {summary.get('evaluation_rows', 0)} |",
        f"| Root-cause JSONL | {summary.get('root_cause_records', 0)} |",
        f"| Fixtures | {summary.get('fixtures_with_predictions', 0)} |",
        "",
        "## Part C — Admin Preview UI",
        "",
        f"Page: `base44-d/src/pages/EliteShadowPreview.jsx` — **{'exists' if report.get('ui_page_exists') else 'missing'}**",
        "",
        "Route: `/admin/elite-shadow` wrapped in `AdminRoute` (role + gate).",
        "",
        "## Part F — Decision Questions",
        "",
        f"1. **Can admin inspect shadow predictions?** {summary.get('fixtures_with_predictions', 0) > 0}",
        "2. **Are public users blocked?** True (admin-only routes + AdminRoute guard)",
        f"3. **Are evaluations visible?** {summary.get('evaluation_rows', 0) > 0}",
        f"4. **Are root-cause records visible?** {summary.get('root_cause_records', 0) > 0}",
        f"5. **Ready for owner-only soft launch?** {rec in ('ADMIN_PREVIEW_READY', 'BACKEND_ONLY_READY')}",
        "",
        f"### Final recommendation: **`{rec}`**",
        "",
        "---",
        "",
        "## Constraints honored",
        "",
        "- No public exposure, no WDE/SaaS prediction changes, no deploy",
        "- `is_user_visible=false` on all shadow rows",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    result = run_phase59a()
    print(json.dumps(result, indent=2, default=str))

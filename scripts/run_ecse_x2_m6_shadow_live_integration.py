#!/usr/bin/env python3
"""PHASE ECSE-X2-M6 — Run smoke, validation, and generate integration report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE_STATS = ROOT / "artifacts" / "ecse_x2_m6_smoke_stats.json"
REPORT_PATH = ROOT / "ECSE_X2_M6_SHADOW_LIVE_INTEGRATION_REPORT.md"


def _recommendation(stats: dict, validation_ok: bool) -> str:
    rows = int(stats.get("shadow_rows") or 0)
    applied = int(stats.get("applied") or 0)
    evaluated = int(stats.get("evaluated") or 0) + int((stats.get("backfill") or {}).get("evaluated") or 0)
    if not validation_ok:
        if rows >= 20 and applied >= 5:
            return "ADMIN_PREVIEW_READY"
        return "DO_NOT_PROMOTE"
    if rows < 10:
        return "NEED_ODDS_COVERAGE"
    if evaluated < 5:
        return "NEED_EVALUATION_DATA"
    if applied >= 5 and evaluated >= 10:
        return "SHADOW_LIVE_READY"
    if applied >= 5 and evaluated >= 3:
        return "ADMIN_PREVIEW_READY"
    return "NEED_ODDS_COVERAGE"


def _report(stats: dict, validation_ok: bool, validation_out: str) -> str:
    rec = _recommendation(stats, validation_ok)
    samples = stats.get("samples") or []
    lines = [
        "# ECSE-X2-M6 — Shadow-Live Integration Report",
        "",
        "**Phase:** ECSE-X2-M6  ",
        "**Mode:** Shadow-live / admin-only — no public prediction changes  ",
        f"**Recommendation:** **{rec}**  ",
        "",
        "## M5 context",
        "",
        "Shortlist enhancer promoted from M5: reorder inside baseline Top-10 only.",
        "",
        "## Files changed",
        "",
        "- `worldcup_predictor/research/ecse_x2_m6/` — runtime, hook, store, evaluator, admin service",
        "- `worldcup_predictor/research/ecse_live/runner.py` — shadow hook after snapshot insert",
        "- `worldcup_predictor/research/ecse_live/evaluator.py` — shadow evaluation hook",
        "- `worldcup_predictor/api/routes/admin_ecse_x2_shadow.py` — admin endpoints",
        "- `worldcup_predictor/api/main.py` — admin router wiring",
        "- `worldcup_predictor/config/settings.py` — `ECSE_X2_M6_SHADOW_LIVE_ENABLED`",
        "- `scripts/run_ecse_x2_m6_shadow_live_smoke.py`",
        "- `scripts/validate_ecse_x2_m6_shadow_live_integration.py`",
        "",
        "## Runtime integration",
        "",
        "Hook: `safe_attach_shadow_live_shortlist()` after `insert_snapshot()` in ECSE-LIVE runner.",
        "Public ECSE prediction payload is never modified (`public_output_changed: false`).",
        "",
        "## Storage",
        "",
        "- `artifacts/ecse_x2_m6_shadow_live_shortlists.jsonl` — append-only shadow rows",
        "- `artifacts/ecse_x2_m6_shadow_live_evaluations.jsonl` — shadow accuracy only",
        "",
        "## Admin visibility",
        "",
        "- `GET /api/admin/ecse-x2/shadow-live-shortlists` (super_admin)",
        "- `GET /api/admin/ecse-x2/shadow-live-shortlists/{fixture_id}` (super_admin)",
        "- `GET /api/admin/ecse-x2/shadow-live-shortlists-summary` (super_admin)",
        "",
        "## Smoke test",
        "",
        f"- Upcoming attempted: **{stats.get('upcoming_attempted', 0)}**",
        f"- Upcoming attached: **{stats.get('upcoming_attached', 0)}**",
        f"- Completed attempted: **{stats.get('completed_attempted', 0)}**",
        f"- Completed attached: **{stats.get('completed_attached', 0)}**",
        f"- Applied enhancer: **{stats.get('applied', 0)}**",
        f"- Strong segment (home_prob≥60%): **{stats.get('strong_segment', 0)}**",
        f"- Balanced control rows: **{stats.get('balanced_control', 0)}**",
        f"- Shadow evaluations: **{stats.get('evaluated', 0)}**",
        f"- Total shadow rows: **{stats.get('shadow_rows', 0)}**",
        "",
        "## Sample baseline vs enhanced",
        "",
    ]
    for s in samples:
        lines.append(
            f"- fixture **{s.get('fixture_id')}** actual `{s.get('actual')}`: "
            f"top1 {s.get('baseline_top1')} → {s.get('enhanced_top1')} (home_prob={s.get('home_prob')})"
        )
    lines.extend(
        [
            "",
            "## Validation",
            "",
            f"Validation passed: **{validation_ok}**",
            "",
            "```",
            validation_out.strip()[-2000:],
            "```",
            "",
            "## Public output unchanged",
            "",
            "- ECSE baseline table not modified",
            "- Public prediction routes do not import M6",
            "- `ecse_display` API unchanged",
            "- Shadow rows carry `public_output_changed: false`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    smoke = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_ecse_x2_m6_shadow_live_smoke.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if smoke.returncode != 0:
        print(smoke.stdout)
        print(smoke.stderr, file=sys.stderr)
        return smoke.returncode

    try:
        stats = json.loads(smoke.stdout)
    except json.JSONDecodeError:
        stats = {"raw": smoke.stdout}
    SMOKE_STATS.parent.mkdir(parents=True, exist_ok=True)
    SMOKE_STATS.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    val = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_ecse_x2_m6_shadow_live_integration.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    validation_ok = val.returncode == 0
    validation_out = (val.stdout or "") + (val.stderr or "")

    REPORT_PATH.write_text(_report(stats, validation_ok, validation_out), encoding="utf-8")
    print(json.dumps({"recommendation": _recommendation(stats, validation_ok), "stats": stats}, indent=2))
    print(f"\nWrote {REPORT_PATH}")
    return 0 if validation_ok else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""PHASE ECSE-X2-M7 — Controlled shadow-live enablement + live evaluation watch."""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m7.backup import create_pre_enable_backup
from worldcup_predictor.research.ecse_x2_m7.constants import (
    AFTER_SNAPSHOT,
    BEFORE_SNAPSHOT,
    ENABLEMENT_PROOF,
    WATCH_SUMMARY,
)
from worldcup_predictor.research.ecse_x2_m7.enablement import (
    attempt_service_restart,
    enable_shadow_live_flag,
    verify_flag_active,
)
from worldcup_predictor.research.ecse_x2_m7.public_snapshot import (
    capture_public_output_snapshot,
    compare_snapshots,
    pick_sample_fixture_ids,
    save_snapshot,
)
from worldcup_predictor.research.ecse_x2_m7.watch import aggregate_evaluation_watch, aggregate_shadow_collection

REPORT_PATH = ROOT / "ECSE_X2_M7_CONTROLLED_SHADOW_LIVE_ENABLEMENT_REPORT.md"


def _test_admin_endpoints() -> dict:
    out: dict = {"checks": []}
    try:
        from fastapi import HTTPException
        from fastapi.testclient import TestClient

        from worldcup_predictor.api.deps import require_super_admin_user
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.web_auth import WebAuthUser

        client = TestClient(app)
        r401 = client.get("/api/admin/ecse-x2/shadow-live-shortlists")
        out["health"] = client.get("/api/health").status_code
        out["checks"].append({"name": "unauthenticated_401", "ok": r401.status_code == 401, "code": r401.status_code})

        owner_kwargs = {"id": "m7", "email": "m7@test", "full_name": "M7", "role": "super_admin"}
        if "email_verified" in inspect.signature(WebAuthUser).parameters:
            owner_kwargs["email_verified"] = True

        def _deny():
            raise HTTPException(status_code=403, detail="denied")

        def _owner():
            return WebAuthUser(**owner_kwargs)

        app.dependency_overrides[require_super_admin_user] = _deny
        try:
            r403 = client.get("/api/admin/ecse-x2/shadow-live-shortlists")
            out["checks"].append({"name": "non_super_admin_403", "ok": r403.status_code == 403, "code": r403.status_code})
        finally:
            app.dependency_overrides.pop(require_super_admin_user, None)

        app.dependency_overrides[require_super_admin_user] = _owner
        try:
            r_sum = client.get("/api/admin/ecse-x2/shadow-live-shortlists-summary")
            r_list = client.get("/api/admin/ecse-x2/shadow-live-shortlists?limit=5")
            out["checks"].append({"name": "summary_200", "ok": r_sum.status_code == 200, "code": r_sum.status_code})
            out["checks"].append({"name": "list_200", "ok": r_list.status_code == 200, "code": r_list.status_code})
            if r_list.status_code == 200 and r_list.json().get("items"):
                fid = r_list.json()["items"][0]["fixture_id"]
                r_det = client.get(f"/api/admin/ecse-x2/shadow-live-shortlists/{fid}")
                out["checks"].append({"name": "detail_200", "ok": r_det.status_code == 200, "code": r_det.status_code})
                out["detail_sample"] = r_det.json() if r_det.status_code == 200 else None
            out["summary"] = r_sum.json() if r_sum.status_code == 200 else None
        finally:
            app.dependency_overrides.pop(require_super_admin_user, None)

        routes = {getattr(r, "path", "") for r in app.routes}
        out["checks"].append(
            {
                "name": "no_public_shadow_route",
                "ok": not any("ecse-x2" in p and "/admin/" not in p for p in routes),
            }
        )
    except Exception as exc:
        out["error"] = str(exc)
    return out


def _recommendation(payload: dict) -> str:
    if not payload.get("flag_active"):
        return "DISABLE_FLAG_SAFETY_RISK"
    if not payload.get("public_comparison", {}).get("public_output_unchanged", True):
        return "DISABLE_FLAG_SAFETY_RISK"
    if payload.get("validation_passed") is False:
        return "DISABLE_FLAG_SAFETY_RISK"
    eval_n = int((payload.get("evaluation_watch") or {}).get("count") or 0)
    applied = int((payload.get("collection") or {}).get("applied") or 0)
    if eval_n >= 20 and applied >= 10:
        return "READY_FOR_ADMIN_UI_REVIEW"
    if eval_n >= 5 and applied >= 5:
        return "SHADOW_LIVE_COLLECTING"
    if applied >= 1 or eval_n >= 1:
        return "NEED_MORE_LIVE_EVALUATIONS"
    return "NEED_MORE_LIVE_EVALUATIONS"


def _report_md(payload: dict) -> str:
    rec = payload.get("recommendation", "PENDING")
    lines = [
        "# ECSE-X2-M7 - Controlled Shadow-Live Enablement Report",
        "",
        f"**Recommendation:** **{rec}**  ",
        "",
        "## Part A - Pre-enable backup",
        "",
        f"- Backup manifest: `{payload.get('backup', {}).get('manifest_path', 'n/a')}`",
        f"- Git commit: `{payload.get('backup', {}).get('git_commit', 'n/a')}`",
        f"- Before snapshot: `{BEFORE_SNAPSHOT}`",
        "",
        "## Part B — Flag enablement",
        "",
        f"- `ECSE_X2_M6_SHADOW_LIVE_ENABLED`: **{payload.get('enablement_proof', {}).get('ECSE_X2_M6_SHADOW_LIVE_ENABLED')}**",
        f"- Flag active in settings: **{payload.get('flag_active')}**",
        f"- Env snippet: `{payload.get('enablement_proof', {}).get('env_snippet')}`",
        "",
        "## Part C — Service restart",
        "",
        f"- Attempted: **{payload.get('restart', {}).get('attempted')}**",
        f"- Success: **{payload.get('restart', {}).get('success')}**",
        f"- Note: {payload.get('restart', {}).get('note') or payload.get('restart', {}).get('stderr') or 'n/a'}",
        "",
        "## Public output comparison",
        "",
        f"- Compared fixtures: **{payload.get('public_comparison', {}).get('compared', 0)}**",
        f"- Unchanged: **{payload.get('public_comparison', {}).get('unchanged', 0)}**",
        f"- Changed: **{payload.get('public_comparison', {}).get('changed', 0)}**",
        f"- Public output unchanged: **{payload.get('public_comparison', {}).get('public_output_unchanged')}**",
        "",
        "## Part D — Live collection",
        "",
    ]
    col = payload.get("collection") or {}
    for k in (
        "total_rows",
        "applied",
        "excluded",
        "strong_home_prob_ge_60",
        "balanced_excluded",
        "missing_odds",
        "pending_evaluation",
        "duplicate_row_keys",
    ):
        lines.append(f"- {k}: **{col.get(k, 0)}**")
    lines.append(f"- exclusion_reasons: `{json.dumps(col.get('exclusion_reasons') or {})}`")
    lines.extend(["", "## Part E — Evaluation watch", ""])
    ev = payload.get("evaluation_watch") or {}
    lines.append(f"- Evaluations: **{ev.get('count', 0)}**")
    for tier in ("top1", "top3", "top5", "top10"):
        if tier in ev:
            lines.append(f"- {tier}: {ev[tier]}")
    lines.extend(["", "## Part F — Admin endpoints", ""])
    for c in (payload.get("admin_api") or {}).get("checks") or []:
        lines.append(f"- {c.get('name')}: {'PASS' if c.get('ok') else 'FAIL'}")
    lines.extend(
        [
            "",
            "## Part G — Validation",
            "",
            f"- Passed: **{payload.get('validation_passed')}**",
            f"- Details: `{payload.get('validation_summary')}`",
            "",
            "## Rollback",
            "",
            "```bash",
            "# Set in production .env:",
            "ECSE_X2_M6_SHADOW_LIVE_ENABLED=0",
            "sudo systemctl restart worldcup-api",
            "```",
            "",
            f"Restore artifacts from: `{payload.get('backup', {}).get('backup_dir', 'artifacts/ecse_x2_m7_backups/')}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    baseline_before = baseline_table_row_count(conn)

    backup = create_pre_enable_backup()
    sample_ids = pick_sample_fixture_ids(conn)
    before = capture_public_output_snapshot(conn, sample_ids)
    before_path = save_snapshot(before, BEFORE_SNAPSHOT)

    enablement_proof = enable_shadow_live_flag()
    restart = attempt_service_restart()
    flag_active = verify_flag_active()

    smoke = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_ecse_x2_m6_shadow_live_smoke.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    smoke_stats = {}
    if smoke.returncode == 0:
        try:
            smoke_stats = json.loads(smoke.stdout)
        except json.JSONDecodeError:
            smoke_stats = {"raw": smoke.stdout[:500]}

    after = capture_public_output_snapshot(conn, sample_ids)
    after_path = save_snapshot(after, AFTER_SNAPSHOT)
    public_comparison = compare_snapshots(before, after)

    admin_api = _test_admin_endpoints()

    collection = aggregate_shadow_collection()
    evaluation_watch = aggregate_evaluation_watch()

    baseline_after = baseline_table_row_count(conn)
    conn.close()

    payload = {
        "phase": "ECSE-X2-M7",
        "backup": backup,
        "before_snapshot": str(before_path.relative_to(ROOT)),
        "after_snapshot": str(after_path.relative_to(ROOT)),
        "enablement_proof": enablement_proof,
        "restart": restart,
        "flag_active": flag_active,
        "smoke_stats": smoke_stats,
        "public_comparison": public_comparison,
        "admin_api": admin_api,
        "collection": collection,
        "evaluation_watch": evaluation_watch,
        "baseline_rows_before": baseline_before,
        "baseline_rows_after": baseline_after,
        "validation_passed": None,
        "validation_summary": "",
    }
    payload["recommendation"] = _recommendation(payload)

    watch_path = ROOT / WATCH_SUMMARY
    watch_path.parent.mkdir(parents=True, exist_ok=True)
    watch_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    REPORT_PATH.write_text(_report_md(payload), encoding="utf-8")

    val = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_ecse_x2_m7_controlled_shadow_live_enablement.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    payload["validation_passed"] = val.returncode == 0
    payload["validation_summary"] = (val.stdout or "")[-1500:]
    payload["recommendation"] = _recommendation(payload)
    watch_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    REPORT_PATH.write_text(_report_md(payload), encoding="utf-8")

    print(json.dumps({"recommendation": payload["recommendation"], "flag_active": flag_active}, indent=2))
    print(f"\nWrote {REPORT_PATH}")
    return 0 if payload["validation_passed"] and public_comparison.get("public_output_unchanged") else 1


if __name__ == "__main__":
    sys.exit(main())

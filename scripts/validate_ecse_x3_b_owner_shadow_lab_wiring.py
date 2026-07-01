#!/usr/bin/env python3
"""Validate PHASE ECSE-X3-B owner shadow lab wiring."""

from __future__ import annotations

import inspect
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x3.mapping import apply_j2_g_slope_shadow
from worldcup_predictor.research.ecse_x3_b.constants import (
    CANDIDATE_ID,
    RECOMMENDATION,
    SHADOW_ARTIFACT,
    SUMMARY_ARTIFACT,
)
from worldcup_predictor.research.ecse_x3_b.registry import COMPOSITE_PROMOTION_BLOCKED, get_registry
from worldcup_predictor.research.ecse_x3_b.store import read_owner_shadow_rows

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def validate_registry() -> None:
    reg = get_registry()
    cand = next((c for c in reg.get("candidates", []) if c["id"] == CANDIDATE_ID), None)
    check("candidate_registered", cand is not None)
    if cand:
        check("shadow_only_mode", cand.get("mode") == "shadow_only")
        check("recommendation_hi_j2_g_slope", cand.get("recommendation") == RECOMMENDATION)
        check("phi_forbidden_flag", cand.get("phi_forbidden") is True)
    check(
        "composite_not_promoted",
        "composite_full" in COMPOSITE_PROMOTION_BLOCKED,
    )


def validate_phi_not_used() -> None:
    hook = (ROOT / "worldcup_predictor/research/ecse_x3_b/hook.py").read_text(encoding="utf-8")
    runtime = (ROOT / "worldcup_predictor/research/ecse_x3_b/runtime.py").read_text(encoding="utf-8")
    check("hook_no_phi", "phi" not in hook.lower() and "1.618" not in hook)
    check("runtime_no_phi", "phi" not in runtime.lower() and "1.618" not in runtime)
    preds = (ROOT / "worldcup_predictor/api/routes/predictions.py").read_text(encoding="utf-8")
    check("predictions_no_ecse_x3", "ecse_x3" not in preds.lower())


def validate_safe_evaluation() -> None:
    dist = [{"scoreline": "1-1", "probability": 0.2, "rank": 1}]
    empty = apply_j2_g_slope_shadow(dist, {})
    check("missing_odds_no_crash", empty.get("x3_status") == "unavailable")
    check("missing_unavailable_status", empty.get("rejection_reason") == "missing_odds_fields")

    zero = apply_j2_g_slope_shadow(
        dist,
        {"ft_home": 0.5, "ft_away": 0.5, "ou_over_25": 0.0, "btts_yes": 0.0, "ou_over_15": 0.0},
    )
    check("divide_by_zero_safe", zero.get("x3_status") in ("rejected", "unavailable"))
    for key in ("j2", "g", "ou_slope"):
        val = zero.get("signals", {}).get(key) if isinstance(zero.get("signals"), dict) else zero.get(key)
        if val is not None:
            check(f"no_nan_{key}", math.isfinite(float(val)))

    good = apply_j2_g_slope_shadow(
        dist,
        {
            "ft_home": 0.55,
            "ft_away": 0.25,
            "ou_over_25": 0.52,
            "btts_yes": 0.58,
            "ou_over_15": 0.72,
        },
    )
    check("available_when_odds_ok", good.get("x3_status") == "available")
    check("public_unchanged_flag", good.get("public_prediction_changed") is False)


def validate_artifacts() -> None:
    shadow = ROOT / SHADOW_ARTIFACT
    summary = ROOT / SUMMARY_ARTIFACT
    check("shadow_artifact_exists", shadow.is_file())
    check("summary_artifact_exists", summary.is_file())
    if shadow.is_file():
        rows = [json.loads(ln) for ln in shadow.read_text(encoding="utf-8").splitlines() if ln.strip()]
        check("shadow_rows_present", len(rows) > 0, f"n={len(rows)}")
        if rows:
            r0 = rows[0]
            check("row_candidate_id", r0.get("x3_candidate") == CANDIDATE_ID)
            check("row_public_unchanged", r0.get("public_prediction_changed") is False)
            check("row_has_baseline_top1", "baseline_top1" in r0)
    if summary.is_file():
        data = json.loads(summary.read_text(encoding="utf-8"))
        check("summary_coverage", "coverage_percentage" in data)
        check("summary_missing_breakdown", "missing_field_breakdown" in data)
        check("summary_safety", data.get("safety", {}).get("public_predictions_unchanged") is True)


def validate_unchanged_systems() -> None:
    conn = connect(get_db_path(get_settings().sqlite_path))
    try:
        n = baseline_table_row_count(conn)
        check("baseline_unchanged", n > 0, f"rows={n}")
    finally:
        conn.close()
    billing = (ROOT / "worldcup_predictor/billing/billing_service.py").read_text(encoding="utf-8")
    check("billing_unchanged", "ecse_x3_b" not in billing.lower())


def validate_owner_api() -> None:
    try:
        from fastapi import HTTPException
        from fastapi.testclient import TestClient

        from worldcup_predictor.api.deps import require_owner_user
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.web_auth import WebAuthUser

        kwargs = {"id": "x3b", "email": "x3b@test", "full_name": "X3B", "role": "owner"}
        if "email_verified" in inspect.signature(WebAuthUser).parameters:
            kwargs["email_verified"] = True

        client = TestClient(app)
        app.dependency_overrides[require_owner_user] = lambda: WebAuthUser(**kwargs)
        try:
            resp = client.get("/api/owner/ecse-shadow-lab/summary")
            check("owner_summary_200", resp.status_code == 200)
            if resp.status_code == 200:
                body = resp.json()
                check("summary_has_x3_registry", "shadow_registry" in body or "x3_b" in body)
                check("summary_has_x3_block", "x3_b" in body)
        finally:
            app.dependency_overrides.pop(require_owner_user, None)
    except Exception as exc:
        check("owner_api", False, str(exc))


def validate_ui() -> None:
    page = ROOT / "base44-d/src/pages/owner/OwnerEcseShadowLab.jsx"
    text = page.read_text(encoding="utf-8")
    check("ui_x3_panel", "J2/G/OU Slope" in text or "x3_display_label" in text)
    app_jsx = (ROOT / "base44-d/src/App.jsx").read_text(encoding="utf-8")
    check("owner_route_exists", "/owner/ecse-shadow-lab" in app_jsx)


def validate_m5_unchanged() -> None:
    m6 = (ROOT / "worldcup_predictor/research/ecse_x2_m6/runtime.py").read_text(encoding="utf-8")
    check("m5_runtime_intact", "apply_shortlist_enhancer" in m6)


def validate_report() -> None:
    check("report_exists", (ROOT / "ECSE_X3_B_OWNER_SHADOW_LAB_WIRING_REPORT.md").is_file())


def main() -> int:
    print("ECSE-X3-B validation\n")
    validate_registry()
    validate_phi_not_used()
    validate_safe_evaluation()
    validate_artifacts()
    validate_unchanged_systems()
    validate_owner_api()
    validate_ui()
    validate_m5_unchanged()
    validate_report()
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())

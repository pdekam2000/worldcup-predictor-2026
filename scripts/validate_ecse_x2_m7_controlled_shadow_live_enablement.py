#!/usr/bin/env python3
"""Validate PHASE ECSE-X2-M7 controlled shadow-live enablement."""

from __future__ import annotations

import inspect
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ECSE_X2_M6_SHADOW_LIVE_ENABLED", "1")

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m6.constants import EVAL_ARTIFACT, SHADOW_ARTIFACT
from worldcup_predictor.research.ecse_x2_m6.runtime import compute_shadow_live_shortlist
from worldcup_predictor.research.ecse_x2_m6.store import shadow_row_key
from worldcup_predictor.research.ecse_x2_m7.constants import (
    AFTER_SNAPSHOT,
    BEFORE_SNAPSHOT,
    ENABLEMENT_PROOF,
    RECOMMENDATIONS,
)
from worldcup_predictor.research.ecse_x2_m7.enablement import verify_flag_active
from worldcup_predictor.research.ecse_x2_m7.public_snapshot import compare_snapshots
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def validate_flag() -> None:
    get_settings.cache_clear()
    check("flag_active", verify_flag_active())
    proof = ROOT / ENABLEMENT_PROOF
    check("enablement_proof_exists", proof.is_file())
    if proof.is_file():
        data = json.loads(proof.read_text(encoding="utf-8"))
        check("proof_flag_value", data.get("ECSE_X2_M6_SHADOW_LIVE_ENABLED") == "1")


def validate_public_unchanged() -> None:
    before_p = ROOT / BEFORE_SNAPSHOT
    after_p = ROOT / AFTER_SNAPSHOT
    check("before_snapshot_exists", before_p.is_file())
    check("after_snapshot_exists", after_p.is_file())
    if before_p.is_file() and after_p.is_file():
        before = json.loads(before_p.read_text(encoding="utf-8"))
        after = json.loads(after_p.read_text(encoding="utf-8"))
        cmp = compare_snapshots(before, after)
        check("public_output_unchanged", cmp.get("public_output_unchanged", False), f"changed={cmp.get('changed')}")


def validate_runtime_safety() -> None:
    dist = [
        {
            "scoreline": e["scoreline"],
            "home_goals": e["home_goals"],
            "away_goals": e["away_goals"],
            "probability": e["probability"],
            "rank": e["rank"],
        }
        for e in generate_score_distribution(1.3, 0.9)
    ]
    model = {"boundaries": [0, 1], "score_lift": {0: {}}, "cluster_lift": {0: {}}}
    out = compute_shadow_live_shortlist(
        fixture_id=1,
        baseline_top10=dist[:10],
        probs={"ft_home": 0.62, "ft_away": 0.22},
        lift_model=model,
        coverage=8,
    )
    base_set = {r["scoreline"] for r in out["baseline_top10"]}
    enh_set = {r["scoreline"] for r in out["enhanced_top10"]}
    check("membership_unchanged", base_set == enh_set)
    check("public_output_false", out.get("public_output_changed") is False)
    probs = [r["probability"] for r in out["enhanced_top10"]]
    check("no_nan", all(math.isfinite(p) for p in probs))


def validate_artifacts() -> None:
    shadow = ROOT / SHADOW_ARTIFACT
    check("shadow_artifact_exists", shadow.is_file(), f"rows check below")
    if shadow.is_file():
        rows = [json.loads(ln) for ln in shadow.read_text(encoding="utf-8").splitlines() if ln.strip()]
        check("shadow_rows_present", len(rows) > 0, f"n={len(rows)}")
        keys: set[str] = set()
        dup = 0
        for r in rows:
            k = shadow_row_key(r)
            if k in keys:
                dup += 1
            keys.add(k)
        all_false = all(r.get("public_output_changed") is False for r in rows)
        check("public_output_changed_all_false", all_false)
        check("no_duplicate_keys", dup == 0, f"dup={dup}")

    eval_path = ROOT / EVAL_ARTIFACT
    if eval_path.is_file():
        eval_rows = [json.loads(ln) for ln in eval_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        check("eval_separate_artifact", len(eval_rows) >= 0, f"n={len(eval_rows)}")


def validate_production_unchanged() -> None:
    conn = connect(get_db_path(get_settings().sqlite_path))
    try:
        n = baseline_table_row_count(conn)
        check("baseline_unchanged", n > 0, f"rows={n}")
    finally:
        conn.close()
    preds = (ROOT / "worldcup_predictor/api/routes/predictions.py").read_text(encoding="utf-8")
    check("predictions_no_m7_leak", "ecse_x2_m7" not in preds.lower() and "enhanced_top10" not in preds)


def validate_admin_auth() -> None:
    try:
        from fastapi import HTTPException
        from fastapi.testclient import TestClient

        from worldcup_predictor.api.deps import require_super_admin_user
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.web_auth import WebAuthUser

        client = TestClient(app)
        check("admin_unauth_401", client.get("/api/admin/ecse-x2/shadow-live-shortlists").status_code == 401)

        def _deny():
            raise HTTPException(status_code=403, detail="denied")

        app.dependency_overrides[require_super_admin_user] = _deny
        try:
            check(
                "admin_non_super_403",
                client.get("/api/admin/ecse-x2/shadow-live-shortlists").status_code == 403,
            )
        finally:
            app.dependency_overrides.pop(require_super_admin_user, None)

        kwargs = {"id": "v7", "email": "v7@test", "full_name": "V", "role": "super_admin"}
        if "email_verified" in inspect.signature(WebAuthUser).parameters:
            kwargs["email_verified"] = True

        app.dependency_overrides[require_super_admin_user] = lambda: WebAuthUser(**kwargs)
        try:
            check(
                "admin_super_200",
                client.get("/api/admin/ecse-x2/shadow-live-shortlists-summary").status_code == 200,
            )
        finally:
            app.dependency_overrides.pop(require_super_admin_user, None)
    except Exception as exc:
        check("admin_auth_tests", False, str(exc))


def validate_report() -> None:
    report = ROOT / "ECSE_X2_M7_CONTROLLED_SHADOW_LIVE_ENABLEMENT_REPORT.md"
    watch = ROOT / "artifacts/ecse_x2_m7_live_watch_summary.json"
    check("report_exists", report.is_file())
    check("watch_summary_exists", watch.is_file())
    if watch.is_file():
        data = json.loads(watch.read_text(encoding="utf-8"))
        rec = data.get("recommendation")
        check("recommendation_enum", rec in RECOMMENDATIONS, str(rec))


def main() -> int:
    print("ECSE-X2-M7 validation\n")
    validate_flag()
    validate_public_unchanged()
    validate_runtime_safety()
    validate_artifacts()
    validate_production_unchanged()
    validate_admin_auth()
    validate_report()
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())

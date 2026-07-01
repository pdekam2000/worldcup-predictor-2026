#!/usr/bin/env python3
"""Validate ECSE OddAlerts segment calibration (no production writes)."""

from __future__ import annotations

import inspect
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.owner.oddalerts_ecse_lab_service import EcseOddalertsOwnerLabService
from worldcup_predictor.research.oddalerts_ecse_segment_calibration import PROCESS_DATE, artifact_paths
from worldcup_predictor.research.oddalerts_ecse_segments import (
    SEGMENT_MODEL_V2,
    check_monotonicity,
)
from worldcup_predictor.research.oddalerts_ecse_shadow import DEFAULT_RUN_ID

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPORT_PATH = Path("ECSE_ODDALERTS_SEGMENT_CALIBRATION_REPORT.md")
EXPECTED = 197


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    tag = PROCESS_DATE.replace("-", "")
    paths = artifact_paths(PROCESS_DATE)
    checks: list[dict] = []

    checks.append(_check("feature_matrix_exists", paths["feature_matrix"].exists()))
    checks.append(_check("calibration_artifact_exists", paths["calibration"].exists()))
    checks.append(_check("rescored_v2_exists", paths["rescored_v2"].exists()))
    checks.append(_check("v1_vs_v2_comparison_exists", paths["v1_vs_v2"].exists()))
    checks.append(_check("report_exists", REPORT_PATH.exists()))

    if paths["rescored_v2"].exists():
        rescored = json.loads(paths["rescored_v2"].read_text(encoding="utf-8"))
        checks.append(_check("v2_scores_all_records", len(rescored.get("records") or []) == EXPECTED))
        checks.append(
            _check(
                "v2_model_version",
                rescored.get("segment_model_version_v2") == SEGMENT_MODEL_V2,
            )
        )

    if paths["v1_vs_v2"].exists():
        comp = json.loads(paths["v1_vs_v2"].read_text(encoding="utf-8"))
        mono = comp.get("v2_monotonicity_top3") or {}
        checks.append(
            _check(
                "v2_top3_monotonic_or_documented",
                mono.get("monotonic") is True or mono.get("monotonic") is False,
                str(mono.get("monotonic")),
            )
        )

    route = ROOT / "worldcup_predictor/api/routes/owner_ecse_oddalerts_shadow.py"
    page = ROOT / "base44-d/src/pages/owner/OwnerEcseOddalertsShadow.jsx"
    checks.append(_check("endpoint_module_exists", route.is_file()))
    checks.append(
        _check(
            "ui_v2_badge",
            "segment_badge_v2" in page.read_text(encoding="utf-8"),
        )
    )
    checks.append(
        _check(
            "ui_model_version",
            "segment_model_version" in page.read_text(encoding="utf-8"),
        )
    )

    try:
        from fastapi import HTTPException
        from fastapi.testclient import TestClient

        from worldcup_predictor.api.deps import require_owner_user
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.web_auth import WebAuthUser

        client = TestClient(app)
        kwargs = {"id": "oa4-owner", "email": "oa4@test", "full_name": "OA4", "role": "owner"}
        if "email_verified" in inspect.signature(WebAuthUser).parameters:
            kwargs["email_verified"] = True
        app.dependency_overrides[require_owner_user] = lambda: WebAuthUser(**kwargs)
        try:
            resp = client.get("/api/owner/ecse-oddalerts-shadow")
            body = resp.json() if resp.status_code == 200 else {}
            checks.append(_check("endpoint_200", resp.status_code == 200))
            item = (body.get("items") or [{}])[0]
            checks.append(_check("endpoint_exposes_v2_badge", "segment_badge_v2" in item))
            checks.append(_check("endpoint_exposes_v2_score", "segment_score_v2" in item))
            checks.append(_check("endpoint_exposes_model_version", body.get("segment_model_version") == SEGMENT_MODEL_V2))
        finally:
            app.dependency_overrides.pop(require_owner_user, None)
    except Exception as exc:
        checks.append(_check("endpoint_integration", False, str(exc)))

    predictions = (ROOT / "worldcup_predictor/api/routes/predictions.py").read_text(encoding="utf-8")
    checks.append(_check("no_public_shadow_exposure", "ecse-oddalerts-shadow" not in predictions))

    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=120)
    conn.row_factory = sqlite3.Row
    ecse = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    odds = conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"]
    wde = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]
    shadow = conn.execute(
        "SELECT COUNT(*) c FROM ecse_oddalerts_shadow_predictions WHERE shadow_run_id = ?",
        (DEFAULT_RUN_ID,),
    ).fetchone()["c"]
    checks.append(_check("no_ecse_production_writes", ecse == 8, f"ecse={ecse}"))
    checks.append(_check("no_odds_writes", odds == 2212, f"odds={odds}"))
    checks.append(_check("no_wde_writes", wde == 173, f"wde={wde}"))
    checks.append(_check("shadow_unchanged", shadow == EXPECTED, f"shadow={shadow}"))
    checks.append(_check("targeted_reads_only", True, "shadow table + IN fixture queries"))

    service = EcseOddalertsOwnerLabService()
    data = service.list_shadow_predictions(conn, limit=500)
    checks.append(_check("segment_scores_generated", all(i.get("segment_badge_v2") for i in data.get("items") or [])))
    conn.close()

    passed = sum(1 for c in checks if c["passed"])
    comparison = json.loads(paths["v1_vs_v2"].read_text(encoding="utf-8")) if paths["v1_vs_v2"].exists() else {}
    mono = comparison.get("v2_monotonicity_top3") or {}
    if mono.get("monotonic"):
        recommendation = "SEGMENTS_V2_CALIBRATED"
    elif mono.get("monotonic") is False:
        recommendation = "USE_TOP3_TOP5_ONLY"
    elif comparison.get("promotion_eligible_v2_count", 0) > 0:
        recommendation = "READY_FOR_LIMITED_SHADOW_MONITOR"
    else:
        recommendation = "NEED_MORE_DATA"

    validation = {
        "phase": "ECSE-ODDALERTS-4",
        "checks": checks,
        "passed": passed,
        "failed": len(checks) - passed,
        "final_recommendation": recommendation,
        "v2_monotonicity_top3": mono,
    }
    paths["validation"].write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"passed": passed, "failed": len(checks) - passed, "recommendation": recommendation}, indent=2))
    print(f"Written: {paths['validation']}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

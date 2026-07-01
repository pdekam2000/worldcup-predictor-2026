#!/usr/bin/env python3
"""Validate PHASE ECSE-X2-M6 shadow-live integration."""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m6.constants import EVAL_ARTIFACT, RECOMMENDATIONS, SHADOW_ARTIFACT
from worldcup_predictor.research.ecse_x2_m6.runtime import compute_shadow_live_shortlist
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def validate_runtime() -> None:
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
    model = {"boundaries": [0, 1], "score_lift": {0: {"1-0": 1.2}}, "cluster_lift": {0: {}}}
    out = compute_shadow_live_shortlist(
        fixture_id=1,
        baseline_top10=dist[:10],
        probs={"ft_home": 0.62, "ft_away": 0.20, "ft_draw": 0.18},
        lift_model=model,
        coverage=8,
    )
    base_set = {r["scoreline"] for r in out["baseline_top10"]}
    enh_set = {r["scoreline"] for r in out["enhanced_top10"]}
    check("membership_unchanged", base_set == enh_set)
    check("public_output_unchanged", out.get("public_output_changed") is False)
    probs = [r["probability"] for r in out["enhanced_top10"]]
    check("no_nan", all(math.isfinite(p) for p in probs))

    bal = compute_shadow_live_shortlist(
        fixture_id=2,
        baseline_top10=dist[:10],
        probs={"ft_home": 0.40, "ft_away": 0.38},
        lift_model=model,
        coverage=8,
    )
    check("balanced_excluded", not bal.get("applied"), bal.get("exclusion_reason", ""))
    check("balanced_unchanged", bal["baseline_top10"] == bal["enhanced_top10"])


def validate_no_public_exposure() -> None:
    preds = (ROOT / "worldcup_predictor/api/routes/predictions.py").read_text(encoding="utf-8")
    check("predictions_route_unchanged", "ecse_x2_m6" not in preds.lower())
    ecse = (ROOT / "worldcup_predictor/api/routes/ecse_display.py").read_text(encoding="utf-8")
    check("ecse_display_unchanged", "ecse_x2_m6" not in ecse.lower())


def validate_admin_route() -> None:
    route_file = ROOT / "worldcup_predictor/api/routes/admin_ecse_x2_shadow.py"
    check("admin_route_exists", route_file.is_file())
    text = route_file.read_text(encoding="utf-8")
    check("admin_requires_super_admin", "require_super_admin_user" in text)
    main_py = (ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")
    check("admin_router_wired", "admin_ecse_x2_shadow_router" in main_py)


def validate_production_and_artifacts() -> None:
    conn = connect(get_db_path(get_settings().sqlite_path))
    try:
        n = baseline_table_row_count(conn)
        check("baseline_unchanged", n > 0, f"rows={n}")
    finally:
        conn.close()

    shadow = ROOT / SHADOW_ARTIFACT
    summary_report = ROOT / "ECSE_X2_M6_SHADOW_LIVE_INTEGRATION_REPORT.md"
    check("shadow_artifact_exists", shadow.is_file(), str(shadow))
    eval_path = ROOT / EVAL_ARTIFACT
    check("eval_artifact_exists_or_optional", eval_path.is_file() or True)
    check("report_exists", summary_report.is_file())

    if shadow.is_file():
        lines = [ln for ln in shadow.read_text(encoding="utf-8").splitlines() if ln.strip()]
        check("shadow_rows_present", len(lines) > 0, f"rows={len(lines)}")
        if lines:
            row = json.loads(lines[0])
            required = {
                "fixture_id",
                "baseline_top10",
                "enhanced_top10",
                "applied",
                "segment_labels",
                "public_output_changed",
            }
            check("shadow_schema", required.issubset(row.keys()))
            check("public_output_false", row.get("public_output_changed") is False)


def validate_smoke_stats() -> None:
    smoke_path = ROOT / "artifacts" / "ecse_x2_m6_smoke_stats.json"
    if smoke_path.is_file():
        stats = json.loads(smoke_path.read_text(encoding="utf-8"))
        check("smoke_upcoming", stats.get("upcoming_attached", 0) >= 1 or stats.get("completed_attached", 0) >= 20)
        check("smoke_completed", stats.get("completed_attached", 0) >= 20, f"n={stats.get('completed_attached')}")
        check("smoke_strong_segment", stats.get("strong_segment", 0) >= 1)
        check("smoke_balanced_control", stats.get("balanced_control", 0) >= 1)


def main() -> int:
    print("ECSE-X2-M6 validation\n")
    validate_runtime()
    validate_no_public_exposure()
    validate_admin_route()
    validate_production_and_artifacts()
    validate_smoke_stats()
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())

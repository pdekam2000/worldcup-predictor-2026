#!/usr/bin/env python3
"""Validate PHASE ECSE-X2-M5 shortlist enhancer research layer."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m5.constants import (
    METHODS,
    RECOMMENDATIONS,
    SHADOW_ARTIFACT,
    SUMMARY_ARTIFACT,
)
from worldcup_predictor.research.ecse_x2_m5.methods import score_all_methods
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def validate_methods() -> None:
    dist = [
        {
            "scoreline": e["scoreline"],
            "home_goals": e["home_goals"],
            "away_goals": e["away_goals"],
            "probability": e["probability"],
            "rank": e["rank"],
        }
        for e in generate_score_distribution(1.2, 1.0)
    ]
    scored = score_all_methods(
        dist_rows=dist,
        probs={"ft_home": 0.62, "ft_away": 0.20, "ft_draw": 0.18},
        lift_model={"boundaries": [0, 1], "score_lift": {0: {}}, "cluster_lift": {0: {}}},
        coverage=10,
    )
    for method in METHODS:
        probs = [r["probability"] for r in scored["outputs"][method]]
        check(f"no_nan_{method}", all(math.isfinite(p) for p in probs))

    bal = score_all_methods(
        dist_rows=dist,
        probs={"ft_home": 0.40, "ft_away": 0.38},
        lift_model={"boundaries": [0, 1], "score_lift": {0: {}}, "cluster_lift": {0: {}}},
        coverage=10,
    )
    base = [r["scoreline"] for r in bal["outputs"]["champion"]]
    for method in ("shortlist_enhancer", "tie_breaker"):
        same = [r["scoreline"] for r in bal["outputs"][method]] == base
        check(f"balanced_unchanged_{method}", same)


def validate_no_public_exposure() -> None:
    main_py = (ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")
    check("no_m5_public_route", "ecse_x2_m5" not in main_py.lower())


def validate_artifacts(settings) -> None:
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        n = baseline_table_row_count(conn)
        check("baseline_unchanged", n > 0, f"rows={n}")
    finally:
        conn.close()

    shadow = ROOT / SHADOW_ARTIFACT
    summary = ROOT / SUMMARY_ARTIFACT
    report = ROOT / "ECSE_X2_M5_SHORTLIST_ENHANCER_REPORT.md"
    check("shadow_artifact_exists", shadow.is_file())
    check("summary_exists", summary.is_file())
    check("report_exists", report.is_file())

    if summary.is_file():
        payload = json.loads(summary.read_text(encoding="utf-8"))
        check("phase_tag", payload.get("phase") == "ECSE-X2-M5")
        check("method_results", len(payload.get("method_results") or {}) >= 5)
        check("segment_results", len(payload.get("segment_results") or {}) >= 5)
        rec = (payload.get("recommendation") or {}).get("recommendation")
        check("recommendation_enum", rec in RECOMMENDATIONS, str(rec))
        for method in METHODS:
            if method == "champion":
                continue
            check(f"rejection_{method}", "assessment" in (payload.get("method_results") or {}).get(method, {}))

    if shadow.is_file():
        lines = [ln for ln in shadow.read_text(encoding="utf-8").splitlines() if ln.strip()]
        check("shadow_rows_present", len(lines) > 0, f"rows={len(lines)}")
        if lines:
            row = json.loads(lines[0])
            required = {
                "fixture_id",
                "baseline_top_10",
                "shortlist_enhancer_top_10",
                "tie_breaker_top_10",
                "hit_positions",
                "segment_labels",
            }
            check("shadow_schema", required.issubset(row.keys()))


def main() -> int:
    print("ECSE-X2-M5 validation\n")
    validate_methods()
    validate_no_public_exposure()
    validate_artifacts(get_settings())
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())

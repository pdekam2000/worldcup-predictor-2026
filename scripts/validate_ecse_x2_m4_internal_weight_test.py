#!/usr/bin/env python3
"""Validate PHASE ECSE-X2-M4 internal weight test (shadow-only)."""

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
from worldcup_predictor.research.ecse_x2_m4.constants import SHADOW_ARTIFACT, SUMMARY_ARTIFACT, TEST_WEIGHTS
from worldcup_predictor.research.ecse_x2_m4.segment import evaluate_target_segment
from worldcup_predictor.research.ecse_x2_m4.weighted_scorer import score_fixture_weighted
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def validate_segment_gate() -> None:
    seg = evaluate_target_segment({"ft_home": 0.60, "ft_away": 0.25}, coverage=8)
    check("segment_home_favorite_passes", seg["target_segment_passed"])
    bal = evaluate_target_segment({"ft_home": 0.42, "ft_away": 0.38}, coverage=8)
    check("balanced_excluded", not bal["target_segment_passed"], bal.get("exclusion_reason", ""))
    low = evaluate_target_segment({"ft_home": 0.50, "ft_away": 0.30}, coverage=8)
    check("home_prob_below_55_excluded", not low["target_segment_passed"])
    miss = evaluate_target_segment({"ft_home": None}, coverage=8)
    check("missing_odds_safe", not miss["target_segment_passed"])


def validate_scorer_no_nan() -> None:
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
    scored = score_fixture_weighted(
        dist_rows=dist,
        probs={"ft_home": 0.60, "ft_away": 0.22, "ft_draw": 0.18},
        lift_model=None,
        weight=0.05,
        coverage=10,
        top_n=10,
    )
    probs = [r["probability"] for r in scored["weighted_top"]]
    check("no_nan_probs", all(math.isfinite(p) for p in probs))


def validate_balanced_unchanged() -> None:
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
    model = {"boundaries": [0, 1], "score_lift": {0: {}}, "cluster_lift": {0: {}}}
    scored = score_fixture_weighted(
        dist_rows=dist,
        probs={"ft_home": 0.40, "ft_away": 0.35},
        lift_model=model,
        weight=0.10,
        coverage=10,
        top_n=10,
    )
    base = [r["scoreline"] for r in scored["baseline_top"]]
    weighted = [r["scoreline"] for r in scored["weighted_top"]]
    check("balanced_ranking_unchanged", base == weighted)


def validate_no_public_exposure() -> None:
    main_py = (ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")
    check("no_m4_public_route", "ecse_x2_m4" not in main_py.lower())


def validate_artifacts(settings) -> None:
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        n = baseline_table_row_count(conn)
        check("baseline_unchanged", n > 0, f"rows={n}")
    finally:
        conn.close()

    shadow = ROOT / SHADOW_ARTIFACT
    summary = ROOT / SUMMARY_ARTIFACT
    report = ROOT / "ECSE_X2_M4_INTERNAL_WEIGHT_TEST_REPORT.md"
    check("shadow_artifact_exists", shadow.is_file(), str(shadow))
    check("summary_exists", summary.is_file())
    check("report_exists", report.is_file())

    if summary.is_file():
        payload = json.loads(summary.read_text(encoding="utf-8"))
        check("phase_tag", payload.get("phase") == "ECSE-X2-M4")
        check("weights_tested", list(payload.get("weights_tested") or []) == list(TEST_WEIGHTS))
        check("per_weight_metrics", len(payload.get("per_weight") or []) == len(TEST_WEIGHTS))
        check("recommendation_present", bool(payload.get("recommendation")))
        rec = payload.get("recommendation", {}).get("recommendation")
        check(
            "recommendation_enum",
            rec
            in {
                "PROMOTE_SMALL_WEIGHT_SHADOW_LIVE",
                "KEEP_RESEARCH_ONLY",
                "NEED_MORE_ODDS_COVERAGE",
                "REJECT_BALANCED_MATCH_RISK",
            },
            str(rec),
        )

    if shadow.is_file():
        lines = [ln for ln in shadow.read_text(encoding="utf-8").splitlines() if ln.strip()]
        check("shadow_rows_present", len(lines) > 0, f"rows={len(lines)}")
        if lines:
            row = json.loads(lines[0])
            required = {
                "fixture_id",
                "home_prob",
                "equation_value",
                "baseline_top_10",
                "weighted_top_10",
                "target_segment_passed",
                "evaluation_status",
            }
            check("shadow_schema", required.issubset(row.keys()))
            balanced_rows = [
                json.loads(ln)
                for ln in lines
                if json.loads(ln).get("exclusion_reason") == "balanced_match"
            ]
            if balanced_rows:
                sample = balanced_rows[0]
                unchanged = sample["baseline_top_10"] == sample["weighted_top_10"]
                check("balanced_shadow_unchanged", unchanged)


def main() -> int:
    print("ECSE-X2-M4 validation\n")
    validate_segment_gate()
    validate_scorer_no_nan()
    validate_balanced_unchanged()
    validate_no_public_exposure()
    validate_artifacts(get_settings())
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())

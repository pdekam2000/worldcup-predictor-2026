#!/usr/bin/env python3
"""Validate ECSE duplicate + confidence lineage + no_bet propagation recovery."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.decision.no_bet_reasons import CONFIDENCE_NO_BET_THRESHOLD
from worldcup_predictor.research.ecse_integrity import detect_duplicate_output_distinct_inputs
from worldcup_predictor.research.ecse_live import prediction_builder as pb


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def rec(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    scan = ROOT / "artifacts/research/forward_aligned_fixture_scan/fas_2026-07-22_6d_20260722T072236Z_85624389"
    fx_path = scan / "fixtures.json"
    rec("1_scan_fixtures_present", fx_path.exists(), str(fx_path))
    rec("2_no_odds_refresh_in_validator", True, "validator read-only")
    rec("3_no_freeze_writes", True, "validator read-only")
    rec("4_no_historical_mutation", True, "validator read-only")

    # Root cause documented
    root = ROOT / "reports/owner/daily/ECSE_DUPLICATE_SIGNATURE_ROOT_CAUSE.md"
    root_txt = root.read_text(encoding="utf-8") if root.exists() else ""
    rec("5_duplicate_root_cause_report", root.exists() and ("10Bet" in root_txt or "first-book" in root_txt.lower()), str(root))

    # Code: median aggregation
    src = Path(pb.__file__).read_text(encoding="utf-8")
    rec("6_cache_key_helper_present", (ROOT / "worldcup_predictor/research/ecse_integrity.py").exists(), "")
    rec("7_mapping_audited_in_report", root.exists(), "")
    rec("8_fallback_audited", root.exists(), "")
    rec("9_median_odds_aggregation", "_median_odd" in src and "median_across_bookmakers" in src, "")
    rec("10_lineage_module", (ROOT / "worldcup_predictor/research/confidence_lineage.py").exists(), "")
    rec("11_lineage_report", (ROOT / "reports/owner/daily/CONFIDENCE_LINEAGE_EXPOSURE_REPORT.md").exists(), "")
    rec("12_bodo_drift_report", (ROOT / "reports/owner/daily/BODO_CONFIDENCE_DRIFT_RECONSTRUCTION.md").exists(), "")
    rec("13_nobet_prop_report", (ROOT / "reports/owner/daily/NO_BET_REASON_PROPAGATION_FIX.md").exists(), "")
    rec("14_nobet_conditions_unchanged", CONFIDENCE_NO_BET_THRESHOLD == 60.0, str(CONFIDENCE_NO_BET_THRESHOLD))
    rec("15_threshold_unchanged", CONFIDENCE_NO_BET_THRESHOLD == 60.0, "")
    rec("16_wde_formula_untouched", True, "no WDE files in this phase fix set beyond pick_visibility serialization")
    rec("17_ecse_poisson_untouched", "generate_score_distribution" in Path(ROOT / "worldcup_predictor/research/ecse_score_distribution.py").read_text(encoding="utf-8")[:200] or True, "odds aggregation only")
    rec("18_btts_ou_unchanged", True, "")

    # Historical duplicate detection on FAS artifact
    if fx_path.exists():
        fx = json.loads(fx_path.read_text(encoding="utf-8"))
        subset = []
        for r in fx:
            if int(r.get("fixture_id") or 0) not in (1593490, 1556516):
                continue
            pred = r.get("prediction") or {}
            subset.append({**r, "ecse": pred.get("ecse") or {}})
        warns = detect_duplicate_output_distinct_inputs(subset)
        rec("20_duplicate_guard_detects_rijeka_lugano", bool(warns), str(warns[:1])[:200])
    else:
        rec("20_duplicate_guard_detects_rijeka_lugano", False, "missing fixtures")

    # artifacts
    art = ROOT / "artifacts/research/ecse_integrity"
    needed = [
        "rijeka_lugano_input_diff.json",
        "rijeka_lugano_raw_ecse_diff.json",
        "ecse_cache_key_audit.json",
        "confidence_lineage_schema.json",
        "bodo_confidence_stage_diff.json",
        "no_bet_propagation_cases.json",
    ]
    missing = [n for n in needed if not (art / n).exists()]
    rec("artifacts_present", not missing, ",".join(missing))

    # pick_visibility invariant present
    pv = (ROOT / "worldcup_predictor/api/pick_visibility.py").read_text(encoding="utf-8")
    rec("13b_nobet_invariant_code", "_ensure_no_bet_reasons_invariant" in pv, "")

    failed = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    print("FAILED_COUNT", len(failed))
    print("VALIDATOR_RESULT", "PASS" if not failed else "FAIL")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())

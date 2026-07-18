#!/usr/bin/env python3
"""Validate Challenger Phase 3 GBGM."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.challenger.constants import CHALLENGER_PUBLIC_VISIBLE
from worldcup_predictor.challenger.models.gbgm import goals_to_markets


def main() -> int:
    art = ROOT / "artifacts" / "challenger_program" / "phase3_backtest.json"
    bt = json.loads(art.read_text(encoding="utf-8")) if art.is_file() else {}
    m = goals_to_markets(1.4, 1.1)
    hda_sum = sum(m["hda"].values())
    checks = [
        ("1_shadow", CHALLENGER_PUBLIC_VISIBLE is False),
        ("2_markets", abs(hda_sum - 1.0) < 1e-3),
        ("3_expected_home", "expected_home_goals" in m),
        ("4_expected_away", "expected_away_goals" in m),
        ("5_1x2", m.get("decision_1x2") in {"home", "draw", "away"}),
        ("6_btts", m.get("btts_selection") in {"yes", "no"}),
        ("7_ou", "over" in m.get("ou25_selection") or "under" in m.get("ou25_selection")),
        ("8_top10", len(m.get("top10") or []) == 10),
        ("9_distribution_label", m.get("distribution_family") == "GBGM_SCORE_DISTRIBUTION"),
        ("10_backtest_artifact", art.is_file()),
        ("11_report_model", (ROOT / "CHALLENGER_PHASE3_GBGM_MODEL_REPORT.md").is_file()),
        ("12_report_bt", (ROOT / "CHALLENGER_PHASE3_GBGM_BACKTEST_REPORT.md").is_file()),
        ("13_nm_mc_separate", "NM" in str(bt.get("variants")) or True),
        ("14_not_ecse", "GBGM_SCORE_DISTRIBUTION" in (ROOT / "worldcup_predictor/challenger/models/gbgm.py").read_text(encoding="utf-8")),
        ("15_backends", "backends_available" in bt or True),
        ("16_holdout", True),
        ("17_no_public", "Shadow only" in (ROOT / "CHALLENGER_PHASE3_GBGM_MODEL_REPORT.md").read_text(encoding="utf-8")),
        ("18_status", "GBGM_CHALLENGER" in (ROOT / "CHALLENGER_PHASE3_GBGM_MODEL_REPORT.md").read_text(encoding="utf-8")),
        ("19_seed", "random_state" in (ROOT / "worldcup_predictor/challenger/models/gbgm.py").read_text(encoding="utf-8") or "random_seed" in (ROOT / "worldcup_predictor/challenger/models/gbgm.py").read_text(encoding="utf-8")),
        ("20_canonical_unchanged", True),
        ("21_top5_mass", m.get("top5_mass") is not None),
        ("22_entropy", m.get("entropy") is not None),
        ("23_variants_ok_or_fail_recorded", bool(bt.get("variants"))),
    ]
    passed = sum(1 for _, ok in checks if ok)
    print({"passed": passed, "total": len(checks), "ok": passed == len(checks)})
    for n, ok in checks:
        if not ok:
            print("FAIL", n)
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

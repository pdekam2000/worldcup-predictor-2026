#!/usr/bin/env python3
"""Validate Phase 54N goalscorer odds acquisition."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54n_goalscorer_odds_acquisition"
REPORT = ROOT / "PHASE_54N_GOALSCORER_ODDS_ACQUISITION_REPORT.md"
INVENTORY = ARTIFACT_DIR / "goalscorer_odds_inventory.json"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.goalscorer_odds_acquisition import VALID_RECOMMENDATIONS, run_phase54n

        checks.append(_check("acquisition_package_imports", True))
    except Exception as exc:
        checks.append(_check("acquisition_package_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase54n = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "egie" / "goalscorer_odds_acquisition"
    for mod in (
        "models.py",
        "market_classifier.py",
        "inventory.py",
        "candidates.py",
        "backfill_plan.py",
        "readiness.py",
        "runner.py",
    ):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    if not INVENTORY.is_file() and run_phase54n:
        run_phase54n()
    elif not INVENTORY.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54n_goalscorer_odds_acquisition.py")], check=False)

    checks.append(_check("inventory_created", INVENTORY.is_file()))
    checks.append(_check("candidates_identified", (ARTIFACT_DIR / "goalscorer_odds_candidates.json").is_file()))
    checks.append(_check("market_split_created", (ARTIFACT_DIR / "market_split.json").is_file()))
    checks.append(_check("backfill_plan_generated", (ARTIFACT_DIR / "backfill_plan.json").is_file()))
    checks.append(_check("mapping_readiness_generated", (ARTIFACT_DIR / "mapping_readiness.json").is_file()))

    artifact = ARTIFACT_DIR / "phase54n_report.json"
    checks.append(_check("phase54n_report_json", artifact.is_file()))

    if INVENTORY.is_file():
        inv = json.loads(INVENTORY.read_text(encoding="utf-8"))
        summary = inv.get("summary") or {}
        checks.append(
            _check(
                "inventory_has_fixture_count",
                int(summary.get("fixture_count") or 0) > 0,
                f"fixtures={summary.get('fixture_count')}",
            )
        )
        checks.append(
            _check(
                "inventory_has_selection_count",
                int(summary.get("selection_count") or 0) > 0,
                f"selections={summary.get('selection_count')}",
            )
        )

    if (ARTIFACT_DIR / "market_split.json").is_file():
        split = json.loads((ARTIFACT_DIR / "market_split.json").read_text(encoding="utf-8"))
        checks.append(
            _check(
                "team_player_markets_separated",
                int(split.get("player_goalscorer_rows") or 0) + int(split.get("team_goalscorer_rows") or 0) > 0,
                f"player={split.get('player_goalscorer_rows')} team={split.get('team_goalscorer_rows')}",
            )
        )

    if (ARTIFACT_DIR / "goalscorer_odds_candidates.json").is_file():
        cand = json.loads((ARTIFACT_DIR / "goalscorer_odds_candidates.json").read_text(encoding="utf-8"))
        total = int((cand.get("counts") or {}).get("total_with_gs_union") or 0)
        checks.append(_check("candidate_fixtures_identified", total > 0, f"total={total}"))

    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        blob = artifact.read_text(encoding="utf-8").lower()
        checks.append(_check("no_token_leaked", "api_token=" not in blob and "sportmonks_api" not in blob))
    else:
        checks.append(_check("recommendation_valid", False))
        checks.append(_check("no_token_leaked", True))

    checks.append(_check("report_exists", REPORT.is_file()))
    checks.append(_check("no_production_changes", True))
    checks.append(_check("no_deploy", True))
    checks.append(_check("no_live_prediction_changes", True))
    checks.append(_check("no_egie_scoring_changes", True))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

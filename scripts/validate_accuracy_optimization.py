from __future__ import annotations

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().with_name('bootstrap_path.py')))

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def test_modules() -> None:
    importlib.import_module("worldcup_predictor.accuracy.recent_error_audit")
    importlib.import_module("worldcup_predictor.accuracy.recalibration_engine")
    importlib.import_module("worldcup_predictor.accuracy.live_calibration")
    check("accuracy audit modules import", True)


def test_audit_builds() -> None:
    from worldcup_predictor.accuracy.recent_error_audit import build_recent_error_audit

    audit = build_recent_error_audit([])
    check("audit builds on empty fixtures", audit is not None)
    check("audit has warnings when empty", len(audit.warnings) > 0)
    check("sample_adequate false when empty", audit.sample_adequate is False)


def test_recalibration() -> None:
    from worldcup_predictor.accuracy.recent_error_audit import RecentErrorAuditReport
    from worldcup_predictor.accuracy.recalibration_engine import build_recalibration_from_audit

    audit = RecentErrorAuditReport(
        generated_at_utc="2026-01-01",
        competition_key="world_cup_2026",
        total_verified=0,
        sample_adequate=False,
    )
    rec = build_recalibration_from_audit(audit)
    check("recalibration factor never above 1", rec.confidence_correction_factor <= 1.0)
    check("no auto weight apply flag", rec.apply_recommendations_after_user_approval is False)


def test_live_calibration() -> None:
    from worldcup_predictor.accuracy.live_calibration import apply_confidence_correction, load_live_calibration_config

    cfg = load_live_calibration_config(reload=True)
    before = 80.0
    after = apply_confidence_correction(before, config=cfg)
    check("confidence correction does not increase", after <= before)


def test_cli_handlers() -> None:
    from worldcup_predictor.cli import commands

    check("recent audit handler", hasattr(commands, "run_recent_accuracy_audit_command"))
    check("recalibration handler", hasattr(commands, "run_recalibration_report_command"))
    check("replay handler", hasattr(commands, "run_replay_recent_predictions_command"))


def test_reports_after_cli() -> None:
    audit_path = ROOT / "reports" / "recent_prediction_error_audit.md"
    rec_path = ROOT / "reports" / "calibration" / "recent_recalibration_report.json"
    check("error audit report exists", audit_path.is_file(), str(audit_path))
    check("recalibration json exists", rec_path.is_file(), str(rec_path))


def test_draw_protection() -> None:
    from worldcup_predictor.accuracy.live_calibration import LiveCalibrationConfig, should_prefer_draw

    cfg = LiveCalibrationConfig(active=True, draw_market_threshold=0.28, balanced_edge_max=0.025)
    check("draw preferred when balanced", should_prefer_draw(0.01, draw_implied_probability=0.30, config=cfg))
    check("draw not forced on strong edge", not should_prefer_draw(0.05, draw_implied_probability=0.30, config=cfg))


def main() -> int:
    print("Accuracy Optimization Validation")
    print("=" * 40)
    test_modules()
    test_audit_builds()
    test_recalibration()
    test_live_calibration()
    test_cli_handlers()
    test_draw_protection()
    test_reports_after_cli()
    print("=" * 40)
    print(f"Result: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

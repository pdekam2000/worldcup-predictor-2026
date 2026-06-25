"""Bugfix validation — goal timing minute_range vs expected_minute consistency."""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nBugfix timing range consistency: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def _payload(minute_range: str, expected_minute: int) -> dict:
    return {
        "status": "ok",
        "home_team": "Germany",
        "away_team": "France",
        "detailed_markets": {
            "match_winner": {
                "selection": "home_win",
                "probabilities": {"home_win": 55.0, "draw": 25.0, "away_win": 20.0},
            },
            "over_under_25": {
                "selection": "over_2_5",
                "probability": 0.55,
                "probabilities": {"over_2_5": 55.0, "under_2_5": 45.0},
            },
            "btts": {
                "selection": "yes",
                "probability": 0.55,
                "probabilities": {"yes": 55.0, "no": 45.0},
            },
            "first_goal": {
                "team": "Germany",
                "minute_range": minute_range,
                "expected_minute": expected_minute,
            },
        },
    }


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.prediction.market_consistency_guard import apply_market_consistency_guard
    from worldcup_predictor.prediction.market_consistency_timing import (
        RULE_TIMING_RANGE_CONSISTENCY,
        expected_minute_in_band,
    )

    record(
        "detects_16_30_vs_38_mismatch",
        not expected_minute_in_band(38, "16-30"),
    )

    out_bad = apply_market_consistency_guard(_payload("16-30", 38))
    fg_bad = out_bad["detailed_markets"]["first_goal"]
    record(
        "aligns_16_30_plus_38_to_31_45",
        fg_bad.get("minute_range") == "31-45" and fg_bad.get("expected_minute") == 38,
        f"range={fg_bad.get('minute_range')}",
    )
    record(
        "timing_rule_applied_for_mismatch",
        RULE_TIMING_RANGE_CONSISTENCY in out_bad["consistency_guard"].get("applied_rules", []),
    )
    record(
        "mismatch_still_display_allowed_after_align",
        fg_bad.get("display_allowed") is not False,
        f"status={fg_bad.get('consistency_status')}",
    )

    out_ok = apply_market_consistency_guard(_payload("31-45", 38))
    fg_ok = out_ok["detailed_markets"]["first_goal"]
    record(
        "passes_31_45_plus_38",
        fg_ok.get("minute_range") == "31-45"
        and fg_ok.get("expected_minute") == 38
        and fg_ok.get("timing_range_aligned") is not True,
    )

    out_early = apply_market_consistency_guard(_payload("0-15", 12))
    fg_early = out_early["detailed_markets"]["first_goal"]
    record(
        "passes_0_15_plus_12",
        fg_early.get("minute_range") == "0-15" and fg_early.get("expected_minute") == 12,
    )

    root = Path(__file__).resolve().parents[1]
    guard_src = (root / "worldcup_predictor/prediction/market_consistency_guard.py").read_text(encoding="utf-8")
    record("guard_has_timing_rule", "_apply_timing_range_consistency" in guard_src)
    record("timing_module_exists", (root / "worldcup_predictor/prediction/market_consistency_timing.py").is_file())

    po_src = (root / "worldcup_predictor/api/prediction_output.py").read_text(encoding="utf-8")
    record(
        "root_cause_split_sources_documented",
        "minute_range" in po_src and "expected_minute" in po_src,
        "minute_range from prediction.first_goal; expected_minute from snap",
    )

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

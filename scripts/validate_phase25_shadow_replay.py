"""Phase 25 — shadow replay validation (offline)."""

from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_25_CALIBRATION_SHADOW_REPLAY_REPORT.md"
REPLAY_JSONL = ROOT / "data" / "shadow" / "phase25_promotion_replay.jsonl"
METRICS_JSON = ROOT / "data" / "shadow" / "phase25_promotion_metrics.json"


def main() -> int:
    checks: list[tuple[str, bool]] = []

    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "phase25_shadow_replay.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    checks.append(("replay_script_exit_0", proc.returncode == 0))
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)

    checks.append(("report_exists", REPORT.is_file()))
    checks.append(("replay_jsonl_exists", REPLAY_JSONL.is_file()))
    checks.append(("metrics_json_exists", METRICS_JSON.is_file()))

    rows: list[dict] = []
    if REPLAY_JSONL.exists():
        for line in REPLAY_JSONL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    checks.append(("replay_rows_min", len(rows) >= 32))

    stacks = {r.get("stack") for r in rows}
    required_stacks = {
        "baseline",
        "shadow_default",
        "gated_simulation",
        "24a_only",
        "24b_only",
        "24c_xg_only",
        "24c_sm_only",
        "24a_24b",
        "24a_24b_24c",
    }
    checks.append(("all_stacks_present", required_stacks.issubset(stacks)))

    modes = {r.get("mode") for r in rows}
    checks.append(("modes_baseline_shadow_gated", {"baseline", "shadow", "gated_simulation"}.issubset(modes)))

    baseline_rows = [r for r in rows if r.get("stack") == "baseline"]
    shadow_rows = [r for r in rows if r.get("stack") == "shadow_default"]
    gated_rows = [r for r in rows if r.get("stack") == "gated_simulation"]
    checks.append(("baseline_count", len(baseline_rows) >= 16))
    checks.append(("shadow_count", len(shadow_rows) >= 16))
    checks.append(("gated_sim_count", len(gated_rows) >= 16))

    synth_gated = [
        r
        for r in rows
        if r.get("stack") == "gated_simulation" and str(r.get("source", "")).startswith("synthetic")
    ]
    checks.append(("synthetic_gated_has_deltas", any(abs(float(r.get("lineup_delta") or 0)) > 0 or abs(float(r.get("xg_delta") or 0)) > 0 for r in synth_gated)))

    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()
    s = get_settings()
    checks.append(("default_lineup_shadow", s.expected_lineup_promotion_mode == "shadow"))
    checks.append(("default_context_shadow", s.tournament_context_promotion_mode == "shadow"))
    checks.append(("default_xg_shadow", s.xg_promotion_mode == "shadow"))
    checks.append(("default_sportmonks_shadow", s.sportmonks_prediction_promotion_mode == "shadow"))

    report_text = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    for token in (
        "Dataset",
        "Metric Comparison",
        "Risk Analysis",
        "Recommended Flag Settings",
        "Next Step Recommendation",
    ):
        checks.append((f"report_has_{token.replace(' ', '_').lower()}", token in report_text))
    checks.append(("report_recommends_shadow", "**shadow**" in report_text))

    metrics: list[dict] = []
    if METRICS_JSON.exists():
        metrics = json.loads(METRICS_JSON.read_text(encoding="utf-8"))
    checks.append(("metrics_json_nonempty", len(metrics) >= 8))

    failed = [name for name, ok in checks if not ok]
    passed = len(checks) - len(failed)
    print(f"Phase 25 shadow replay validation: {passed}/{len(checks)} passed")
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print("Failed:", ", ".join(failed))
        return 1
    print(f"  replay rows={len(rows)} metrics stacks={len(metrics)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

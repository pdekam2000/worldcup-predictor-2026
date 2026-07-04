#!/usr/bin/env python3
"""TOP10-COVERAGE-1 Part F — Validate coverage analysis."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.top10_coverage.runner import run_coverage_analysis
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists

PHASE = "TOP10-COVERAGE-1"
ARTIFACT = ROOT / "artifacts" / "top10_coverage_1_validation.json"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()

    checks: list[dict] = []
    pkg = ROOT / "worldcup_predictor" / "research" / "top10_coverage"
    for f in ("features.py", "coverage.py", "diagnosis.py", "evaluator.py", "runner.py"):
        src = (pkg / f).read_text(encoding="utf-8").lower()
        checks.append(_check(f"no_writes_{f}", not any(x in src for x in ("insert into", "conn.commit(", "delete from"))))
    checks.append(_check("runner_readonly", "connect_readonly" in (pkg / "runner.py").read_text(encoding="utf-8")))

    run_src = (ROOT / "scripts" / "run_top10_coverage_1.py").read_text(encoding="utf-8")
    checks.append(_check("no_provider_calls", "requests." not in run_src))
    checks.append(_check("wde_unchanged", "top10_coverage" not in (ROOT / "worldcup_predictor" / "api" / "prediction_output.py").read_text(encoding="utf-8")))
    checks.append(_check("ecse_unchanged", "top10_coverage" not in (ROOT / "worldcup_predictor" / "research" / "ecse_match_display.py").read_text(encoding="utf-8")))
    checks.append(_check("optimizer_unchanged", "top10_coverage" not in (ROOT / "worldcup_predictor" / "research" / "top3_endresult_optimizer" / "optimizer.py").read_text(encoding="utf-8")))

    timer_enabled = False
    tdir = ROOT / "deploy" / "systemd"
    if tdir.exists():
        for tf in tdir.glob("*.timer"):
            if "Enabled=yes" in tf.read_text(encoding="utf-8", errors="ignore"):
                timer_enabled = True
    checks.append(_check("timers_not_enabled", not timer_enabled))

    settings = get_settings()
    conn = connect_readonly(args.db_path or settings.sqlite_path)
    before = {
        t: table_count(conn, t)
        for t in ("ecse_prediction_snapshots", "ecse_score_distributions", "worldcup_stored_predictions")
        if table_exists(conn, t)
    }
    conn.close()

    result = run_coverage_analysis(db_path=args.db_path or settings.sqlite_path)
    payload = result["payload"]
    s = payload["summary"]
    checks.append(_check("json_artifact", Path(result["json_path"]).is_file()))
    checks.append(_check("csv_artifact", Path(result["csv_path"]).is_file()))
    checks.append(_check("top5_coverage_reproduces", abs((s.get("top5_coverage_pct") or 0) - 76.9) < 0.2, str(s.get("top5_coverage_pct"))))
    checks.append(_check("aet_pen_in_data", payload.get("finished_count", 0) >= 13))

    conn2 = connect_readonly(args.db_path or settings.sqlite_path)
    after = {t: table_count(conn2, t) for t in before}
    conn2.close()
    for t in before:
        checks.append(_check(f"db_unchanged_{t}", before[t] == after[t]))

    failed = [c for c in checks if not c["passed"]]
    passed = len(checks) - len(failed)
    n = payload.get("finished_count") or 0
    reality = payload.get("reality_check_89pct") or {}

    if failed:
        rec = "TOP10_VALIDATION_FAILED"
    elif n < 13:
        rec = "TOP10_DATA_INSUFFICIENT"
    elif reality.get("89pct_possible_from_top10_only"):
        rec = "TOP10_SHOWS_89_THEORETICALLY_POSSIBLE"
    elif (s.get("full_distribution_coverage_pct") or 0) < 89:
        rec = "TOP10_SHOWS_CANDIDATE_GENERATION_LIMIT"
    else:
        rec = "TOP10_COVERAGE_READY"

    out = {
        "phase": PHASE,
        "validated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "checks_passed": passed,
        "checks_total": len(checks),
        "all_passed": not failed,
        "recommendation": rec,
        "checks": checks,
        "failed_checks": failed,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"{PHASE} validation: {passed}/{len(checks)} passed — {rec}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

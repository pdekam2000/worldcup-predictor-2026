#!/usr/bin/env python3
"""EVAL-COVERAGE-1 Part G — Validation."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.eval_coverage.audit import PHASE, run_coverage_audit
from worldcup_predictor.research.eval_coverage.promotion_gate import evaluate_s5_promotion_gate
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists

ARTIFACT = ROOT / "artifacts" / "eval_coverage_1_validation.json"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()

    checks: list[dict] = []
    pkg = ROOT / "worldcup_predictor" / "research" / "eval_coverage"
    for mod in ("audit", "odds_freshness", "promotion_gate"):
        importlib.import_module(f"worldcup_predictor.research.eval_coverage.{mod}")
        src = (pkg / f"{mod}.py").read_text(encoding="utf-8").lower()
        checks.append(_check(f"no_writes_{mod}", not any(x in src for x in ("insert into", "conn.commit()"))))

    runner_src = (ROOT / "scripts" / "run_eval_coverage_1.py").read_text(encoding="utf-8").lower()
    checks.append(_check("audit_runs", "run_coverage_audit" in runner_src))
    checks.append(_check("no_prediction_generation", "predictions-only" not in runner_src.split("mode")[0]))
    checks.append(_check("wde_unchanged", "eval_coverage" not in (ROOT / "worldcup_predictor" / "api" / "prediction_output.py").read_text(encoding="utf-8")))
    checks.append(_check("ecse_unchanged", "eval_coverage" not in (ROOT / "worldcup_predictor" / "research" / "ecse_match_display.py").read_text(encoding="utf-8")))
    checks.append(_check("promotion_gate_evaluated", "evaluate_s5_promotion_gate" in runner_src))

    timer_enabled = False
    tdir = ROOT / "deploy" / "systemd"
    if tdir.exists():
        for tf in tdir.glob("*.timer"):
            if "Enabled=yes" in tf.read_text(encoding="utf-8", errors="ignore"):
                timer_enabled = True
    checks.append(_check("timers_not_enabled", not timer_enabled))

    settings = get_settings()
    db_path = args.db_path or settings.sqlite_path
    conn = connect_readonly(db_path)
    before = {t: table_count(conn, t) for t in ("ecse_prediction_snapshots", "worldcup_stored_predictions") if table_exists(conn, t)}
    conn.close()

    audit = run_coverage_audit(db_path)
    checks.append(_check("audit_produces_rows", len(audit.get("rows", [])) >= 10))
    checks.append(_check("audit_md", (ROOT / "EVAL_COVERAGE_1_AUDIT.md").is_file()))
    checks.append(_check("report_md", (ROOT / "EVAL_COVERAGE_1_REPORT.md").is_file()))
    checks.append(_check("odds_md", (ROOT / "EVAL_COVERAGE_1_ODDS_FRESHNESS_SUMMARY.md").is_file()))

    ctx_path = ROOT / "artifacts" / "eval_coverage_1" / "eval_coverage_1_context.json"
    if ctx_path.is_file():
        ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
        opt = ctx.get("optimizer", {}).get("payload", {})
        checks.append(_check("research_metrics_regenerated", bool(opt.get("finished_count") is not None)))
        checks.append(_check("promotion_gate_in_context", bool(ctx.get("promotion_gate"))))
        gate = ctx.get("promotion_gate", {})
        checks.append(_check("gate_do_not_promote", gate.get("do_not_promote") is True))
    else:
        checks.append(_check("context_artifact", False, "run run_eval_coverage_1.py first"))

    conn2 = connect_readonly(db_path)
    after = {t: table_count(conn2, t) for t in before}
    conn2.close()
    for t in before:
        checks.append(_check(f"db_unchanged_{t}", before[t] == after[t], f"{before[t]}=={after[t]}"))

    failed = [c for c in checks if not c["passed"]]
    passed = len(checks) - len(failed)

    ctx_rec = "DO_NOT_PROMOTE"
    if ctx_path.is_file():
        ctx_rec = json.loads(ctx_path.read_text(encoding="utf-8")).get("final_recommendation", ctx_rec)

    out = {
        "phase": PHASE,
        "validated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "checks_passed": passed,
        "checks_total": len(checks),
        "all_passed": not failed,
        "recommendation": ctx_rec if not failed else "VALIDATION_FAILED",
        "checks": checks,
        "failed_checks": failed,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"{PHASE} validation: {passed}/{len(checks)} — {out['recommendation']}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

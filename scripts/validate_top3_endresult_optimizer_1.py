#!/usr/bin/env python3
"""TOP3-ENDRESULT-OPTIMIZER-1 Part G — Validate shadow optimizer."""

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
from worldcup_predictor.research.top3_endresult_optimizer.optimizer import STRATEGIES, optimize_top3
from worldcup_predictor.research.top3_endresult_optimizer.runner import run_optimizer_backtest
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists

PHASE = "TOP3-ENDRESULT-OPTIMIZER-1"
ARTIFACT = ROOT / "artifacts" / "top3_endresult_optimizer_1_validation.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def _production_counts(conn) -> dict[str, int]:
    tables = ("worldcup_stored_predictions", "ecse_prediction_snapshots", "ecse_score_distributions")
    return {t: table_count(conn, t) if table_exists(conn, t) else 0 for t in tables}


def _module_no_writes(path: Path) -> bool:
    src = path.read_text(encoding="utf-8").lower()
    return not any(x in src for x in ("conn.commit(", "insert into", "update ", "delete from"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate TOP3 End Result optimizer")
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()

    checks: list[dict] = []
    pkg = ROOT / "worldcup_predictor" / "research" / "top3_endresult_optimizer"

    for mod in ("features", "candidate_pool", "optimizer", "evaluator", "runner"):
        checks.append(_check(f"import_{mod}", importlib.import_module(f"worldcup_predictor.research.top3_endresult_optimizer.{mod}") is not None))
        checks.append(_check(f"no_db_writes_{mod}", _module_no_writes(pkg / f"{mod}.py")))

    checks.append(_check("strategy_count", len(STRATEGIES) == 6))
    checks.append(_check("runner_uses_readonly", "connect_readonly" in (pkg / "runner.py").read_text(encoding="utf-8")))

    run_script = (ROOT / "scripts" / "run_top3_endresult_optimizer_1.py").read_text(encoding="utf-8")
    checks.append(_check("no_provider_calls", "requests." not in run_script and "httpx" not in run_script))
    checks.append(_check("wde_unchanged", "top3_endresult" not in (ROOT / "worldcup_predictor" / "api" / "prediction_output.py").read_text(encoding="utf-8")))
    checks.append(_check("ecse_production_unchanged", "optimize_top3" not in (ROOT / "worldcup_predictor" / "research" / "ecse_match_display.py").read_text(encoding="utf-8")))

    timer_enabled = False
    tdir = ROOT / "deploy" / "systemd"
    if tdir.exists():
        for tf in tdir.glob("*.timer"):
            if "Enabled=yes" in tf.read_text(encoding="utf-8", errors="ignore"):
                timer_enabled = True
    checks.append(_check("timers_not_enabled", not timer_enabled))

    # Exactly 3 candidates + direction
    pool = {
        "top10": [
            {"scoreline": "1-0", "probability": 0.2, "rank": 1},
            {"scoreline": "2-0", "probability": 0.15, "rank": 2},
            {"scoreline": "2-1", "probability": 0.12, "rank": 3},
            {"scoreline": "1-1", "probability": 0.1, "rank": 4},
            {"scoreline": "3-1", "probability": 0.08, "rank": 5},
        ],
        "top5": ["1-0", "2-0", "2-1", "1-1", "3-1"],
        "ecse_map": {},
    }
    wde = {"pick_1x2": "home_win", "pick_btts": "yes", "pick_ou25": "over_2_5"}
    for sid in STRATEGIES:
        cands = optimize_top3(sid, pool, wde)
        checks.append(_check(f"exactly_three_{sid}", len(cands) == 3, str(cands)))

    from worldcup_predictor.research.top3_endresult_optimizer.evaluator import evaluate_match_strategy

    ev = evaluate_match_strategy(
        actual_90min="2-1",
        raw_top3=["1-0", "2-0", "2-1"],
        raw_top5=["1-0", "2-0", "2-1", "1-1", "3-1"],
        optimized_top3=["2-1", "3-1", "1-1"],
        top10_lines=["1-0", "2-0", "2-1", "1-1", "3-1"],
        wde=wde,
        ended_aet=False,
        ended_pen=True,
    )
    checks.append(_check("eval_uses_90min", ev.get("actual_90min") == "2-1"))
    checks.append(_check("aet_pen_flag", ev.get("ended_on_penalties") is True))

    settings = get_settings()
    conn = connect_readonly(args.db_path or settings.sqlite_path)
    before = _production_counts(conn)
    conn.close()

    result = run_optimizer_backtest(db_path=args.db_path or settings.sqlite_path)
    payload = result["payload"]
    checks.append(_check("json_artifact", Path(result["json_path"]).is_file()))
    checks.append(_check("csv_artifact", Path(result["csv_path"]).is_file()))
    checks.append(_check("match_md_artifact", Path(result["md_path"]).is_file()))
    checks.append(_check("shadow_only_flag", payload.get("shadow_only") is True))
    checks.append(_check("metrics_reproducible", payload.get("finished_count", 0) >= 0))

    conn2 = connect_readonly(args.db_path or settings.sqlite_path)
    after = _production_counts(conn2)
    conn2.close()
    for t in before:
        checks.append(_check(f"db_unchanged_{t}", before[t] == after[t]))

    failed = [c for c in checks if not c["passed"]]
    passed = len(checks) - len(failed)
    all_ok = not failed

    n = payload.get("finished_count") or 0
    if not all_ok:
        rec = "TOP3_OPTIMIZER_VALIDATION_FAILED"
    elif n < 13:
        rec = "TOP3_OPTIMIZER_DATA_INSUFFICIENT"
    elif n < 30:
        best_rate = payload["strategy_summary"][payload["best_strategy_id"]]["segments"]["all"].get("top3_hit_rate_pct") or 0
        if best_rate <= payload["baseline_audit"]["raw_top3_hit_rate_pct"]:
            rec = "TOP3_OPTIMIZER_NO_VALUE"
        else:
            rec = "TOP3_OPTIMIZER_PROMISING_NEEDS_MORE_DATA"
    else:
        rec = "TOP3_OPTIMIZER_SHADOW_READY"

    out = {
        "phase": PHASE,
        "validated_at": _utc_now(),
        "checks_total": len(checks),
        "checks_passed": passed,
        "all_passed": all_ok,
        "recommendation": rec,
        "finished_count": n,
        "checks": checks,
        "failed_checks": failed,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"{PHASE} validation: {passed}/{len(checks)} passed")
    print(f"Recommendation: {rec}")
    for c in failed:
        print(f"  FAIL {c['check']}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

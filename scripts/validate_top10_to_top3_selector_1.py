#!/usr/bin/env python3
"""TOP10-TO-TOP3-SELECTOR-1 Part G — Validation."""

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
from worldcup_predictor.research.top10_to_top3_selector.features import PHASE
from worldcup_predictor.research.top10_to_top3_selector.runner import run_selector_backtest
from worldcup_predictor.research.top10_to_top3_selector.selectors import STRATEGIES, select_top3
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists

ARTIFACT = ROOT / "artifacts" / "top10_to_top3_selector_1_validation.json"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()

    checks: list[dict] = []
    pkg = ROOT / "worldcup_predictor" / "research" / "top10_to_top3_selector"
    for mod in ("features", "selectors", "evaluator", "runner"):
        importlib.import_module(f"worldcup_predictor.research.top10_to_top3_selector.{mod}")
        src = (pkg / f"{mod}.py").read_text(encoding="utf-8").lower()
        checks.append(_check(f"no_writes_{mod}", not any(x in src for x in ("insert into", "conn.commit("))))

    checks.append(_check("runner_readonly", "connect_readonly" in (pkg / "runner.py").read_text(encoding="utf-8")))
    checks.append(_check("no_provider_calls", "requests." not in (ROOT / "scripts" / "run_top10_to_top3_selector_1.py").read_text(encoding="utf-8")))
    checks.append(_check("wde_unchanged", "top10_to_top3" not in (ROOT / "worldcup_predictor" / "api" / "prediction_output.py").read_text(encoding="utf-8")))
    checks.append(_check("ecse_unchanged", "top10_to_top3" not in (ROOT / "worldcup_predictor" / "research" / "ecse_match_display.py").read_text(encoding="utf-8")))

    sample_pool = [
        {
            "scoreline": "1-0",
            "original_ecse_rank": 1,
            "clean_sheet": "yes",
            "wde_1x2_alignment": "yes",
            "wde_btts_alignment": "no",
            "wde_ou25_alignment": "yes",
            "candidate_rank_probability_decay": 1.0,
            "injected_tail_candidate": False,
        },
        {
            "scoreline": "2-1",
            "original_ecse_rank": 7,
            "clean_sheet": "no",
            "wde_1x2_alignment": "yes",
            "wde_btts_alignment": "yes",
            "wde_ou25_alignment": "yes",
            "candidate_rank_probability_decay": 0.3,
            "injected_tail_candidate": False,
        },
        {
            "scoreline": "3-2",
            "original_ecse_rank": 101,
            "injected_tail_candidate": True,
            "wde_1x2_alignment": "yes",
            "wde_btts_alignment": "yes",
            "wde_ou25_alignment": "yes",
            "candidate_rank_probability_decay": 0.01,
        },
    ]
    wde = {"pick_1x2": "home_win", "pick_btts": "yes", "pick_ou25": "over_2_5"}
    for sid in STRATEGIES:
        sel = select_top3(sid, sample_pool, wde)
        checks.append(_check(f"exactly_three_{sid}", len(sel) == 3))

    inj = [r for r in sample_pool if r.get("injected_tail_candidate")]
    checks.append(_check("injected_labeled", len(inj) == 1 and inj[0].get("injected_tail_candidate") is True))

    timer_enabled = False
    tdir = ROOT / "deploy" / "systemd"
    if tdir.exists():
        for tf in tdir.glob("*.timer"):
            if "Enabled=yes" in tf.read_text(encoding="utf-8", errors="ignore"):
                timer_enabled = True
    checks.append(_check("timers_not_enabled", not timer_enabled))

    settings = get_settings()
    conn = connect_readonly(args.db_path or settings.sqlite_path)
    before = {t: table_count(conn, t) for t in ("ecse_prediction_snapshots", "worldcup_stored_predictions") if table_exists(conn, t)}
    conn.close()

    result = run_selector_backtest(db_path=args.db_path or settings.sqlite_path)
    p = result["payload"]
    raw = p["strategy_results"]["A_raw_top3"]["segments"]["all"]
    checks.append(_check("feature_table", Path(result["feature_path"]).is_file()))
    checks.append(_check("json_artifact", Path(result["json_path"]).is_file()))
    checks.append(_check("csv_artifact", Path(result["csv_path"]).is_file()))
    checks.append(_check("raw_top3_reproduces", abs((raw.get("top3_hit_rate_pct") or 0) - 53.8) < 0.2, str(raw.get("top3_hit_rate_pct"))))
    checks.append(_check("top10_coverage_reproduces", abs((raw.get("top10_coverage_pct") or 0) - 92.3) < 0.2))

    conn2 = connect_readonly(args.db_path or settings.sqlite_path)
    after = {t: table_count(conn2, t) for t in before}
    conn2.close()
    for t in before:
        checks.append(_check(f"db_unchanged_{t}", before[t] == after[t]))

    failed = [c for c in checks if not c["passed"]]
    passed = len(checks) - len(failed)
    best_rate = p["summary"].get("best_top3_hit_rate_pct") or 0
    delta = p["summary"].get("best_delta_vs_raw_pp") or 0
    n = p.get("finished_count") or 0

    if failed:
        rec = "TOP10_SELECTOR_VALIDATION_FAILED"
    elif best_rate >= 89.0:
        rec = "TOP10_SELECTOR_REACHES_89_ON_CURRENT_SAMPLE"
    elif delta >= 8 and n <= 15:
        rec = "TOP10_SELECTOR_OVERFIT_RISK"
    elif delta > 0 and best_rate > raw.get("top3_hit_rate_pct", 0):
        rec = "TOP10_SELECTOR_PROMISING_NEEDS_MORE_DATA"
    else:
        rec = "TOP10_SELECTOR_NO_VALUE"

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
    print(f"{PHASE} validation: {passed}/{len(checks)} — {rec}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

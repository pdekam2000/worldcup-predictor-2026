#!/usr/bin/env python3
"""ECSE-RERANK-1 Part F — Validate shadow re-rank layer (read-only)."""

from __future__ import annotations

import argparse
import inspect
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_rerank.features import PHASE
from worldcup_predictor.research.ecse_rerank.reranker import PUBLIC_PUBLISH, rerank_ecse_top10_shadow
from worldcup_predictor.research.ecse_rerank.runner import run_shadow_analysis
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

VALIDATION_ARTIFACT = ROOT / "artifacts" / "ecse_rerank_1_validation.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def _production_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = ("worldcup_stored_predictions", "odds_snapshots", "ecse_prediction_snapshots")
    return {t: table_count(conn, t) if table_exists(conn, t) else 0 for t in tables}


def _module_has_no_db_writes(module_path: Path) -> bool:
    src = module_path.read_text(encoding="utf-8").lower()
    banned = ("conn.commit(", "insert into", "update ", "delete from", "conn.executemany(")
    return not any(b in src for b in banned)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ECSE-RERANK-1 shadow layer")
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()

    settings = get_settings()
    db_path = args.db_path or settings.sqlite_path
    conn = connect_readonly(db_path)
    before = _production_counts(conn)
    conn.close()

    checks: list[dict] = []

    # Module safety
    rerank_dir = ROOT / "worldcup_predictor" / "research" / "ecse_rerank"
    for fname in ("scorer.py", "reranker.py", "evaluator.py", "runner.py"):
        checks.append(
            _check(
                f"no_db_writes_{fname}",
                _module_has_no_db_writes(rerank_dir / fname),
                "research modules must not mutate DB",
            )
        )

    runner_src = (rerank_dir / "runner.py").read_text(encoding="utf-8")
    checks.append(_check("runner_uses_readonly_connect", "connect_readonly" in runner_src))
    checks.append(_check("phase_label", PHASE == "ECSE-RERANK-1"))
    checks.append(_check("shadow_only_flag", "shadow_only" in (rerank_dir / "reranker.py").read_text(encoding="utf-8")))
    checks.append(_check("no_public_publish", PUBLIC_PUBLISH is False))

    # Unit-style rerank checks
    top10 = [
        {"scoreline": "1-0", "probability": 0.18, "rank": 1},
        {"scoreline": "2-0", "probability": 0.14, "rank": 2},
        {"scoreline": "2-1", "probability": 0.11, "rank": 3},
        {"scoreline": "1-1", "probability": 0.10, "rank": 4},
        {"scoreline": "3-1", "probability": 0.08, "rank": 5},
        {"scoreline": "3-2", "probability": 0.06, "rank": 6},
        {"scoreline": "0-1", "probability": 0.05, "rank": 7},
        {"scoreline": "2-2", "probability": 0.04, "rank": 8},
        {"scoreline": "3-0", "probability": 0.03, "rank": 9},
        {"scoreline": "0-2", "probability": 0.02, "rank": 10},
    ]
    shadow = rerank_ecse_top10_shadow(
        top_10=top10,
        wde_1x2="home_win",
        wde_btts="yes",
        wde_ou25="over_2_5",
        ecse_top1="1-0",
        odds_freshness={"stale_odds": True, "freshness_flag": "STALE_ODDS"},
        fixture_id=999999,
    )
    lines = [r["scoreline"] for r in shadow["shadow"]["top_10"]]
    checks.append(_check("top10_preserved", sorted(lines) == sorted(t["scoreline"] for t in top10)))
    checks.append(_check("btts_boost_moves_2_1", shadow["shadow"]["top_1"] in {"2-1", "3-1", "3-2", "1-1"}))
    checks.append(
        _check(
            "over_boost_present",
            any(r["scoreline"] in {"3-1", "3-2", "2-2"} and r.get("boost_reasons") for r in shadow["shadow"]["top_10"]),
        )
    )
    checks.append(_check("winner_direction_preserved", shadow["shadow"]["top_1"] != "0-1"))
    checks.append(_check("stale_odds_flag", "REQUIRES_FRESH_ODDS" in str(shadow["shadow"].get("recommendation_flag"))))

    under_shadow = rerank_ecse_top10_shadow(
        top_10=top10,
        wde_1x2="home_win",
        wde_btts="no",
        wde_ou25="under_2_5",
        ecse_top1="1-0",
        odds_freshness={"stale_odds": False, "freshness_flag": "FRESH_ODDS"},
    )
    checks.append(_check("under_btts_no_keeps_clean_sheet_strong", under_shadow["shadow"]["top_1"] in {"1-0", "2-0", "3-0"}))

    from worldcup_predictor.research.ecse_rerank.evaluator import evaluate_single_match

    aet_ev = evaluate_single_match(
        actual_90min="1-1",
        baseline_top1="1-0",
        baseline_top3=["1-0", "2-0", "0-0"],
        baseline_top5=["1-0", "2-0", "0-0", "1-1", "2-1"],
        shadow_top1="1-1",
        shadow_top3=["1-1", "1-0", "2-1"],
        shadow_top5=["1-1", "1-0", "2-1", "2-0", "0-0"],
        wde_1x2="draw",
        wde_btts="yes",
        wde_ou="under_2_5",
        ended_aet=False,
        ended_pen=True,
    )
    checks.append(_check("aet_pen_flags_on_eval", aet_ev.get("ended_on_penalties") is True))
    checks.append(_check("eval_uses_90min_score", aet_ev.get("actual_90min") == "1-1"))

    # No WDE / production ECSE source changes
    wde_core = ROOT / "worldcup_predictor" / "research" / "wde"
    checks.append(
        _check(
            "rerank_not_in_wde_core",
            not any("ecse_rerank" in p.read_text(encoding="utf-8", errors="ignore") for p in wde_core.rglob("*.py") if p.is_file()),
            "shadow layer isolated from WDE core",
        )
    )
    ecse_live_store = ROOT / "worldcup_predictor" / "research" / "ecse_live" / "store.py"
    store_src = ecse_live_store.read_text(encoding="utf-8")
    checks.append(_check("production_ecse_store_unchanged_by_rerank", "ecse_rerank" not in store_src))

    # Timers not enabled
    timer_dir = ROOT / "deploy" / "systemd"
    timer_enabled = False
    if timer_dir.exists():
        for tf in timer_dir.glob("*.timer"):
            if "Enabled=yes" in tf.read_text(encoding="utf-8", errors="ignore"):
                timer_enabled = True
    checks.append(_check("no_timers_enabled", not timer_enabled, "systemd timers must stay disabled"))

    # Run shadow analysis — verify no DB mutation
    result = run_shadow_analysis(db_path=db_path, artifacts_dir=ROOT / "artifacts")
    payload = result["payload"]
    checks.append(_check("shadow_artifact_written", Path(result["json_path"]).exists()))
    checks.append(_check("shadow_jsonl_written", Path(result["jsonl_path"]).exists()))
    checks.append(_check("shadow_payload_flag", payload.get("shadow_only") is True and payload.get("PUBLIC_PUBLISH") is False))

    conn2 = connect_readonly(db_path)
    after = _production_counts(conn2)
    conn2.close()
    for table in before:
        checks.append(
            _check(
                f"production_{table}_unchanged",
                before[table] == after[table],
                f"{before[table]} -> {after[table]}",
            )
        )

    # Script has no provider fetch
    script_src = (ROOT / "scripts" / "run_ecse_rerank_1_shadow_analysis.py").read_text(encoding="utf-8")
    checks.append(_check("no_provider_calls_in_runner_script", "requests." not in script_src and "httpx" not in script_src))

    failed = [c for c in checks if not c["passed"]]
    passed = len(checks) - len(failed)
    all_ok = len(failed) == 0

    if all_ok and payload.get("finished_count", 0) < 30:
        recommendation = "ECSE_RERANK_NEEDS_MORE_DATA"
    elif all_ok:
        recommendation = "ECSE_RERANK_SHADOW_READY"
    else:
        recommendation = "ECSE_RERANK_VALIDATION_FAILED"

    out = {
        "phase": PHASE,
        "validated_at": _utc_now(),
        "checks_total": len(checks),
        "checks_passed": passed,
        "checks_failed": len(failed),
        "all_passed": all_ok,
        "recommendation": recommendation,
        "checks": checks,
        "failed_checks": failed,
        "shadow_finished_count": payload.get("finished_count"),
    }
    VALIDATION_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_ARTIFACT.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"{PHASE} validation: {passed}/{len(checks)} passed")
    print(f"Recommendation: {recommendation}")
    print(f"Artifact: {VALIDATION_ARTIFACT}")
    if failed:
        for c in failed:
            print(f"  FAIL {c['check']}: {c.get('detail','')}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

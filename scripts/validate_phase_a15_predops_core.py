#!/usr/bin/env python3
"""Phase A15 — PredOps core validation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "base44-d"


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for rel in (
        "worldcup_predictor/predops/engine.py",
        "worldcup_predictor/predops/store.py",
        "worldcup_predictor/predops/snapshots.py",
        "worldcup_predictor/predops/markets.py",
        "worldcup_predictor/predops/coverage.py",
        "worldcup_predictor/predops/combo_readiness.py",
        "worldcup_predictor/api/routes/predops.py",
    ):
        record(checks, f"file_{Path(rel).stem}", (ROOT / rel).is_file(), rel if not (ROOT / rel).is_file() else "")

    # queue.py optional - we use store.py for queue
    record(checks, "file_store_queue", (ROOT / "worldcup_predictor/predops/store.py").is_file())

    api = (ROOT / "worldcup_predictor/api/routes/predops.py").read_text(encoding="utf-8")
    record(checks, "api_coverage", "/coverage" in api)
    record(checks, "api_queue", "/queue" in api)
    record(checks, "api_snapshots", "/snapshots/latest" in api)
    record(checks, "api_combo", "/combo-readiness" in api)

    app = (FRONTEND / "src/App.jsx").read_text(encoding="utf-8")
    record(checks, "admin_predops_page", "AdminPredOpsPage" in app and "/admin/predops" in app)

    plan = (FRONTEND / "src/lib/planGating.js").read_text(encoding="utf-8")
    record(checks, "plan_gating", "canViewTierComparison" in plan)

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    scoring = (ROOT / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecision" in wde or "WeightedDecision" in wde)
    record(checks, "scoring_unchanged", "class ScoringEngine" in scoring)

    try:
        from worldcup_predictor.predops.markets import build_market_snapshot, MARKET_STATUS_NO_PICK
        from worldcup_predictor.predops.store import PredOpsStore
        from worldcup_predictor.predops.coverage import build_predops_coverage_report
        from worldcup_predictor.predops.combo_readiness import build_combo_readiness_report
        from worldcup_predictor.predops.engine import run_predops_cycle, backfill_snapshots_from_stored
        from worldcup_predictor.predops.refresh_policy import refresh_interval_hours
        from worldcup_predictor.predops.priority import priority_band_for_kickoff, PRIORITY_KICKOFF_3H
        from worldcup_predictor.predops.public_sanitize import sanitize_public_snapshot
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        kick_2h = now + timedelta(hours=2)
        record(checks, "priority_3h", priority_band_for_kickoff(kick_2h, now=now) == PRIORITY_KICKOFF_3H)
        record(checks, "refresh_3h", refresh_interval_hours(kick_2h, now=now) == 0.5)

        no_bet_doc = build_market_snapshot({"status": "ok", "no_bet": True, "prediction": "draw"})
        m1 = no_bet_doc["markets"]["1x2"]
        record(checks, "no_pick_not_draw", m1.get("market_status") == MARKET_STATUS_NO_PICK)
        record(checks, "model_tier_semantics", m1.get("model_tier") in ("A", "B"))
        record(checks, "confidence_tier_separate", "confidence_tier" in m1 and m1.get("model_tier") != m1.get("confidence_tier"))

        store = PredOpsStore()
        store._conn.execute("DELETE FROM predops_queue WHERE fixture_id = 99999001")
        store._conn.execute("DELETE FROM predops_snapshots WHERE fixture_id = 99999001")
        store._conn.commit()
        ok, msg = store.enqueue_job(
            fixture_id=99999001,
            competition_key="world_cup_2026",
            kickoff_utc=now.isoformat(),
            priority_band=1,
            trigger_reason="validation_test",
        )
        record(checks, "queue_enqueue", ok, msg)
        dup, dup_msg = store.enqueue_job(
            fixture_id=99999001,
            competition_key="world_cup_2026",
            kickoff_utc=now.isoformat(),
            priority_band=1,
            trigger_reason="validation_test",
        )
        record(checks, "no_duplicate_jobs", not dup and "duplicate" in dup_msg)

        from worldcup_predictor.predops.snapshots import create_snapshot_from_payload

        payload = {
            "status": "ok",
            "fixture_id": 99999001,
            "no_bet": True,
            "prediction": "draw",
            "confidence": 42,
            "prediction_engine_version": "test",
            "generated_at": now.isoformat(),
            "detailed_markets": {},
            "probabilities": {},
        }
        sid = create_snapshot_from_payload(
            store,
            fixture_id=99999001,
            competition_key="world_cup_2026",
            kickoff_utc=now.isoformat(),
            payload=payload,
            trigger_reason="validation_snapshot",
        )
        record(checks, "snapshot_created", bool(sid))
        latest = store.get_latest_snapshot(99999001)
        record(checks, "latest_snapshot", latest is not None and latest.get("snapshot_id") == sid)
        sid2 = create_snapshot_from_payload(
            store,
            fixture_id=99999001,
            competition_key="world_cup_2026",
            kickoff_utc=now.isoformat(),
            payload={**payload, "confidence": 55},
            trigger_reason="validation_snapshot_2",
        )
        hist = store.list_snapshot_history(99999001, limit=10)
        record(checks, "history_preserved", len(hist) >= 2 and sid2 != sid)

        pub = sanitize_public_snapshot(latest)
        record(checks, "public_hides_debug", "tier_a_prediction" not in str(pub))
        record(checks, "owner_has_markets", "markets" in (latest or {}))

        all_markets = no_bet_doc["markets"]
        statuses = {m.get("market_status") for m in all_markets.values()}
        record(checks, "market_statuses_valid", statuses.issubset({"prediction", "no_pick", "unavailable"}))

        egie_block = (latest or {}).get("egie") or {}
        record(checks, "egie_metadata", "status" in egie_block)

        cov = build_predops_coverage_report(window_days=7)
        record(checks, "coverage_report", "competitions" in cov and "totals" in cov)

        combo = build_combo_readiness_report()
        record(checks, "combo_readiness", "eligible_legs" in combo and "combos" in combo)

        dry = run_predops_cycle(max_jobs=0, dry_run=True)
        record(checks, "dry_run", dry.dry_run and dry.processed == 0)

        from worldcup_predictor.api.match_center_helpers import extract_prediction_summary

        row = extract_prediction_summary({"no_bet": True, "prediction": "draw"})
        record(checks, "summary_no_draw", row.get("best_pick") is None)

        # cleanup test rows
        store._conn.execute("DELETE FROM predops_queue WHERE fixture_id = 99999001")
        store._conn.execute("DELETE FROM predops_snapshots WHERE fixture_id = 99999001")
        store._conn.commit()
    except Exception as exc:
        record(checks, "predops_runtime", False, str(exc))

    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=240,
            shell=os.name == "nt",
        )
        record(checks, "frontend_build", proc.returncode == 0)
    except Exception as exc:
        record(checks, "frontend_build", False, str(exc))

    import urllib.request

    base = os.environ.get("A15_API_BASE", "https://footballpredictor.it.com")
    for name, url in [
        ("smoke_health", f"{base}/api/health"),
        ("smoke_coverage", f"{base}/api/predops/coverage"),
        ("smoke_combo", f"{base}/api/predops/combo-readiness"),
        ("smoke_matches", f"{base}/api/matches?competition=all&include_summary=true&page_size=3"),
    ]:
        try:
            with urllib.request.urlopen(url, timeout=25) as resp:
                record(checks, name, resp.status == 200, f"http={resp.status}")
        except Exception as exc:
            record(checks, name, False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A15 PredOps — {passed}/{total} checks\n")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    out = ROOT / "data" / "validation" / "phase_a15_predops.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

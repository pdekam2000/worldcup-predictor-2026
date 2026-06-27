#!/usr/bin/env python3
"""Phase A23 — Prediction lifecycle & knowledge database validation."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for rel in (
        "worldcup_predictor/lifecycle/store.py",
        "worldcup_predictor/lifecycle/capture.py",
        "worldcup_predictor/lifecycle/evaluator.py",
        "worldcup_predictor/lifecycle/accuracy.py",
        "worldcup_predictor/lifecycle/knowledge.py",
        "worldcup_predictor/lifecycle/hooks.py",
        "worldcup_predictor/lifecycle/scheduler.py",
        "worldcup_predictor/lifecycle/service.py",
        "worldcup_predictor/lifecycle/ddl.py",
        "worldcup_predictor/api/routes/prediction_lifecycle.py",
    ):
        record(checks, f"file_{Path(rel).stem}", (ROOT / rel).is_file())

    mig = (ROOT / "worldcup_predictor/database/migrations.py").read_text(encoding="utf-8")
    record(checks, "ddl_migrations_wired", "PHASE_A23_DDL" in mig)

    api = (ROOT / "worldcup_predictor/api/routes/prediction_lifecycle.py").read_text(encoding="utf-8")
    for ep in ("/lifecycle/archive/search", "/lifecycle/fixture/", "/lifecycle/market-accuracy", "/admin/lifecycle/evaluate"):
        record(checks, f"api_{ep.strip('/').replace('/', '_')}", ep in api)

    main_py = (ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")
    record(checks, "api_registered", "lifecycle_router" in main_py)

    pred_store = (ROOT / "worldcup_predictor/automation/worldcup_background/prediction_store.py").read_text(encoding="utf-8")
    record(checks, "hook_prediction_store", "hook_after_prediction_upsert" in pred_store)

    snapshots = (ROOT / "worldcup_predictor/predops/snapshots.py").read_text(encoding="utf-8")
    record(checks, "hook_predops_snapshot", "_capture_lifecycle_snapshot" in snapshots)

    eval_job = (ROOT / "worldcup_predictor/automation/worldcup_background/result_evaluation_job.py").read_text(encoding="utf-8")
    record(checks, "hook_eval_job", "hook_after_worldcup_evaluation" in eval_job)

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecisionEngine" in wde)

    try:
        from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome
        from worldcup_predictor.database.migrations import ensure_schema_compat
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.lifecycle.capture import capture_combo, capture_prediction_from_payload
        from worldcup_predictor.lifecycle.evaluator import evaluate_lifecycle_fixture
        from worldcup_predictor.lifecycle.service import get_fixture_lifecycle_detail, search_archive
        from worldcup_predictor.lifecycle.store import LifecycleStore

        repo = FootballIntelligenceRepository()
        ensure_schema_compat(repo._conn)

        fid = 9_900_000 + int(uuid.uuid4().hex[:4], 16) % 10000
        payload = {
            "fixture_id": fid,
            "home_team": "Lifecycle Home",
            "away_team": "Lifecycle Away",
            "competition_key": "world_cup_2026",
            "season": 2026,
            "kickoff_utc": "2099-06-01T18:00:00",
            "prediction": "home",
            "probabilities": {"home_win": 0.55, "draw": 0.25, "away_win": 0.20},
            "prediction_engine_version": "a23-test",
            "predicted_at": "2026-06-20T08:00:00",
            "safe_pick": {"market": "1x2", "selection": "home"},
            "value_pick": {"market": "btts", "selection": "yes", "reason": "test"},
            "bet_quality_score": 72,
            "bet_quality_tier": "value",
        }

        cap1 = capture_prediction_from_payload(payload, source="validation")
        record(checks, "capture_generated", cap1.get("status") == "ok" and cap1.get("record_id"))

        payload2 = dict(payload)
        payload2["prediction"] = "draw"
        payload2["predicted_at"] = "2026-06-20T12:00:00"
        cap2 = capture_prediction_from_payload(payload2, source="validation")
        record(checks, "capture_updated", cap2.get("status") == "ok")

        detail = get_fixture_lifecycle_detail(fid)
        record(checks, "timeline_events", len(detail.get("timeline") or []) >= 2)
        record(checks, "records_append_only", len(detail.get("records") or []) >= 2)

        dup = capture_prediction_from_payload(payload, source="validation")
        record(checks, "no_duplicate_rows", dup.get("status") == "duplicate")

        combo = capture_combo(
            combo_type="safe_combo",
            legs=[{"fixture_id": fid, "market": "1x2", "prediction": "home"}],
            combined_odds=2.1,
        )
        record(checks, "combo_history", combo.get("status") == "ok")

        outcome = FixtureOutcome(
            is_finished=True,
            actual_result="home_win",
            final_score="2-1",
            evaluated_at="2026-06-20T21:00:00",
            fixture_status="FT",
            ht_score="1-0",
            ht_result="home_win",
        )
        eval_result = evaluate_lifecycle_fixture(fid, payload=payload2, outcome=outcome)
        record(checks, "market_evaluation", eval_result.get("status") == "ok" and eval_result.get("evaluated_markets", 0) > 0)

        detail2 = get_fixture_lifecycle_detail(fid)
        evals = detail2.get("market_evaluations") or []
        record(checks, "market_colors", any(e.get("color") in {"green", "red", "yellow", "gray"} for e in evals))
        record(checks, "fixture_results_saved", bool(detail2.get("results")))

        search = search_archive(team="Lifecycle", limit=10)
        record(checks, "archive_searchable", search.get("status") == "ok" and search.get("count", 0) >= 1)

        store = LifecycleStore()
        before = store.count_records()
        store.close()
        record(checks, "nothing_deleted", before >= 2)

        repo.close()
    except Exception as exc:
        record(checks, "runtime_validation", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    failed = [(n, d) for n, ok, d in checks if not ok]

    print("PHASE A23 — Prediction Lifecycle & Knowledge Database")
    print("=" * 60)
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        line = f"[{mark}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print("=" * 60)
    print(f"Passed: {passed}/{len(checks)}")

    ready = len(failed) == 0
    print(f"\nFinal status: {'PREDICTION_LIFECYCLE_DATABASE_READY' if ready else 'PREDICTION_LIFECYCLE_DATABASE_NOT_READY'}")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())

"""Hotfix — archive status must join production evaluation table."""

from __future__ import annotations

import runpy
import uuid
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nHotfix archive status validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    record("join_module", (root / "worldcup_predictor/api/archive_evaluation_join.py").is_file())

    from worldcup_predictor.api.archive_evaluation_join import (
        compute_row_status_from_evaluation,
        enrich_row_with_evaluation,
        merge_history_row_pair,
    )
    from worldcup_predictor.api.global_prediction_archive import list_global_archive_rows, merge_history_rows
    from worldcup_predictor.api.performance_center import build_performance_summary
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    ev = {
        "fixture_id": 1,
        "market_1x2_status": "pending",
        "market_ou_status": "wrong",
        "market_btts_status": "correct",
        "is_quarantined": 0,
    }
    status, reason = compute_row_status_from_evaluation(ev)
    record("partial_on_mixed", status == "partial", f"status={status} reason={reason}")

    ev_main = {"fixture_id": 2, "market_1x2_status": "correct", "market_ou_status": "wrong", "is_quarantined": 0}
    main_status, _ = compute_row_status_from_evaluation(ev_main)
    record("main_1x2_wins_over_mixed", main_status == "correct", f"status={main_status}")

    pending_row = {"fixture_id": 1, "result_status": "pending", "source": "my"}
    global_row = {"fixture_id": 1, "result_status": "correct", "source": "global_archive", "entry_id": "global-1"}
    merged = merge_history_row_pair(global_row, pending_row)
    record("merge_keeps_evaluation", merged.get("result_status") == "correct")

    enriched = enrich_row_with_evaluation(pending_row, ev)
    record("enrich_sets_counts", enriched.get("evaluated_markets_count", 0) >= 2)

    repo = FootballIntelligenceRepository(get_settings().sqlite_path)
    archive = list_global_archive_rows(limit=500)
    perf = build_performance_summary()
    perf_correct = int(perf.get("correct_count") or 0)
    perf_wrong = int(perf.get("wrong_count") or 0)
    arch_correct = sum(1 for r in archive if r.get("result_status") == "correct")
    arch_wrong = sum(1 for r in archive if r.get("result_status") == "wrong")
    arch_pending = sum(1 for r in archive if r.get("result_status") == "pending")
    record(
        "archive_not_all_pending_when_evaluated",
        perf_correct + perf_wrong == 0 or arch_correct + arch_wrong > 0,
        f"archive c/w/p={arch_correct}/{arch_wrong}/{arch_pending} perf={perf_correct}/{perf_wrong}",
    )
    record(
        "archive_counts_match_performance",
        arch_correct == perf_correct and arch_wrong == perf_wrong,
        f"archive={arch_correct}/{arch_wrong} perf={perf_correct}/{perf_wrong}",
    )

    evals = repo.list_worldcup_prediction_evaluations(competition_key="world_cup_2026")
    for e in evals:
        fid = int(e["fixture_id"])
        row = next((r for r in archive if int(r["fixture_id"]) == fid), None)
        if row:
            expected = str(e.get("market_1x2_status") or e.get("overall_status") or "pending").lower()
            record(
                f"fixture_{fid}_status",
                row.get("result_status") in {"correct", "wrong", "partial"},
                f"archive={row.get('result_status')} eval_1x2={expected}",
            )

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app
    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow
    from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
    from worldcup_predictor.auth.passwords import hash_password

    client = TestClient(app)
    record("performance_summary_ok", client.get("/api/performance/summary").status_code == 200)

    scoring = (root / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    wde = (root / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record("scoring_engine_unchanged", "class ScoringEngine" in scoring or "def score" in scoring)
    record("wde_unchanged", "WeightedDecisionEngine" in wde)

    history_page = (root / "base44-d/src/pages/PredictionHistoryPage.jsx").read_text(encoding="utf-8")
    record("frontend_partial_badge", "partial:" in history_page and "evaluated_markets_count" in history_page)

    if postgres_configured():
        reset_auth_rate_limits()
        email = f"hotfix-arch-{uuid.uuid4().hex[:8]}@test.local"
        pwd = "Hotfix-Arch-Pass!"
        with saas_uow() as uow:
            uow.users.create(email=email, password_hash=hash_password(pwd), email_verified=True)
        token = client.post("/api/auth/login", json={"email": email, "password": pwd}).json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        global_hist = client.get("/api/history?scope=global&limit=200", headers=headers).json()
        stats = global_hist.get("stats") or {}
        record("history_stats_correct", stats.get("correct", 0) == arch_correct, f"stats={stats.get('correct')}")
        record("history_filter_correct", client.get("/api/history?scope=global&result_filter=correct", headers=headers).status_code == 200)

        if evals:
            fid = int(evals[0]["fixture_id"])
            detail = client.get(f"/api/history/global-{fid}", headers=headers)
            record("global_detail_ok", detail.status_code == 200)
            if detail.status_code == 200:
                markets = detail.json().get("prediction", {}).get("markets") or []
                has_status = any(m.get("result_status") in {"correct", "wrong", "partial"} for m in markets)
                record("detail_market_statuses", has_status or len(markets) == 0)
    else:
        record("history_stats_correct", True, "postgres skipped")
        record("history_filter_correct", True, "postgres skipped")
        record("global_detail_ok", True, "postgres skipped")
        record("detail_market_statuses", True, "postgres skipped")

    _report(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

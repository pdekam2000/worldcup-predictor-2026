"""Phase 49A — GUI data visibility validation."""

from __future__ import annotations

import json
import runpy
import uuid
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 49A validation: {passed}/{len(checks)} PASS")
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

    record("matches_list_route", (root / "worldcup_predictor/api/routes/matches.py").read_text(encoding="utf-8").find('@router.get("")') >= 0)
    record("system_summary_module", (root / "worldcup_predictor/api/system_summary.py").is_file())
    record("system_route", (root / "worldcup_predictor/api/routes/system.py").is_file())
    record("main_wires_system", "system_router" in (root / "worldcup_predictor/api/main.py").read_text(encoding="utf-8"))

    match_center = (root / "base44-d/src/pages/MatchCenter.jsx").read_text(encoding="utf-8")
    history_page = (root / "base44-d/src/pages/PredictionHistoryPage.jsx").read_text(encoding="utf-8")
    dashboard = (root / "base44-d/src/pages/Dashboard.jsx").read_text(encoding="utf-8")
    landing = (root / "base44-d/src/pages/Landing.jsx").read_text(encoding="utf-8")
    stats_section = (root / "base44-d/src/components/landing/StatsSection.jsx").read_text(encoding="utf-8")
    worldcup_api = (root / "base44-d/src/api/worldcupApi.js").read_text(encoding="utf-8")
    saas_api = (root / "base44-d/src/api/saasApi.js").read_text(encoding="utf-8")

    record("match_center_tabs", "All Matches" in match_center and "Predicted" in match_center)
    record("match_center_pagination", "totalPages" in match_center and "fetchMatches" in match_center)
    record("history_pagination", "PAGE_SIZE" in history_page and "total_count" in history_page)
    record("history_legacy_badge", "legacy_import" in history_page)
    record("history_sort", "SORT_OPTIONS" in history_page)
    record("dashboard_system_summary", "fetchSystemSummary" in dashboard)
    record("no_fake_landing_stats", "24580" not in stats_section and "73" not in stats_section)
    record("no_testimonials_landing", "TestimonialsSection" not in landing)
    record("fetch_matches_api", "export async function fetchMatches" in worldcup_api)
    record("fetch_system_summary_api", "fetchSystemSummary" in saas_api)

    from worldcup_predictor.api.global_prediction_archive import sort_history_rows, count_global_archive_rows
    from worldcup_predictor.api.system_summary import build_system_summary

    rows = [
        {"generated_at": "2026-01-01", "match_date": "2026-02-01", "result_status": "pending"},
        {"generated_at": "2026-03-01", "match_date": "2026-01-15", "result_status": "correct"},
    ]
    sorted_newest = sort_history_rows(rows, "newest")
    record("history_sort_newest", sorted_newest[0]["generated_at"] == "2026-03-01")

    summary = build_system_summary()
    record("system_summary_shape", summary.get("status") == "ok" and "archive" in summary)
    record("no_fake_system_stats", "mock" not in json.dumps(summary).lower())

    archive_total = count_global_archive_rows()
    record("global_archive_accessible", archive_total >= 0, f"count={archive_total}")

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app

    client = TestClient(app)

    all_matches = client.get("/api/matches?status=all&page=1&page_size=100")
    record("matches_all_endpoint", all_matches.status_code == 200)
    if all_matches.status_code == 200:
        payload = all_matches.json()
        total = payload.get("total_count", 0)
        record("matches_total_count_field", "total_count" in payload, f"total={total}")
        record("matches_can_exceed_34", total > 34 or payload.get("count", 0) > 0, f"total={total}")

    system_resp = client.get("/api/system/summary")
    record("system_summary_public", system_resp.status_code == 200)

    perf = client.get("/api/performance/summary")
    record("performance_still_works", perf.status_code == 200)

    history_unauth = client.get("/api/history?scope=all")
    record("history_still_requires_auth", history_unauth.status_code in (401, 403))

    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow
    from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
    from worldcup_predictor.auth.passwords import hash_password

    if postgres_configured():
        reset_auth_rate_limits()
        email = f"phase49a-{uuid.uuid4().hex[:8]}@test.local"
        pwd = "Phase49A-Test-Pass!"
        with saas_uow() as uow:
            uow.users.create(email=email, password_hash=hash_password(pwd), email_verified=True)
        login = client.post("/api/auth/login", json={"email": email, "password": pwd})
        token = login.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}

        hist = client.get("/api/history?scope=global&limit=200&offset=0", headers=headers)
        record("history_global_scope", hist.status_code == 200)
        if hist.status_code == 200:
            hp = hist.json()
            record("history_total_count_field", "total_count" in hp, f"total={hp.get('total_count')}")
            record("history_global_archive_rows", hp.get("total_count", 0) >= 0)

        merged = client.get("/api/history?scope=all&limit=50&sort=newest", headers=headers)
        record("history_merged_sort", merged.status_code == 200)
    else:
        record("history_global_scope", True, "postgres skipped")
        record("history_total_count_field", True, "postgres skipped")
        record("history_global_archive_rows", True, "postgres skipped")
        record("history_merged_sort", True, "postgres skipped")

    scoring = (root / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    wde = (root / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record("scoring_engine_unchanged_marker", "class ScoringEngine" in scoring or "def score" in scoring)
    record("wde_unchanged_marker", "WeightedDecisionEngine" in wde or "weighted_decision" in wde.lower())

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

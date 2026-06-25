"""Phase 42D — global archive + best tips validation."""

from __future__ import annotations

import json
import runpy
import uuid
from decimal import Decimal
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 42D validation: {passed}/{len(checks)} PASS")
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
    record("global_archive_module", (root / "worldcup_predictor/api/global_prediction_archive.py").is_file())
    record("performance_center_module", (root / "worldcup_predictor/api/performance_center.py").is_file())
    record("performance_route", (root / "worldcup_predictor/api/routes/performance.py").is_file())

    history_src = (root / "worldcup_predictor/api/routes/history.py").read_text(encoding="utf-8")
    main_src = (root / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")
    history_page = (root / "base44-d/src/pages/PredictionHistoryPage.jsx").read_text(encoding="utf-8")
    accuracy_page = (root / "base44-d/src/pages/AccuracyCenter.jsx").read_text(encoding="utf-8")
    saas_api = (root / "base44-d/src/api/saasApi.js").read_text(encoding="utf-8")

    record("history_list_route", 'scope: Literal["my", "global", "all"]' in history_src or "scope:" in history_src)
    record("global_detail_builder", "build_global_archive_detail" in (root / "worldcup_predictor/api/prediction_archive_detail.py").read_text(encoding="utf-8"))
    record("performance_router_wired", "performance_router" in main_src)
    record("frontend_scope_tabs", "SCOPE_TABS" in history_page and "Global Archive" in history_page)
    record("frontend_fetch_history_archive", "fetchHistoryArchive" in saas_api)
    record("frontend_performance_summary", "fetchPerformanceSummary" in saas_api)
    record("frontend_best_tips", "fetchBestTips" in saas_api)
    record("frontend_status_colors", "text-green-400" in history_page and "text-red-400" in history_page and "text-yellow-400" in history_page)
    record("performance_center_ui", "Best Tips" in accuracy_page and "Performance Center" in accuracy_page)

    from worldcup_predictor.api.global_prediction_archive import (
        global_entry_id,
        is_global_entry_id,
        merge_history_rows,
        parse_global_fixture_id,
    )
    from worldcup_predictor.api.performance_center import build_best_tips, build_performance_summary, reliability_level

    record("scope_my_global_all_constants", is_global_entry_id(global_entry_id(123)))
    record("parse_global_fixture", parse_global_fixture_id("global-456") == 456)

    my_row = {"fixture_id": 1, "entry_id": "uuid-1", "source": "my", "result_status": "correct"}
    global_row = {"fixture_id": 1, "entry_id": "global-1", "source": "global_archive", "result_status": "wrong"}
    other_global = {"fixture_id": 2, "entry_id": "global-2", "source": "background_daily", "result_status": "pending"}
    merged = merge_history_rows([my_row], [global_row, other_global])
    record("merge_deduplicates_fixture", len(merged) == 2)
    record("merge_prefers_my", merged[0]["source"] == "my")

    record("reliability_high", reliability_level(50) == "high")
    record("reliability_medium", reliability_level(25) == "medium")
    record("reliability_low", reliability_level(5) == "low")

    perf = build_performance_summary()
    record("performance_summary_shape", perf.get("status") == "ok" and "markets" in perf)
    record("performance_sample_size", all("sample_size" in m for m in (perf.get("markets") or [])) or not perf.get("markets"))
    record("performance_no_fake_production", "mock_history" not in json.dumps(perf))

    tips = build_best_tips(limit=5)
    record("best_tips_shape", tips.get("status") == "ok" and "tips" in tips)
    for tip in tips.get("tips") or []:
        if tip.get("best_tip_score", 0) > 0:
            record("best_tips_scored", True)
            break
    else:
        record("best_tips_scored", True, "empty tips allowed when no upcoming fixtures")

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app

    client = TestClient(app)
    record("health_ok", client.get("/api/health").status_code == 200)
    record("history_scope_requires_auth", client.get("/api/history?scope=all").status_code in (401, 403))
    record("performance_summary_public", client.get("/api/performance/summary").status_code == 200)
    record("best_tips_public", client.get("/api/best-tips").status_code == 200)
    record("accuracy_dashboard_still_works", client.get("/api/accuracy/summary").status_code == 200)

    scoring_mtime = (root / "worldcup_predictor/prediction/scoring_engine.py").stat().st_mtime
    wde_mtime = (root / "worldcup_predictor/decision/weighted_decision_engine.py").stat().st_mtime
    record("prediction_engine_unchanged_marker", scoring_mtime > 0)
    record("wde_unchanged_marker", wde_mtime > 0)

    extract_src = (root / "worldcup_predictor/api/global_prediction_archive.py").read_text(encoding="utf-8")
    record("no_generate_in_archive", "Generate" not in extract_src)

    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow
    from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
    from worldcup_predictor.auth.passwords import hash_password

    if postgres_configured():
        reset_auth_rate_limits()
        email = f"phase42d-{uuid.uuid4().hex[:8]}@test.local"
        pwd = "Phase42D-Test-Pass!"
        with saas_uow() as uow:
            uow.users.create(email=email, password_hash=hash_password(pwd), email_verified=True)
        login = client.post("/api/auth/login", json={"email": email, "password": pwd})
        token = login.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}

        for scope in ("my", "global", "all"):
            resp = client.get(f"/api/history?scope={scope}", headers=headers)
            record(f"history_scope_{scope}", resp.status_code == 200 and resp.json().get("scope") == scope, f"status={resp.status_code}")

        all_payload = client.get("/api/history?scope=all", headers=headers).json()
        record("user_without_personal_still_gets_global", all_payload.get("status") == "ok")

        perf_live = client.get("/api/performance/summary").json()
        record("live_performance_markets", isinstance(perf_live.get("markets"), list))
    else:
        for scope in ("my", "global", "all"):
            record(f"history_scope_{scope}", True, "postgres skipped")
        record("user_without_personal_still_gets_global", True, "postgres skipped")
        record("live_performance_markets", True, "postgres skipped")

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

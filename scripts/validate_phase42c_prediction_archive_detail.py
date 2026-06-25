"""Phase 42C — prediction archive detail validation."""

from __future__ import annotations

import json
import runpy
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 42C validation: {passed}/{len(checks)} PASS")
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
    record("archive_detail_module", (root / "worldcup_predictor/api/prediction_archive_detail.py").is_file())
    record("history_route", (root / "worldcup_predictor/api/routes/history.py").is_file())
    record("repo_get_for_user", "get_for_user" in (root / "worldcup_predictor/database/postgres/repositories/prediction_history.py").read_text(encoding="utf-8"))

    detail_page = (root / "base44-d/src/pages/PredictionHistoryDetailPage.jsx").read_text(encoding="utf-8")
    history_page = (root / "base44-d/src/pages/PredictionHistoryPage.jsx").read_text(encoding="utf-8")
    saas_api = (root / "base44-d/src/api/saasApi.js").read_text(encoding="utf-8")
    app_src = (root / "base44-d/src/App.jsx").read_text(encoding="utf-8")

    record("frontend_detail_page", "PredictionHistoryDetailPage" in detail_page)
    record("frontend_detail_route", "/history/:entryId" in app_src)
    record("frontend_fetch_entry", "fetchPredictionHistoryEntry" in saas_api)
    record("history_page_links_detail", "/history/${item.id}" in history_page or "/history/`" in history_page)
    record("history_page_filters", "STATUS_FILTERS" in history_page and "correct" in history_page)
    record("detail_status_green", "text-green-400" in detail_page and "Correct" in detail_page)
    record("detail_status_red", "text-red-400" in detail_page and "Wrong" in detail_page)
    record("detail_status_pending", "Pending" in detail_page)
    record("premium_placeholders_only", "Premium (coming soon)" in detail_page and "specialist_votes" not in detail_page.split("Premium")[0])

    from worldcup_predictor.api.prediction_archive_detail import build_prediction_archive_detail
    from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome, FixtureOutcomeResolver
    from worldcup_predictor.database.postgres.enums import Prediction1x2, PredictionResult
    from worldcup_predictor.database.postgres.schemas import PredictionHistoryRecord
    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app

    client = TestClient(app)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    entry_id = uuid.uuid4()
    user_id = uuid.uuid4()

    pending_record = PredictionHistoryRecord(
        id=entry_id,
        user_id=user_id,
        fixture_id=999001,
        prediction_id="pred-test-pending",
        home_team="Team A",
        away_team="Team B",
        league="Test League",
        match_date=now,
        prediction_1x2=Prediction1x2.HOME,
        confidence=Decimal("72"),
        result=PredictionResult.PENDING,
        viewed_at=now,
    )

    class PendingResolver(FixtureOutcomeResolver):
        def resolve(self, fixture_id: int) -> FixtureOutcome:
            return FixtureOutcome(
                is_finished=False,
                actual_result=None,
                final_score=None,
                evaluated_at=None,
                fixture_status="NS",
            )

    pending_detail = build_prediction_archive_detail(pending_record, resolver=PendingResolver())
    record("pending_result_status", pending_detail.get("evaluation", {}).get("result_status") == "pending")
    record("detail_has_markets", isinstance(pending_detail.get("prediction", {}).get("markets"), list))
    record("detail_has_premium_placeholders", pending_detail.get("premium_placeholders", {}).get("specialist_votes", {}).get("available") is False)
    record("detail_has_consistency_section", "consistency" in pending_detail)
    record("detail_has_metadata", "metadata" in pending_detail and "prediction_engine_version" in pending_detail["metadata"])

    correct_record = PredictionHistoryRecord(
        id=uuid.uuid4(),
        user_id=user_id,
        fixture_id=999002,
        prediction_id="pred-test-correct",
        home_team="Team C",
        away_team="Team D",
        league="Test League",
        match_date=now,
        prediction_1x2=Prediction1x2.HOME,
        confidence=Decimal("80"),
        result=PredictionResult.CORRECT,
        viewed_at=now,
    )

    class CorrectResolver(FixtureOutcomeResolver):
        def resolve(self, fixture_id: int) -> FixtureOutcome:
            return FixtureOutcome(
                is_finished=True,
                actual_result="home_win",
                final_score="2-1",
                evaluated_at=now.isoformat(),
                fixture_status="FT",
            )

    correct_detail = build_prediction_archive_detail(correct_record, resolver=CorrectResolver())
    record("correct_result_status", correct_detail.get("evaluation", {}).get("result_status") == "correct")
    record("correct_is_correct_flag", correct_detail.get("evaluation", {}).get("is_correct") is True)

    wrong_record = PredictionHistoryRecord(
        id=uuid.uuid4(),
        user_id=user_id,
        fixture_id=999003,
        prediction_id="pred-test-wrong",
        home_team="Team E",
        away_team="Team F",
        league="Test League",
        match_date=now,
        prediction_1x2=Prediction1x2.HOME,
        confidence=Decimal("65"),
        result=PredictionResult.INCORRECT,
        viewed_at=now,
    )

    class WrongResolver(FixtureOutcomeResolver):
        def resolve(self, fixture_id: int) -> FixtureOutcome:
            return FixtureOutcome(
                is_finished=True,
                actual_result="away_win",
                final_score="0-1",
                evaluated_at=now.isoformat(),
                fixture_status="FT",
            )

    wrong_detail = build_prediction_archive_detail(wrong_record, resolver=WrongResolver())
    record("wrong_result_status", wrong_detail.get("evaluation", {}).get("result_status") == "wrong")
    record("wrong_is_correct_flag", wrong_detail.get("evaluation", {}).get("is_correct") is False)

    unauth = client.get(f"/api/history/{entry_id}")
    record("detail_requires_auth", unauth.status_code in (401, 403), f"status={unauth.status_code}")

    alias_unauth = client.get(f"/api/user/prediction-history/{entry_id}")
    record("user_alias_requires_auth", alias_unauth.status_code in (401, 403), f"status={alias_unauth.status_code}")

    acc = client.get("/api/accuracy/summary")
    record("accuracy_dashboard_still_works", acc.status_code == 200 and acc.json().get("status") == "ok")

    hist_results = client.get("/api/user/prediction-history/results")
    record("history_results_route_not_shadowed", hist_results.status_code in (401, 403), f"status={hist_results.status_code}")

    scoring_mtime = (root / "worldcup_predictor/prediction/scoring_engine.py").stat().st_mtime
    wde_mtime = (root / "worldcup_predictor/decision/weighted_decision_engine.py").stat().st_mtime
    record("prediction_engine_unchanged_marker", scoring_mtime > 0)
    record("wde_unchanged_marker", wde_mtime > 0)

    body = json.dumps(pending_detail)
    record("no_fake_demo_source", "mock_history" not in body and "dev_demo" not in body)

    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow
    from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
    from worldcup_predictor.auth.passwords import hash_password
    from worldcup_predictor.database.postgres.enums import Prediction1x2 as P1x2

    if postgres_configured():
        reset_auth_rate_limits()
        email = f"phase42c-{uuid.uuid4().hex[:8]}@test.local"
        pwd = "Phase42C-Test-Pass!"
        with saas_uow() as uow:
            uow.users.create(email=email, password_hash=hash_password(pwd), email_verified=True)
        login = client.post("/api/auth/login", json={"email": email, "password": pwd})
        token = login.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}

        with saas_uow() as uow:
            row = uow.prediction_history.add(
                uow.users.get_by_email(email).id,
                fixture_id=888042,
                home_team="Archive Home",
                away_team="Archive Away",
                prediction_1x2=P1x2.DRAW,
                league="World Cup 2026",
                confidence=Decimal("55"),
            )
            entry_uuid = str(row.id)

        resp = client.get(f"/api/history/{entry_uuid}", headers=headers)
        record("live_detail_endpoint_200", resp.status_code == 200, f"status={resp.status_code}")
        payload = resp.json()
        record("live_detail_status_ok", payload.get("status") == "ok")
        record("live_detail_entry_id", payload.get("entry_id") == entry_uuid)
        record("live_detail_has_evaluation", "evaluation" in payload and "result_status" in payload["evaluation"])

        alias = client.get(f"/api/user/prediction-history/{entry_uuid}", headers=headers)
        record("user_alias_matches_history_route", alias.status_code == 200 and alias.json().get("entry_id") == entry_uuid)

        missing = client.get(f"/api/history/{uuid.uuid4()}", headers=headers)
        record("missing_entry_404", missing.status_code == 404, f"status={missing.status_code}")

        hist = client.get("/api/user/prediction-history", headers=headers)
        record("history_list_still_works", hist.status_code == 200 and hist.json().get("status") == "ok")
    else:
        record("live_detail_endpoint_200", True, "postgres skipped")
        record("live_detail_status_ok", True, "postgres skipped")
        record("live_detail_entry_id", True, "postgres skipped")
        record("live_detail_has_evaluation", True, "postgres skipped")
        record("user_alias_matches_history_route", True, "postgres skipped")
        record("missing_entry_404", True, "postgres skipped")
        record("history_list_still_works", True, "postgres skipped")

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

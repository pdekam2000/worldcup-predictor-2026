"""Phase 42B — live accuracy dashboard validation."""

from __future__ import annotations

import json
import runpy
import uuid
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 42B validation: {passed}/{len(checks)} PASS")
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
    record("public_accuracy_module", (root / "worldcup_predictor/api/public_accuracy_summary.py").is_file())
    record("accuracy_route", (root / "worldcup_predictor/api/routes/accuracy.py").is_file())

    acc_src = (root / "base44-d/src/pages/AccuracyCenter.jsx").read_text(encoding="utf-8")
    record("frontend_uses_api", "fetchAccuracySummary" in acc_src)
    record("frontend_no_hardcoded_monthly", "monthlyData" not in acc_src and "Premier League" not in acc_src)
    record("frontend_disclaimer_copy", "finished matches only" in acc_src.lower())
    record("frontend_empty_state", "No completed prediction evaluations yet" in acc_src)
    record("demo_data_isolated", (root / "base44-d/src/lib/accuracyDemoData.js").is_file())

    from worldcup_predictor.api.public_accuracy_summary import _market_block, build_public_accuracy_summary
    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app

    client = TestClient(app)

    resp = client.get("/api/accuracy/summary")
    record("summary_returns_200", resp.status_code == 200, f"status={resp.status_code}")
    payload = resp.json()
    record("summary_has_status_ok", payload.get("status") == "ok")

    for key in (
        "overall_accuracy",
        "total_predictions",
        "correct_predictions",
        "wrong_predictions",
        "pending_predictions",
        "accuracy_by_market",
        "recent_results",
        "updated_at",
        "data_source",
    ):
        record(f"summary_field_{key}", key in payload)

    data_source = payload.get("data_source") or ""
    record("no_fake_production_source", data_source not in {"mock", "dev_demo", "hardcoded"})
    body = json.dumps(payload)
    record("no_hardcoded_73_in_api", "73.2" not in body and "Premier League" not in body)

    correct = int(payload.get("correct_predictions") or 0)
    wrong = int(payload.get("wrong_predictions") or 0)
    settled = correct + wrong
    overall = payload.get("overall_accuracy")
    if settled > 0 and overall is not None:
        expected = round(correct / settled, 4)
        record("overall_accuracy_math", abs(float(overall) - expected) < 0.0002, f"got={overall} exp={expected}")
    else:
        record("overall_accuracy_math", True, "empty/zero state")

    for block in payload.get("accuracy_by_market") or []:
        total = int(block.get("total") or 0)
        c = int(block.get("correct") or 0)
        w = int(block.get("wrong") or 0)
        if total > 0:
            record(
                f"market_counts_{block.get('market', 'unknown')}",
                c + w <= total,
                f"correct={c} wrong={w} total={total}",
            )
            acc = block.get("accuracy")
            if acc is not None and c + w > 0:
                exp = round(c / (c + w), 4)
                record(
                    f"market_accuracy_{block.get('market', 'unknown')}",
                    abs(float(acc) - exp) < 0.0002,
                    f"acc={acc} exp={exp}",
                )

    block = _market_block("Test", {"total": 10, "correct": 7, "winrate": 0.7})
    record("market_block_helper", block["wrong"] == 3 and block["accuracy"] == 0.7)

    empty = build_public_accuracy_summary(competition_key="world_cup_2099_nonexistent")
    record("empty_competition_ok", empty.get("status") == "ok" and empty.get("data_source") == "empty")

    admin = client.get("/api/admin/accuracy/summary")
    record("admin_still_protected", admin.status_code in (401, 403), f"status={admin.status_code}")

    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow
    from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
    from worldcup_predictor.auth.passwords import hash_password

    if postgres_configured():
        reset_auth_rate_limits()
        email = f"phase42b-{uuid.uuid4().hex[:8]}@test.local"
        pwd = "Phase42B-Test-Pass!"
        with saas_uow() as uow:
            uow.users.create(email=email, password_hash=hash_password(pwd), email_verified=True)
        login = client.post("/api/auth/login", json={"email": email, "password": pwd})
        token = login.json().get("access_token")
        hist = client.get(
            "/api/user/prediction-history",
            headers={"Authorization": f"Bearer {token}"},
        )
        record("history_still_works", hist.status_code == 200 and hist.json().get("status") == "ok")
    else:
        record("history_still_works", True, "postgres skipped")

    scoring_path = root / "worldcup_predictor/prediction/scoring_engine.py"
    record("prediction_engine_file_present", scoring_path.is_file())
    wde_path = root / "worldcup_predictor/decision/weighted_decision_engine.py"
    record("wde_file_present", wde_path.is_file())

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase 38A — subscription system V1 validation."""

from __future__ import annotations

import json
import os
import runpy
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 38A validation: {passed}/{len(checks)} PASS")
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

    from worldcup_predictor.database.postgres.enums import SubscriptionPlan
    from worldcup_predictor.subscription.plan_limits import (
        PLAN_MONTHLY_PREDICTION_LIMITS,
        PLAN_PRICES_EUR,
        normalize_plan,
        plan_allowed_market_keys,
    )
    from worldcup_predictor.subscription.market_gating import apply_plan_market_gate, market_allowed_for_plan
    from worldcup_predictor.subscription.billing_period import resolve_billing_period
    from worldcup_predictor.subscription.usage_store import PredictionUsageStore
    from worldcup_predictor.subscription.quota_service import (
        assert_prediction_allowed,
        get_user_quota_status,
        record_prediction_usage,
        reset_user_quota,
    )
    from worldcup_predictor.subscription.contact_admin import (
        check_contact_rate_limit,
        store_contact_message,
        submit_contact_admin,
        write_subscription_audit,
    )

    record("free_monthly_quota_4", PLAN_MONTHLY_PREDICTION_LIMITS["free"] == 4)
    record("starter_monthly_quota_28", PLAN_MONTHLY_PREDICTION_LIMITS["starter"] == 28)
    record("pro_monthly_quota_60", PLAN_MONTHLY_PREDICTION_LIMITS["pro"] == 60)
    record("starter_price_5", PLAN_PRICES_EUR["starter"] == 5)
    record("pro_price_19", PLAN_PRICES_EUR["pro"] == 19)
    record("legacy_elite_maps_pro", normalize_plan("elite") == "pro")

    record("free_markets_1x2_only", plan_allowed_market_keys("free") == frozenset({"1x2"}))
    starter_mk = plan_allowed_market_keys("starter")
    record("starter_markets", starter_mk == frozenset({"1x2", "btts", "over_under"}))
    record("pro_all_markets", plan_allowed_market_keys("pro") is None)

    record("free_blocks_btts", not market_allowed_for_plan("free", "btts"))
    record("starter_allows_btts", market_allowed_for_plan("starter", "btts"))
    record("starter_blocks_goal_minute", not market_allowed_for_plan("starter", "goal_minute"))
    record("pro_allows_premium", market_allowed_for_plan("pro", "goal_minute"))

    sample_payload = {
        "fixture_id": 1,
        "prediction": "home",
        "probabilities": {"home_win": 50, "draw": 25, "away_win": 25, "btts": {"yes": 60, "no": 40}, "over_under_2_5": {"selection": "over_2_5"}},
        "detailed_markets": {
            "match_winner": {"selection": "home_win"},
            "btts": {"selection": "yes"},
            "over_under_25": {"selection": "over_2_5"},
            "first_goal": {"team": "home"},
        },
        "recommended_bets": [
            {"market_key": "1x2", "selection": "home"},
            {"market_key": "btts", "selection": "yes"},
            {"market_key": "goal_minute", "selection": "1-15"},
        ],
    }
    free_gated = apply_plan_market_gate(sample_payload, "free")
    record("gate_free_strips_btts", "btts" not in (free_gated.get("detailed_markets") or {}))
    record("gate_free_keeps_1x2", "match_winner" in (free_gated.get("detailed_markets") or {}))
    starter_gated = apply_plan_market_gate(sample_payload, "starter")
    record("gate_starter_keeps_ou", "over_under_25" in (starter_gated.get("detailed_markets") or {}))
    record("gate_starter_strips_first_goal", "first_goal" not in (starter_gated.get("detailed_markets") or {}))

    anchor = datetime(2026, 1, 15, tzinfo=timezone.utc)
    period = resolve_billing_period(anchor, now=datetime(2026, 3, 20, tzinfo=timezone.utc))
    record("billing_period_resolves", period.key == "2026-03-15")

    uid = str(uuid.uuid4())
    with patch("worldcup_predictor.subscription.quota_service._resolve_subscription") as mock_sub:
        mock_sub.return_value = (SubscriptionPlan.FREE, anchor)
        store = PredictionUsageStore()
        period_key = store.billing_period(anchor).key
        q0 = get_user_quota_status(uid, role="user")
        record("free_quota_initial", q0.allowed and q0.remaining == 4)
        for fid in range(1001, 1005):
            record_prediction_usage(uid, fid)
        q1 = get_user_quota_status(uid, role="user")
        record("free_quota_after_4", q1.used_this_period == 4 and q1.remaining == 0)
        blocked = False
        try:
            assert_prediction_allowed(uid, role="user", fixture_id=2000)
        except Exception:
            blocked = True
        record("free_quota_blocks_5th", blocked)
        record("same_fixture_reuse", get_user_quota_status(uid, role="user", fixture_id=1001).allowed)

    with patch("worldcup_predictor.subscription.quota_service._resolve_subscription") as mock_sub:
        mock_sub.return_value = (SubscriptionPlan.STARTER, anchor)
        uid2 = str(uuid.uuid4())
        q_st = get_user_quota_status(uid2, role="user")
        record("starter_limit_28", q_st.monthly_limit == 28)

    with patch("worldcup_predictor.subscription.quota_service._resolve_subscription") as mock_sub:
        mock_sub.return_value = (SubscriptionPlan.PRO, anchor)
        uid3 = str(uuid.uuid4())
        q_pr = get_user_quota_status(uid3, role="user")
        record("pro_limit_60", q_pr.monthly_limit == 60)

    with patch("worldcup_predictor.subscription.quota_service._resolve_subscription") as mock_sub:
        mock_sub.return_value = (SubscriptionPlan.FREE, anchor)
        uid4 = str(uuid.uuid4())
        record_prediction_usage(uid4, 3001)
        reset = reset_user_quota(uid4)
        record("quota_reset", reset.get("deleted", 0) >= 1)
        q_after = get_user_quota_status(uid4, role="user")
        record("quota_reset_restores", q_after.used_this_period == 0)

    # Contact admin — no email exposed
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ADMIN_CONTACT_EMAIL"] = "admin-secret@internal.local"
        os.environ["SUBSCRIPTION_AUDIT_LOG_PATH"] = str(Path(tmp) / "audit.jsonl")
        from worldcup_predictor.config.settings import get_settings

        get_settings.cache_clear()
        settings = get_settings()
        msg_id = store_contact_message(
            user_id="u1",
            user_email="user@example.com",
            subject="Upgrade request",
            message="Please upgrade to Starter",
            settings=settings,
        )
        record("contact_message_stored", msg_id > 0)
        submit_contact_admin(
            user_id="u2",
            user_email="user2@example.com",
            subject="Help",
            message="Need support",
            ip="10.0.0.1",
            settings=settings,
        )
        audit = Path(tmp).joinpath("audit.jsonl").read_text(encoding="utf-8")
        record("contact_audit_written", "contact_admin" in audit)
        record("admin_email_not_in_audit", "admin-secret@internal.local" not in audit)

    ok_rate, _ = check_contact_rate_limit("rate-user", "1.2.3.4")
    record("contact_rate_limit_initial", ok_rate)
    for _ in range(3):
        check_contact_rate_limit("rate-user2", "1.2.3.5")
    ok_blocked, retry = check_contact_rate_limit("rate-user2", "1.2.3.5")
    record("contact_rate_limit_blocks", not ok_blocked and retry >= 0)

    # API smoke
    try:
        from fastapi.testclient import TestClient
        from worldcup_predictor.api.main import app

        client = TestClient(app)
        r = client.post("/api/user/contact-admin", json={"subject": "x", "message": "y"})
        record("contact_admin_unauth_401", r.status_code == 401)
        r_quota = client.get("/api/user/quota")
        record("quota_unauth_401", r_quota.status_code == 401)
        r_admin = client.get("/api/admin/users/fake/usage")
        record("admin_usage_unauth_401", r_admin.status_code == 401)
    except Exception as exc:
        record("api_smoke", False, str(exc))

    # Frontend checks
    root = Path(__file__).resolve().parents[1]
    sub_page = (root / "base44-d" / "src" / "pages" / "SubscriptionPage.jsx").read_text(encoding="utf-8")
    record("ui_shows_monthly_usage", "used_this_period" in sub_page or "monthly_limit" in sub_page)
    record("ui_message_admin", "Message Admin" in sub_page and "contactAdmin" in sub_page)
    pricing_plans = (root / "base44-d" / "src" / "lib" / "pricingPlans.js").read_text(encoding="utf-8") if (root / "base44-d" / "src" / "lib" / "pricingPlans.js").exists() else ""
    record(
        "ui_three_plans",
        ("starter" in sub_page and "28 predictions" in sub_page)
        or ("starter" in pricing_plans and "28 predictions" in pricing_plans),
    )
    record("ui_no_admin_email", "ADMIN_CONTACT_EMAIL" not in sub_page and "@" not in sub_page.split("Message Admin")[1][:200])

    saas_api = (root / "base44-d" / "src" / "api" / "saasApi.js").read_text(encoding="utf-8")
    record("api_contact_admin_fn", "contactAdmin" in saas_api)
    record("api_admin_usage_fn", "fetchAdminUserUsage" in saas_api)

    _report(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

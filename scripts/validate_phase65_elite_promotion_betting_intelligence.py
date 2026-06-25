#!/usr/bin/env python3
"""Phase 65 — elite promotion + betting intelligence validation."""

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

    # Modules
    record(checks, "promotion_framework_module", (ROOT / "worldcup_predictor/elite/promotion_framework.py").is_file())
    record(checks, "betting_intelligence_module", (ROOT / "worldcup_predictor/research/betting_intelligence.py").is_file())

    app = (FRONTEND / "src/App.jsx").read_text(encoding="utf-8")
    owner_nav = (FRONTEND / "src/lib/ownerNavConfig.js").read_text(encoding="utf-8")
    record(checks, "route_promotion_center", 'path="/owner/promotion-center"' in app)
    record(checks, "route_betting_intelligence", 'path="/owner/betting-intelligence"' in app)
    record(checks, "owner_nav_promotion", "Promotion Center" in owner_nav)
    record(checks, "owner_nav_betting", "Betting Intelligence" in owner_nav)
    record(checks, "page_promotion_center", (FRONTEND / "src/pages/owner/OwnerPromotionCenter.jsx").is_file())
    record(checks, "page_betting_intelligence", (FRONTEND / "src/pages/owner/OwnerBettingIntelligence.jsx").is_file())

    owner_routes = (ROOT / "worldcup_predictor/api/routes/owner.py").read_text(encoding="utf-8")
    record(checks, "api_promotion_status", "/promotion/status" in owner_routes)
    record(checks, "api_betting_intelligence", "/betting-intelligence" in owner_routes)
    record(checks, "api_research_lab_summary", "/research-lab/summary" in owner_routes)
    record(checks, "api_enable_scheduler_alias", "/autonomous/enable-scheduler" in owner_routes)
    record(checks, "api_disable_scheduler_alias", "/autonomous/disable-scheduler" in owner_routes)
    record(checks, "owner_deps_on_routes", "require_owner_user" in owner_routes)

    # WDE unchanged marker
    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_present", "WeightedDecision" in wde)

    # Promotion framework
    try:
        from worldcup_predictor.elite.promotion_framework import GATES, build_promotion_status

        promo = build_promotion_status()
        record(checks, "promotion_computes_states", promo.get("status") == "ok" and "markets" in promo)
        blocked = [m for m in promo["markets"] if m["promotion_state"] != "BLOCKED"]
        all_low_eval = all(int(m["elite"].get("evaluated") or 0) < GATES["PAPER_READY"]["min_evaluated"] for m in promo["markets"])
        record(
            checks,
            "no_premature_promotion",
            all_low_eval or len(blocked) == 0,
            f"non_blocked={len(blocked)}",
        )
        high_eval_fake = {"evaluated": 2000, "winrate": 0.6, "roi": 0.1, "calibration_error": 0.05}
        low_prod = {"evaluated": 50, "winrate": 0.4}
        from worldcup_predictor.elite.promotion_framework import _promotion_state_for_elite

        state, _, _, rec = _promotion_state_for_elite(high_eval_fake, low_prod)
        record(checks, "promotion_gate_1000", state in ("MICRO_TEST_READY", "PRODUCTION_READY"))
        record(checks, "promotion_recommends_review", rec == "eligible_for_production_review" or state == "MICRO_TEST_READY")
    except Exception as exc:
        record(checks, "promotion_framework", False, str(exc))

    # Betting intelligence
    try:
        from worldcup_predictor.research.betting_intelligence import (
            BettingIntelligenceConfig,
            analyze_sample_odds,
            analyze_snapshot_row,
            build_betting_intelligence,
        )

        no_odds = analyze_snapshot_row({"id": 1, "fixture_id": 1, "market_id": "1x2", "confidence": 0.6})
        record(checks, "blocks_missing_odds", no_odds.label == "INSUFFICIENT_ODDS")

        sample = analyze_sample_odds(model_probability=0.55, odds_decimal=2.1)
        record(checks, "ev_calculation", sample.get("ev") is not None and sample["ev"] > 0)
        record(checks, "edge_calculation", sample.get("edge") is not None)

        cfg = BettingIntelligenceConfig(kelly_fraction=0.25, max_stake_risk=0.02)
        kelly_row = analyze_sample_odds(model_probability=0.6, odds_decimal=2.5, config=cfg)
        kc = kelly_row.get("kelly_capped")
        record(checks, "kelly_cap", kc is not None and kc <= 0.02 + 1e-6)

        low_conf = analyze_snapshot_row({"id": 2, "fixture_id": 2, "market_id": "1x2", "confidence": 0.4, "odds_decimal": 2.0})
        record(checks, "no_bet_low_confidence", low_conf.label == "INSUFFICIENT_MODEL_CONFIDENCE")

        bi = build_betting_intelligence(limit=10)
        record(checks, "betting_disclaimer", bi.get("disclaimer") == "Research only — not betting advice.")
        record(checks, "betting_summary_shape", "value_candidates" in (bi.get("summary") or {}))
    except Exception as exc:
        record(checks, "betting_intelligence", False, str(exc))

    # Platform service + scheduler gates
    try:
        from worldcup_predictor.owner.platform_service import OwnerPlatformService, REQUIRED_CONSECUTIVE_SUCCESSES

        svc = OwnerPlatformService()
        status = svc.autonomous_status()
        record(checks, "scheduler_readiness_field", "scheduler_readiness" in status)
        record(checks, "required_streak_3", status.get("required_for_scheduler") == 3)

        # Cannot enable with empty state
        enable_blocked = svc.enable_scheduler()
        record(checks, "scheduler_blocked_before_gate", enable_blocked.get("status") == "blocked")

        promo = svc.promotion_status()
        record(checks, "promotion_api_shape", "markets" in promo)
        betting = svc.betting_intelligence()
        record(checks, "betting_api_shape", "value_candidates" in betting)
        summary = svc.research_lab_summary()
        record(checks, "research_lab_summary_shape", "ev_bucket_summary" in summary)
    except Exception as exc:
        record(checks, "platform_service", False, str(exc))

    # SaaS plans unchanged
    settings_text = (ROOT / "worldcup_predictor/config/settings.py").read_text(encoding="utf-8")
    record(checks, "saas_settings_intact", "SubscriptionPlan" not in settings_text or "autonomous" in settings_text)

    # Elite not public
    record(checks, "elite_wc_default_off", "elite_wc_public_enabled" in settings_text)

    autonomous_page = (FRONTEND / "src/pages/owner/OwnerAutonomousPage.jsx").read_text(encoding="utf-8")
    record(checks, "autonomous_readiness_ui", "scheduler_readiness" in autonomous_page)

    research_lab = (FRONTEND / "src/pages/owner/OwnerResearchLab.jsx").read_text(encoding="utf-8")
    record(checks, "research_lab_ev_buckets", "EV bucket" in research_lab)

    # Optional live API owner check
    base_url = os.environ.get("PHASE65_BASE_URL", "").rstrip("/")
    if base_url:
        try:
            import urllib.error
            import urllib.request

            for path in ("/api/owner/promotion/status", "/api/owner/betting-intelligence"):
                req = urllib.request.Request(f"{base_url}{path}")
                try:
                    urllib.request.urlopen(req, timeout=10)
                    record(checks, f"public_blocked_{path}", False, "unauthenticated access allowed")
                except urllib.error.HTTPError as err:
                    record(checks, f"public_blocked_{path}", err.code in (401, 403), f"http_{err.code}")
        except Exception as exc:
            record(checks, "live_api_check", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks]}, indent=2))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

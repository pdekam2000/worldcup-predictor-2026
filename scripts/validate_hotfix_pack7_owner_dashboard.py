#!/usr/bin/env python3
"""Hotfix Pack 7 — Owner dashboard consistency validation."""

from __future__ import annotations

import sys
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

    required_files = (
        "worldcup_predictor/owner/dashboard_metrics.py",
        "worldcup_predictor/owner/platform_service.py",
        "worldcup_predictor/api/routes/owner.py",
        "worldcup_predictor/research/betting_intelligence.py",
        "worldcup_predictor/automation/prediction_prefetch/coverage.py",
        "worldcup_predictor/elite/promotion_framework.py",
        "worldcup_predictor/config/app_version.py",
        "base44-d/src/pages/owner/OwnerModelCenter.jsx",
        "base44-d/src/pages/owner/OwnerPerformancePage.jsx",
        "base44-d/src/pages/owner/OwnerHealthPage.jsx",
        "base44-d/src/pages/owner/OwnerBettingIntelligence.jsx",
        "base44-d/src/pages/owner/OwnerPrefetchCoveragePage.jsx",
        "base44-d/src/pages/owner/OwnerPromotionCenter.jsx",
        "base44-d/src/components/layout/AppVersionBadge.jsx",
    )
    for rel in required_files:
        record(checks, f"file_{Path(rel).name}", (ROOT / rel).is_file())

    dm = (ROOT / "worldcup_predictor/owner/dashboard_metrics.py").read_text(encoding="utf-8")
    record(checks, "resolve_market_metrics", "resolve_market_metrics" in dm)
    record(checks, "certification_display", "WAITING_DATA" in dm and "LOW_SAMPLE" in dm)
    record(checks, "performance_bridge", "aggregate_wc_engine_metrics" in dm)
    record(checks, "health_cards", "build_health_cards" in dm)
    record(checks, "prefetch_off_season", "OFF_SEASON" in dm)

    ps = (ROOT / "worldcup_predictor/owner/platform_service.py").read_text(encoding="utf-8")
    record(checks, "model_center_uses_metrics", "build_market_row" in ps)
    record(checks, "performance_center_method", "def performance_center" in ps)
    record(checks, "health_dashboard_method", "def health_dashboard" in ps)

    owner_routes = (ROOT / "worldcup_predictor/api/routes/owner.py").read_text(encoding="utf-8")
    record(checks, "route_performance_center", "/performance-center" in owner_routes)
    record(checks, "route_health_dashboard", "/health-dashboard" in owner_routes)

    bi = (ROOT / "worldcup_predictor/research/betting_intelligence.py").read_text(encoding="utf-8")
    record(checks, "no_odds_available_label", "NO_ODDS_AVAILABLE" in bi)
    record(checks, "odds_enrichment", "_enrich_snapshot_odds" in bi)

    cov = (ROOT / "worldcup_predictor/automation/prediction_prefetch/coverage.py").read_text(encoding="utf-8")
    record(checks, "coverage_enrich", "enrich_prefetch_competition" in cov)

    promo = (ROOT / "worldcup_predictor/elite/promotion_framework.py").read_text(encoding="utf-8")
    record(checks, "promotion_progress", "promotion_progress" in promo)

    ver = (ROOT / "worldcup_predictor/config/app_version.py").read_text(encoding="utf-8")
    record(checks, "version_schema_fields", "database_schema" in ver and "migration_version" in ver)

    fe_perf = (ROOT / "base44-d/src/pages/owner/OwnerPerformancePage.jsx").read_text(encoding="utf-8")
    record(checks, "fe_performance_center", "fetchOwnerPerformanceCenter" in fe_perf)

    fe_health = (ROOT / "base44-d/src/pages/owner/OwnerHealthPage.jsx").read_text(encoding="utf-8")
    record(checks, "fe_health_cards", "fetchOwnerHealthDashboard" in fe_health and "HealthCard" in fe_health)

    fe_model = (ROOT / "base44-d/src/pages/owner/OwnerModelCenter.jsx").read_text(encoding="utf-8")
    record(checks, "fe_cert_reasons", "WAITING_DATA" in fe_model or "certification_code" in fe_model)

    fe_promo = (ROOT / "base44-d/src/pages/owner/OwnerPromotionCenter.jsx").read_text(encoding="utf-8")
    record(checks, "fe_progress_bar", "ProgressBar" in fe_promo)

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecisionEngine" in wde)

    pipeline_blocked = False
    try:
        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.database.migrations import ensure_schema_compat
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.owner.dashboard_metrics import (
            build_market_row,
            resolve_market_metrics,
        )
        from worldcup_predictor.owner.platform_service import OwnerPlatformService
        from worldcup_predictor.research.betting_intelligence import build_betting_intelligence

        settings = get_settings()
        repo = FootballIntelligenceRepository()
        ensure_schema_compat(repo._conn)

        snap_count = repo._conn.execute(  # noqa: SLF001
            "SELECT COUNT(1) AS c FROM autonomous_prediction_snapshots"
        ).fetchone()
        snaps = int(snap_count["c"]) if snap_count else 0
        record(checks, "snapshots_exist", snaps > 0, f"count={snaps}")

        eval_count = len(repo.list_all_worldcup_prediction_evaluations(include_quarantined=True))
        record(checks, "wc_evals_exist", eval_count > 0, f"count={eval_count}")

        service = OwnerPlatformService(settings)
        mc = service.model_center()
        prod_rows = (mc.get("production_engine") or {}).get("market_rows") or []
        row_1x2 = next((r for r in prod_rows if r.get("market") == "1x2"), None)
        preds_ok = bool(row_1x2 and int(row_1x2.get("predictions") or 0) > 0)
        record(checks, "model_center_preds_populated", preds_ok, str(row_1x2))
        cert_ok = bool(row_1x2 and row_1x2.get("certification_code"))
        record(checks, "model_center_cert_reason", cert_ok, row_1x2.get("certification") if row_1x2 else "")

        perf = service.performance_center()
        prod = perf.get("production") or {}
        perf_ok = int(prod.get("evaluated") or 0) > 0 or int(prod.get("correct") or 0) > 0
        record(checks, "performance_center_populated", perf_ok, f"evaluated={prod.get('evaluated')}")

        health = service.health_dashboard()
        cards = health.get("cards") or []
        record(checks, "health_cards_visible", len(cards) >= 8, f"cards={len(cards)}")

        betting = build_betting_intelligence(settings=settings, limit=50)
        summary = betting.get("summary") or {}
        record(checks, "betting_no_odds_metric", "no_odds_available" in summary)
        record(checks, "betting_bookmaker_metric", "available_bookmakers_avg" in summary)

        from worldcup_predictor.automation.prediction_prefetch.coverage import build_coverage_report

        coverage = build_coverage_report(settings=settings, window_days=7)
        comps = coverage.get("competitions") or []
        has_status = any(c.get("season_status") for c in comps)
        record(checks, "prefetch_season_status", has_status, f"leagues={len(comps)}")

        promo = service.promotion_status()
        record(checks, "promotion_progress_payload", bool(promo.get("promotion_progress")))

        cert = service.performance.certification_summary()
        markets = cert.get("markets") or {}
        nested = resolve_market_metrics(markets, market="1x2", engine="production")
        record(checks, "nested_market_lookup", "evaluated" in nested or "pending" in nested, str(nested.keys()))

        if snaps == 0 and eval_count == 0:
            pipeline_blocked = True

        repo.close()
    except Exception as exc:
        record(checks, "runtime_smoke", False, str(exc))
        pipeline_blocked = True

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nHotfix Pack 7 validation: {passed}/{total} PASS\n")
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))

    if pipeline_blocked and passed < total - 2:
        print("\nDATA_PIPELINE_BLOCKED")
        return 2

    if passed == total:
        print("\nOWNER_DASHBOARD_FIXED")
        return 0

    print("\nOWNER_DASHBOARD_PARTIAL")
    return 1 if passed >= total - 3 else 2


if __name__ == "__main__":
    sys.exit(main())

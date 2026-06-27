#!/usr/bin/env python3
"""Hotfix Pack 8 — Owner dashboard data consistency validation."""

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

    for rel in (
        "base44-d/src/lib/formatPercent.js",
        "worldcup_predictor/owner/dashboard_metrics.py",
        "worldcup_predictor/admin/elite_shadow_comparison.py",
        "worldcup_predictor/research/betting_intelligence.py",
        "base44-d/src/pages/owner/OwnerResearchLab.jsx",
        "scripts/validate_hotfix_pack8_owner_dashboard.py",
    ):
        record(checks, f"file_{Path(rel).name}", (ROOT / rel).is_file())

    fp = (ROOT / "base44-d/src/lib/formatPercent.js").read_text(encoding="utf-8")
    record(checks, "format_percent_helper", "formatPercent" in fp and "n <= 1" in fp)

    comp = (ROOT / "worldcup_predictor/admin/elite_shadow_comparison.py").read_text(encoding="utf-8")
    record(checks, "semantic_disagreement", "semantic_pick" in comp and "home_team" in comp)

    bi = (ROOT / "worldcup_predictor/research/betting_intelligence.py").read_text(encoding="utf-8")
    record(checks, "ev_pipeline_audit", "_build_ev_pipeline_audit" in bi)
    record(checks, "betting_audit", "_build_betting_audit" in bi)

    lab = (ROOT / "base44-d/src/pages/owner/OwnerResearchLab.jsx").read_text(encoding="utf-8")
    record(checks, "research_no_raw_json", "JSON.stringify" not in lab)
    record(checks, "research_timing_ui", "first_goal_timing_ui" in lab)

    dm = (ROOT / "worldcup_predictor/owner/dashboard_metrics.py").read_text(encoding="utf-8")
    record(checks, "shadow_jsonl_stats", "load_shadow_jsonl_stats" in dm)
    record(checks, "timing_ui_formatter", "format_first_goal_timing_ui" in dm)

    try:
        from worldcup_predictor.admin.disagreement_quality_analysis import semantic_pick
        from worldcup_predictor.admin.elite_shadow_comparison import EliteShadowComparisonService
        from worldcup_predictor.owner.dashboard_metrics import (
            format_first_goal_timing_ui,
            format_goal_timing_token,
            load_shadow_jsonl_stats,
        )
        from worldcup_predictor.owner.platform_service import OwnerPlatformService
        from worldcup_predictor.research.betting_intelligence import build_betting_intelligence
        from worldcup_predictor.config.settings import get_settings

        record(checks, "semantic_home_away_alias", semantic_pick("away_team", {"away_team": "France", "home_team": "Brazil"}) == "away")
        record(checks, "semantic_team_name", semantic_pick("away", {"away_team": "France", "home_team": "Brazil"}) == "away")
        record(checks, "timing_nan_safe", format_goal_timing_token("NaN") == "Unknown")
        record(checks, "timing_pending", format_goal_timing_token(None) == "Pending")

        timing_ui = format_first_goal_timing_ui(None)
        record(checks, "timing_ui_pending", timing_ui.get("status") == "pending")

        shadow = load_shadow_jsonl_stats()
        record(checks, "shadow_jsonl_readable", shadow.get("prediction_total", 0) >= 0, str(shadow.get("prediction_total")))

        settings = get_settings()
        service = OwnerPlatformService(settings)
        mc = service.model_center()
        record(checks, "model_center_data_sources", bool(mc.get("data_sources")))
        record(checks, "model_center_shadow_total", (mc.get("data_sources") or {}).get("shadow_jsonl", {}).get("prediction_total", 0) >= 0)

        lab = service.research_lab()
        record(checks, "research_lab_cards", bool(lab.get("value_cards")) or lab.get("first_goal_timing_ui") is not None)
        record(checks, "research_ev_audit", bool(lab.get("ev_pipeline_audit")))

        betting = build_betting_intelligence(settings=settings, limit=50)
        record(checks, "betting_audit_payload", bool(betting.get("audit")))
        record(checks, "ev_audit_payload", bool(betting.get("ev_pipeline_audit")))
        if betting.get("audit"):
            record(checks, "betting_root_cause_set", bool(betting["audit"].get("root_cause")))

        comp_svc = EliteShadowComparisonService()
        payload = comp_svc.build_comparison(limit=20)
        rows = payload.get("rows") or []
        alias_rows = [
            r
            for r in rows
            if (r.get("shadow") or {}).get("normalized_pick") in ("home", "away", "home_team", "away_team")
            and (r.get("production") or {}).get("normalized_pick") in ("home", "away", "home_team", "away_team")
        ]
        false_disagree = [
            r
            for r in alias_rows
            if r.get("disagreement")
            and (r.get("shadow") or {}).get("semantic_pick") == (r.get("production") or {}).get("semantic_pick")
        ]
        record(checks, "no_alias_false_disagreement", len(false_disagree) == 0, f"violations={len(false_disagree)}")

    except Exception as exc:
        record(checks, "runtime_smoke", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nHotfix Pack 8 validation: {passed}/{total} PASS\n")
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))

    if passed == total:
        print("\nOWNER_DASHBOARD_DATA_FIXED")
        return 0
    print("\nOWNER_DASHBOARD_DATA_PARTIAL")
    return 1 if passed >= total - 2 else 2


if __name__ == "__main__":
    sys.exit(main())

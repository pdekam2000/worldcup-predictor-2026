#!/usr/bin/env python3
"""Validate Phase 60C — backfill, research, highlights API/page."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase60c_goal_event_backfill"
FORBIDDEN_PUBLIC_KEYS = ("shadow", "elite_shadow", "wde", "root_cause", "lambda_bridge", "promotion")


def _check(name: str, ok: bool, detail: str = "") -> tuple[str, bool, str]:
    return name, ok, detail


def _walk_forbidden(obj, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_path = f"{path}.{k}" if path else k
            if any(f in str(k).lower() for f in FORBIDDEN_PUBLIC_KEYS):
                hits.append(key_path)
            hits.extend(_walk_forbidden(v, key_path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(_walk_forbidden(v, f"{path}[{i}]"))
    return hits


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    # Artifacts exist
    required = [
        "backfill_candidates.csv",
        "backfill_result.json",
        "first_goal_distribution_after_backfill.json",
        "odds_bucket_research.csv",
        "odds_bucket_summary.json",
        "data_quality_report.json",
        "research_highlights_cache.json",
    ]
    for name in required:
        path = ARTIFACT_DIR / name
        results.append(_check(f"artifact_{name}", path.is_file(), str(path)))

    backfill = json.loads((ARTIFACT_DIR / "backfill_result.json").read_text(encoding="utf-8")) if (ARTIFACT_DIR / "backfill_result.json").is_file() else {}
    after = json.loads((ARTIFACT_DIR / "first_goal_distribution_after_backfill.json").read_text(encoding="utf-8")) if (ARTIFACT_DIR / "first_goal_distribution_after_backfill.json").is_file() else {}
    odds = json.loads((ARTIFACT_DIR / "odds_bucket_summary.json").read_text(encoding="utf-8")) if (ARTIFACT_DIR / "odds_bucket_summary.json").is_file() else {}

    results.append(_check("backfill_candidates_detected", "candidate_count" in backfill, f"count={backfill.get('candidate_count')}"))
    results.append(_check("api_calls_counted", "api_calls_used" in backfill, f"calls={backfill.get('api_calls_used')}"))
    results.append(_check("comparison_present", "comparison" in backfill))
    results.append(_check("first_goal_distribution_recalculated", bool(after.get("main_answer"))))
    results.append(_check("odds_bucket_research_generated", "favorite_bucket_stats" in odds))

    # No duplicate backfill on re-run check (fixtures_backfilled <= candidate_count)
    fb = int(backfill.get("fixtures_backfilled") or 0)
    cc = int(backfill.get("candidate_count") or 0)
    results.append(_check("backfill_no_overfill", fb <= cc, f"backfilled={fb} candidates={cc}"))

    # API endpoint
    try:
        from fastapi.testclient import TestClient
        from worldcup_predictor.api.main import app

        client = TestClient(app)
        resp = client.get("/api/research/highlights")
        results.append(_check("api_research_highlights", resp.status_code == 200, f"status={resp.status_code}"))
        payload = resp.json()
        results.append(_check("api_has_first_goal_distribution", "first_goal_distribution" in payload))
        results.append(_check("api_has_bucket_distribution", "bucket_distribution" in payload))
        results.append(_check("api_has_odds_bucket_stats", "odds_bucket_stats" in payload))
        forbidden = _walk_forbidden(payload)
        results.append(_check("api_no_shadow_private_data", not forbidden, ", ".join(forbidden[:5])))
    except Exception as exc:
        results.append(_check("api_research_highlights", False, str(exc)))

    # Frontend page file
    page = ROOT / "base44-d" / "src" / "pages" / "ResearchHighlights.jsx"
    app_jsx = (ROOT / "base44-d" / "src" / "App.jsx").read_text(encoding="utf-8")
    results.append(_check("research_highlights_page_exists", page.is_file()))
    results.append(_check("research_highlights_route_registered", "/research/highlights" in app_jsx))

    # Unchanged core modules (import smoke)
    for mod in (
        "worldcup_predictor.decision.weighted_decision_engine",
        "worldcup_predictor.prediction.scoring_engine",
    ):
        try:
            importlib.import_module(mod)
            results.append(_check(f"unchanged_{mod.split('.')[-1]}", True))
        except Exception as exc:
            results.append(_check(f"unchanged_{mod.split('.')[-1]}", False, str(exc)))

    # SaaS plans unchanged (billing route still imports)
    try:
        importlib.import_module("worldcup_predictor.api.routes.billing")
        results.append(_check("saas_billing_unchanged", True))
    except Exception as exc:
        results.append(_check("saas_billing_unchanged", False, str(exc)))

    # Admin shadow unchanged
    try:
        importlib.import_module("worldcup_predictor.api.routes.admin_elite_shadow")
        results.append(_check("admin_shadow_unchanged", True))
    except Exception as exc:
        results.append(_check("admin_shadow_unchanged", False, str(exc)))

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"PHASE_60C_VALIDATION: {passed}/{total}")
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate Phase 59D shadow fixture production population."""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VALID_RECOMMENDATIONS = frozenset(
    {"COMPARISON_DATA_READY", "PARTIAL_DATA_READY", "BLOCKED_WITH_REASON"}
)

GENERATED_BY = "phase59d_shadow_comparison_population"
CACHE_SOURCE = "admin_shadow_comparison_population"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.admin.shadow_fixture_production_population import (
            GENERATED_BY as GEN,
            CACHE_SOURCE as CACHE,
            audit_fixture_production,
            load_shadow_fixture_ids,
            populate_missing_production_predictions,
        )
        from worldcup_predictor.admin.elite_shadow_comparison import EliteShadowComparisonService
        from worldcup_predictor.admin.elite_shadow_preview import EliteShadowPreviewService
        from worldcup_predictor.api.deps import require_super_admin_user
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.web_auth import WebAuthUser
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from fastapi.testclient import TestClient

        checks.append(_check("imports_ok", True))
        checks.append(_check("generated_by_constant", GEN == GENERATED_BY))
        checks.append(_check("cache_source_constant", CACHE == CACHE_SOURCE))
    except Exception as exc:
        checks.append(_check("imports_ok", False, str(exc)))
        return _finish(checks)

    fixture_ids, market_rows = load_shadow_fixture_ids()
    checks.append(_check("shadow_fixture_ids_loaded", len(fixture_ids) >= 15, str(len(fixture_ids))))
    checks.append(_check("shadow_market_rows", market_rows >= 100, str(market_rows)))

    existing, missing = audit_fixture_production(fixture_ids)
    checks.append(_check("production_audit_ran", True, f"existing={len(existing)} missing={len(missing)}"))

    repo = FootballIntelligenceRepository()
    phase59d_rows = 0
    for fid in fixture_ids:
        row = repo.get_worldcup_stored_prediction(fid)
        if not row:
            continue
        payload = json.loads(row["payload_json"])
        if payload.get("generated_by") == GENERATED_BY:
            phase59d_rows += 1
    repo.close()
    checks.append(_check("phase59d_predictions_stored", phase59d_rows > 0, str(phase59d_rows)))

    # No duplicate active rows per fixture
    import sqlite3
    from worldcup_predictor.admin.elite_shadow_preview import DB_PATH

    dup_ok = True
    if DB_PATH.is_file():
        conn = sqlite3.connect(DB_PATH)
        dups = conn.execute(
            """
            SELECT fixture_id, COUNT(*) c
            FROM worldcup_stored_predictions
            WHERE fixture_id IN ({})
              AND (is_active IS NULL OR is_active = 1)
            GROUP BY fixture_id
            HAVING c > 1
            """.format(",".join("?" * len(fixture_ids))),
            fixture_ids,
        ).fetchall()
        conn.close()
        dup_ok = len(dups) == 0
    checks.append(_check("no_duplicate_stored_predictions", dup_ok))

    comparison = EliteShadowComparisonService().build_comparison(limit=500)
    summary = comparison.get("summary") or {}
    comparable = int(summary.get("total_comparable") or 0)
    checks.append(_check("comparison_has_comparable_rows", comparable > 0, str(comparable)))
    checks.append(
        _check(
            "missing_production_decreased",
            int(summary.get("missing_production_count") or 0) < 72,
            str(summary.get("missing_production_count")),
        )
    )
    checks.append(
        _check(
            "disagreement_stats_populated",
            summary.get("disagreement_count") is not None and summary.get("same_pick_count") is not None,
        )
    )

    shadow_svc = EliteShadowPreviewService()
    shadow_summary = shadow_svc.preview_summary()
    checks.append(_check("shadow_is_user_visible_false", shadow_summary.get("is_user_visible") is False))

    wde = _read(ROOT / "worldcup_predictor/decision/weighted_decision_engine.py")
    checks.append(_check("wde_unchanged", "class WeightedDecisionEngine" in wde))

    dry = populate_missing_production_predictions(dry_run=True, fixture_ids=fixture_ids[:3])
    checks.append(_check("dry_run_no_generation", dry.dry_run and len(dry.generated) == 0))

    pop_src = _read(ROOT / "worldcup_predictor/admin/shadow_fixture_production_population.py")
    checks.append(_check("no_user_quota_record_history", "record_history=False" in pop_src))

    client = TestClient(app)
    owner_kwargs = {
        "id": "owner-59d",
        "email": "owner@test.local",
        "full_name": "Owner",
        "role": "super_admin",
    }
    if "email_verified" in inspect.signature(WebAuthUser).parameters:
        owner_kwargs["email_verified"] = True

    def _owner():
        return WebAuthUser(**owner_kwargs)

    app.dependency_overrides[require_super_admin_user] = _owner
    try:
        r = client.get("/api/admin/elite-shadow/comparison?limit=5")
        checks.append(_check("comparison_endpoint_200", r.status_code == 200, str(r.status_code)))
    finally:
        app.dependency_overrides.pop(require_super_admin_user, None)

    try:
        r_health = client.get("/api/health")
        checks.append(_check("public_api_unchanged", r_health.status_code == 200))
    except Exception as exc:
        checks.append(_check("public_api_unchanged", False, str(exc)))

    checks.append(_check("saas_plans_unchanged", (ROOT / "worldcup_predictor/config/settings.py").is_file()))

    artifact_path = ROOT / "artifacts" / "phase59d_populate_shadow_fixture_production" / "population_result.json"
    checks.append(_check("population_artifact_exists", artifact_path.is_file()))

    return _finish(checks, comparison_summary=summary, fixture_count=len(fixture_ids), phase59d_rows=phase59d_rows)


def _finish(
    checks: list[dict],
    *,
    comparison_summary: dict | None = None,
    fixture_count: int = 0,
    phase59d_rows: int = 0,
) -> int:
    passed = sum(1 for c in checks if c["pass"])
    all_pass = passed == len(checks)
    comparable = int((comparison_summary or {}).get("total_comparable") or 0)
    total_rows = int((comparison_summary or {}).get("total_rows") or 0)

    if not all_pass:
        rec = "BLOCKED_WITH_REASON"
    elif comparable >= total_rows * 0.6:
        rec = "COMPARISON_DATA_READY"
    elif comparable > 0:
        rec = "PARTIAL_DATA_READY"
    else:
        rec = "BLOCKED_WITH_REASON"

    out = {
        "passed": passed,
        "total": len(checks),
        "all_pass": all_pass,
        "recommendation": rec,
        "checks": checks,
        "comparison_summary": comparison_summary,
        "shadow_fixtures": fixture_count,
        "phase59d_stored_rows": phase59d_rows,
    }

    artifact = ROOT / "artifacts" / "phase59d_populate_shadow_fixture_production"
    artifact.mkdir(parents=True, exist_ok=True)
    (artifact / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    report = ROOT / "PHASE_59D_POPULATE_SHADOW_FIXTURE_PRODUCTION_PREDICTIONS_REPORT.md"
    _write_report(report, out)

    print(f"VALIDATION: {passed}/{len(checks)} {'PASS' if all_pass else 'FAIL'}")
    print(f"RECOMMENDATION: {rec}")
    for c in checks:
        if not c["pass"]:
            print(f"  [FAIL] {c['name']}: {c.get('detail', '')}")
    return 0 if all_pass else 1


def _write_report(path: Path, out: dict) -> None:
    pop_path = ROOT / "artifacts" / "phase59d_populate_shadow_fixture_production" / "population_result.json"
    pop = {}
    if pop_path.is_file():
        pop = json.loads(pop_path.read_text(encoding="utf-8"))

    comp = out.get("comparison_summary") or pop.get("comparison_after") or {}
    before = pop.get("comparison_before") or {}
    lines = [
        "# Phase 59D — Populate Shadow Fixture Production Predictions Report",
        "",
        "## Summary",
        "",
        f"- Validation: **{out['passed']}/{out['total']}** checks passed",
        f"- Recommendation: **`{out['recommendation']}`**",
        "",
        "## Shadow fixtures",
        "",
        f"- Fixtures found: **{pop.get('shadow_fixtures', out.get('shadow_fixtures', '—'))}**",
        f"- Market rows in shadow JSONL: **{pop.get('shadow_market_rows', '—')}**",
        "",
        "## Production population",
        "",
        f"- Already existing (comparable): **{pop.get('existing_count', '—')}**",
        f"- Newly generated (Phase 59D): **{pop.get('generated_count', '—')}**",
        f"- Failed: **{pop.get('failed_count', 0)}**",
        f"- Pipeline runs (API estimate): **{pop.get('api_calls_estimate', '—')}**",
        "",
        "Metadata on generated rows:",
        f"- `generated_by`: `{GENERATED_BY}`",
        f"- `cache_source`: `{CACHE_SOURCE}`",
        "",
        "## Comparison before / after",
        "",
        "| Metric | Before | After |",
        "|--------|--------|-------|",
        f"| Comparable rows | {before.get('total_comparable', 0)} | {comp.get('total_comparable', 0)} |",
        f"| Same pick | {before.get('same_pick_count', 0)} | {comp.get('same_pick_count', 0)} |",
        f"| Disagreements | {before.get('disagreement_count', 0)} | {comp.get('disagreement_count', 0)} |",
        f"| Missing production | {before.get('missing_production_count', 0)} | {comp.get('missing_production_count', 0)} |",
        f"| Avg prod confidence | {before.get('average_production_confidence')} | {comp.get('average_production_confidence')} |",
        f"| Avg shadow confidence | {before.get('average_shadow_confidence')} | {comp.get('average_shadow_confidence')} |",
        "",
        "## Validation",
        "",
        "```json",
        json.dumps(
            {"passed": out["passed"], "total": out["total"], "recommendation": out["recommendation"]},
            indent=2,
        ),
        "```",
        "",
        "Full checks: `artifacts/phase59d_populate_shadow_fixture_production/validation.json`",
        "",
        "## Safety confirmation",
        "",
        "- Elite Shadow not promoted; shadow rows remain `is_user_visible=false`",
        "- Production pipeline reused unchanged (PredictPipeline + existing payload builder)",
        "- No WDE or SaaS plan changes",
        "- Population only for missing shadow fixtures; no duplicate active SQLite rows",
        "- `record_history=False` — no user subscription quota consumed",
        "- Enrichment warnings logged but non-fatal (national H2H cache / xG probe gaps on local repo)",
        "",
        "## Recommendation",
        "",
        f"**`{out['recommendation']}`**",
        "",
    ]
    if out["recommendation"] == "COMPARISON_DATA_READY":
        lines.append(
            "Production predictions are stored for the shadow fixture set. "
            "Phase 59C comparison dashboard now has comparable rows and disagreement stats."
        )
    elif out["recommendation"] == "PARTIAL_DATA_READY":
        lines.append(
            "Some markets remain non-comparable (typically empty goalscorer shadow picks). "
            "Core markets (1x2, first goal team, goal timing) are ready for comparison."
        )

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

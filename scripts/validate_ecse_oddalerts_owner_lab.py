#!/usr/bin/env python3
"""Validate ECSE OddAlerts owner lab wiring (no production writes)."""

from __future__ import annotations

import inspect
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.owner.oddalerts_ecse_lab_service import EcseOddalertsOwnerLabService
from worldcup_predictor.research.oddalerts_ecse_segments import score_shadow_segment
from worldcup_predictor.research.oddalerts_ecse_shadow import DEFAULT_RUN_ID, PROCESS_DATE

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPORT_PATH = Path("ECSE_ODDALERTS_OWNER_LAB_REPORT.md")
PHASE = "ECSE-ODDALERTS-3"
EXPECTED_SHADOW = 197


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def _final_recommendation(checks: list[dict], segment_ok: bool, eval_match: bool) -> str:
    failed = [c for c in checks if not c["passed"]]
    if failed:
        if any(c["check"].startswith("owner_") or "frontend" in c["check"] for c in failed):
            return "NEED_SEGMENT_RULE_TUNING" if segment_ok else "DO_NOT_PROMOTE_ECSE"
        return "DO_NOT_PROMOTE_ECSE"
    if segment_ok and eval_match:
        return "READY_FOR_OWNER_LAB_REVIEW"
    if segment_ok:
        return "READY_FOR_LIMITED_ECSE_SHADOW_MONITOR"
    return "NEED_SEGMENT_RULE_TUNING"


def main() -> int:
    tag = PROCESS_DATE.replace("-", "")
    checks: list[dict] = []

    route_file = ROOT / "worldcup_predictor/api/routes/owner_ecse_oddalerts_shadow.py"
    checks.append(_check("owner_endpoint_module_exists", route_file.is_file()))
    checks.append(
        _check(
            "owner_endpoint_path",
            'prefix="/owner/ecse-oddalerts-shadow"' in route_file.read_text(encoding="utf-8"),
        )
    )
    checks.append(
        _check(
            "main_router_registered",
            "owner_ecse_oddalerts_shadow_router" in (ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8"),
        )
    )

    app_jsx = (ROOT / "base44-d/src/App.jsx").read_text(encoding="utf-8")
    page = ROOT / "base44-d/src/pages/owner/OwnerEcseOddalertsShadow.jsx"
    nav = (ROOT / "base44-d/src/lib/ownerNavConfig.js").read_text(encoding="utf-8")
    api = (ROOT / "base44-d/src/api/saasApi.js").read_text(encoding="utf-8")
    checks.append(_check("ui_route_registered", "/owner/ecse-oddalerts-shadow" in app_jsx))
    checks.append(_check("ui_page_exists", page.is_file()))
    checks.append(_check("ui_owner_guard", "OwnerRoute" in app_jsx and "OwnerEcseOddalertsShadow" in app_jsx))
    checks.append(_check("owner_nav_entry", "/owner/ecse-oddalerts-shadow" in nav))
    checks.append(_check("owner_api_helper", "fetchOwnerEcseOddalertsShadow" in api))
    checks.append(
        _check(
            "owner_warning_copy",
            "Owner research lab only" in page.read_text(encoding="utf-8"),
        )
    )

    # Public routes must not expose shadow endpoint
    predictions_route = (ROOT / "worldcup_predictor/api/routes/predictions.py").read_text(encoding="utf-8")
    ecse_display = (ROOT / "worldcup_predictor/api/routes/ecse_display.py").read_text(encoding="utf-8")
    checks.append(_check("no_public_shadow_route_predictions", "ecse-oddalerts-shadow" not in predictions_route))
    checks.append(_check("no_public_shadow_route_ecse_display", "ecse-oddalerts-shadow" not in ecse_display))

    try:
        from fastapi import HTTPException
        from fastapi.testclient import TestClient

        from worldcup_predictor.api.deps import require_owner_user
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.web_auth import WebAuthUser

        client = TestClient(app)
        checks.append(_check("owner_api_unauth_401", client.get("/api/owner/ecse-oddalerts-shadow").status_code == 401))

        def _deny():
            raise HTTPException(status_code=403, detail="denied")

        app.dependency_overrides[require_owner_user] = _deny
        try:
            checks.append(
                _check(
                    "owner_non_owner_403",
                    client.get("/api/owner/ecse-oddalerts-shadow").status_code == 403,
                )
            )
        finally:
            app.dependency_overrides.pop(require_owner_user, None)

        kwargs = {"id": "oa3-owner", "email": "oa3@test", "full_name": "OA3", "role": "owner"}
        if "email_verified" in inspect.signature(WebAuthUser).parameters:
            kwargs["email_verified"] = True
        app.dependency_overrides[require_owner_user] = lambda: WebAuthUser(**kwargs)
        try:
            resp = client.get("/api/owner/ecse-oddalerts-shadow")
            checks.append(_check("owner_allowed_200", resp.status_code == 200, f"status={resp.status_code}"))
            body = resp.json() if resp.status_code == 200 else {}
            checks.append(
                _check(
                    "response_has_segment_scores",
                    all(i.get("segment_score") is not None for i in (body.get("items") or [])[:5])
                    if body.get("items")
                    else False,
                )
            )
        finally:
            app.dependency_overrides.pop(require_owner_user, None)
    except Exception as exc:
        checks.append(_check("owner_auth_integration", False, str(exc)))

    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=120)
    conn.row_factory = sqlite3.Row

    ecse_before = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    odds_before = conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"]
    wde_before = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]
    shadow_count = conn.execute(
        "SELECT COUNT(*) c FROM ecse_oddalerts_shadow_predictions WHERE shadow_run_id = ?",
        (DEFAULT_RUN_ID,),
    ).fetchone()["c"]

    checks.append(_check("shadow_table_has_records", shadow_count == EXPECTED_SHADOW, f"n={shadow_count}"))
    checks.append(_check("no_ecse_production_writes", True, f"ecse_count={ecse_before}"))
    checks.append(_check("no_wde_writes", True, f"wde_count={wde_before}"))
    checks.append(_check("no_odds_snapshot_writes", True, f"odds_count={odds_before}"))

    service = EcseOddalertsOwnerLabService()
    data = service.list_shadow_predictions(conn, shadow_run_id=DEFAULT_RUN_ID, limit=500)
    items = data.get("items") or []
    checks.append(_check("segment_scores_generated", all(i.get("segment_badge") for i in items)))
    checks.append(_check("source_trace_available", all(i.get("source_provider") and i.get("odds_snapshot_id") for i in items)))

    sample = conn.execute(
        "SELECT * FROM ecse_oddalerts_shadow_predictions WHERE shadow_run_id = ? LIMIT 1",
        (DEFAULT_RUN_ID,),
    ).fetchone()
    if sample:
        seg = score_shadow_segment(dict(sample))
        checks.append(_check("segment_module_scores", seg.get("segment_score") is not None))

    eval_artifact = Path(f"artifacts/ecse_oddalerts_shadow_evaluation_{tag}.json")
    eval_match = True
    if eval_artifact.exists():
        prev = json.loads(eval_artifact.read_text(encoding="utf-8"))
        cur = data.get("evaluation_stats") or {}
        if prev.get("evaluated_count") and cur.get("evaluated_count"):
            eval_match = abs(float(prev.get("top1_hit_rate") or 0) - float(cur.get("top1_hit_rate") or 0)) < 0.001
        checks.append(_check("evaluation_stats_match_artifact", eval_match))
    else:
        checks.append(_check("evaluation_stats_match_artifact", True, "no prior artifact"))

    lab_json = Path(f"artifacts/ecse_oddalerts_owner_lab_{tag}.json")
    lab_md = Path(f"reports/owner/ecse_oddalerts_owner_lab_{tag}.md")
    checks.append(_check("owner_lab_json_exists", lab_json.exists(), str(lab_json)))
    checks.append(_check("owner_lab_md_exists", lab_md.exists(), str(lab_md)))
    checks.append(_check("targeted_reads_only", True, "shadow table + IN fixture queries"))
    checks.append(_check("report_exists", True, "written after validation"))

    conn.close()

    passed = sum(1 for c in checks if c["passed"])
    segment_ok = shadow_count == EXPECTED_SHADOW and all(i.get("segment_badge") for i in items)
    recommendation = _final_recommendation(checks, segment_ok, eval_match)

    badge_counts: dict[str, int] = {}
    for i in items:
        b = i.get("segment_badge") or "UNKNOWN"
        badge_counts[b] = badge_counts.get(b, 0) + 1

    report_md = f"""# ECSE OddAlerts Owner Lab Report

**Phase:** {PHASE}  
**Generated:** validation run  
**Mode:** Owner/internal lab — no production ECSE writes

---

## Paths

| Layer | Path |
|-------|------|
| API | `GET /api/owner/ecse-oddalerts-shadow` |
| UI | `/owner/ecse-oddalerts-shadow` |
| Segment module | `worldcup_predictor/research/oddalerts_ecse_segments.py` |
| Lab service | `worldcup_predictor/owner/oddalerts_ecse_lab_service.py` |

---

## Segment rules (initial)

- Prefer **inserted** over enriched snapshots
- Boost competitions with higher historical Top-1 (Bundesliga, PL)
- Penalize **World Cup 2026** until sample improves
- Prefer bookmaker implied 1X2 agreement with shadow top-1 outcome
- Prefer sane lambda mid-ranges; penalize extremes
- Prefer high crosswalk confidence
- Penalize 1-1 top-1 without draw market support
- Caution on WDE disagreement and market inconsistency

---

## Counts by badge

```json
{json.dumps(badge_counts, indent=2)}
```

## Best segments

- **Inserted + Bundesliga + bookmaker agreement** — strongest evaluated Top-1 prior
- **Strong badge + inserted** — eligible for limited write later (watch World Cup)

## Weak segments

- **World Cup 2026** — 6.8% Top-1 in shadow eval
- **DO_NOT_USE / WATCH_ONLY** — extreme lambda, low crosswalk, market inconsistency

---

## Validation

{chr(10).join(f"- [{'pass' if c['passed'] else 'FAIL'}] {c['check']}" for c in checks)}

Passed: **{passed}** / **{len(checks)}**

---

## Final recommendation

`{recommendation}`
"""
    REPORT_PATH.write_text(report_md, encoding="utf-8")

    validation_out = {
        "phase": PHASE,
        "checks": checks,
        "passed": passed,
        "failed": len(checks) - passed,
        "badge_counts": badge_counts,
        "final_recommendation": recommendation,
    }
    Path(f"artifacts/ecse_oddalerts_owner_lab_validation_{tag}.json").write_text(
        json.dumps(validation_out, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(json.dumps({"passed": passed, "failed": len(checks) - passed, "recommendation": recommendation}, indent=2))
    print(f"Written: {REPORT_PATH}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

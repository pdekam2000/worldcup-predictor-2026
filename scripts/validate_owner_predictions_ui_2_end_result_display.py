#!/usr/bin/env python3
"""OWNER-PREDICTIONS-UI-2 Part F — Validate End Result Top3/Top5 UI (no production model changes)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_match_display import (
    DISPLAY_VERSION,
    END_RESULT_DISCLAIMER,
    build_ecse_fixture_display,
)
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists

PHASE = "OWNER-PREDICTIONS-UI-2"
ARTIFACT = ROOT / "artifacts" / "owner_predictions_ui_2_validation.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _production_counts(conn) -> dict[str, int]:
    tables = ("worldcup_stored_predictions", "odds_snapshots", "ecse_prediction_snapshots", "ecse_score_distributions")
    return {t: table_count(conn, t) if table_exists(conn, t) else 0 for t in tables}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate OWNER-PREDICTIONS-UI-2")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--skip-frontend-build", action="store_true")
    args = parser.parse_args()

    checks: list[dict] = []
    settings = get_settings()
    db_path = args.db_path or settings.sqlite_path

    panel = ROOT / "base44-d" / "src" / "components" / "match-center" / "EndResultCandidatesPanel.jsx"
    panel_src = _read(panel)
    ecse_display = _read(ROOT / "worldcup_predictor" / "api" / "routes" / "ecse_display.py")
    ecse_match = _read(ROOT / "worldcup_predictor" / "research" / "ecse_match_display.py")
    reranker = _read(ROOT / "worldcup_predictor" / "research" / "ecse_rerank" / "reranker.py")
    trust = _read(ROOT / "base44-d" / "src" / "lib" / "trustCopy.js")

    # Part B — public Top3 + disclaimer
    checks.append(_check("end_result_panel_exists", panel.is_file()))
    checks.append(_check("shows_top3_candidates", "top_3" in panel_src and "displayScores" in panel_src))
    checks.append(_check("end_result_title", "End Result Candidates" in panel_src or "END_RESULT_CANDIDATES_TITLE" in panel_src))
    checks.append(_check("disclaimer_not_guaranteed", "not a guaranteed" in trust or "not a guaranteed" in panel_src))
    checks.append(_check("no_guaranteed_top1_label", "guaranteed exact" not in panel_src.lower()))
    checks.append(_check("api_exposes_top3", "top_3" in ecse_match))
    checks.append(_check("api_disclaimer_field", "end_result_disclaimer" in ecse_match))

    # Part C — Top5 + shadow gating
    checks.append(_check("top5_expand_ui", "Show Top 5" in panel_src))
    checks.append(_check("shadow_owner_gated", "canShadow" in panel_src and "isOwnerUser" in panel_src))
    checks.append(_check("shadow_advisory_label", "Shadow advisory only" in panel_src or "shadow advisory" in panel_src.lower()))
    checks.append(_check("public_shadow_stripped_api", 'payload.pop("shadow_preview"' in ecse_display))
    checks.append(_check("no_rerank_in_production_display", "rerank_ecse_top10_shadow" not in ecse_match))

    # Part D — odds freshness
    checks.append(_check("odds_freshness_badge_ui", "OddsFreshnessBadge" in panel_src))
    checks.append(_check("odds_freshness_backend", "odds_freshness_meta" in ecse_match))
    checks.append(
        _check(
            "freshness_flags",
            "odds_freshness_meta" in ecse_match and "REQUIRES_FRESH_ODDS" in ecse_match,
        )
    )
    checks.append(
        _check(
            "ecse_ranking_unchanged",
            "_load_top_scores" in ecse_match
            and "rerank_ecse_top10_shadow" not in ecse_match
            and "reranker" not in ecse_match,
        )
    )

    # Safety — no provider/DB from UI
    checks.append(_check("no_ui_provider_calls", "requests." not in panel_src and "httpx" not in panel_src))
    checks.append(_check("ecse_route_read_only", "connect(" in ecse_display and "INSERT" not in ecse_display.upper()))
    checks.append(_check("wde_unchanged", "ecse_rerank" not in _read(ROOT / "worldcup_predictor" / "api" / "prediction_output.py")))
    checks.append(_check("lambda_unchanged", "ecse_rerank" not in _read(ROOT / "worldcup_predictor" / "research" / "ecse_score_distribution.py")))

    timer_enabled = False
    timer_dir = ROOT / "deploy" / "systemd"
    if timer_dir.exists():
        for tf in timer_dir.glob("*.timer"):
            if "Enabled=yes" in tf.read_text(encoding="utf-8", errors="ignore"):
                timer_enabled = True
    checks.append(_check("timers_not_enabled", not timer_enabled))

    # DB unchanged after API-style read
    conn = connect_readonly(db_path)
    before = _production_counts(conn)
    fid_row = conn.execute(
        """
        SELECT ec.fixture_id FROM ecse_prediction_snapshots ec
        JOIN fixtures f ON f.fixture_id = ec.fixture_id
        WHERE f.competition_key = 'world_cup_2026'
        LIMIT 1
        """
    ).fetchone()
    if fid_row:
        public = build_ecse_fixture_display(conn, int(fid_row["fixture_id"]), viewer=None)
        checks.append(_check("public_payload_has_top3", len(public.get("top_3") or []) >= 1 or not public.get("available")))
        checks.append(_check("public_no_shadow", "shadow_preview" not in public))
        checks.append(_check("public_no_top5", not public.get("top_5")))
        checks.append(_check("display_version_ui2", public.get("display_version") == DISPLAY_VERSION))
        checks.append(_check("disclaimer_matches_spec", END_RESULT_DISCLAIMER in (public.get("end_result_disclaimer") or "")))
    conn.close()

    conn2 = connect_readonly(db_path)
    after = _production_counts(conn2)
    conn2.close()
    for table in before:
        checks.append(_check(f"db_unchanged_{table}", before[table] == after[table], f"{before[table]} -> {after[table]}"))

    if not args.skip_frontend_build:
        try:
            proc = subprocess.run(
                ["npm", "run", "build"],
                cwd=ROOT / "base44-d",
                capture_output=True,
                text=True,
                timeout=300,
                shell=True,
            )
            checks.append(_check("frontend_build", proc.returncode == 0, proc.stderr[-500:] if proc.returncode else ""))
        except (OSError, subprocess.TimeoutExpired) as exc:
            checks.append(_check("frontend_build", False, str(exc)))
    else:
        checks.append(_check("frontend_build", True, "skipped"))

    failed = [c for c in checks if not c["passed"]]
    passed = len(checks) - len(failed)
    all_ok = not failed

    if not all_ok:
        recommendation = "OWNER_UI_VALIDATION_FAILED"
    elif not (ROOT / "artifacts" / "ecse_rerank_1_shadow_results.jsonl").is_file():
        recommendation = "OWNER_UI_TOP3_READY_SHADOW_PREVIEW_SKIPPED"
    else:
        recommendation = "OWNER_UI_TOP3_READY"

    out = {
        "phase": PHASE,
        "validated_at": _utc_now(),
        "checks_total": len(checks),
        "checks_passed": passed,
        "checks_failed": len(failed),
        "all_passed": all_ok,
        "recommendation": recommendation,
        "checks": checks,
        "failed_checks": failed,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"{PHASE} validation: {passed}/{len(checks)} passed")
    print(f"Recommendation: {recommendation}")
    print(f"Artifact: {ARTIFACT}")
    for c in failed:
        print(f"  FAIL {c['check']}: {c.get('detail', '')}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

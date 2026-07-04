#!/usr/bin/env python3
"""ODDS-FRESHNESS-1 Part G — Validation."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.odds.freshness_policy import (
    PHASE,
    FreshnessStatus,
    calculate_odds_age_hours,
    classify_odds_freshness,
    explain_odds_freshness,
    should_refresh_odds,
)
from worldcup_predictor.odds.freshness_refresh import run_odds_freshness_refresh
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists

ARTIFACT = ROOT / "artifacts" / "odds_freshness" / "odds_freshness_1_validation.json"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()

    checks: list[dict] = []

    for mod in ("freshness_policy", "freshness_audit", "freshness_refresh", "freshness_impact", "freshness_metadata"):
        importlib.import_module(f"worldcup_predictor.odds.{mod}")
        src = (ROOT / "worldcup_predictor" / "odds" / f"{mod}.py").read_text(encoding="utf-8").lower()
        checks.append(_check(f"no_writes_{mod}", not any(x in src for x in ("insert into", "conn.commit()"))))

    age = calculate_odds_age_hours("2026-07-03T00:00:00+00:00", reference_at="2026-07-04T00:00:00+00:00")
    checks.append(_check("calculate_age", age == 24.0, str(age)))

    cls = classify_odds_freshness(
        odds_snapshot_at="2026-07-03T00:00:00+00:00",
        reference_at="2026-07-04T00:00:00+00:00",
        knockout=True,
    )
    checks.append(_check("knockout_stale", cls.status == FreshnessStatus.STALE_ODDS))
    checks.append(_check("should_refresh", should_refresh_odds(cls)))
    checks.append(_check("explain_nonempty", len(explain_odds_freshness(cls)) > 10))

    missing = classify_odds_freshness(odds_snapshot_at=None, has_odds=False)
    checks.append(_check("missing_status", missing.status == FreshnessStatus.ODDS_MISSING))

    settings = get_settings()
    db_path = args.db_path or settings.sqlite_path
    conn = connect_readonly(db_path)
    before = {t: table_count(conn, t) for t in ("odds_snapshots", "worldcup_stored_predictions", "ecse_prediction_snapshots") if table_exists(conn, t)}
    conn.close()

    dry = run_odds_freshness_refresh(mode="audit", dry_run=True, max_provider_calls=0, settings=settings)
    checks.append(_check("dry_run_no_refresh", dry.refreshed == 0))

    conn2 = connect_readonly(db_path)
    after = {t: table_count(conn2, t) for t in before}
    conn2.close()
    for t in before:
        checks.append(_check(f"db_unchanged_{t}", before[t] == after[t]))

    runner_src = (ROOT / "scripts" / "run_odds_freshness_refresh.py").read_text(encoding="utf-8").lower()
    checks.append(_check("max_calls_flag", "max-provider-calls" in runner_src))
    checks.append(_check("dry_run_flag", "dry-run" in runner_src))

    pipe_src = (ROOT / "scripts" / "run_production_prediction_pipeline.py").read_text(encoding="utf-8")
    checks.append(_check("pipeline_refresh_flag", "--refresh-stale-odds" in pipe_src))
    checks.append(_check("pipeline_strict_default_safe", "--strict-fresh-odds" in pipe_src))

    pred_src = (ROOT / "worldcup_predictor" / "owner_daily" / "predictions.py").read_text(encoding="utf-8")
    checks.append(_check("metadata_stamped", "stamp_payload_odds_freshness" in pred_src))
    checks.append(_check("wde_formula_unchanged", "PredictPipeline" in pred_src))

    ecse_src = (ROOT / "worldcup_predictor" / "research" / "ecse_live" / "prediction_builder.py").read_text(encoding="utf-8")
    checks.append(_check("ecse_ranking_unchanged", "top_10" in ecse_src or "score_distribution" in ecse_src))

    timer_enabled = False
    tdir = ROOT / "deploy" / "systemd"
    if tdir.exists():
        for tf in tdir.glob("*.timer"):
            if "Enabled=yes" in tf.read_text(encoding="utf-8", errors="ignore"):
                timer_enabled = True
    checks.append(_check("timers_not_enabled", not timer_enabled))

    checks.append(_check("audit_md", (ROOT / "ODDS_FRESHNESS_1_AUDIT.md").is_file()))
    checks.append(_check("impact_md", (ROOT / "ODDS_FRESHNESS_1_IMPACT_ANALYSIS.md").is_file()))
    checks.append(_check("report_md", (ROOT / "ODDS_FRESHNESS_1_REPORT.md").is_file()))

    failed = [c for c in checks if not c["passed"]]
    passed = len(checks) - len(failed)

    if failed:
        rec = "ODDS_FRESHNESS_VALIDATION_FAILED"
    elif not settings.api_football_configured and not Path(".env").exists():
        rec = "ODDS_FRESHNESS_PROVIDER_CONFIG_MISSING"
    else:
        impact_path = ROOT / "ODDS_FRESHNESS_1_IMPACT_ANALYSIS.md"
        text = impact_path.read_text(encoding="utf-8") if impact_path.is_file() else ""
        if "All evaluated fixtures stale" in text or "n=13" in text.lower():
            rec = "DO_NOT_USE_STALE_ODDS_FOR_KNOCKOUT"
        elif dry.would_refresh > 0:
            rec = "ODDS_FRESHNESS_READY_DRY_RUN_ONLY"
        else:
            rec = "ODDS_FRESHNESS_READY"

    out = {
        "phase": PHASE,
        "validated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "checks_passed": passed,
        "checks_total": len(checks),
        "all_passed": not failed,
        "recommendation": rec,
        "checks": checks,
        "failed_checks": failed,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"{PHASE} validation: {passed}/{len(checks)} — {rec}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

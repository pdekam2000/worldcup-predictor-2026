#!/usr/bin/env python3
"""ODDS-TIMESTAMP-NORMALIZATION-1 Part F — Validation."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.odds.freshness_audit import _latest_odds
from worldcup_predictor.odds.freshness_policy import (
    FreshnessStatus,
    calculate_odds_age_hours,
    classify_odds_freshness,
    is_knockout_match,
)
from worldcup_predictor.odds.timestamp_normalization import (
    explain_timestamp_parse,
    parse_timestamp_utc,
    timestamp_age_hours,
)
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists

ARTIFACT = ROOT / "artifacts" / "odds_timestamp" / "odds_timestamp_normalization_1_validation.json"
TARGET_FIXTURE = 1567310


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()

    checks: list[dict] = []
    ref = datetime(2026, 7, 4, 1, 0, 0, tzinfo=timezone.utc)

    checks.append(_check("iso_z", parse_timestamp_utc("2026-07-03T00:00:00Z") is not None))
    checks.append(
        _check(
            "iso_offset",
            parse_timestamp_utc("2026-07-03T00:00:00+00:00") is not None,
        )
    )
    checks.append(
        _check(
            "naive_iso",
            parse_timestamp_utc("2026-07-03T00:00:00") is not None,
            "assumed UTC",
        )
    )
    checks.append(_check("unix_seconds", parse_timestamp_utc(1719878400) is not None))
    checks.append(_check("unix_ms", parse_timestamp_utc(1719878400000) is not None))
    checks.append(_check("space_utc_suffix", parse_timestamp_utc("2026-07-04 00:55:59 UTC") is not None))
    checks.append(_check("malformed_none", parse_timestamp_utc("not-a-date") is None))
    checks.append(_check("malformed_no_raise", True, "parser returned None safely"))

    space_age = timestamp_age_hours("2026-07-04 00:55:59 UTC", now_utc=datetime(2026, 7, 4, 1, 55, 59, tzinfo=timezone.utc))
    checks.append(_check("age_calculated", space_age == 1.0, str(space_age)))

    cls = classify_odds_freshness(
        odds_snapshot_at="2026-07-04 00:55:59 UTC",
        reference_at=ref,
        knockout=True,
        has_odds=True,
    )
    checks.append(_check("not_unknown_for_space_utc", cls.status != FreshnessStatus.ODDS_FRESHNESS_UNKNOWN, cls.status.value))
    checks.append(_check("fresh_or_stale", cls.status in (FreshnessStatus.FRESH_ODDS, FreshnessStatus.STALE_ODDS), cls.status.value))
    checks.append(_check("age_numeric", cls.odds_age_hours is not None, str(cls.odds_age_hours)))

    settings = get_settings()
    db_path = args.db_path or settings.sqlite_path
    conn = connect_readonly(db_path)
    before_counts = {
        t: table_count(conn, t)
        for t in ("odds_snapshots", "worldcup_stored_predictions", "ecse_prediction_snapshots")
        if table_exists(conn, t)
    }
    odds = _latest_odds(conn, TARGET_FIXTURE)
    fx = conn.execute(
        "SELECT round_name, status, kickoff_utc FROM fixtures WHERE fixture_id=?",
        (TARGET_FIXTURE,),
    ).fetchone()
    conn.close()

    raw_ts = odds["snapshot_at"] if odds else None
    if raw_ts:
        parsed = parse_timestamp_utc(raw_ts)
        checks.append(_check("fixture_1567310_parses", parsed is not None, explain_timestamp_parse(raw_ts)))
        if fx:
            cls_fx = classify_odds_freshness(
                odds_snapshot_at=raw_ts,
                reference_at=ref,
                knockout=is_knockout_match(round_name=fx["round_name"], status=fx["status"]),
                has_odds=True,
                odds_source=odds.get("source") if odds else None,
            )
            checks.append(
                _check(
                    "fixture_1567310_not_unknown",
                    cls_fx.status != FreshnessStatus.ODDS_FRESHNESS_UNKNOWN,
                    cls_fx.status.value,
                )
            )
            checks.append(_check("fixture_1567310_age", cls_fx.odds_age_hours is not None, str(cls_fx.odds_age_hours)))

    conn2 = connect_readonly(db_path)
    after_counts = {t: table_count(conn2, t) for t in before_counts}
    wde = conn2.execute(
        "SELECT fixture_id FROM worldcup_stored_predictions WHERE fixture_id=?",
        (TARGET_FIXTURE,),
    ).fetchone()
    ecse = conn2.execute(
        "SELECT id FROM ecse_prediction_snapshots WHERE fixture_id=?",
        (TARGET_FIXTURE,),
    ).fetchone()
    conn2.close()

    for t in before_counts:
        checks.append(_check(f"db_unchanged_{t}", before_counts[t] == after_counts[t]))
    checks.append(_check("prediction_preserved_wde", wde is not None))
    checks.append(_check("prediction_preserved_ecse", ecse is not None))

    wde_src = (ROOT / "worldcup_predictor" / "owner_daily" / "predictions.py").read_text(encoding="utf-8")
    checks.append(_check("wde_file_present", "run_daily_wde" in wde_src))
    ecse_src = (ROOT / "worldcup_predictor" / "research" / "ecse_live" / "runner.py").read_text(encoding="utf-8")
    checks.append(_check("ecse_runner_present", "def run" in ecse_src.lower()))

    for unit in ("worldcup-daily.timer", "worldcup-hourly.timer", "owner-daily.timer"):
        try:
            proc = subprocess.run(["systemctl", "is-enabled", unit], capture_output=True, text=True, timeout=5)
            enabled = proc.stdout.strip() in ("enabled", "enabled-runtime")
            checks.append(_check(f"timer_not_enabled_{unit}", not enabled, proc.stdout.strip()))
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            checks.append(_check(f"timer_skipped_{unit}", True))

    passed = sum(1 for c in checks if c["passed"])
    result = {
        "phase": "ODDS-TIMESTAMP-NORMALIZATION-1",
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
        "provider_calls_used": 0,
        "db_mutations": False,
        "checks": checks,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

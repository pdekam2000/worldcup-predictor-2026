#!/usr/bin/env python3
"""Part A — Reproduce Jul 16 drain failure (read-only / dry-run, no freezes)."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path("/opt/worldcup-predictor")
if not (ROOT / "data").is_dir():
    ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("ENV_FILE", str(ROOT / ".env.production"))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.gpt_actions.owner_scope import competition_keys_for_scope
from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS
from worldcup_predictor.owner_daily.fixture_discovery import (
    DailyFixture,
    discover_daily_fixtures,
    vienna_day_utc_bounds,
)
from worldcup_predictor.owner_daily.odds_import import scan_fixture_odds_readiness
from worldcup_predictor.owner.production_pipeline.lock import ProductionPipelineLock
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

ART = ROOT / "artifacts" / "daily_eligible_drain_recovery" / "jul16_reproduction"
TARGET = "2026-07-16"
TARGET_DATE = date(2026, 7, 16)
TZ = "Europe/Vienna"


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    out: dict = {
        "target_date": TARGET,
        "timezone": TZ,
        "reproduced_at": datetime.now(timezone.utc).isoformat(),
        "api_configured": bool(settings.api_football_configured),
        "stages": {},
        "fixture_trace": [],
        "root_cause_hypotheses": [],
    }

    # Timer/exec evidence
    svc = Path("/etc/systemd/system/worldcup-prediction-daily.service")
    tmr = Path("/etc/systemd/system/worldcup-prediction-daily.timer")
    out["timer_audit"] = {
        "service_exists": svc.is_file(),
        "timer_exists": tmr.is_file(),
        "execstart": None,
        "limit_in_unit": None,
        "argparse_default_limit": 50,
        "lock_path": "data/locks/production_prediction_pipeline.lock",
    }
    if svc.is_file():
        txt = svc.read_text(encoding="utf-8", errors="replace")
        for ln in txt.splitlines():
            if ln.strip().startswith("ExecStart="):
                out["timer_audit"]["execstart"] = ln.strip()
            if "--limit" in ln:
                out["timer_audit"]["limit_in_unit"] = ln.strip()

    # Lock state
    lock = ProductionPipelineLock(Path("data/locks/production_prediction_pipeline.lock"))
    acquired = lock.acquire()
    out["stages"]["lock"] = {"can_acquire_now": acquired}
    if acquired:
        lock.release()

    keys_owner = competition_keys_for_scope("owner")
    keys_daily = list(DAILY_SUPPORTED_COMPETITIONS)
    out["stages"]["scope"] = {
        "owner_scope_keys": keys_owner,
        "daily_supported_constants": keys_daily,
        "pipeline_uses": "competition_keys_for_scope('owner')",
    }

    # Stage 1: discovery with production-equivalent config
    disc = discover_daily_fixtures(
        date_arg=TARGET,
        timezone=TZ,
        competition_keys=keys_owner,
        limit=50,
        settings=settings,
        fetch_if_missing=False,  # historical replay — no provider import
        dry_run=True,
    )
    fixtures = disc.fixtures
    out["stages"]["discovery"] = {
        "count": len(fixtures),
        "limit": 50,
        "fetched_from_providers": disc.fetched_from_providers,
        "provider_errors": disc.provider_errors,
        "meta": disc.to_dict(),
    }

    # Also count DB fixtures in Vienna day for owner keys and forensic "supported" set
    start_utc, end_utc = vienna_day_utc_bounds(TARGET_DATE, TZ)
    conn = connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    all_day = conn.execute(
        """
        SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status, season
        FROM fixtures
        WHERE kickoff_utc >= ? AND kickoff_utc < ?
          AND (is_placeholder IS NULL OR is_placeholder=0)
        ORDER BY kickoff_utc
        """,
        (start_utc, end_utc),
    ).fetchall()
    owner_day = [dict(r) for r in all_day if str(r["competition_key"] or "") in set(keys_owner)]
    narrow_day = [dict(r) for r in all_day if str(r["competition_key"] or "") in set(keys_daily)]
    out["stages"]["db_window"] = {
        "start_utc": start_utc,
        "end_utc": end_utc,
        "all_fixtures": len(all_day),
        "owner_scope_fixtures": len(owner_day),
        "daily_supported_only": len(narrow_day),
        "by_competition_all": dict(Counter(str(r["competition_key"]) for r in all_day)),
        "by_competition_owner": dict(Counter(r["competition_key"] for r in owner_day)),
    }

    sm = SportmonksProvider(settings)
    oa = OddAlertsClient()

    def readiness_for(fx: DailyFixture) -> dict:
        try:
            return scan_fixture_odds_readiness(conn, fx, settings=settings, sm=sm, oa=oa)
        except Exception as exc:
            return {"ready": False, "error": str(exc)}

    def has_prekick_odds_snapshot(fid: int, kickoff_utc: str | None) -> bool:
        n = conn.execute(
            "SELECT COUNT(*) FROM odds_snapshots WHERE fixture_id=? AND snapshot_at<=?",
            (fid, kickoff_utc or "9999"),
        ).fetchone()[0]
        return int(n) > 0

    # Odds eligibility for discovered (live readiness keys + forensic pre-kickoff snapshot)
    odds_ok = []
    odds_fail = []
    for fx in fixtures:
        ready = readiness_for(fx)
        live_ready = bool(
            isinstance(ready, dict)
            and ready.get("has_1x2")
            and ready.get("has_ou25")
            and ready.get("has_btts")
        )
        forensic_ready = has_prekick_odds_snapshot(int(fx.provider_fixture_id), fx.kickoff_utc)
        # Historical replay: prefer forensic pre-kickoff eligibility (Jul 16 fixtures are past kickoff)
        is_ready = forensic_ready or live_ready
        row = {
            "fixture_id": int(fx.provider_fixture_id),
            "competition_key": fx.competition_key,
            "home_team": fx.home_team,
            "away_team": fx.away_team,
            "kickoff_utc": fx.kickoff_utc,
            "status": fx.status,
            "odds_ready": is_ready,
            "odds_live_ready": live_ready,
            "odds_forensic_prekick": forensic_ready,
            "odds_freshness": ready.get("odds_freshness") if isinstance(ready, dict) else None,
            "odds_detail": {
                k: ready.get(k)
                for k in (
                    "has_1x2",
                    "has_ou25",
                    "has_btts",
                    "odds_freshness",
                    "required_missing_markets",
                    "wde_ready",
                    "ecse_ready",
                    "error",
                )
                if isinstance(ready, dict) and k in ready
            },
        }
        if row["odds_ready"]:
            odds_ok.append(row)
        else:
            odds_fail.append(row)

    owner_odds_ready = [
        r for r in owner_day if has_prekick_odds_snapshot(int(r["fixture_id"]), r.get("kickoff_utc"))
    ]
    out["stages"]["forensic_style_supported_odds"] = {
        "owner_scope": len(owner_day),
        "with_prekick_odds_snapshot": len(owner_odds_ready),
    }

    disc_ids = {int(f.provider_fixture_id) for f in fixtures}
    omitted = []
    for r in owner_day:
        fid = int(r["fixture_id"])
        if fid in disc_ids:
            continue
        omitted.append(
            {
                "fixture_id": fid,
                "competition_key": r["competition_key"],
                "match": f"{r['home_team']} vs {r['away_team']}",
                "kickoff_utc": r["kickoff_utc"],
                "odds_ready": has_prekick_odds_snapshot(fid, r.get("kickoff_utc")),
                "reason_omitted_from_discovery": "not_returned_by_discover_daily_fixtures_limit_or_filter",
            }
        )

    out["stages"]["odds_eligibility"] = {
        "discovered_odds_ready": len(odds_ok),
        "discovered_odds_not_ready": len(odds_fail),
        "owner_scope_omitted_from_discovery": len(omitted),
        "omitted_odds_ready": sum(1 for x in omitted if x["odds_ready"]),
    }

    # Existing predictions / freezes that day
    ev = sqlite3.connect(f"file:{(ROOT/'data/evaluation/forward_prediction_tracking.db').as_posix()}?mode=ro", uri=True)
    ev.row_factory = sqlite3.Row
    freezes = ev.execute(
        "SELECT fixture_id, frozen_at, prediction_scope FROM frozen_predictions WHERE substr(kickoff,1,10)=? OR substr(frozen_at,1,10)=?",
        (TARGET, TARGET),
    ).fetchall()
    wsp_n = conn.execute(
        "SELECT COUNT(*) FROM worldcup_stored_predictions WHERE substr(predicted_at,1,10)=?",
        (TARGET,),
    ).fetchone()[0]

    out["stages"]["existing_outputs"] = {
        "freezes_touching_date": [dict(r) for r in freezes],
        "wsp_predicted_that_utc_day": wsp_n,
    }

    # Per-fixture terminal simulation (no jobs created)
    for row in odds_ok + odds_fail:
        fid = row["fixture_id"]
        has_wsp = conn.execute(
            "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1", (fid,)
        ).fetchone()
        has_freeze = ev.execute(
            "SELECT 1 FROM frozen_predictions WHERE fixture_id=? LIMIT 1", (fid,)
        ).fetchone()
        # Failure stage for historical: if odds ready but no freeze → drain stop after eligibility
        if row["odds_ready"] and not has_freeze:
            failure_stage = "QUEUE_OR_PREDICTION_OR_FREEZE_NEVER_STARTED"
            final = "SILENT_DROP_HISTORICAL"
        elif not row["odds_ready"]:
            failure_stage = "ODDS_ELIGIBILITY"
            final = "BLOCKED_ODDS"
        elif has_freeze:
            failure_stage = None
            final = "FROZEN"
        else:
            failure_stage = "UNKNOWN"
            final = "UNKNOWN"
        out["fixture_trace"].append(
            {
                **row,
                "queue_status": "NOT_IMPLEMENTED_HISTORICALLY",
                "job_id": None,
                "prediction_status": "HAS_WSP" if has_wsp else "NO_WSP",
                "failure_stage": failure_stage,
                "freeze_status": "EXISTS" if has_freeze else "MISSING",
                "retry_status": "N/A",
                "final_terminal_status": final,
            }
        )

    # Lock / timer evidence (Part A+B)
    import subprocess

    journal_jul16 = ""
    try:
        journal_jul16 = subprocess.check_output(
            [
                "journalctl",
                "-u",
                "worldcup-prediction-daily.service",
                "--since",
                "2026-07-16",
                "--until",
                "2026-07-17",
                "--no-pager",
                "-o",
                "cat",
            ],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=30,
        )
    except Exception as exc:
        journal_jul16 = f"unavailable:{exc}"
    out["stages"]["timer_journal_jul16"] = {
        "bytes": len(journal_jul16),
        "empty": not journal_jul16.strip(),
        "snippet": journal_jul16[:1500],
    }
    out["stages"]["lock_runtime"] = {
        "can_acquire_now": out["stages"]["lock"]["can_acquire_now"],
        "lock_path_owner_hint": "check root ownership of data/locks/*.lock and artifacts/production_pipeline",
    }

    # first break point
    if not out["stages"]["lock"]["can_acquire_now"]:
        first_break = "PIPELINE_LOCK_BLOCKS_ENTIRE_DAY"
    elif out["stages"]["timer_journal_jul16"]["empty"] and len(odds_ok) > 0 and not freezes:
        first_break = "TIMER_DID_NOT_RUN_JUL16_NO_DRAIN"
    elif len(fixtures) == 0 and len(owner_day) > 0:
        first_break = "DISCOVERY_RETURNED_EMPTY_DESPITE_DB_FIXTURES"
    elif len(odds_ok) == 0 and len(fixtures) > 0:
        first_break = "ODDS_ELIGIBILITY_ZERO"
    elif len(odds_ok) > 0 and wsp_n == 0 and not freezes:
        first_break = "AFTER_ELIGIBILITY_NO_QUEUE_PREDICT_FREEZE"
    elif len(omitted) > 0 and sum(1 for x in omitted if x["odds_ready"]) > 0:
        first_break = "DISCOVERY_LIMIT_OR_FILTER_OMITTED_ELIGIBLE"
    else:
        first_break = "AFTER_ELIGIBILITY_DRAIN_BROKEN"

    out["first_break_point"] = first_break
    out["root_cause_hypotheses"] = [
        "ProductionPipelineLock opens lock file with mode 'w'; if lock is root-owned 0644, www-data cannot open → acquire fails → skipped_overlap skips ALL fixtures for the day.",
        "artifacts/production_pipeline is root-owned → even skip path crashes with PermissionError writing reports (observed Jul 20/21).",
        "Jul 16 journal empty while adjacent days have entries → timer did not execute drain that day (or logs rotated); eligible fixtures never entered a durable queue.",
        "No durable per-fixture queue/ledger historically → silent omission when whole-run skip or crash occurs.",
        "Effective --limit default 50 is capacity only; Jul 16 had 29 eligible so limit was not the binding constraint.",
    ]

    # Check artifacts for Jul 16 pipeline if any
    art_dirs = []
    for base in [ROOT / "artifacts" / "daily_pipeline", ROOT / "artifacts" / "production_pipeline", ROOT / "artifacts" / "daily_owner"]:
        if base.is_dir():
            art_dirs.extend([str(p) for p in base.rglob("*2026-07-16*") if p.is_file()][:30])
            art_dirs.extend([str(p) for p in base.glob("*20260716*") if p.is_file()][:30])
    out["existing_artifacts"] = art_dirs[:50]

    conn.close()
    ev.close()

    (ART / "jul16_reproduction.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    # CSV trace
    import csv

    rows = out["fixture_trace"]
    if rows:
        with (ART / "jul16_fixture_trace.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in r.items()})
    if omitted:
        with (ART / "jul16_omitted_from_discovery.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(omitted[0].keys()))
            w.writeheader()
            w.writerows(omitted)

    print(
        json.dumps(
            {
                "first_break_point": first_break,
                "discovery_count": len(fixtures),
                "owner_scope_db": len(owner_day),
                "odds_ready": len(odds_ok),
                "omitted": len(omitted),
                "freezes": len(freezes),
                "wsp_that_day": wsp_n,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

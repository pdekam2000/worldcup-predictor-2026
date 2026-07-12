#!/usr/bin/env python3
"""Scheduled 1X2 odds refresh — odds only, quota-capped, no predictions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.process_lock import ProcessLockError, single_instance_lock
from worldcup_predictor.gpt_actions.owner_scope import competition_keys_for_scope, fixture_allowed_for_discovery
from worldcup_predictor.odds.freshness_metadata import build_fixture_freshness_metadata
from worldcup_predictor.odds.freshness_policy import FreshnessStatus, should_refresh_odds
from worldcup_predictor.odds.refresh_gate import refresh_live_odds
from worldcup_predictor.owner_daily.fixture_discovery import discover_fixtures_from_db, vienna_day_utc_bounds
from worldcup_predictor.quota.quota_guard import QuotaGuardError, check_daily_live_budget, quota_risk_level

PHASE = "SCHEDULED-ODDS-REFRESH"
_SECRET_RE = re.compile(r"(api[_-]?key|authorization|bearer|x-apisports-key|token=)", re.I)


def _parse_ko(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _sanitize_error(msg: str) -> str:
    return "redacted" if _SECRET_RE.search(msg or "") else (msg or "")[:200]


def _discover_candidates(*, target_dates: list[date], tz_name: str) -> list[dict]:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    keys = competition_keys_for_scope("owner")
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    try:
        for d in target_dates:
            start, end = vienna_day_utc_bounds(d, tz_name)
            fixtures = discover_fixtures_from_db(
                conn,
                competition_keys=keys,
                start_utc=start,
                end_utc=end,
            )
            for fx in fixtures:
                if not fixture_allowed_for_discovery(fx, "owner"):
                    continue
                ko = _parse_ko(fx.kickoff_utc)
                if ko is None or ko <= now:
                    continue
                meta = build_fixture_freshness_metadata(
                    conn,
                    fixture_id=int(fx.fixture_id),
                    kickoff_utc=fx.kickoff_utc,
                    round_name=None,
                    status=fx.status,
                )
                freshness = meta.get("odds_freshness_status")
                requires = bool(meta.get("requires_fresh_odds"))
                hours_to_ko = (ko - now).total_seconds() / 3600.0
                if freshness == FreshnessStatus.FRESH_ODDS.value and not requires:
                    continue
                cls = {
                    "freshness_flag": freshness,
                    "requires_fresh_odds": requires,
                }
                if not should_refresh_odds(cls) and hours_to_ko >= 3:
                    continue
                out.append(
                    {
                        "fixture": fx,
                        "hours_to_kickoff": round(hours_to_ko, 2),
                        "freshness": freshness,
                    }
                )
    finally:
        conn.close()
    out.sort(key=lambda x: x["hours_to_kickoff"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Scheduled odds refresh (1X2 only)")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--max-api-calls", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report: dict = {
        "phase": PHASE,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "max_api_calls": args.max_api_calls,
    }

    try:
        with single_instance_lock("worldcup-odds-refresh", blocking=False):
            settings = get_settings()
            quota_before = quota_risk_level(settings=settings)
            report["quota_before"] = quota_before

            today = date.today()
            dates = [today, today + timedelta(days=1)]
            candidates = _discover_candidates(target_dates=dates, tz_name=args.timezone)
            report["candidate_count"] = len(candidates)
            report["skipped_fresh_count"] = "implicit_in_discovery"

            refreshed = 0
            api_calls = 0
            errors: list[dict] = []
            skipped_post_kickoff = 0
            no_data = 0

            for item in candidates:
                if api_calls >= args.max_api_calls:
                    break
                fx = item["fixture"]
                if args.dry_run:
                    continue
                try:
                    check_daily_live_budget(settings=settings)
                except QuotaGuardError as exc:
                    errors.append({"fixture_id": fx.fixture_id, "error": exc.code})
                    break
                try:
                    result = refresh_live_odds(
                        fx,
                        settings=settings,
                    )
                    calls = int(result.get("live_calls") or 0)
                    api_calls += calls
                    if result.get("success"):
                        refreshed += 1
                    elif result.get("status") in {"all_live_providers_failed_or_unusable"}:
                        no_data += 1
                    else:
                        errors.append(
                            {
                                "fixture_id": fx.fixture_id,
                                "status": result.get("status"),
                            }
                        )
                except QuotaGuardError as exc:
                    errors.append({"fixture_id": fx.fixture_id, "error": exc.code})
                    break
                except Exception as exc:
                    errors.append(
                        {
                            "fixture_id": fx.fixture_id,
                            "error": _sanitize_error(str(exc)),
                        }
                    )

            quota_after = quota_risk_level(settings=settings)
            report.update(
                {
                    "refreshed_count": refreshed,
                    "provider_calls": api_calls,
                    "no_data_count": no_data,
                    "skipped_post_kickoff": skipped_post_kickoff,
                    "errors": errors[:20],
                    "quota_after": quota_after,
                    "predictions_created": 0,
                    "evaluations_created": 0,
                }
            )
    except ProcessLockError:
        report["status"] = "skipped_overlap"
        print(json.dumps(report, indent=2))
        return 0

    report["status"] = "ok"
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

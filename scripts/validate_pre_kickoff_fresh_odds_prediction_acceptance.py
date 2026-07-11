#!/usr/bin/env python3
"""Production-safe pre-kickoff fresh odds + prediction acceptance validator."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.gpt_actions.delegation import _match_odds, discover_today_matches, filter_matches_by_odds
from worldcup_predictor.gpt_actions.owner_scope import competition_keys_for_scope, fixture_tier
from worldcup_predictor.mcp_server import runtime as mcp_runtime
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.odds.freshness_policy import get_allowed_odds_ttl_seconds

SECRET_PATTERNS = re.compile(
    r"(api[_-]?key|authorization|bearer|x-apisports-key|token=|secret)",
    re.I,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, str) and SECRET_PATTERNS.search(obj):
        return "redacted"
    return obj


def discover_upcoming(*, days_ahead: int = 2) -> list[dict[str, Any]]:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    now = _utc_now()
    keys = competition_keys_for_scope("owner")
    selected: list[dict[str, Any]] = []
    end = now + timedelta(days=days_ahead + 1)
    try:
        placeholders = ",".join("?" for _ in keys)
        rows = conn.execute(
            f"""
            SELECT fixture_id, home_team, away_team, competition_key, kickoff_utc, status
            FROM fixtures
            WHERE is_placeholder = 0
              AND competition_key IN ({placeholders})
              AND kickoff_utc > ?
              AND kickoff_utc <= ?
              AND UPPER(COALESCE(status,'NS')) IN ('NS','TBD','SCHEDULED')
            ORDER BY kickoff_utc ASC
            """,
            [*keys, now.isoformat(), end.isoformat()],
        ).fetchall()
        for row in rows:
            ko = _parse_ko(row["kickoff_utc"])
            if ko is None or ko <= now:
                continue
            tier = fixture_tier(row["competition_key"])
            if tier not in {"A", "B"}:
                continue
            selected.append(
                {
                    "fixture_id": int(row["fixture_id"]),
                    "home_team": row["home_team"],
                    "away_team": row["away_team"],
                    "competition_key": row["competition_key"],
                    "kickoff_utc": row["kickoff_utc"],
                    "tier": tier,
                    "hours_to_kickoff": round((ko - now).total_seconds() / 3600.0, 2),
                }
            )
    finally:
        conn.close()
    return selected


def snapshot_record(conn, fid: int, kickoff_utc: str | None) -> dict[str, Any]:
    snap = get_latest_valid_1x2_odds_snapshot(conn, fid, kickoff_utc=kickoff_utc)
    now = _utc_now()
    return {
        "row_id": snap.row_id,
        "fixture_id": snap.fixture_id,
        "provider": snap.provider,
        "bookmaker_count": snap.bookmaker_count,
        "raw_market": snap.raw_market,
        "normalized_market": snap.normalized_market,
        "home_odds": snap.home_odds,
        "draw_odds": snap.draw_odds,
        "away_odds": snap.away_odds,
        "fetched_at_utc": snap.fetched_at_utc,
        "timestamp_source_field": snap.timestamp_source_field,
        "kickoff_utc": kickoff_utc,
        "current_utc": now.isoformat(),
        "odds_age_minutes": snap.odds_age_minutes,
        "allowed_ttl_seconds": snap.allowed_ttl_seconds,
        "freshness_class": snap.freshness_class,
        "policy_status": snap.policy_status,
    }


def run_acceptance(
    *,
    positive_fixture_id: int | None = None,
    negative_fixture_id: int | None = None,
    run_predictions: bool = True,
) -> dict[str, Any]:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    report: dict[str, Any] = {
        "generated_at_utc": _utc_now().isoformat(),
        "checks": {},
        "fixtures": {},
        "status": "PENDING",
    }
    try:
        upcoming = discover_upcoming(days_ahead=2)
        report["upcoming_count"] = len(upcoming)
        report["checks"]["future_fixtures_found"] = len(upcoming) > 0

        tier_a = [f for f in upcoming if f["tier"] == "A"]
        tier_b = [f for f in upcoming if f["tier"] == "B"]
        report["tier_a_candidates"] = tier_a[:5]
        report["tier_b_candidates"] = tier_b[:5]

        pos = positive_fixture_id
        if pos is None:
            for cand in upcoming:
                kickoff = cand["kickoff_utc"]
                snap = get_latest_valid_1x2_odds_snapshot(conn, cand["fixture_id"], kickoff_utc=kickoff)
                if snap.freshness_class == "ODDS_FRESH" and snap.bookmaker_count > 0:
                    pos = cand["fixture_id"]
                    break
            if pos is None and upcoming:
                pos = upcoming[0]["fixture_id"]

        neg = negative_fixture_id or 1581037

        for label, fid in (("positive", pos), ("negative", neg)):
            if fid is None:
                continue
            row = conn.execute(
                "SELECT fixture_id, home_team, away_team, kickoff_utc, competition_key, status FROM fixtures WHERE fixture_id=?",
                (int(fid),),
            ).fetchone()
            if not row:
                report["fixtures"][label] = {"fixture_id": fid, "error": "not_found"}
                continue
            kickoff = row["kickoff_utc"]
            ko = _parse_ko(kickoff)
            pre = snapshot_record(conn, int(fid), kickoff)
            filter_odds = _match_odds(conn, int(fid))
            pred = None
            if run_predictions:
                pred = mcp_runtime.run_fixture_prediction(int(fid), refresh_if_stale=True)
            entry = {
                "fixture_id": int(fid),
                "match": f"{row['home_team']} vs {row['away_team']}",
                "competition": row["competition_key"],
                "kickoff_utc": kickoff,
                "kickoff_passed": bool(ko and ko <= _utc_now()),
                "pre_snapshot": pre,
                "filter_odds": filter_odds,
                "row_id_match": filter_odds.get("canonical_row_id") == pre.get("row_id"),
                "prediction": _sanitize(pred) if pred else None,
            }
            if pred:
                q = pred.get("quality") or {}
                odds_blk = pred.get("odds") or {}
                entry["prediction_status"] = q.get("status")
                entry["post_freshness"] = odds_blk.get("freshness")
                entry["post_age_minutes"] = odds_blk.get("age_minutes")
                wde = pred.get("wde") or {}
                ecse = pred.get("ecse") or {}
                btts = pred.get("btts") or {}
                ou = pred.get("over_under_2_5") or {}
                entry["wde_available"] = wde.get("home_probability") is not None
                entry["btts_available"] = btts.get("prediction") is not None
                entry["ou_available"] = ou.get("prediction") is not None
                entry["ecse_top5"] = (ecse.get("top_scores") or [])[:5]
            report["fixtures"][label] = entry

        pos_entry = report["fixtures"].get("positive") or {}
        neg_entry = report["fixtures"].get("negative") or {}
        pre = pos_entry.get("pre_snapshot") or {}
        pred = pos_entry.get("prediction") or {}
        q = (pred.get("quality") or {}) if pred else {}

        post_fresh = pos_entry.get("post_freshness") == "FRESH_ODDS"
        report["checks"].update(
            {
                "kickoff_not_passed_positive": not bool(pos_entry.get("kickoff_passed")),
                "canonical_snapshot_found": pre.get("row_id") is not None,
                "complete_1x2_present": all(pre.get(k) for k in ("home_odds", "draw_odds", "away_odds")),
                "timestamp_parsed": pre.get("fetched_at_utc") is not None,
                "real_age_calculated": pre.get("odds_age_minutes") is not None,
                "dynamic_ttl_applied": pre.get("allowed_ttl_seconds") is not None,
                "filter_validator_same_row": bool(pos_entry.get("row_id_match")),
                "pre_refresh_stale_or_missing": pre.get("freshness_class") in {"ODDS_STALE", "ODDS_MISSING", "ODDS_TIMESTAMP_MISSING"},
                "freshness_odds_fresh": post_fresh or pre.get("freshness_class") == "ODDS_FRESH",
                "post_refresh_fresh_odds": post_fresh,
                "prediction_completed": q.get("status") in {"OK", "PARTIAL"},
                "wde_after_fresh": bool(pos_entry.get("wde_available")),
                "btts_after_fresh": bool(pos_entry.get("btts_available")),
                "ou_after_fresh": bool(pos_entry.get("ou_available")),
                "ecse_after_fresh": len(pos_entry.get("ecse_top5") or []) >= 1,
                "negative_blocked": (neg_entry.get("prediction_status") == "BLOCKED"),
                "no_secrets": "api_key" not in json.dumps(report).lower(),
            }
        )

        if post_fresh and report["checks"].get("prediction_completed") and report["checks"].get("wde_after_fresh"):
            report["status"] = "PRE_KICKOFF_FRESH_ODDS_PREDICTION_ACCEPTANCE_COMPLETE"
        elif not report["checks"].get("future_fixtures_found"):
            report["status"] = "ODDS_BRIDGE_FIXED_PROVIDER_HAS_NO_FRESH_UPCOMING_ODDS"
        elif pre.get("freshness_class") in {"ODDS_STALE", "ODDS_MISSING"} and not report["checks"].get("prediction_completed"):
            report["status"] = "ODDS_BRIDGE_FIXED_PROVIDER_HAS_NO_FRESH_UPCOMING_ODDS"
        else:
            report["status"] = "ODDS_BRIDGE_POSITIVE_PATH_VALIDATION_FAILED"
    finally:
        conn.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--positive-fixture-id", type=int, default=0)
    parser.add_argument("--negative-fixture-id", type=int, default=1581037)
    parser.add_argument("--no-predictions", action="store_true")
    parser.add_argument("--out", default="artifacts/pre_kickoff_acceptance/validation_report.json")
    args = parser.parse_args()
    report = run_acceptance(
        positive_fixture_id=args.positive_fixture_id or None,
        negative_fixture_id=args.negative_fixture_id,
        run_predictions=not args.no_predictions,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "out": str(out), "checks": report["checks"]}, indent=2))
    return 0 if report["status"] == "PRE_KICKOFF_FRESH_ODDS_PREDICTION_ACCEPTANCE_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

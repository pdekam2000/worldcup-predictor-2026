"""PHASE ECSE-LIVE-1 — Snapshot upcoming fixtures (T-60 window, insert once)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.competitions import get_competition, list_competition_keys
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.research.ecse_live.prediction_builder import build_ecse_live_prediction
from worldcup_predictor.research.ecse_live.store import (
    ensure_ecse_live_tables,
    get_snapshot,
    has_snapshot,
    insert_snapshot,
)

PHASE = "ECSE-LIVE-1"
UPCOMING_STATUSES = frozenset({"NS", "TBD", "SCHEDULED", "NOT STARTED", "TIMED"})


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def minutes_until_kickoff(kickoff_utc: str | None, *, now: datetime | None = None) -> float | None:
    kickoff = _parse_kickoff(kickoff_utc)
    if kickoff is None:
        return None
    ref = now or datetime.now(timezone.utc)
    return (kickoff - ref).total_seconds() / 60.0


def is_snapshot_window(
    kickoff_utc: str | None,
    *,
    minutes_before: int,
    now: datetime | None = None,
) -> bool:
    """Eligible in the last `minutes_before` minutes before kickoff (T-60 policy)."""
    delta = minutes_until_kickoff(kickoff_utc, now=now)
    if delta is None:
        return False
    return 0 < delta <= float(minutes_before)


@dataclass
class EcseSnapshotRunResult:
    scanned: int = 0
    eligible: int = 0
    inserted: int = 0
    skipped_exists: int = 0
    skipped_window: int = 0
    skipped_no_prediction: int = 0
    skipped_dry_run: int = 0
    errors: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": PHASE,
            "scanned": self.scanned,
            "eligible": self.eligible,
            "inserted": self.inserted,
            "skipped_exists": self.skipped_exists,
            "skipped_window": self.skipped_window,
            "skipped_no_prediction": self.skipped_no_prediction,
            "skipped_dry_run": self.skipped_dry_run,
            "errors": self.errors,
            "details": self.details[:50],
        }


def discover_upcoming_fixture_rows(
    settings: Settings,
    *,
    limit_per_competition: int = 80,
) -> list[dict[str, Any]]:
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for comp_key in list_competition_keys(enabled_only=True):
        try:
            comp = get_competition(comp_key)
        except KeyError:
            continue
        if not comp.enabled:
            continue
        for row in repo.list_upcoming_fixtures(comp_key, season=comp.season, limit=limit_per_competition):
            fid = int(row["fixture_id"])
            if fid in seen:
                continue
            seen.add(fid)
            item = dict(row)
            item["competition_key"] = comp_key
            rows.append(item)
    return rows


def run_ecse_snapshot_runner(
    conn: sqlite3.Connection,
    *,
    settings: Settings | None = None,
    snapshot_minutes_before: int | None = None,
    limit: int = 100,
) -> EcseSnapshotRunResult:
    settings = settings or get_settings()
    ensure_ecse_live_tables(conn)
    minutes_before = (
        snapshot_minutes_before
        if snapshot_minutes_before is not None
        else settings.ecse_live_snapshot_minutes_before
    )
    result = EcseSnapshotRunResult()
    now = datetime.now(timezone.utc)

    fixtures = discover_upcoming_fixture_rows(settings)[:limit]
    result.scanned = len(fixtures)

    for fx in fixtures:
        fid = int(fx["fixture_id"])
        status = str(fx.get("status") or "NS").upper()
        if status not in UPCOMING_STATUSES and status not in {"", "NS"}:
            continue

        if has_snapshot(conn, fid):
            result.skipped_exists += 1
            continue

        if not is_snapshot_window(fx.get("kickoff_utc"), minutes_before=minutes_before, now=now):
            result.skipped_window += 1
            continue

        result.eligible += 1

        if settings.ecse_live_dry_run:
            result.skipped_dry_run += 1
            continue

        try:
            if settings.ecse_live_use_providers:
                from worldcup_predictor.research.ecse_live.api_log import ApiCallTracker
                from worldcup_predictor.research.ecse_live.fixture_resolver import resolve_fixture_all_providers
                from worldcup_predictor.research.ecse_live.prematch_fetch import fetch_prematch_bundle

                tracker = ApiCallTracker()
                resolved = resolve_fixture_all_providers(
                    home_team=str(fx.get("home_team") or ""),
                    away_team=str(fx.get("away_team") or ""),
                    settings=settings,
                    tracker=tracker,
                    conn=conn,
                )
                if resolved and resolved.fixture_id:
                    resolved.fixture_id = fid
                    resolved.kickoff_utc = resolved.kickoff_utc or fx.get("kickoff_utc")
                    bundle = fetch_prematch_bundle(resolved, settings=settings, tracker=tracker, conn=conn)
                    prediction = build_ecse_live_prediction(conn, fid, fx, prematch_bundle=bundle)
                else:
                    prediction = build_ecse_live_prediction(conn, fid, fx)
            else:
                prediction = build_ecse_live_prediction(conn, fid, fx)
        except Exception as exc:
            result.errors += 1
            result.details.append({"fixture_id": fid, "error": str(exc)})
            continue

        if not prediction:
            result.skipped_no_prediction += 1
            continue

        sid, reason = insert_snapshot(conn, prediction)
        if reason == "inserted":
            result.inserted += 1
            result.details.append(
                {
                    "fixture_id": fid,
                    "snapshot_id": sid,
                    "top_1_score": prediction["top_1_score"],
                    "source": prediction.get("prediction_source"),
                }
            )
            from worldcup_predictor.research.ecse_x2_m6.hook import safe_attach_shadow_live_shortlist

            safe_attach_shadow_live_shortlist(
                conn, fixture_id=fid, prediction=prediction, snapshot_id=sid
            )
        elif reason == "already_exists":
            result.skipped_exists += 1
        else:
            result.errors += 1

    return result


def run_ecse_provider_snapshot_for_fixture(
    conn: sqlite3.Connection,
    *,
    home_team: str,
    away_team: str,
    settings: Settings | None = None,
    force: bool = False,
    skip_window: bool = False,
) -> dict[str, Any]:
    """Discover providers, fetch prematch, build + freeze ECSE snapshot (internal)."""
    from worldcup_predictor.research.ecse_live.api_log import ApiCallTracker
    from worldcup_predictor.research.ecse_live.fixture_resolver import resolve_fixture_all_providers
    from worldcup_predictor.research.ecse_live.prematch_fetch import fetch_prematch_bundle

    settings = settings or get_settings()
    ensure_ecse_live_tables(conn)
    tracker = ApiCallTracker()
    outcome: dict[str, Any] = {
        "home_team": home_team,
        "away_team": away_team,
        "status": "pending",
    }

    resolved = resolve_fixture_all_providers(
        home_team=home_team,
        away_team=away_team,
        settings=settings,
        tracker=tracker,
        conn=conn,
    )
    if not resolved or not resolved.fixture_id:
        outcome["status"] = "not_discovered"
        outcome["api_log"] = tracker.to_dict()
        return outcome

    fid = int(resolved.fixture_id)
    outcome["fixture_id"] = fid
    outcome["resolved"] = resolved.to_dict()

    if has_snapshot(conn, fid) and not force:
        frozen = get_snapshot(conn, fid)
        outcome["status"] = "already_frozen"
        if frozen:
            outcome["top_1_score"] = frozen.get("top_1_score")
            try:
                import json as _json

                top10 = _json.loads(frozen.get("top_10_scorelines_json") or "[]")
                outcome["top_10"] = [x.get("scoreline") for x in top10 if isinstance(x, dict)]
            except Exception:
                pass
        outcome["api_log"] = tracker.to_dict()
        return outcome

    if not skip_window and not is_snapshot_window(
        resolved.kickoff_utc,
        minutes_before=settings.ecse_live_snapshot_minutes_before,
    ):
        outcome["status"] = "outside_snapshot_window"
        outcome["api_log"] = tracker.to_dict()
        return outcome

    if settings.ecse_live_dry_run:
        outcome["status"] = "dry_run"
        outcome["api_log"] = tracker.to_dict()
        return outcome

    bundle = fetch_prematch_bundle(resolved, settings=settings, tracker=tracker, conn=conn)
    outcome["coverage"] = bundle.coverage
    outcome["prematch"] = bundle.to_dict()

    fixture_row = {
        "fixture_id": fid,
        "home_team": resolved.home_team,
        "away_team": resolved.away_team,
        "kickoff_utc": resolved.kickoff_utc,
        "competition_key": resolved.competition_key,
    }
    prediction = build_ecse_live_prediction(conn, fid, fixture_row, prematch_bundle=bundle)
    if not prediction:
        outcome["status"] = "no_prediction"
        outcome["api_log"] = tracker.to_dict()
        return outcome

    outcome["top_10"] = [s["scoreline"] for s in prediction.get("top_10_scorelines", [])]
    outcome["top_1_score"] = prediction.get("top_1_score")
    outcome["lambda_home"] = prediction.get("lambda_home")
    outcome["lambda_away"] = prediction.get("lambda_away")

    sid, reason = insert_snapshot(conn, prediction)
    outcome["snapshot_id"] = sid
    outcome["snapshot_reason"] = reason
    outcome["status"] = "frozen" if reason == "inserted" else reason
    if reason == "inserted":
        from worldcup_predictor.research.ecse_x2_m6.hook import safe_attach_shadow_live_shortlist

        safe_attach_shadow_live_shortlist(
            conn, fixture_id=fid, prediction=prediction, snapshot_id=sid
        )
    outcome["api_log"] = tracker.to_dict()
    return outcome


def run_ecse_provider_snapshot_runner(
    conn: sqlite3.Connection,
    *,
    settings: Settings | None = None,
    targets: list[dict[str, str]] | None = None,
    force: bool = False,
    skip_window: bool = True,
) -> dict[str, Any]:
    """Run provider pipeline for explicit targets or upcoming DB fixtures."""
    settings = settings or get_settings()
    results: list[dict[str, Any]] = []

    if targets:
        for t in targets:
            results.append(
                run_ecse_provider_snapshot_for_fixture(
                    conn,
                    home_team=t["home_team"],
                    away_team=t["away_team"],
                    settings=settings,
                    force=force,
                    skip_window=skip_window,
                )
            )
        return {
            "phase": PHASE,
            "mode": "targets",
            "count": len(results),
            "frozen": sum(1 for r in results if r.get("status") == "frozen"),
            "already_frozen": sum(1 for r in results if r.get("status") == "already_frozen"),
            "results": results,
        }

    base = run_ecse_snapshot_runner(conn, settings=settings)
    return {"phase": PHASE, "mode": "schedule", "schedule": base.to_dict()}

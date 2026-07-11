"""Canonical prediction pipeline delegation for MCP tools."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.config.app_version import build_version_payload
from worldcup_predictor.config.provider_readiness import provider_diagnostic
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.odds.refresh_gate import ensure_fresh_odds_before_prediction
from worldcup_predictor.odds.freshness_metadata import build_fixture_freshness_metadata
from worldcup_predictor.odds.freshness_policy import FreshnessStatus
from worldcup_predictor.odds.strict_live_refresh import refresh_fixture_odds_live
from worldcup_predictor.gpt_actions.bridge_semantics import (
    extract_wde_semantics,
    latest_prediction_report_payload,
    prediction_report_by_date_payload,
)
from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture, discover_fixtures_from_db, vienna_day_utc_bounds
from worldcup_predictor.owner_daily.predictions import run_daily_ecse, run_daily_wde
from worldcup_predictor.owner_daily.report import _load_ecse, _load_wde, _owner_label
from worldcup_predictor.owner_manual_exact.resolver import resolve_fixture
from worldcup_predictor.owner_manual_exact.team_aliases import canonical_team_name
from worldcup_predictor.research.ecse_live.prediction_builder import MODEL_VERSION as ECSE_MODEL_VERSION
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables, get_snapshot

_PREDICTION_LOCK = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _pct(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return round(v * 100, 2) if v <= 1 else round(v, 2)


def _market_block(payload: dict[str, Any]) -> dict[str, Any]:
    sem = extract_wde_semantics(payload)
    return {
        "home_prob": sem["home_prob"],
        "draw_prob": sem["draw_prob"],
        "away_prob": sem["away_prob"],
        "pick": sem["decision_pick"],
        "effective_pick": sem["effective_pick"],
        "probability_argmax": sem["probability_argmax"],
        "decision_source": sem["decision_source"],
        "confidence": sem["confidence"],
        "btts": sem["btts"],
        "ou25": sem["ou25"],
        "model_version": sem["model_version"],
    }


def _load_stored_payload(repo: FootballIntelligenceRepository, fixture_id: int) -> dict[str, Any] | None:
    row = repo.get_worldcup_stored_prediction(fixture_id)
    if not row or not row.get("payload_json"):
        return None
    try:
        return json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return None


def _fixture_row(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status, season, round_name
           FROM fixtures WHERE fixture_id=? AND is_placeholder=0 LIMIT 1""",
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else None


def _to_daily_fixture(row: dict[str, Any]) -> DailyFixture:
    raw_key = str(row["competition_key"])
    canon = normalize_competition_key(raw_key) or raw_key
    return DailyFixture(
        fixture_id=int(row["fixture_id"]),
        provider_fixture_id=int(row["fixture_id"]),
        competition_key=canon,
        home_team=str(row["home_team"]),
        away_team=str(row["away_team"]),
        kickoff_utc=str(row.get("kickoff_utc") or ""),
        status=str(row.get("status") or "NS"),
        season=int(row["season"]) if row.get("season") is not None else None,
    )


def _fetch_candidates_for_date(conn: sqlite3.Connection, target: date) -> list[dict[str, Any]]:
    start_utc, end_utc = vienna_day_utc_bounds(target, DEFAULT_TIMEZONE)
    fixtures = discover_fixtures_from_db(
        conn,
        competition_keys=list(DAILY_SUPPORTED_COMPETITIONS),
        start_utc=start_utc,
        end_utc=end_utc,
        limit=500,
    )
    return [
        {
            "fixture_id": f.fixture_id,
            "home_team": f.home_team,
            "away_team": f.away_team,
            "kickoff_utc": f.kickoff_utc,
            "status": f.status,
            "competition_key": f.competition_key,
        }
        for f in fixtures
    ]


def _kickoff_meta_for_date(target: date) -> dict[str, Any]:
    tz = ZoneInfo(DEFAULT_TIMEZONE)
    local_dt = datetime.combine(target, time(12, 0), tzinfo=tz)
    utc_dt = local_dt.astimezone(timezone.utc)
    return {"kickoff_utc": utc_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")}


def resolve_fixtures(matches: list[dict[str, Any]], *, settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    out: list[dict[str, Any]] = []
    try:
        for match in matches:
            target = date.fromisoformat(str(match["date"]))
            candidates = _fetch_candidates_for_date(conn, target)
            kickoff_meta = _kickoff_meta_for_date(target)
            resolved = resolve_fixture(
                conn,
                {"home_team": match["home_team"], "away_team": match["away_team"]},
                kickoff_meta=kickoff_meta,
                candidates=candidates,
            )
            status = resolved.get("resolution_status")
            method = str(resolved.get("resolution_method") or "unresolved")
            confidence: float | None = None
            if status == "RESOLVED":
                if method == "known_fixture_id_map":
                    confidence = 1.0
                else:
                    confidence = float(resolved.get("match_score") or 0.95)
                out.append(
                    {
                        "fixture_id": resolved.get("fixture_id"),
                        "home_team": resolved.get("home_team_canonical") or canonical_team_name(match["home_team"]),
                        "away_team": resolved.get("away_team_canonical") or canonical_team_name(match["away_team"]),
                        "kickoff_utc": resolved.get("kickoff_utc"),
                        "competition": resolved.get("competition_key"),
                        "status": resolved.get("match_status"),
                        "resolution_method": method,
                        "resolution_confidence": confidence,
                    }
                )
            else:
                out.append(
                    {
                        "fixture_id": None,
                        "home_team": resolved.get("home_team_canonical") or match["home_team"],
                        "away_team": resolved.get("away_team_canonical") or match["away_team"],
                        "kickoff_utc": kickoff_meta.get("kickoff_utc"),
                        "competition": None,
                        "status": None,
                        "resolution_method": "ambiguous_or_unresolved",
                        "resolution_confidence": float((resolved.get("closest_candidates") or [{}])[0].get("match_score") or 0),
                        "ambiguous_candidates": resolved.get("closest_candidates") or [],
                        "reject_reasons": resolved.get("reject_reasons") or [],
                    }
                )
    finally:
        conn.close()
    return out


def _freshness_record(conn: sqlite3.Connection, row: dict[str, Any]) -> dict[str, Any]:
    fid = int(row["fixture_id"])
    meta = build_fixture_freshness_metadata(
        conn,
        fixture_id=fid,
        kickoff_utc=row.get("kickoff_utc"),
        round_name=row.get("round_name"),
        status=row.get("status"),
    )
    status = str(meta.get("odds_freshness_status") or "")
    age_hours = meta.get("odds_age_hours")
    threshold = meta.get("stale_threshold_hours")
    age_minutes = round(float(age_hours) * 60, 1) if age_hours is not None else None
    threshold_minutes = round(float(threshold) * 60, 1) if threshold is not None else None
    is_fresh = status == FreshnessStatus.FRESH_ODDS.value
    return {
        "fixture_id": fid,
        "odds_status": status,
        "age_minutes": age_minutes,
        "threshold_minutes": threshold_minutes,
        "fresh": is_fresh,
        "stale": status in (FreshnessStatus.STALE_ODDS.value, FreshnessStatus.REQUIRES_FRESH_ODDS.value),
        "markets_available": meta.get("markets_available"),
        "last_provider": meta.get("odds_source"),
        "warning": meta.get("freshness_warning"),
        "requires_fresh_odds": bool(meta.get("requires_fresh_odds")),
        "_meta": meta,
    }


def odds_freshness_audit(fixture_ids: list[int], *, settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    results: list[dict[str, Any]] = []
    try:
        for fid in fixture_ids:
            row = _fixture_row(conn, fid)
            if not row:
                results.append({"fixture_id": fid, "error": "fixture_not_found"})
                continue
            rec = _freshness_record(conn, row)
            rec.pop("_meta", None)
            results.append(rec)
    finally:
        conn.close()
    return results


def refresh_stale_odds(fixture_ids: list[int], *, settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    results: list[dict[str, Any]] = []
    try:
        for fid in fixture_ids:
            row = _fixture_row(conn, fid)
            if not row:
                results.append(
                    {
                        "fixture_id": fid,
                        "refresh_attempted": False,
                        "blocked_reason": "fixture_not_found",
                    }
                )
                continue
            before = _freshness_record(conn, row)
            if before.get("fresh") and not before.get("requires_fresh_odds"):
                after = before
                results.append(
                    {
                        "fixture_id": fid,
                        "refresh_attempted": False,
                        "provider_attempts": [],
                        "selected_provider": before.get("last_provider"),
                        "markets_available": before.get("markets_available"),
                        "freshness_after": {k: after[k] for k in before if k != "_meta"},
                        "blocked_reason": None,
                        "note": "already_fresh",
                    }
                )
                continue
            daily = _to_daily_fixture(row)
            refresh = refresh_fixture_odds_live(daily, settings=settings, dry_run=False)
            after_row = _fixture_row(conn, fid) or row
            after = _freshness_record(conn, after_row)
            blocked = None
            if not refresh.get("imported") and refresh.get("status") != "dry_run_live_odds_valid":
                blocked = str(refresh.get("status") or "refresh_failed")
            elif after.get("requires_fresh_odds"):
                blocked = "freshness_still_invalid"
            results.append(
                {
                    "fixture_id": fid,
                    "refresh_attempted": True,
                    "provider_attempts": refresh.get("attempts") or refresh.get("provider_attempts") or [],
                    "selected_provider": refresh.get("provider") or refresh.get("selected_live_provider"),
                    "markets_available": refresh.get("market_quality"),
                    "freshness_after": {k: after[k] for k in after if k != "_meta"},
                    "blocked_reason": blocked,
                    "live_calls": refresh.get("live_calls"),
                }
            )
    finally:
        conn.close()
    return results


def _ecse_top_scores(ecse: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not ecse:
        return []
    rows = ecse.get("top_10_scorelines") or ecse.get("top_5_scores") or ecse.get("top_3_scores") or []
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows[:5], start=1):
        if isinstance(row, dict):
            score = row.get("scoreline") or row.get("score") or row.get("label")
            prob = row.get("probability")
        else:
            score, prob = str(row), None
        if prob is not None:
            p = float(prob)
            if p > 1:
                p /= 100.0
        else:
            p = None
        out.append({"score": score, "rank": idx, "probability": p})
    return out


def _format_prediction_result(
    *,
    row: dict[str, Any],
    freshness: dict[str, Any],
    payload: dict[str, Any] | None,
    ecse_snap: dict[str, Any] | None,
    status: str,
    warnings: list[str],
    wde_execution_status: str | None = None,
    wde_result_source: str | None = None,
    wde_failure_code: str | None = None,
    wde_failure_stage: str | None = None,
) -> dict[str, Any]:
    wde_block = _market_block(payload) if payload else {}
    btts = wde_block.get("btts") or {}
    ou25 = wde_block.get("ou25") or {}
    ecse_loaded = _load_ecse_from_snap(ecse_snap)
    label = _owner_label(
        {
            "predicted_1x2": wde_block.get("pick"),
            "confidence_score": wde_block.get("confidence"),
            "no_bet_flag": bool((payload or {}).get("no_bet_flag")),
        }
        if payload
        else None,
        ecse_loaded,
    )
    wde_warning = None
    for w in warnings:
        if w.startswith("wde_skipped:"):
            wde_warning = w.split(":", 1)[1]
            if not wde_failure_code:
                wde_failure_code = wde_warning
            break
    return {
        "fixture": {
            "fixture_id": int(row["fixture_id"]),
            "home_team": row.get("home_team"),
            "away_team": row.get("away_team"),
            "kickoff_utc": row.get("kickoff_utc"),
            "competition": row.get("competition_key"),
            "status": row.get("status"),
        },
        "odds": {
            "provider": freshness.get("last_provider"),
            "freshness": freshness.get("odds_status"),
            "age_minutes": freshness.get("age_minutes"),
        },
        "wde": {
            "home_probability": wde_block.get("home_prob"),
            "draw_probability": wde_block.get("draw_prob"),
            "away_probability": wde_block.get("away_prob"),
            "prediction": wde_block.get("pick"),
            "decision_pick": wde_block.get("pick"),
            "effective_pick": wde_block.get("effective_pick"),
            "probability_argmax": wde_block.get("probability_argmax"),
            "decision_source": wde_block.get("decision_source"),
            "confidence": wde_block.get("confidence"),
            "model_version": wde_block.get("model_version"),
            "wde_execution_status": wde_execution_status,
            "wde_result_source": wde_result_source,
            "wde_warning": wde_warning,
            "wde_failure_code": wde_failure_code,
            "wde_failure_stage": wde_failure_stage,
        },
        "btts": {
            "prediction": btts.get("selection") or btts.get("pick"),
            "yes_probability": _pct(btts.get("yes") or btts.get("option_a")),
            "no_probability": _pct(btts.get("no") or btts.get("option_b")),
        },
        "over_under_2_5": {
            "prediction": ou25.get("selection") or ou25.get("pick"),
            "over_probability": _pct(ou25.get("over") or ou25.get("option_a")),
            "under_probability": _pct(ou25.get("under") or ou25.get("option_b")),
        },
        "ecse": {
            "top_scores": _ecse_top_scores(ecse_snap),
            "model_version": ECSE_MODEL_VERSION,
        },
        "quality": {
            "status": status,
            "owner_label": label,
            "warnings": warnings,
        },
    }


def _load_ecse_from_snap(snap: dict[str, Any] | None) -> dict[str, Any] | None:
    if not snap:
        return None
    return {
        "top_1_score": snap.get("top_1_score"),
        "confidence_score": float(snap.get("confidence_score") or 0),
    }


def run_fixture_prediction(
    fixture_id: int,
    *,
    refresh_if_stale: bool = True,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    warnings: list[str] = []
    with _PREDICTION_LOCK:
        conn = connect(settings.sqlite_path)
        ensure_ecse_live_tables(conn)
        repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        try:
            row = _fixture_row(conn, fixture_id)
            if not row:
                return {"quality": {"status": "FAILED", "warnings": ["fixture_not_found"]}}

            daily = _to_daily_fixture(row)
            gate = ensure_fresh_odds_before_prediction(
                conn,
                row,
                daily,
                settings=settings,
                refresh_if_needed=refresh_if_stale,
            )
            if not gate.get("allowed"):
                diag = gate.get("diagnostics") or {}
                freshness = gate.get("freshness") or _freshness_record(conn, row)
                freshness.pop("_meta", None)
                block_reason = gate.get("final_block_reason") or "odds_freshness_invalid"
                return {
                    "quality": {
                        "status": "BLOCKED",
                        "warnings": ["odds_freshness_invalid", block_reason],
                    },
                    "odds": {
                        "provider": diag.get("provider_used") or freshness.get("last_provider"),
                        "freshness": freshness.get("odds_status") or diag.get("freshness_status"),
                        "age_minutes": freshness.get("age_minutes"),
                        "block_diagnostics": diag,
                    },
                    "fixture": {
                        "fixture_id": fixture_id,
                        "home_team": row.get("home_team"),
                        "away_team": row.get("away_team"),
                        "kickoff_utc": row.get("kickoff_utc"),
                        "competition": row.get("competition_key"),
                    },
                }

            freshness = _freshness_record(conn, row)
            payload_before = _load_stored_payload(repo, fixture_id)
            wde_status, wde_detail = run_daily_wde(
                daily,
                settings=settings,
                repo=repo,
                conn=conn,
                dry_run=False,
                force=True,
                strict_fresh_odds=True,
            )
            if wde_status == "skipped":
                code = wde_detail.get("wde_failure_code") or wde_detail.get("reason")
                warnings.append(f"wde_skipped:{code}")

            ecse_status, ecse_detail = run_daily_ecse(
                daily, settings=settings, conn=conn, dry_run=False, force=True
            )
            if ecse_status == "skipped":
                warnings.append(f"ecse_skipped:{ecse_detail.get('reason')}")

            payload = _load_stored_payload(repo, fixture_id)
            ecse_snap = get_snapshot(conn, fixture_id)
            status = "OK"
            if not payload:
                status = "PARTIAL"
                warnings.append("wde_payload_missing")
            if not ecse_snap:
                status = "PARTIAL" if payload else "FAILED"
                warnings.append("ecse_snapshot_missing")

            if wde_status == "generated":
                wde_execution_status = "executed"
                wde_result_source = "fresh_engine"
            elif wde_status == "skipped":
                wde_execution_status = "skipped"
                wde_result_source = "stored_prediction" if (payload or payload_before) else "none"
            else:
                wde_execution_status = str(wde_status)
                wde_result_source = "stored_prediction" if payload else "none"

            freshness = _freshness_record(conn, row)
            freshness.pop("_meta", None)
            return _format_prediction_result(
                row=row,
                freshness=freshness,
                payload=payload,
                ecse_snap=ecse_snap,
                status=status,
                warnings=warnings,
                wde_execution_status=wde_execution_status,
                wde_result_source=wde_result_source,
                wde_failure_code=wde_detail.get("wde_failure_code") if wde_status == "skipped" else None,
                wde_failure_stage=wde_detail.get("wde_failure_stage") if wde_status == "skipped" else None,
            )
        finally:
            conn.close()


def run_batch_predictions(
    fixture_ids: list[int],
    *,
    refresh_if_stale: bool = True,
    settings: Settings | None = None,
) -> dict[str, Any]:
    started = _utc_now_iso()
    results: list[dict[str, Any]] = []
    successful = blocked = failed = 0
    for fid in fixture_ids:
        try:
            item = run_fixture_prediction(fid, refresh_if_stale=refresh_if_stale, settings=settings)
            status = (item.get("quality") or {}).get("status")
            if status == "BLOCKED":
                blocked += 1
            elif status in ("OK", "PARTIAL"):
                successful += 1
            else:
                failed += 1
            results.append({"fixture_id": fid, **item})
        except Exception as exc:
            failed += 1
            results.append(
                {
                    "fixture_id": fid,
                    "quality": {"status": "FAILED", "warnings": [str(exc)[:200]]},
                }
            )
    return {
        "batch_id": str(uuid.uuid4()),
        "started_at": started,
        "finished_at": _utc_now_iso(),
        "requested": len(fixture_ids),
        "successful": successful,
        "blocked": blocked,
        "failed": failed,
        "results": results,
    }


def latest_prediction_report(*, max_bytes: int) -> dict[str, Any]:
    return latest_prediction_report_payload(max_bytes=max_bytes)


def prediction_report_by_date(target: date, *, max_bytes: int) -> dict[str, Any]:
    return prediction_report_by_date_payload(target, max_bytes=max_bytes)


def model_status(*, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    try:
        wde_count = conn.execute("SELECT COUNT(*) FROM worldcup_stored_predictions").fetchone()[0]
        ecse_count = conn.execute(
            "SELECT COUNT(*) FROM ecse_prediction_snapshots"
        ).fetchone()[0] if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ecse_prediction_snapshots'"
        ).fetchone() else 0
        latest_pred = conn.execute(
            "SELECT MAX(predicted_at) FROM worldcup_stored_predictions"
        ).fetchone()[0]
    except sqlite3.Error:
        wde_count = ecse_count = 0
        latest_pred = None
    finally:
        conn.close()

    diag = provider_diagnostic(settings)
    db_path = settings.sqlite_path
    db_exists = bool(db_path and Path(db_path).exists())
    version = build_version_payload()
    from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

    oa = OddAlertsClient()
    return {
        "wde_available": wde_count > 0,
        "ecse_available": ecse_count > 0,
        "wde_model_version": version.get("app_version"),
        "ecse_model_version": ECSE_MODEL_VERSION,
        "canonical_pipeline_ready": diag.get("production_prediction_allowed"),
        "db_connectivity": db_exists,
        "latest_prediction_timestamp": latest_pred,
        "odds_freshness_subsystem": "ODDS-FRESHNESS-1",
        "strict_live_refresh": "strict_live_refresh",
        "providers": {
            "api_football_configured": diag.get("API_FOOTBALL_KEY_present"),
            "sportmonks_configured": diag.get("SPORTMONKS_API_KEY_present"),
            "oddalerts_configured": bool(oa.is_configured),
        },
    }


def provider_status(*, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
    from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

    diag = provider_diagnostic(settings)
    oa = OddAlertsClient()
    sm = SportmonksProvider(settings=settings)
    return {
        "api_football": {
            "configured": bool(diag.get("API_FOOTBALL_KEY_present")),
            "reachable": None,
            "coverage_state": diag.get("provider_readiness_summary"),
        },
        "sportmonks": {
            "configured": bool(sm.is_configured),
            "reachable": None,
            "coverage_state": "configured" if sm.is_configured else "not_configured",
        },
        "oddalerts": {
            "configured": bool(oa.is_configured),
            "reachable": None,
            "coverage_state": "crosswalk_required",
        },
    }

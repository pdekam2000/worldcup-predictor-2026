"""Prediction coverage reporting — Phase A14."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.api.match_center_helpers import extract_prediction_summary
from worldcup_predictor.automation.prediction_prefetch.priority import priority_band_for_kickoff, priority_label
from worldcup_predictor.automation.worldcup_background.freshness import _parse_dt, is_prediction_fresh
from worldcup_predictor.automation.worldcup_background.stale_prediction_policy import (
    is_stored_prediction_quality_valid,
)
from worldcup_predictor.config.competitions import list_competition_keys
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner.dashboard_metrics import enrich_prefetch_competition


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _classify_row(
    *,
    has_stored: bool,
    payload: dict[str, Any] | None,
    kickoff_utc,
) -> str:
    if not has_stored or not payload:
        return "missing"
    if payload.get("status") != "ok":
        return "failed"
    quality_ok, _ = is_stored_prediction_quality_valid(payload)
    if not quality_ok:
        return "stale"
    kick = _parse_dt(kickoff_utc) or _parse_dt(payload.get("kickoff_utc"))
    fresh, _ = is_prediction_fresh(payload, kickoff_utc=kick)
    return "fresh" if fresh else "stale"


def _is_bettable(payload: dict[str, Any] | None) -> bool:
    if not payload or payload.get("no_bet"):
        return False
    summary = extract_prediction_summary(payload)
    return bool(summary.get("best_pick"))


def collect_upcoming_fixtures(
    *,
    settings: Settings | None = None,
    window_days: int = 7,
) -> list[dict[str, Any]]:
    """Same fixture universe as Match Center (schedule cache / provider)."""
    from worldcup_predictor.api.match_center_aggregator import aggregate_all_competitions
    from worldcup_predictor.schedule.match_center import classify_status

    settings = settings or get_settings()
    agg = aggregate_all_competitions(settings=settings)
    now = _utc_now()
    end = now + timedelta(days=int(window_days))
    rows: list[dict[str, Any]] = []

    for block in agg.get("results") or []:
        comp = block["comp"]
        for fixture in block.get("fixtures") or []:
            if classify_status(fixture.status) != "upcoming":
                continue
            kick_raw = fixture.kickoff_time
            kick = _parse_dt(kick_raw)
            if kick is None or kick < now or kick > end:
                continue
            rows.append(
                {
                    "fixture_id": int(fixture.fixture_id),
                    "kickoff_utc": str(kick_raw),
                    "competition_key": comp.key,
                    "competition_name": comp.name,
                    "home_team": fixture.home_team,
                    "away_team": fixture.away_team,
                    "priority_band": priority_band_for_kickoff(kick, now=now),
                    "priority_label": priority_label(priority_band_for_kickoff(kick, now=now)),
                }
            )
    return rows


def build_coverage_report(
    *,
    settings: Settings | None = None,
    window_days: int = 7,
    competition_keys: list[str] | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    keys = competition_keys or list_competition_keys(enabled_only=True)
    keys_set = set(keys)

    fixtures = [f for f in collect_upcoming_fixtures(settings=settings, window_days=window_days) if f["competition_key"] in keys_set]

    stored_by_fixture: dict[int, dict[str, Any]] = {}
    for key in keys:
        for row in repo.list_worldcup_stored_predictions(competition_key=key, limit=2000, offset=0):
            fid = row.get("fixture_id")
            if fid is None:
                continue
            try:
                payload = json.loads(row["payload_json"]) if isinstance(row.get("payload_json"), str) else row.get("payload_json")
            except (json.JSONDecodeError, TypeError):
                payload = None
            if isinstance(payload, dict):
                stored_by_fixture[int(fid)] = payload

    by_comp: dict[str, dict[str, Any]] = {
        k: {
            "competition_key": k,
            "fixtures": 0,
            "predictions": 0,
            "bettable": 0,
            "fresh": 0,
            "stale": 0,
            "missing": 0,
            "failed": 0,
            "coverage_pct": 0.0,
            "bettable_pct": 0.0,
        }
        for k in keys
    }

    combo_ready = 0
    waiting = 0
    no_bet = 0

    for fx in fixtures:
        ck = fx["competition_key"]
        if ck not in by_comp:
            continue
        block = by_comp[ck]
        block["fixtures"] += 1
        fid = int(fx["fixture_id"])
        payload = stored_by_fixture.get(fid)
        has_stored = payload is not None
        if has_stored:
            block["predictions"] += 1
        status = _classify_row(has_stored=has_stored, payload=payload, kickoff_utc=fx.get("kickoff_utc"))
        block[status] = block.get(status, 0) + 1
        if _is_bettable(payload):
            block["bettable"] += 1
            combo_ready += 1
        elif has_stored and payload and payload.get("no_bet"):
            no_bet += 1
        elif not has_stored:
            waiting += 1

    for block in by_comp.values():
        fx_count = block["fixtures"]
        if fx_count:
            block["coverage_pct"] = round(100.0 * block["predictions"] / fx_count, 1)
            block["bettable_pct"] = round(100.0 * block["bettable"] / fx_count, 1)

    conn = repo._conn  # noqa: SLF001
    competitions_out = [
        enrich_prefetch_competition(dict(block), conn=conn, window_days=window_days)
        for block in by_comp.values()
    ]

    total_fixtures = sum(b["fixtures"] for b in competitions_out)
    total_predictions = sum(b["predictions"] for b in competitions_out)
    total_bettable = sum(b["bettable"] for b in competitions_out)

    return {
        "status": "ok",
        "version": "a14-v1",
        "window_days": window_days,
        "generated_at": _utc_now().isoformat(),
        "totals": {
            "fixtures": total_fixtures,
            "predictions": total_predictions,
            "bettable": total_bettable,
            "coverage_pct": round(100.0 * total_predictions / total_fixtures, 1) if total_fixtures else 0.0,
            "bettable_pct": round(100.0 * total_bettable / total_fixtures, 1) if total_fixtures else 0.0,
            "fresh": sum(b.get("fresh", 0) for b in competitions_out),
            "stale": sum(b.get("stale", 0) for b in competitions_out),
            "missing": sum(b.get("missing", 0) for b in competitions_out),
            "failed": sum(b.get("failed", 0) for b in competitions_out),
            "off_season_leagues": sum(1 for b in competitions_out if b.get("season_status") == "OFF_SEASON"),
        },
        "combo_readiness": {
            "ready": combo_ready,
            "waiting_for_prediction": waiting,
            "no_bet": no_bet,
        },
        "competitions": sorted(competitions_out, key=lambda x: (-x["fixtures"], x["competition_key"])),
    }

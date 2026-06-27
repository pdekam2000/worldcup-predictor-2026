"""PredOps coverage reporting — Phase A15."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.api.match_center_helpers import extract_prediction_summary
from worldcup_predictor.automation.prediction_prefetch.coverage import collect_upcoming_fixtures
from worldcup_predictor.automation.worldcup_background.freshness import _parse_dt, is_prediction_fresh
from worldcup_predictor.config.competitions import list_competition_keys
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.predops.refresh_policy import is_refresh_due, should_enqueue_refresh
from worldcup_predictor.predops.store import PredOpsStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _classify_fixture(
    *,
    fid: int,
    snap: dict[str, Any] | None,
    stored_payload: dict[str, Any] | None,
    kickoff_utc,
    queue_state: str | None,
) -> str:
    if queue_state == "generating":
        return "generating"
    if queue_state == "queued":
        return "queued"
    if not snap and not stored_payload:
        return "missing"
    payload = (snap or {}).get("payload") or stored_payload
    if not payload:
        return "missing"
    if payload.get("status") != "ok":
        return "failed"
    state = (snap or {}).get("coverage_state")
    if state == "no_bet" or payload.get("no_bet"):
        return "no_bet"
    if state == "unavailable":
        return "unavailable"
    kick = _parse_dt(kickoff_utc)
    fresh, _ = is_prediction_fresh(payload, kickoff_utc=kick)
    if fresh:
        return "completed"
    due, _ = is_refresh_due(
        last_generated_at=(snap or {}).get("generated_at") or payload.get("generated_at"),
        kickoff_utc=kick,
    )
    return "stale" if due else "completed"


def build_predops_coverage_report(
    *,
    settings: Settings | None = None,
    window_days: int = 7,
    competition_keys: list[str] | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    store = PredOpsStore(settings)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    keys = competition_keys or list_competition_keys(enabled_only=True)
    keys_set = set(keys)

    fixtures = [f for f in collect_upcoming_fixtures(settings=settings, window_days=window_days) if f["competition_key"] in keys_set]
    fixture_ids = [int(f["fixture_id"]) for f in fixtures]
    latest_snaps = store.latest_by_fixtures(fixture_ids)

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
            "latest_snapshots": 0,
            "coverage_pct": 0.0,
            "fresh_pct": 0.0,
            "completed": 0,
            "stale": 0,
            "missing": 0,
            "queued": 0,
            "generating": 0,
            "failed": 0,
            "no_bet": 0,
            "unavailable": 0,
            "tier_a_markets": 0,
            "tier_b_markets": 0,
            "agreement": 0,
            "disagreement": 0,
            "egie_available": 0,
            "egie_no_pick": 0,
            "egie_missing": 0,
        }
        for k in keys
    }

    tier_a_total = tier_b_total = agree = disagree = 0
    egie_avail = egie_no_pick = egie_missing = 0

    for fx in fixtures:
        ck = fx["competition_key"]
        if ck not in by_comp:
            continue
        block = by_comp[ck]
        block["fixtures"] += 1
        fid = int(fx["fixture_id"])
        snap = latest_snaps.get(fid)
        if snap:
            block["latest_snapshots"] += 1
        qstate = store.fixture_queue_state(fid)
        state = _classify_fixture(
            fid=fid,
            snap=snap,
            stored_payload=stored_by_fixture.get(fid),
            kickoff_utc=fx.get("kickoff_utc"),
            queue_state=qstate,
        )
        block[state] = block.get(state, 0) + 1

        markets_doc = (snap or {}).get("markets") or {}
        mkt = markets_doc.get("markets") if isinstance(markets_doc, dict) else {}
        if isinstance(mkt, dict):
            for mb in mkt.values():
                if not isinstance(mb, dict):
                    continue
                if mb.get("model_tier") == "A":
                    tier_a_total += 1
                    block["tier_a_markets"] += 1
                if mb.get("model_tier") == "B":
                    tier_b_total += 1
                    block["tier_b_markets"] += 1
                agree_st = (mb.get("final_selected_prediction") or {}).get("agreement_status")
                if agree_st == "agree":
                    agree += 1
                    block["agreement"] += 1
                elif agree_st == "disagree":
                    disagree += 1
                    block["disagreement"] += 1

        egie = (snap or {}).get("egie") or {}
        est = egie.get("status")
        if est == "available":
            egie_avail += 1
            block["egie_available"] += 1
        elif est == "no_pick":
            egie_no_pick += 1
            block["egie_no_pick"] += 1
        else:
            egie_missing += 1
            block["egie_missing"] += 1

    for block in by_comp.values():
        fx_count = block["fixtures"]
        if fx_count:
            has_snap = block["latest_snapshots"]
            block["coverage_pct"] = round(100.0 * has_snap / fx_count, 1)
            freshish = block.get("completed", 0)
            block["fresh_pct"] = round(100.0 * freshish / fx_count, 1)

    total_fixtures = sum(b["fixtures"] for b in by_comp.values())
    total_snaps = sum(b["latest_snapshots"] for b in by_comp.values())

    return {
        "status": "ok",
        "version": "a15-v1",
        "window_days": window_days,
        "generated_at": _utc_now().isoformat(),
        "totals": {
            "fixtures": total_fixtures,
            "latest_snapshots": total_snaps,
            "coverage_pct": round(100.0 * total_snaps / total_fixtures, 1) if total_fixtures else 0.0,
            "completed": sum(b.get("completed", 0) for b in by_comp.values()),
            "stale": sum(b.get("stale", 0) for b in by_comp.values()),
            "missing": sum(b.get("missing", 0) for b in by_comp.values()),
            "queued": sum(b.get("queued", 0) for b in by_comp.values()),
            "generating": sum(b.get("generating", 0) for b in by_comp.values()),
            "failed": sum(b.get("failed", 0) for b in by_comp.values()),
            "no_bet": sum(b.get("no_bet", 0) for b in by_comp.values()),
            "unavailable": sum(b.get("unavailable", 0) for b in by_comp.values()),
        },
        "model_coverage": {
            "tier_a_markets": tier_a_total,
            "tier_b_markets": tier_b_total,
            "agreement_pct": round(100.0 * agree / max(agree + disagree, 1), 1),
            "disagreement_pct": round(100.0 * disagree / max(agree + disagree, 1), 1),
        },
        "egie_coverage": {
            "available": egie_avail,
            "no_pick": egie_no_pick,
            "missing": egie_missing,
        },
        "competitions": sorted(by_comp.values(), key=lambda x: (-x["fixtures"], x["competition_key"])),
    }

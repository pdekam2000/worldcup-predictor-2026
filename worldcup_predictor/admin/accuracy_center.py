"""Admin Accuracy Center — Phase 33 evaluation + stored prediction assembly."""

from __future__ import annotations

import json
from typing import Any, Literal

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

StatusColor = Literal["green", "red", "yellow", "gray"]


def _status_color(status: str | None) -> StatusColor:
    s = str(status or "").lower()
    if s == "correct":
        return "green"
    if s == "wrong":
        return "red"
    if s == "pending":
        return "yellow"
    return "gray"


def _pick_label(payload: dict[str, Any], key: str) -> str | None:
    pick = payload.get(key)
    if isinstance(pick, dict):
        return pick.get("pick") or pick.get("selection")
    return None


def _parse_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row or not row.get("payload_json"):
        return {}
    try:
        data = json.loads(row["payload_json"])
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_detail(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("detail_json")
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return {}


def build_accuracy_row(
    evaluation: dict[str, Any],
    *,
    payload: dict[str, Any],
    fixture: dict[str, Any] | None,
) -> dict[str, Any]:
    detail = _parse_detail(evaluation)
    pick_tier = detail.get("pick_tier") or payload.get("pick_tier") or (
        "caution" if evaluation.get("no_bet") else "official"
    )
    tracking = payload.get("accuracy_tracking") or {}
    nat = payload.get("national_team_intelligence") or {}

    home = (fixture or {}).get("home_team") or payload.get("home_team") or "Home"
    away = (fixture or {}).get("away_team") or payload.get("away_team") or "Away"

    overall = evaluation.get("overall_status") or "pending"
    return {
        "fixture_id": evaluation.get("fixture_id"),
        "match": f"{home} vs {away}",
        "home_team": home,
        "away_team": away,
        "competition_key": evaluation.get("competition_key") or payload.get("competition_key") or "world_cup_2026",
        "kickoff_utc": (fixture or {}).get("kickoff_utc") or payload.get("kickoff_utc"),
        "prediction_date": payload.get("predicted_at") or (fixture or {}).get("updated_at"),
        "confidence": payload.get("confidence"),
        "data_quality": payload.get("data_quality"),
        "pick_tier": pick_tier,
        "official_recommended": bool(tracking.get("official_recommended")) and not evaluation.get("no_bet"),
        "no_bet": bool(evaluation.get("no_bet")),
        "safe_pick": _pick_label(payload, "safe_pick"),
        "value_pick": _pick_label(payload, "value_pick"),
        "aggressive_pick": _pick_label(payload, "aggressive_pick"),
        "caution_pick": _pick_label(payload, "caution_pick"),
        "actual_result": evaluation.get("actual_result"),
        "final_score": evaluation.get("final_score"),
        "evaluation_status": overall,
        "status_color": _status_color(overall),
        "safe_pick_status": evaluation.get("safe_pick_status"),
        "value_pick_status": evaluation.get("value_pick_status"),
        "aggressive_pick_status": evaluation.get("aggressive_pick_status"),
        "market_1x2_status": evaluation.get("market_1x2_status"),
        "evaluated_at": evaluation.get("evaluated_at"),
        "national_form_score": nat.get("national_form_score"),
        "national_h2h_score": nat.get("national_h2h_score"),
        "is_quarantined": bool(evaluation.get("is_quarantined")),
        "quarantine_reason": evaluation.get("quarantine_reason"),
        "evaluation_source": evaluation.get("evaluation_source"),
    }


def list_accuracy_center_rows(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    status_filter: str = "all",
    pick_tier_filter: str = "all",
    confidence_min: float | None = None,
    confidence_max: float | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
    offset: int = 0,
    include_quarantined: bool = False,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    evaluations = repo.list_worldcup_prediction_evaluations_filtered(
        competition_key=competition_key,
        status_filter=status_filter,
        pick_tier_filter=pick_tier_filter,
        confidence_min=confidence_min,
        confidence_max=confidence_max,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        include_quarantined=include_quarantined,
    )
    total = repo.count_worldcup_prediction_evaluations_filtered(
        competition_key=competition_key,
        status_filter=status_filter,
        pick_tier_filter=pick_tier_filter,
        confidence_min=confidence_min,
        confidence_max=confidence_max,
        date_from=date_from,
        date_to=date_to,
        include_quarantined=include_quarantined,
    )

    rows: list[dict[str, Any]] = []
    for ev in evaluations:
        fid = int(ev["fixture_id"])
        stored_row = repo.get_worldcup_stored_prediction(fid)
        payload = _parse_payload(stored_row)
        fixture = repo.get_fixture_row(fid)
        rows.append(build_accuracy_row(ev, payload=payload, fixture=fixture))

    summary = None
    try:
        from worldcup_predictor.automation.worldcup_background.accuracy_summary import get_accuracy_summary

        summary = get_accuracy_summary(settings=settings, competition_key=competition_key)
    except Exception:
        summary = None
    if not summary:
        from worldcup_predictor.automation.worldcup_background.accuracy_summary import rebuild_accuracy_summary

        summary = rebuild_accuracy_summary(settings=settings, competition_key=competition_key)

    stats = {
        "total_predictions": summary.get("total_stored_predictions") or repo.count_worldcup_stored_predictions(competition_key),
        "evaluated_predictions": summary.get("evaluated_predictions", 0),
        "correct": summary.get("correct", 0),
        "wrong": summary.get("wrong", 0),
        "pending": summary.get("pending", 0),
        "overall_winrate": summary.get("winrate"),
        "official_pick_winrate": (summary.get("official_picks") or {}).get("winrate"),
        "caution_pick_winrate": (summary.get("caution_picks") or {}).get("winrate"),
        "safe_pick_winrate": (summary.get("safe_pick") or {}).get("winrate"),
        "value_pick_winrate": (summary.get("value_pick") or {}).get("winrate"),
        "aggressive_pick_winrate": (summary.get("aggressive_pick") or {}).get("winrate"),
        "no_bet_rate": summary.get("no_bet_rate"),
        "updated_at": summary.get("updated_at"),
    }

    quarantined_count = repo.count_worldcup_prediction_evaluations(
        competition_key=competition_key,
        include_quarantined=True,
    ) - repo.count_worldcup_prediction_evaluations(competition_key=competition_key)

    return {
        "status": "ok",
        "competition_key": competition_key,
        "total": total,
        "limit": limit,
        "offset": offset,
        "statistics": stats,
        "rows": rows,
        "quarantined_evaluations": max(0, quarantined_count),
        "include_quarantined": include_quarantined,
    }


def get_fixture_inspector(
    fixture_id: int,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    stored_row = repo.get_worldcup_stored_prediction(fixture_id)
    if not stored_row:
        return None

    payload = _parse_payload(stored_row)
    fixture = repo.get_fixture_row(fixture_id)

    eval_rows = repo.list_worldcup_prediction_evaluations_filtered(
        fixture_id=fixture_id,
        limit=1,
    )
    evaluation = eval_rows[0] if eval_rows else None
    detail = _parse_detail(evaluation) if evaluation else {}

    nat = payload.get("national_team_intelligence") or {}
    specialist = payload.get("specialist_summary") or {}
    agents = specialist.get("agents") or {}

    reason_analysis: list[str] = []
    overall = (evaluation or {}).get("overall_status")
    if overall == "correct":
        reason_analysis.append("Primary evaluation matched actual outcome.")
    elif overall == "wrong":
        reason_analysis.append("Primary evaluation did not match actual outcome.")
        if payload.get("no_bet"):
            reason_analysis.append("Fixture was below official threshold (caution tier).")
    elif overall == "pending":
        reason_analysis.append("Match not finished or outcome unavailable.")

    markets = detail.get("markets") or {}
    for label, key in (
        ("Safe pick", "safe_pick"),
        ("Value pick", "value_pick"),
        ("Aggressive pick", "aggressive_pick"),
        ("Caution pick", "caution_pick"),
    ):
        st = markets.get(key)
        if st in {"correct", "wrong"}:
            reason_analysis.append(f"{label}: {st}.")

    return {
        "status": "ok",
        "fixture_id": fixture_id,
        "match": build_accuracy_row(
            evaluation or {"fixture_id": fixture_id, "overall_status": "pending", "no_bet": payload.get("no_bet")},
            payload=payload,
            fixture=fixture,
        ),
        "stored_prediction": payload,
        "evaluation": evaluation,
        "evaluation_detail": detail,
        "confidence": payload.get("confidence"),
        "data_quality": payload.get("data_quality"),
        "national_form_score": nat.get("national_form_score"),
        "national_h2h_score": nat.get("national_h2h_score"),
        "squad_strength": nat.get("squad_strength_score"),
        "injury_impact": nat.get("injury_impact_score"),
        "consensus_strength": (payload.get("specialist_summary") or {}).get("aggregated_score"),
        "specialist_agents": agents,
        "actual_result": (evaluation or {}).get("actual_result"),
        "final_score": (evaluation or {}).get("final_score"),
        "evaluation_status": overall or "pending",
        "status_color": _status_color(overall),
        "reason_analysis": reason_analysis,
    }

"""Phase 42D — public performance summary + Best Tips scoring."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.api.global_prediction_archive import _parse_payload, global_entry_id
from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.automation.worldcup_background.accuracy_summary import get_accuracy_summary, rebuild_accuracy_summary
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

_MARKET_DEFS: tuple[tuple[str, str, str], ...] = (
    ("1X2", "market_1x2", "market_1x2_status"),
    ("Over/Under 2.5", "market_over_under_2_5", "market_ou_status"),
    ("BTTS", "market_btts", "market_btts_status"),
    ("Double Chance", "market_double_chance", "market_dc_status"),
    ("HT Result", "market_ht_result", "market_ht_status"),
    ("Correct Score", "market_correct_score", "market_cs_status"),
    ("First Goal Team", "market_first_goal_team", "market_fg_team_status"),
    ("Goalscorer", "market_goalscorer", "market_goalscorer_status"),
    ("Goal Minute", "market_goal_minute", "market_goal_minute_status"),
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def reliability_level(sample_size: int) -> str:
    if sample_size >= 50:
        return "high"
    if sample_size >= 20:
        return "medium"
    return "low"


def _market_block_from_eval_rows(
    market_name: str,
    status_col: str,
    rows: list[dict[str, Any]],
    *,
    stored_by_fixture: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    relevant: list[str] = []
    confidences: list[float] = []
    for row in rows:
        if int(row.get("is_quarantined") or 0):
            continue
        status = str(row.get(status_col) or "pending").lower()
        if status in {"correct", "wrong"}:
            relevant.append(status)
            if stored_by_fixture:
                fid = int(row.get("fixture_id") or 0)
                payload = stored_by_fixture.get(fid) or {}
                raw = payload.get("confidence")
                if raw is not None:
                    try:
                        c = float(raw)
                        if 0 <= c <= 1:
                            c *= 100
                        confidences.append(c)
                    except (TypeError, ValueError):
                        pass
    total = len(relevant)
    correct = sum(1 for s in relevant if s == "correct")
    wrong = total - correct
    pending = sum(
        1
        for row in rows
        if not int(row.get("is_quarantined") or 0)
        and str(row.get(status_col) or "pending").lower() not in {"correct", "wrong"}
    )
    predictions = total + pending
    accuracy = round(correct / total, 4) if total else None
    avg_conf = round(sum(confidences) / len(confidences), 1) if confidences else None
    return {
        "market_name": market_name,
        "predictions": predictions,
        "total": total,
        "evaluated": total,
        "correct": correct,
        "wrong": wrong,
        "pending": pending,
        "accuracy": accuracy,
        "winrate": accuracy,
        "average_confidence": avg_conf,
        "sample_size": total,
        "reliability_level": reliability_level(total),
    }


def _market_block_from_summary_key(market_name: str, block: dict[str, Any] | None) -> dict[str, Any]:
    block = block or {}
    total = int(block.get("total") or 0)
    correct = int(block.get("correct") or 0)
    wrong = max(0, total - correct)
    winrate = block.get("winrate")
    accuracy = float(winrate) if winrate is not None else (round(correct / total, 4) if total else None)
    return {
        "market_name": market_name,
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "pending": 0,
        "accuracy": accuracy,
        "sample_size": total,
        "reliability_level": reliability_level(total),
    }


def build_performance_summary(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    summary = get_accuracy_summary(settings=settings, competition_key=competition_key)
    if not summary or int(summary.get("evaluated_predictions") or 0) <= 0:
        summary = rebuild_accuracy_summary(settings=settings, competition_key=competition_key)

    eval_rows = repo.list_worldcup_prediction_evaluations(competition_key=competition_key)
    eval_rows = [r for r in eval_rows if not int(r.get("is_quarantined") or 0)]
    stored_rows = repo.list_worldcup_stored_predictions(
        competition_key=competition_key, limit=2000, offset=0, include_quarantined=False
    )
    stored_by_fixture = {int(r["fixture_id"]): _parse_payload(r) for r in stored_rows if r.get("fixture_id")}
    dates = [str(r.get("evaluated_at") or "") for r in eval_rows if r.get("evaluated_at")]
    dates.sort()

    evaluated = int((summary or {}).get("evaluated_predictions") or 0)
    correct = int((summary or {}).get("correct") or 0)
    wrong = int((summary or {}).get("wrong") or 0)
    pending = int((summary or {}).get("pending") or 0)

    markets: list[dict[str, Any]] = []
    if summary:
        markets.extend(
            [
                _market_block_from_summary_key("1X2", summary.get("market_1x2")),
                _market_block_from_summary_key("Over/Under 2.5", summary.get("market_over_under_2_5")),
                _market_block_from_summary_key("BTTS", summary.get("market_btts")),
                _market_block_from_summary_key("Double Chance", summary.get("market_double_chance")),
            ]
        )
        for market_name, summary_key, _ in _MARKET_DEFS[4:]:
            block = summary.get(summary_key)
            if isinstance(block, dict) and int(block.get("total") or 0) > 0:
                markets.append(_market_block_from_summary_key(market_name, block))

    for market_name, _, status_col in _MARKET_DEFS:
        if any(m["market_name"] == market_name for m in markets):
            continue
        block = _market_block_from_eval_rows(market_name, status_col, eval_rows, stored_by_fixture=stored_by_fixture)
        if block["total"] > 0:
            markets.append(block)

    ranked = [m for m in markets if m.get("accuracy") is not None and m.get("sample_size", 0) > 0]
    ranked.sort(key=lambda m: float(m["accuracy"]), reverse=True)
    best_market = ranked[0]["market_name"] if ranked else None
    worst_market = ranked[-1]["market_name"] if ranked else None

    from worldcup_predictor.api.public_accuracy_summary import _build_recent_results
    from worldcup_predictor.monitoring.production_accuracy_monitor import build_monitoring_bundle

    overall = summary.get("winrate") if summary else None
    if overall is None and evaluated > 0:
        overall = round(correct / evaluated, 4)

    monitoring = build_monitoring_bundle(settings=settings, competition_key=competition_key)

    return {
        "status": "ok",
        "version": "v2",
        "overall_accuracy": overall,
        "total_evaluated": evaluated,
        "correct_count": correct,
        "wrong_count": wrong,
        "pending_count": pending,
        "date_range_from": dates[0] if dates else None,
        "date_range_to": dates[-1] if dates else None,
        "last_updated": (summary or {}).get("updated_at") or _utc_now_iso(),
        "markets": markets,
        "best_performing_market": best_market if evaluated > 0 else None,
        "worst_performing_market": worst_market if evaluated > 0 else None,
        "recent_results": _build_recent_results(repo, competition_key=competition_key, limit=20),
        "competition_key": competition_key,
        "disclaimer": "Calculated from finished matches only.",
        "data_source": "worldcup_sqlite_evaluations",
        "empty_state_message": "No completed real prediction evaluations yet." if evaluated <= 0 else None,
        "results_refresh_note": "Results are checked automatically every 30 minutes after matches finish.",
        "accuracy_trends": monitoring.get("accuracy_trends"),
        "market_leaderboard": monitoring.get("market_leaderboard"),
        "rule_a_monitoring": monitoring.get("rule_a_monitoring"),
        "agent_contribution": monitoring.get("agent_contribution"),
        "snapshot_count": monitoring.get("snapshot_count"),
    }


def _sample_reliability_score(sample_size: int) -> float:
    return min(1.0, max(0.0, sample_size / 50.0))


def _market_historical_accuracy(markets: list[dict[str, Any]], market_key: str) -> tuple[float, int]:
    aliases = {
        "1x2": "1X2",
        "match_winner": "1X2",
        "over_under_2_5": "Over/Under 2.5",
        "over_under_25": "Over/Under 2.5",
        "btts": "BTTS",
        "double_chance": "Double Chance",
        "first_team_to_score": "First Goal Team",
        "first_goal": "First Goal Team",
    }
    label = aliases.get(market_key, market_key)
    for block in markets:
        if block.get("market_name") == label:
            acc = block.get("accuracy")
            sample = int(block.get("sample_size") or 0)
            return (float(acc) if acc is not None else 0.0, sample)
    return 0.0, 0


def _is_market_withheld(block: dict[str, Any]) -> bool:
    if not isinstance(block, dict):
        return True
    status = str(block.get("consistency_status") or "").lower()
    if status == "withheld" or block.get("display_allowed") is False:
        return True
    if block.get("withheld"):
        return True
    return False


def _confidence_pct(block: dict[str, Any], payload: dict[str, Any]) -> float:
    for source in (block, payload):
        for key in ("probability", "confidence"):
            raw = source.get(key)
            if raw is None:
                continue
            try:
                num = float(raw)
            except (TypeError, ValueError):
                continue
            if 0 <= num <= 1:
                return num
            return num / 100.0
    raw = payload.get("confidence")
    if raw is not None:
        try:
            num = float(raw)
            return num / 100.0 if num > 1 else num
        except (TypeError, ValueError):
            pass
    return 0.0


def _risk_level(score: float, sample_size: int) -> str:
    if sample_size < 20:
        return "low_sample"
    if score >= 0.72:
        return "moderate"
    if score >= 0.6:
        return "elevated"
    return "high"


def build_best_tips(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    limit: int = 12,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    resolver = FixtureOutcomeResolver(settings=settings)
    perf = build_performance_summary(settings=settings, competition_key=competition_key)
    market_blocks = perf.get("markets") or []

    stored_rows = repo.list_worldcup_stored_predictions(competition_key=competition_key, limit=500, offset=0)
    tips: list[dict[str, Any]] = []

    market_labels = {
        "match_winner": "1X2",
        "over_under_25": "Over/Under 2.5",
        "btts": "BTTS",
        "double_chance": "Double Chance",
        "first_goal": "First Goal Team",
    }

    for row in stored_rows:
        fixture_id = int(row["fixture_id"])
        outcome = resolver.resolve(fixture_id)
        if outcome.is_finished:
            continue

        payload = _parse_payload(row)
        dm = payload.get("detailed_markets") or {}
        if not isinstance(dm, dict):
            continue

        fixture = repo.get_fixture_row(fixture_id) or {}
        home = fixture.get("home_team") or payload.get("home_team") or "Home"
        away = fixture.get("away_team") or payload.get("away_team") or "Away"
        match_date = fixture.get("kickoff_utc") or row.get("kickoff_utc") or payload.get("kickoff_utc")
        data_quality_raw = payload.get("data_quality")
        try:
            data_quality_score = float(data_quality_raw) / 100.0 if data_quality_raw is not None else 0.7
        except (TypeError, ValueError):
            data_quality_score = 0.7
        if data_quality_score > 1:
            data_quality_score /= 100.0

        for market_key, block in dm.items():
            if not isinstance(block, dict):
                continue
            if _is_market_withheld(block):
                continue
            selection = block.get("selection") or block.get("team") or block.get("pick")
            if not selection:
                continue

            hist_acc, sample_size = _market_historical_accuracy(market_blocks, market_key)
            if sample_size < 5:
                continue

            confidence = _confidence_pct(block, payload)
            score = (
                0.45 * hist_acc
                + 0.30 * confidence
                + 0.15 * _sample_reliability_score(sample_size)
                + 0.10 * data_quality_score
            )

            tips.append(
                {
                    "fixture_id": fixture_id,
                    "match_name": f"{home} vs {away}",
                    "match_date": match_date,
                    "market": market_labels.get(market_key, market_key.replace("_", " ").title()),
                    "market_key": market_key,
                    "prediction": str(selection),
                    "confidence": round(confidence * 100, 1),
                    "historical_market_accuracy": hist_acc,
                    "sample_size": sample_size,
                    "best_tip_score": round(score, 4),
                    "reason": (
                        f"Strong {market_labels.get(market_key, market_key)} track record "
                        f"({round(hist_acc * 100, 1)}% over {sample_size}) with {round(confidence * 100, 1)}% model confidence."
                    ),
                    "risk_level": _risk_level(score, sample_size),
                    "source_prediction_id": global_entry_id(fixture_id),
                }
            )

    tips.sort(key=lambda t: float(t.get("best_tip_score") or 0), reverse=True)
    top = tips[: max(1, min(limit, 50))]

    return {
        "status": "ok",
        "tips": top,
        "count": len(top),
        "updated_at": _utc_now_iso(),
        "disclaimer": "Best Tips prefer historically strong markets on upcoming fixtures only.",
    }

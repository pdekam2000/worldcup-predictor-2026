"""Advisory learning engine — Phase 34 (read-only, no auto weight changes)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.admin.accuracy_center import _parse_detail, _parse_payload
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

_DISCLAIMER = (
    "Advisory report only — human review required. "
    "No model weights or thresholds were modified automatically."
)
_MIN_LEARNING_SAMPLE = 20


def _rate(correct: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(correct / total, 4)


def _bucket(confidence: float | None) -> str:
    c = float(confidence or 0)
    if c < 50:
        return "0-50"
    if c < 60:
        return "50-60"
    if c < 70:
        return "60-70"
    if c < 80:
        return "70-80"
    return "80-100"


def _record_outcome(status: str | None) -> str | None:
    s = str(status or "").lower()
    if s in {"correct", "wrong"}:
        return s
    return None


def _accumulate(bucket: dict[str, list[int]], key: str, status: str | None) -> None:
    outcome = _record_outcome(status)
    if outcome is None:
        return
    bucket.setdefault(key, [0, 0])
    bucket[key][1] += 1
    if outcome == "correct":
        bucket[key][0] += 1


def _metrics_from_bucket(bucket: dict[str, list[int]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key, (correct, total) in bucket.items():
        out.append({
            "key": key,
            "label": key.replace("_", " ").title(),
            "total": total,
            "correct": correct,
            "winrate": _rate(correct, total),
        })
    out.sort(key=lambda x: (x.get("winrate") is None, -(x.get("winrate") or 0)))
    return out


def _recommendations(
    agents: list[dict[str, Any]],
    markets: list[dict[str, Any]],
    buckets: list[dict[str, Any]],
) -> dict[str, list[str]]:
    weight_increase: list[str] = []
    weight_decrease: list[str] = []
    threshold_changes: list[str] = []
    agent_improvements: list[str] = []

    for row in agents:
        wr = row.get("winrate")
        if wr is None or row.get("total", 0) < 3:
            continue
        if wr >= 0.65:
            weight_increase.append(f"Consider increasing weight for {row['label']} (winrate {wr:.1%}, n={row['total']}).")
        elif wr <= 0.45:
            weight_decrease.append(f"Consider decreasing weight for {row['label']} (winrate {wr:.1%}, n={row['total']}).")
            agent_improvements.append(f"Review {row['label']} signal quality — underperforming baseline.")

    for row in markets:
        wr = row.get("winrate")
        if wr is None or row.get("total", 0) < 3:
            continue
        if wr >= 0.68:
            weight_increase.append(f"Market {row['label']} performing well ({wr:.1%}).")
        elif wr <= 0.42:
            weight_decrease.append(f"Market {row['label']} underperforming ({wr:.1%}) — tighten gates.")

    for row in buckets:
        wr = row.get("winrate")
        if wr is None or row.get("total", 0) < 3:
            continue
        if row["key"] == "50-60" and wr < 0.5:
            threshold_changes.append("Official threshold (60) may be appropriate — sub-60 bucket under 50% winrate.")
        if row["key"] == "60-70" and wr >= 0.65:
            threshold_changes.append("60-70 confidence bucket strong — current premium threshold validated.")

    return {
        "suggested_weight_increases": weight_increase[:8],
        "suggested_weight_decreases": weight_decrease[:8],
        "suggested_threshold_changes": threshold_changes[:5],
        "suggested_agent_improvements": agent_improvements[:8],
    }


def build_learning_dashboard(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    evaluations = repo.list_worldcup_prediction_evaluations(competition_key=competition_key)

    settled_count = sum(
        1 for ev in evaluations if str(ev.get("overall_status") or "").lower() in {"correct", "wrong"}
    )
    insufficient = settled_count < _MIN_LEARNING_SAMPLE

    agent_bucket: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    market_bucket: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    rec_bucket: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    conf_bucket: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for ev in evaluations:
        fid = int(ev["fixture_id"])
        payload = _parse_payload(repo.get_worldcup_stored_prediction(fid))
        detail = _parse_detail(ev)
        markets = detail.get("markets") or {}

        conf = payload.get("confidence")
        try:
            conf_f = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            conf_f = None
        if conf_f is not None and conf_f <= 1:
            conf_f *= 100

        overall = ev.get("overall_status")
        _accumulate(conf_bucket, _bucket(conf_f), overall)

        for key, label in (
            ("safe_pick", "Safe Pick"),
            ("value_pick", "Value Pick"),
            ("aggressive_pick", "Aggressive Pick"),
            ("caution_pick", "Caution Pick"),
        ):
            _accumulate(rec_bucket, label, markets.get(key))

        for key, label in (
            ("market_1x2", "1X2"),
            ("over_under_2_5", "Over/Under 2.5"),
            ("market_btts", "BTTS"),
            ("double_chance", "Double Chance"),
        ):
            st = markets.get(key) or ev.get(f"{key.replace('market_', '')}_status")
            _accumulate(market_bucket, label, st)

        nat = payload.get("national_team_intelligence") or {}
        if nat.get("national_form_score") is not None:
            _accumulate(agent_bucket, "National Form", overall)
        if nat.get("national_h2h_score") is not None:
            _accumulate(agent_bucket, "National H2H", overall)
        if nat.get("injury_impact_score") is not None:
            _accumulate(agent_bucket, "Injury Engine", overall)
        if nat.get("consensus_strength") is not None or (payload.get("specialist_summary") or {}).get("aggregated_score"):
            _accumulate(agent_bucket, "Consensus Agent", overall)

        specialist = payload.get("specialist_summary") or {}
        for name, block in (specialist.get("agents") or {}).items():
            if isinstance(block, dict) and block.get("status") in {"available", "partial"}:
                _accumulate(agent_bucket, name.replace("_", " ").title(), overall)

    agent_metrics = _metrics_from_bucket(agent_bucket)
    market_metrics = _metrics_from_bucket(market_bucket)
    recommendation_metrics = _metrics_from_bucket(rec_bucket)
    confidence_metrics = _metrics_from_bucket(conf_bucket)

    recommendations = _recommendations(agent_metrics, market_metrics, confidence_metrics) if not insufficient else {
        "suggested_weight_increases": [],
        "suggested_weight_decreases": [],
        "suggested_threshold_changes": [],
        "suggested_agent_improvements": [],
    }

    top_agents = [a for a in agent_metrics if a.get("winrate") is not None and (a.get("total") or 0) >= _MIN_LEARNING_SAMPLE][:5] if not insufficient else []
    worst_agents = sorted(
        [a for a in agent_metrics if a.get("winrate") is not None and (a.get("total") or 0) >= _MIN_LEARNING_SAMPLE],
        key=lambda x: x.get("winrate") or 0,
    )[:5] if not insufficient else []

    base = {
        "status": "ok",
        "competition_key": competition_key,
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "disclaimer": _DISCLAIMER,
        "insufficient_data": insufficient,
        "min_sample_required": _MIN_LEARNING_SAMPLE,
        "settled_evaluations": settled_count,
        "trust_message": (
            f"Learning insights require at least {_MIN_LEARNING_SAMPLE} evaluated real predictions."
            if insufficient
            else None
        ),
        "agent_performance": agent_metrics,
        "market_performance": market_metrics,
        "recommendation_performance": recommendation_metrics,
        "confidence_bucket_performance": confidence_metrics,
        "top_agents": top_agents,
        "worst_agents": worst_agents,
        "best_markets": [m for m in market_metrics if m.get("winrate") is not None][:5] if not insufficient else [],
        "worst_markets": sorted(
            [m for m in market_metrics if m.get("winrate") is not None],
            key=lambda x: x.get("winrate") or 0,
        )[:5] if not insufficient else [],
        "recommendations": recommendations,
    }

    try:
        from worldcup_predictor.admin.accuracy_optimization import build_accuracy_optimization_report

        optimization = build_accuracy_optimization_report(
            settings=settings, competition_key=competition_key,
        )
        base["optimization"] = optimization
        base["schema_version"] = optimization.get("schema_version", "35-v1")
    except Exception:
        base["optimization"] = None

    return base


def generate_and_store_learning_report(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    version: str = "v2",
) -> dict[str, Any]:
    settings = settings or get_settings()
    if version == "v2":
        from worldcup_predictor.admin.accuracy_optimization import generate_and_store_optimization_report_v2

        return generate_and_store_optimization_report_v2(settings=settings, competition_key=competition_key)

    dashboard = build_learning_dashboard(settings=settings, competition_key=competition_key)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    report_id = repo.insert_learning_report(
        competition_key=competition_key,
        report_type="advisory_v1",
        payload=dashboard,
    )
    dashboard["report_id"] = report_id
    return dashboard


def list_learning_reports(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    limit: int = 20,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    return repo.list_learning_reports(competition_key=competition_key, limit=limit)

"""Self-Learning Accuracy Engine V2 — read-only analytics, human review required."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.learning.learning_capture import _AGENT_LABELS
from worldcup_predictor.learning.self_learning_models import (
    AgentPerformanceMetrics,
    CalibrationBucket,
    LeaguePerformanceMetrics,
    LearningRecommendation,
    MarketTypeMetrics,
    SelfLearningReportV2,
)

_CALIBRATION_BUCKETS = (
    ("50-60", 50, 60),
    ("60-70", 60, 70),
    ("70-80", 70, 80),
    ("80-90", 80, 90),
    ("90-100", 90, 100),
)

_COMPETITION_LABELS = {
    "world_cup_2026": "World Cup",
    "uefa_nations_league": "UEFA Nations League",
    "bundesliga": "Bundesliga",
    "premier_league": "Premier League",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _actual_lean(actual_1x2: str | None) -> str | None:
    if not actual_1x2:
        return None
    if actual_1x2 == "draw":
        return "draw"
    if actual_1x2 == "home_win":
        return "home"
    if actual_1x2 == "away_win":
        return "away"
    return None


def _sync_from_evaluated(repo: Any, evaluated: list[Any]) -> int:
    """Backfill learning records from evaluated predictions when missing."""
    synced = 0
    for ev in evaluated:
        try:
            record_id = f"{ev.fixture_id}-legacy-{ev.prediction_created_at[:10]}"
            payload = {
                "fixture_id": ev.fixture_id,
                "prediction_id": record_id,
                "competition_key": "world_cup_2026",
                "match_name": ev.match_name,
                "predicted_1x2": ev.predicted_1x2,
                "predicted_over_under": ev.predicted_over_under,
                "confidence": ev.confidence_score,
                "specialists": {},
                "actual_1x2": ev.actual_1x2,
                "actual_over_under": ev.actual_over_under,
                "one_x_two_correct": ev.one_x_two_correct,
                "over_under_correct": ev.over_under_correct,
                "draw_correct": ev.predicted_1x2 == "draw" and ev.one_x_two_correct,
            }
            if repo.append_learning_record_v2(
                record_id=record_id,
                fixture_id=ev.fixture_id,
                prediction_id=record_id,
                competition_key="world_cup_2026",
                payload=payload,
                created_at=ev.prediction_created_at,
            ):
                repo.mark_learning_record_verified(
                    record_id,
                    outcome_payload={
                        "actual_1x2": ev.actual_1x2,
                        "actual_over_under": ev.actual_over_under,
                        "one_x_two_correct": ev.one_x_two_correct,
                        "over_under_correct": ev.over_under_correct,
                    },
                    verified_at=ev.evaluated_at,
                )
                synced += 1
        except Exception:
            continue
    return synced


def _load_records(repo: Any, competition_key: str | None) -> list[dict[str, Any]]:
    records = repo.fetch_learning_records_v2(competition_key=competition_key)
    if records:
        return records
    try:
        from worldcup_predictor.accuracy.service import AccuracyTrackerService
        from worldcup_predictor.config.settings import get_settings

        svc = AccuracyTrackerService(get_settings(), competition_key=competition_key or "world_cup_2026")
        snap = svc.load_summary()
        _sync_from_evaluated(repo, snap.evaluated)
        records = repo.fetch_learning_records_v2(competition_key=competition_key)
    except Exception:
        pass
    return records


def _agent_metrics(records: list[dict[str, Any]]) -> list[AgentPerformanceMetrics]:
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "hits": 0,
            "misses": 0,
            "false_pos": 0,
            "false_neg": 0,
            "neutral": 0,
            "samples": 0,
            "contribution": 0.0,
        }
    )

    for rec in records:
        payload = rec.get("payload") or {}
        actual = _actual_lean(payload.get("actual_1x2"))
        if actual is None and payload.get("one_x_two_correct") is None:
            continue
        if actual is None:
            actual = "home" if payload.get("one_x_two_correct") and payload.get("predicted_1x2") == "home_win" else (
                "away" if payload.get("one_x_two_correct") and payload.get("predicted_1x2") == "away_win" else "draw"
            )

        specialists = payload.get("specialists") or {}
        for agent_key, meta in specialists.items():
            if not isinstance(meta, dict):
                continue
            lean = meta.get("lean")
            if not lean:
                continue
            label = meta.get("label") or _AGENT_LABELS.get(agent_key, agent_key)
            s = stats[agent_key]
            s["label"] = label
            s["samples"] += 1
            impact = float(meta.get("impact_score") or 50)
            s["contribution"] += impact / 100.0

            aligned = lean == actual or (lean == "neutral" and actual == "draw")
            if lean == "neutral":
                s["neutral"] += 1
                continue
            if aligned:
                s["hits"] += 1
            else:
                s["misses"] += 1
                if lean in {"home", "away", "draw"}:
                    s["false_pos"] += 1
                if actual in {"home", "away"} and lean != actual:
                    s["false_neg"] += 1

    metrics: list[AgentPerformanceMetrics] = []
    for agent_key, s in stats.items():
        samples = s["samples"]
        hits = s["hits"]
        misses = s["misses"]
        evaluated = hits + misses
        acc = round(hits / evaluated, 4) if evaluated else None
        win_rate = acc
        fp = round(s["false_pos"] / evaluated, 4) if evaluated else None
        fn = round(s["false_neg"] / evaluated, 4) if evaluated else None
        contrib = round(s["contribution"] / max(samples, 1) * 100, 1)
        reliability = 50.0
        if acc is not None:
            reliability = _clamp(acc * 100 - (fp or 0) * 20 - (fn or 0) * 15 + min(samples, 20), 0, 100)
        metrics.append(
            AgentPerformanceMetrics(
                agent_key=agent_key,
                label=s.get("label") or _AGENT_LABELS.get(agent_key, agent_key),
                samples=samples,
                accuracy=acc,
                win_rate=win_rate,
                contribution_score=contrib,
                false_positive_rate=fp,
                false_negative_rate=fn,
                agent_reliability_score=round(reliability, 1),
            )
        )

    if not metrics:
        for agent_key, label in _AGENT_LABELS.items():
            metrics.append(
                AgentPerformanceMetrics(
                    agent_key=agent_key,
                    label=label,
                    samples=0,
                    agent_reliability_score=50.0,
                )
            )

    metrics.sort(key=lambda m: m.agent_reliability_score, reverse=True)
    return metrics


def _league_metrics(records: list[dict[str, Any]], repo: Any) -> list[LeaguePerformanceMetrics]:
    by_league: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"1x2": [], "ou": [], "draw": [], "samples": 0}
    )

    for rec in records:
        payload = rec.get("payload") or {}
        ck = rec.get("competition_key") or payload.get("competition_key") or "unknown"
        if payload.get("one_x_two_correct") is not None:
            by_league[ck]["1x2"].append(bool(payload["one_x_two_correct"]))
            by_league[ck]["samples"] += 1
        if payload.get("over_under_correct") is not None:
            by_league[ck]["ou"].append(bool(payload["over_under_correct"]))
        if payload.get("draw_correct") is not None:
            by_league[ck]["draw"].append(bool(payload["draw_correct"]))
        elif payload.get("predicted_1x2") == "draw" and payload.get("one_x_two_correct") is not None:
            by_league[ck]["draw"].append(bool(payload["one_x_two_correct"]))

    try:
        for row in repo.performance_by_competition():
            ck = row["competition_key"]
            market = row["market"]
            wr = row.get("winrate")
            if wr is None:
                continue
            if market == "1x2":
                by_league[ck]["1x2"].extend([True] * int(wr * 10) + [False] * int((1 - wr) * 10))
            elif market == "over_under_2_5":
                by_league[ck]["ou"].extend([True] * int(wr * 10) + [False] * int((1 - wr) * 10))
    except Exception:
        pass

    out: list[LeaguePerformanceMetrics] = []
    for ck, data in by_league.items():
        x2 = data["1x2"]
        ou = data["ou"]
        dr = data["draw"]
        x2_acc = round(sum(x2) / len(x2), 4) if x2 else None
        ou_acc = round(sum(ou) / len(ou), 4) if ou else None
        dr_acc = round(sum(dr) / len(dr), 4) if dr else None
        scores = [v for v in (x2_acc, ou_acc) if v is not None]
        reliability = round(_clamp(sum(scores) / len(scores) * 100, 0, 100), 1) if scores else 50.0
        out.append(
            LeaguePerformanceMetrics(
                competition_key=ck,
                label=_COMPETITION_LABELS.get(ck, ck.replace("_", " ").title()),
                samples=data["samples"],
                one_x_two_accuracy=x2_acc,
                over_under_accuracy=ou_acc,
                draw_accuracy=dr_acc,
                league_reliability_score=reliability,
            )
        )
    out.sort(key=lambda l: l.league_reliability_score, reverse=True)
    return out


def _market_metrics(records: list[dict[str, Any]]) -> list[MarketTypeMetrics]:
    buckets: dict[str, dict[str, Any]] = {
        "1x2": {"correct": 0, "total": 0, "conf": []},
        "over_2_5": {"correct": 0, "total": 0, "conf": []},
        "under_2_5": {"correct": 0, "total": 0, "conf": []},
        "draw": {"correct": 0, "total": 0, "conf": []},
    }

    for rec in records:
        payload = rec.get("payload") or {}
        conf = float(payload.get("confidence") or 0)
        if payload.get("one_x_two_correct") is not None:
            buckets["1x2"]["total"] += 1
            buckets["1x2"]["conf"].append(conf)
            if payload["one_x_two_correct"]:
                buckets["1x2"]["correct"] += 1
        if payload.get("over_under_correct") is not None:
            key = payload.get("predicted_over_under") or "over_2_5"
            mk = "over_2_5" if "over" in str(key) else "under_2_5"
            buckets[mk]["total"] += 1
            buckets[mk]["conf"].append(conf)
            if payload["over_under_correct"]:
                buckets[mk]["correct"] += 1
        if payload.get("predicted_1x2") == "draw" and payload.get("one_x_two_correct") is not None:
            buckets["draw"]["total"] += 1
            buckets["draw"]["conf"].append(conf)
            if payload["one_x_two_correct"]:
                buckets["draw"]["correct"] += 1

    labels = {
        "1x2": "1X2",
        "over_2_5": "Over 2.5",
        "under_2_5": "Under 2.5",
        "draw": "Draw",
    }
    out: list[MarketTypeMetrics] = []
    for mk, data in buckets.items():
        total = data["total"]
        acc = round(data["correct"] / total, 4) if total else None
        avg_conf = round(sum(data["conf"]) / len(data["conf"]), 1) if data["conf"] else 0.0
        out.append(
            MarketTypeMetrics(
                market=mk,
                label=labels[mk],
                samples=total,
                accuracy=acc,
                average_confidence=avg_conf,
            )
        )
    out.sort(key=lambda m: (m.accuracy or 0), reverse=True)
    return out


def _calibration(records: list[dict[str, Any]]) -> list[CalibrationBucket]:
    verified = [
        r for r in records
        if (r.get("payload") or {}).get("one_x_two_correct") is not None
    ]
    buckets: list[CalibrationBucket] = []
    for label, lo, hi in _CALIBRATION_BUCKETS:
        subset = [
            r for r in verified
            if lo <= float((r.get("payload") or {}).get("confidence") or 0) < hi
            or (hi == 100 and float((r.get("payload") or {}).get("confidence") or 0) >= lo)
        ]
        if not subset:
            buckets.append(CalibrationBucket(label=label, predicted_confidence_avg=(lo + hi) / 2, actual_hit_rate=None, count=0))
            continue
        hits = sum(1 for r in subset if (r.get("payload") or {}).get("one_x_two_correct"))
        hit_rate = round(hits / len(subset), 4)
        avg_conf = round(sum(float((r.get("payload") or {}).get("confidence") or 0) for r in subset) / len(subset), 1)
        gap = round(avg_conf / 100 - hit_rate, 4) if hit_rate is not None else None
        buckets.append(
            CalibrationBucket(
                label=label,
                predicted_confidence_avg=avg_conf,
                actual_hit_rate=hit_rate,
                count=len(subset),
                calibration_gap=gap,
            )
        )
    return buckets


def _insights(
    agents: list[AgentPerformanceMetrics],
    leagues: list[LeaguePerformanceMetrics],
    markets: list[MarketTypeMetrics],
    calibration: list[CalibrationBucket],
) -> list[str]:
    insights: list[str] = []
    if agents and agents[0].samples > 0:
        top = agents[0]
        insights.append(f"{top.label} is the strongest contributor (reliability {top.agent_reliability_score:.0f}/100).")
    weak = [a for a in agents if a.samples >= 3 and (a.agent_reliability_score or 0) < 45]
    for w in weak[:2]:
        insights.append(f"{w.label} contributes little or shows weak alignment (reliability {w.agent_reliability_score:.0f}/100).")

    sm = next((a for a in agents if a.agent_key == "sharp_money_intelligence_agent"), None)
    if sm and sm.samples >= 2 and (sm.agent_reliability_score or 0) >= 70:
        insights.append("Sharp Money is highly reliable in tracked samples.")

    inj = next((a for a in agents if a.agent_key == "injury_suspension_intelligence_agent"), None)
    if inj and inj.samples >= 2 and (inj.agent_reliability_score or 0) < 50:
        insights.append("Injury Intelligence is weaker when data confidence is low.")

    weather = next((a for a in agents if a.agent_key == "weather_agent"), None)
    if weather and weather.samples >= 2 and (weather.contribution_score or 0) < 30:
        insights.append("Weather contributes little to verified outcomes in current sample.")

    if leagues:
        best = leagues[0]
        if best.samples >= 2:
            insights.append(f"{best.label} shows highest league reliability ({best.league_reliability_score:.0f}/100).")

    best_m = next((m for m in markets if m.samples >= 2 and m.accuracy is not None), None)
    worst_m = next((m for m in reversed(markets) if m.samples >= 2 and m.accuracy is not None), None)
    if best_m and worst_m and best_m.market != worst_m.market:
        insights.append(f"System performs best on {best_m.label} and weakest on {worst_m.label} in current sample.")

    over_cal = next((c for c in calibration if c.count >= 3 and c.calibration_gap is not None and c.calibration_gap > 0.1), None)
    if over_cal:
        insights.append(
            f"Confidence {over_cal.label} bucket over-estimates accuracy "
            f"(predicted ~{over_cal.predicted_confidence_avg:.0f}%, actual {over_cal.actual_hit_rate * 100:.0f}%)."
        )

    if not insights:
        insights.append("Insufficient verified history — collect more finished-match evaluations.")
    return insights[:8]


def _recommendations(
    agents: list[AgentPerformanceMetrics],
    calibration: list[CalibrationBucket],
) -> list[LearningRecommendation]:
    recs: list[LearningRecommendation] = []
    lineup = next((a for a in agents if a.agent_key == "lineup_intelligence_agent"), None)
    if lineup and (lineup.agent_reliability_score or 0) >= 75 and lineup.samples >= 3:
        boost = min(8, int((lineup.agent_reliability_score - 60) / 3))
        recs.append(
            LearningRecommendation(
                category="weight_suggestion",
                message=f"Consider increasing Lineup Intelligence influence by ~{boost}% (human review required).",
                priority="medium",
            )
        )

    weather = next((a for a in agents if a.agent_key == "weather_agent"), None)
    if weather and weather.samples >= 5 and (weather.agent_reliability_score or 0) < 40:
        recs.append(
            LearningRecommendation(
                category="weight_suggestion",
                message="Consider reducing Weather factor weight — low verified contribution in current sample.",
                priority="low",
            )
        )

    sm = next((a for a in agents if a.agent_key == "sharp_money_intelligence_agent"), None)
    if sm and (sm.agent_reliability_score or 0) >= 72 and sm.samples >= 3:
        recs.append(
            LearningRecommendation(
                category="weight_suggestion",
                message="Consider modest Sharp Money weight increase in high-consensus World Cup fixtures (review only).",
                priority="medium",
            )
        )

    for bucket in calibration:
        if bucket.count >= 5 and bucket.calibration_gap is not None and bucket.calibration_gap > 0.12:
            recs.append(
                LearningRecommendation(
                    category="calibration",
                    message=(
                        f"Review confidence caps for {bucket.label} predictions — "
                        f"actual hit rate {bucket.actual_hit_rate * 100:.0f}% vs avg confidence {bucket.predicted_confidence_avg:.0f}%."
                    ),
                    priority="high",
                )
            )
            break

    if not recs:
        recs.append(
            LearningRecommendation(
                category="general",
                message="Continue collecting verified predictions before adjusting factor weights.",
                priority="low",
            )
        )

    return recs


def build_self_learning_report(
    *,
    competition_key: str | None = None,
    repository: Any | None = None,
) -> SelfLearningReportV2:
    """Build full Self-Learning Report V2 — never raises."""
    try:
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        repo = repository or FootballIntelligenceRepository()
        records = _load_records(repo, competition_key)
        verified = [
            r for r in records
            if (r.get("payload") or {}).get("one_x_two_correct") is not None
            or r.get("verified_at")
        ]

        agents = _agent_metrics(records)
        leagues = _league_metrics(records, repo)
        markets = _market_metrics(records)
        calibration = _calibration(records)
        insights = _insights(agents, leagues, markets, calibration)
        recommendations = _recommendations(agents, calibration)

        history_sample = [
            {
                "fixture_id": r.get("fixture_id"),
                "match_name": (r.get("payload") or {}).get("match_name"),
                "predicted_1x2": (r.get("payload") or {}).get("predicted_1x2"),
                "confidence": (r.get("payload") or {}).get("confidence"),
                "verified": r.get("verified_at") is not None,
            }
            for r in reversed(records[-15:])
        ]

        if hasattr(repo, "close") and repository is None:
            repo.close()

        return SelfLearningReportV2(
            total_records=len(records),
            verified_records=len(verified),
            pending_records=max(0, len(records) - len(verified)),
            agent_rankings=agents,
            league_rankings=leagues,
            market_type_metrics=markets,
            calibration_buckets=calibration,
            insights=insights,
            recommendations=recommendations,
            prediction_history_sample=history_sample,
        )
    except Exception:
        return SelfLearningReportV2(
            total_records=0,
            verified_records=0,
            pending_records=0,
            agent_rankings=[],
            league_rankings=[],
            market_type_metrics=[],
            calibration_buckets=[],
            insights=["Learning report unavailable — safe fallback applied."],
            recommendations=[
                LearningRecommendation(
                    category="general",
                    message="Collect more verified predictions before generating weight recommendations.",
                    priority="low",
                )
            ],
        )


def build_agent_performance_report(**kwargs: Any) -> dict[str, Any]:
    report = build_self_learning_report(**kwargs)
    return {
        "agent_rankings": [a.to_dict() for a in report.agent_rankings],
        "insights": report.insights,
        "verified_records": report.verified_records,
        "disclaimer": report.disclaimer,
        "version": report.version,
    }


def build_calibration_report(**kwargs: Any) -> dict[str, Any]:
    report = build_self_learning_report(**kwargs)
    return {
        "calibration_buckets": [c.to_dict() for c in report.calibration_buckets],
        "verified_records": report.verified_records,
        "insights": [i for i in report.insights if "confidence" in i.lower() or "bucket" in i.lower()],
        "disclaimer": report.disclaimer,
        "version": report.version,
    }

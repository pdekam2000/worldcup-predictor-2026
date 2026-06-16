"""Unified accuracy / winrate metrics for User + Developer dashboards."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from worldcup_predictor.accuracy.history_store import PredictionHistoryStore
from worldcup_predictor.accuracy.metrics import compute_accuracy_metrics
from worldcup_predictor.accuracy.models import AccuracySummaryMetrics, EvaluatedPrediction
from worldcup_predictor.accuracy.service import AccuracyTrackerService
from worldcup_predictor.verification.store import VerificationStore


@dataclass
class MarketAccuracy:
    market: str
    evaluated: int
    correct: int

    @property
    def rate(self) -> float | None:
        if self.evaluated == 0:
            return None
        return round(self.correct / self.evaluated, 4)


@dataclass
class PeriodAccuracy:
    total_predictions: int = 0
    verified_predictions: int = 0
    correct_1x2: int = 0
    correct_ou: int = 0
    correct_scoreline: int = 0
    correct_first_goal_team: int = 0
    correct_first_goal_minute: int = 0
    correct_first_goal_scorer: int = 0
    evaluated_1x2: int = 0
    evaluated_ou: int = 0
    evaluated_scoreline: int = 0
    evaluated_first_goal_team: int = 0
    evaluated_first_goal_minute: int = 0
    evaluated_first_goal_scorer: int = 0

    def rate_1x2(self) -> float | None:
        return _rate(self.correct_1x2, self.evaluated_1x2)

    def rate_ou(self) -> float | None:
        return _rate(self.correct_ou, self.evaluated_ou)

    def rate_scoreline(self) -> float | None:
        return _rate(self.correct_scoreline, self.evaluated_scoreline)

    def rate_first_goal_team(self) -> float | None:
        return _rate(self.correct_first_goal_team, self.evaluated_first_goal_team)

    def rate_first_goal_minute(self) -> float | None:
        return _rate(self.correct_first_goal_minute, self.evaluated_first_goal_minute)

    def rate_first_goal_scorer(self) -> float | None:
        return _rate(self.correct_first_goal_scorer, self.evaluated_first_goal_scorer)


@dataclass
class AccuracyDashboardSnapshot:
    all_time: PeriodAccuracy
    last_30_days: PeriodAccuracy
    summary: AccuracySummaryMetrics
    verification_markets: list[MarketAccuracy] = field(default_factory=list)
    formula_notes: list[str] = field(default_factory=list)


def _rate(correct: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(correct / total, 4)


def _parse_evaluated_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _period_from_evaluated(
    evaluated: list[EvaluatedPrediction],
    *,
    since: datetime | None = None,
    total_predictions: int = 0,
) -> PeriodAccuracy:
    period = PeriodAccuracy(total_predictions=total_predictions)
    for item in evaluated:
        if since is not None:
            ts = _parse_evaluated_at(item.evaluated_at)
            if ts is None or ts < since:
                continue
        period.verified_predictions += 1
        period.evaluated_1x2 += 1
        if item.one_x_two_correct:
            period.correct_1x2 += 1
        period.evaluated_ou += 1
        if item.over_under_correct:
            period.correct_ou += 1
        if item.predicted_scoreline:
            period.evaluated_scoreline += 1
            if item.scoreline_exact_correct:
                period.correct_scoreline += 1
        if item.first_goal_evaluated:
            period.evaluated_first_goal_team += 1
            if item.first_goal_correct:
                period.correct_first_goal_team += 1
    return period


def _verification_markets(store: VerificationStore | None = None) -> list[MarketAccuracy]:
    target = store or VerificationStore()
    rows = target.load_all()
    buckets: dict[str, list[bool]] = {}
    for row in rows:
        market = str(getattr(row, "market", "") or "")
        if not market:
            continue
        buckets.setdefault(market, []).append(bool(getattr(row, "correct", False)))
    out: list[MarketAccuracy] = []
    labels = {
        "1x2": "1X2",
        "over_under_2_5": "Over/Under 2.5",
        "scoreline_exact": "Exact scoreline",
        "first_goal_team": "First goal team",
        "first_goal_scorer": "First goal scorer",
        "halftime_bucket": "Halftime bucket",
        "first_goal_minute_band": "First goal minute band",
    }
    for key, results in sorted(buckets.items()):
        out.append(
            MarketAccuracy(
                market=labels.get(key, key),
                evaluated=len(results),
                correct=sum(1 for ok in results if ok),
            )
        )
    return out


def build_accuracy_dashboard(
    fixtures: list,
    *,
    competition_key: str = "world_cup_2026",
) -> AccuracyDashboardSnapshot:
    """Compute exact winrate metrics from stored predictions vs finished results."""
    service = AccuracyTrackerService(competition_key=competition_key)
    snapshot = service.refresh(fixtures)
    evaluated = snapshot.evaluated
    since_30 = datetime.now(timezone.utc) - timedelta(days=30)

    all_time = _period_from_evaluated(
        evaluated,
        total_predictions=snapshot.metrics.total_predictions,
    )
    all_time.verified_predictions = len(evaluated)

    last_30 = _period_from_evaluated(evaluated, since=since_30)
    last_30.total_predictions = snapshot.metrics.total_predictions

    vmarkets = _verification_markets()
    for vm in vmarkets:
        if vm.market == "First goal scorer":
            all_time.evaluated_first_goal_scorer = vm.evaluated
            all_time.correct_first_goal_scorer = vm.correct
        if vm.market == "First goal minute band":
            all_time.evaluated_first_goal_minute = vm.evaluated
            all_time.correct_first_goal_minute = vm.correct

    formulas = [
        "1X2: predicted outcome vs actual home/draw/away on finished fixtures.",
        "O/U 2.5: total goals > 2 vs predicted over/under.",
        "Exact scoreline: predicted score string equals final score.",
        "First goal team: first scorer event team vs prediction (when events available).",
        "First goal scorer / minute band: from verification store when event data supports evaluation.",
        "Last 30 days: evaluated_at within rolling 30-day UTC window.",
        "Latest prediction per fixture used (AccuracyTrackerService.refresh).",
    ]
    return AccuracyDashboardSnapshot(
        all_time=all_time,
        last_30_days=last_30,
        summary=snapshot.metrics,
        verification_markets=vmarkets,
        formula_notes=formulas,
    )

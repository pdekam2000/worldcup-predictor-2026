from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.backtesting.models import MatchBacktestResult

CONFIDENCE_BUCKETS: list[tuple[str, float, float]] = [
    ("0-40", 0.0, 40.0),
    ("40-60", 40.0, 60.0),
    ("60-75", 60.0, 75.0),
    ("75-90", 75.0, 90.0),
    ("90-100", 90.0, 100.01),
]

HIGH_CONFIDENCE_THRESHOLD = 75.0


@dataclass
class ConfidenceBucketMetrics:
    label: str
    count: int = 0
    one_x_two_correct: int = 0
    over_under_correct: int = 0
    average_confidence: float = 0.0

    @property
    def one_x_two_accuracy(self) -> float | None:
        if self.count == 0:
            return None
        return round(self.one_x_two_correct / self.count, 4)

    @property
    def over_under_accuracy(self) -> float | None:
        if self.count == 0:
            return None
        return round(self.over_under_correct / self.count, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "count": self.count,
            "one_x_two_accuracy": self.one_x_two_accuracy,
            "over_under_accuracy": self.over_under_accuracy,
            "average_confidence": round(self.average_confidence, 2),
        }


@dataclass
class BacktestMetrics:
    total_matches: int = 0
    one_x_two_accuracy: float | None = None
    over_under_2_5_accuracy: float | None = None
    halftime_bucket_accuracy: float | None = None
    average_confidence: float = 0.0
    high_confidence_accuracy: float | None = None
    high_confidence_count: int = 0
    no_bet_count: int = 0
    no_bet_rate: float | None = None
    first_goal_skipped_count: int = 0
    halftime_evaluated_count: int = 0
    specialists_ran_count: int = 0
    confidence_buckets: list[ConfidenceBucketMetrics] = field(default_factory=list)
    strongest_market: str | None = None
    weakest_market: str | None = None
    data_limitations: list[str] = field(default_factory=list)
    weight_recommendations: list[str] = field(default_factory=list)
    is_demo_data: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_matches": self.total_matches,
            "one_x_two_accuracy": self.one_x_two_accuracy,
            "over_under_2_5_accuracy": self.over_under_2_5_accuracy,
            "halftime_bucket_accuracy": self.halftime_bucket_accuracy,
            "average_confidence": round(self.average_confidence, 2),
            "high_confidence_accuracy": self.high_confidence_accuracy,
            "high_confidence_count": self.high_confidence_count,
            "no_bet_count": self.no_bet_count,
            "no_bet_rate": self.no_bet_rate,
            "first_goal_skipped_count": self.first_goal_skipped_count,
            "halftime_evaluated_count": self.halftime_evaluated_count,
            "specialists_ran_count": self.specialists_ran_count,
            "confidence_buckets": [bucket.to_dict() for bucket in self.confidence_buckets],
            "strongest_market": self.strongest_market,
            "weakest_market": self.weakest_market,
            "data_limitations": self.data_limitations,
            "weight_recommendations": self.weight_recommendations,
            "is_demo_data": self.is_demo_data,
            "disclaimer": (
                "Historical backtest performance does not guarantee future results. "
                "Model evaluation and calibration only — not betting advice."
            ),
        }


def compute_metrics(
    results: list[MatchBacktestResult],
    *,
    is_demo_data: bool = False,
) -> BacktestMetrics:
    if not results:
        return BacktestMetrics(
            data_limitations=["No historical matches evaluated."],
            is_demo_data=is_demo_data,
        )

    one_x_two_hits = sum(1 for r in results if r.one_x_two_correct)
    ou_hits = sum(1 for r in results if r.over_under_correct)
    ht_results = [r for r in results if r.halftime_evaluated]
    ht_hits = sum(1 for r in ht_results if r.halftime_bucket_correct)

    avg_confidence = sum(r.confidence_score for r in results) / len(results)
    high_conf = [r for r in results if r.confidence_score >= HIGH_CONFIDENCE_THRESHOLD]
    high_conf_hits = sum(1 for r in high_conf if r.one_x_two_correct)

    no_bet_count = sum(1 for r in results if r.no_bet_flag)
    buckets = _build_confidence_buckets(results)

    market_scores = {
        "1X2": one_x_two_hits / len(results),
        "Over/Under 2.5": ou_hits / len(results),
    }
    if ht_results:
        market_scores["Halftime bucket"] = ht_hits / len(ht_results)

    strongest = max(market_scores, key=market_scores.get)  # type: ignore[arg-type]
    weakest = min(market_scores, key=market_scores.get)  # type: ignore[arg-type]

    limitations = _build_limitations(results, is_demo_data)
    recommendations = _build_weight_recommendations(market_scores, buckets, no_bet_count, len(results))

    return BacktestMetrics(
        total_matches=len(results),
        one_x_two_accuracy=round(one_x_two_hits / len(results), 4),
        over_under_2_5_accuracy=round(ou_hits / len(results), 4),
        halftime_bucket_accuracy=round(ht_hits / len(ht_results), 4) if ht_results else None,
        average_confidence=avg_confidence,
        high_confidence_accuracy=round(high_conf_hits / len(high_conf), 4) if high_conf else None,
        high_confidence_count=len(high_conf),
        no_bet_count=no_bet_count,
        no_bet_rate=round(no_bet_count / len(results), 4),
        first_goal_skipped_count=sum(1 for r in results if r.first_goal_skipped),
        halftime_evaluated_count=len(ht_results),
        specialists_ran_count=sum(1 for r in results if r.specialists_ran),
        confidence_buckets=buckets,
        strongest_market=strongest,
        weakest_market=weakest,
        data_limitations=limitations,
        weight_recommendations=recommendations,
        is_demo_data=is_demo_data,
    )


def _build_confidence_buckets(results: list[MatchBacktestResult]) -> list[ConfidenceBucketMetrics]:
    bucket_map = {label: ConfidenceBucketMetrics(label=label) for label, _, _ in CONFIDENCE_BUCKETS}

    for result in results:
        label = _confidence_bucket_label(result.confidence_score)
        bucket = bucket_map[label]
        bucket.count += 1
        bucket.average_confidence += result.confidence_score
        if result.one_x_two_correct:
            bucket.one_x_two_correct += 1
        if result.over_under_correct:
            bucket.over_under_correct += 1

    ordered: list[ConfidenceBucketMetrics] = []
    for label, _, _ in CONFIDENCE_BUCKETS:
        bucket = bucket_map[label]
        if bucket.count:
            bucket.average_confidence /= bucket.count
        ordered.append(bucket)
    return ordered


def _confidence_bucket_label(score: float) -> str:
    for label, low, high in CONFIDENCE_BUCKETS:
        if low <= score < high:
            return label
    return "90-100"


def _build_limitations(results: list[MatchBacktestResult], is_demo: bool) -> list[str]:
    limitations: list[str] = [
        "Historical performance does not guarantee future World Cup 2026 outcomes.",
        "Backtest evaluates model calibration only — not betting profitability.",
    ]
    if is_demo:
        limitations.append("Demo CSV used — illustrative sample, not a full historical dataset.")
    if any(r.first_goal_skipped for r in results):
        limitations.append("First-goal predictions skipped — historical first-goal data not in CSV.")
    missing_ht = sum(1 for r in results if not r.halftime_evaluated)
    if missing_ht:
        limitations.append(f"{missing_ht} matches missing halftime scores — excluded from HT bucket accuracy.")
    if sum(1 for r in results if not r.specialists_ran):
        limitations.append("Some matches ran without full specialist synthesis.")
    return limitations


def _build_weight_recommendations(
    market_scores: dict[str, float],
    buckets: list[ConfidenceBucketMetrics],
    no_bet_count: int,
    total: int,
) -> list[str]:
    recs: list[str] = []
    weakest = min(market_scores, key=market_scores.get)  # type: ignore[arg-type]
    weakest_score = market_scores[weakest]

    if weakest == "1X2" and weakest_score < 0.45:
        recs.append("Consider increasing team_form and head_to_head weights in WeightedDecisionEngine for 1X2.")
    if weakest == "Over/Under 2.5" and weakest_score < 0.50:
        recs.append("Review tactics_agent and weather_agent goal adjustments — O/U 2.5 underperformed.")
    if weakest == "Halftime bucket":
        recs.append("Halftime bucket model is weak — reduce halftime confidence or refine first-half goal ratio.")

    high_buckets = [b for b in buckets if b.label in ("75-90", "90-100") and b.count > 0]
    for bucket in high_buckets:
        acc = bucket.one_x_two_accuracy
        if acc is not None and acc < 0.55:
            recs.append(
                f"Confidence bucket {bucket.label} is overconfident — tighten confidence caps in audit engine."
            )

    if total and no_bet_count / total > 0.5:
        recs.append("High no-bet rate — improve historical data completeness (odds, form) before 2026 reliance.")

    if not recs:
        recs.append("Weights are reasonable on this sample — expand CSV with more competitions before tuning.")
    return recs

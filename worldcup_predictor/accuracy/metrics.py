from __future__ import annotations

from worldcup_predictor.accuracy.models import AccuracySummaryMetrics, ConfidenceRangeMetrics, EvaluatedPrediction
from worldcup_predictor.backtesting.metrics import CONFIDENCE_BUCKETS
from worldcup_predictor.performance.grades import best_and_worst_market, compute_model_grade, market_league_table

MIN_BUCKET_COUNT = 2


def compute_accuracy_metrics(
    evaluated: list[EvaluatedPrediction],
    *,
    pending_predictions: int = 0,
    total_predictions: int = 0,
) -> AccuracySummaryMetrics:
    if not evaluated:
        return AccuracySummaryMetrics(
            pending_predictions=pending_predictions,
            total_predictions=total_predictions,
            data_limitations=[
                "No finished matches with stored predictions evaluated yet.",
                "Run predictions before kickoff to build learning memory.",
            ],
        )

    one_x_two_hits = sum(1 for item in evaluated if item.one_x_two_correct)
    ou_hits = sum(1 for item in evaluated if item.over_under_correct)
    ht_items = [item for item in evaluated if item.halftime_evaluated]
    ht_hits = sum(1 for item in ht_items if item.halftime_bucket_correct)
    sl_items = [item for item in evaluated if item.predicted_scoreline]
    sl_hits = sum(1 for item in sl_items if item.scoreline_exact_correct)
    fg_items = [item for item in evaluated if item.first_goal_evaluated]
    fg_hits = sum(1 for item in fg_items if item.first_goal_correct)

    no_bet = [item for item in evaluated if item.no_bet_flag]
    non_no_bet = [item for item in evaluated if not item.no_bet_flag]

    buckets = _build_confidence_buckets(evaluated)
    best_range, worst_range = _best_worst_ranges(buckets)

    limitations = [
        "Historical model evaluation does not guarantee future World Cup outcomes.",
        "Accuracy tracking measures calibration only — not profit or betting performance.",
    ]
    if any(item.first_goal_skipped for item in evaluated):
        skipped_fg = sum(1 for item in evaluated if item.first_goal_skipped)
        limitations.append(
            f"{skipped_fg} finished matches missing first-goal event data — excluded from first-goal evaluation."
        )
    missing_ht = sum(1 for item in evaluated if not item.halftime_evaluated)
    if missing_ht:
        limitations.append(
            f"{missing_ht} finished matches missing halftime scores — excluded from HT bucket evaluation."
        )

    metrics = AccuracySummaryMetrics(
        total_evaluated=len(evaluated),
        one_x_two_accuracy=round(one_x_two_hits / len(evaluated), 4),
        over_under_2_5_accuracy=round(ou_hits / len(evaluated), 4),
        halftime_bucket_accuracy=round(ht_hits / len(ht_items), 4) if ht_items else None,
        halftime_evaluated_count=len(ht_items),
        scoreline_exact_accuracy=round(sl_hits / len(sl_items), 4) if sl_items else None,
        scoreline_evaluated_count=len(sl_items),
        first_goal_accuracy=round(fg_hits / len(fg_items), 4) if fg_items else None,
        first_goal_evaluated_count=len(fg_items),
        total_predictions=total_predictions or len(evaluated) + pending_predictions,
        average_confidence=sum(item.confidence_score for item in evaluated) / len(evaluated),
        no_bet_count=len(no_bet),
        no_bet_one_x_two_accuracy=_accuracy(no_bet, "one_x_two_correct"),
        non_no_bet_one_x_two_accuracy=_accuracy(non_no_bet, "one_x_two_correct"),
        no_bet_over_under_accuracy=_accuracy(no_bet, "over_under_correct"),
        non_no_bet_over_under_accuracy=_accuracy(non_no_bet, "over_under_correct"),
        confidence_buckets=buckets,
        best_confidence_range=best_range,
        worst_confidence_range=worst_range,
        pending_predictions=pending_predictions,
        first_goal_skipped_count=sum(1 for item in evaluated if item.first_goal_skipped),
        data_limitations=limitations,
    )
    metrics.model_grade = compute_model_grade(metrics.one_x_two_accuracy)
    league = market_league_table(metrics)
    metrics.best_market, metrics.worst_market = best_and_worst_market(league)
    return metrics


def _accuracy(items: list[EvaluatedPrediction], field_name: str) -> float | None:
    if not items:
        return None
    hits = sum(1 for item in items if getattr(item, field_name))
    return round(hits / len(items), 4)


def _confidence_bucket_label(score: float) -> str:
    for label, low, high in CONFIDENCE_BUCKETS:
        if low <= score < high:
            return label
    return "90-100"


def _build_confidence_buckets(evaluated: list[EvaluatedPrediction]) -> list[ConfidenceRangeMetrics]:
    bucket_map = {label: ConfidenceRangeMetrics(label=label) for label, _, _ in CONFIDENCE_BUCKETS}
    for item in evaluated:
        label = _confidence_bucket_label(item.confidence_score)
        bucket = bucket_map[label]
        bucket.count += 1
        bucket.average_confidence += item.confidence_score
        if item.one_x_two_correct:
            bucket.one_x_two_correct += 1
        if item.over_under_correct:
            bucket.over_under_correct += 1

    ordered: list[ConfidenceRangeMetrics] = []
    for label, _, _ in CONFIDENCE_BUCKETS:
        bucket = bucket_map[label]
        if bucket.count:
            bucket.average_confidence /= bucket.count
        ordered.append(bucket)
    return ordered


def _best_worst_ranges(buckets: list[ConfidenceRangeMetrics]) -> tuple[str | None, str | None]:
    eligible = [bucket for bucket in buckets if bucket.count >= MIN_BUCKET_COUNT and bucket.one_x_two_accuracy is not None]
    if not eligible:
        return None, None
    best = max(eligible, key=lambda bucket: bucket.one_x_two_accuracy or 0.0)
    worst = min(eligible, key=lambda bucket: bucket.one_x_two_accuracy or 0.0)
    return best.label, worst.label

"""Adaptive Confidence Engine — evolves confidence using learning memory."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from worldcup_predictor.adaptive_confidence.knowledge_base import (
    AdaptiveKnowledgeBase,
    AdaptiveKnowledgeSnapshot,
    get_knowledge_snapshot,
)
from worldcup_predictor.adaptive_confidence.models import (
    AdaptiveConfidenceAdjustment,
    CalibrationLabel,
    ModelExperienceSummary,
)
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import ConfidenceLevel, MatchPrediction
from worldcup_predictor.learning.patterns.pattern_discovery import (
    AnalysisRow,
    PatternDiscoveryEngine,
    MIN_PATTERN_SAMPLES,
)
from worldcup_predictor.learning.patterns.pattern_models import DiscoveredPattern

MIN_SIMILAR_SAMPLES = 10
MAX_TOTAL_BONUS = 25.0
MAX_TOTAL_PENALTY = -15.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _confidence_bucket(score: float) -> str:
    if score < 40:
        return "0-40"
    if score < 60:
        return "40-60"
    if score < 75:
        return "60-75"
    if score < 90:
        return "75-90"
    return "90-100"


def _confidence_level_from_score(score: float) -> ConfidenceLevel:
    if score >= 70:
        return ConfidenceLevel.HIGH
    if score >= 50:
        return ConfidenceLevel.MEDIUM
    if score > 0:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.UNAVAILABLE


def _norm_dq(value: float) -> float:
    return value * 100 if value <= 1.0 else value


def _situation_row_from_report(
    report: MatchIntelligenceReport,
    prediction: MatchPrediction,
) -> AnalysisRow:
    dq = prediction.confidence_breakdown.data_quality_score if prediction.confidence_breakdown else 0.0
    lineups = bool(report.lineups and report.lineups.get("available"))
    has_odds = "odds" not in (report.missing_data or []) and bool(report.odds)
    has_xg = bool((report.supplemental_sources or {}).get("rapid_xg_statistics"))
    return AnalysisRow(
        prediction_id="current",
        fixture_id=prediction.fixture_id,
        competition_key=prediction.competition_key,
        market="1x2",
        result="pending",
        data_quality=dq,
        prediction_quality=prediction.prediction_quality_score,
        confidence=prediction.confidence_score,
        lineups_available=lineups,
        is_preliminary=not lineups,
        no_bet_flag=prediction.no_bet_flag,
        selected_by_engine=False,
        has_odds=has_odds,
        has_xg=has_xg,
        odds_disagreement=False,
        has_fixture_result=False,
        selection_level=None,
    )


def _similar_situation_rows(
    current: AnalysisRow,
    history: list[AnalysisRow],
) -> list[AnalysisRow]:
    dq = _norm_dq(current.data_quality)
    matched: list[AnalysisRow] = []
    for row in history:
        if current.competition_key and row.competition_key != current.competition_key:
            continue
        row_dq = _norm_dq(row.data_quality)
        if abs(row_dq - dq) > 15:
            continue
        if row.lineups_available != current.lineups_available:
            continue
        if row.has_odds != current.has_odds:
            continue
        matched.append(row)
    return matched


def _similar_situation_bonus(
    matched: list[AnalysisRow],
    baseline: float,
) -> tuple[float, int, float | None]:
    if len(matched) < MIN_SIMILAR_SAMPLES:
        return 0.0, len(matched), None
    correct = sum(1 for r in matched if r.is_correct)
    winrate = correct / len(matched)
    delta = winrate - baseline
    sample_weight = min(len(matched) / 50.0, 1.5)
    bonus = delta * 100.0 * sample_weight
    bonus = _clamp(bonus, MAX_TOTAL_PENALTY, MAX_TOTAL_BONUS)
    return round(bonus, 1), len(matched), round(winrate, 4)


def _pattern_matches_current(pattern: DiscoveredPattern, current: AnalysisRow) -> bool:
    templates = {t.pattern_id: t for t in PatternDiscoveryEngine()._pattern_templates()}
    template = templates.get(pattern.pattern_id)
    if template is None:
        return False
    return template.predicate(current)


def _pattern_bonus(
    current: AnalysisRow,
    pattern_report: Any | None,
) -> tuple[float, list[str]]:
    if pattern_report is None:
        return 0.0, []
    bonus = 0.0
    matched_ids: list[str] = []
    candidates = (
        list(getattr(pattern_report, "success_causes", []) or [])
        + list(getattr(pattern_report, "strongest_patterns", []) or [])
        + list(getattr(pattern_report, "failure_causes", []) or [])
        + list(getattr(pattern_report, "weakest_patterns", []) or [])
    )
    seen: set[str] = set()
    for pattern in candidates:
        if pattern.pattern_id in seen:
            continue
        seen.add(pattern.pattern_id)
        if not _pattern_matches_current(pattern, current):
            continue
        matched_ids.append(pattern.pattern_id)
        strength = pattern.statistical_strength
        sample_factor = min(pattern.sample_size / 30.0, 1.5)
        if pattern.kind == "success":
            delta = max(0.0, pattern.winrate - pattern.baseline_winrate)
            bonus += min(delta * 80.0 * sample_factor + strength * 10.0, 8.0)
        else:
            delta = max(0.0, pattern.baseline_winrate - pattern.winrate)
            bonus -= min(delta * 80.0 * sample_factor + strength * 10.0, 8.0)
    return round(_clamp(bonus, -10.0, 10.0), 1), matched_ids


def _competition_bonus(
    competition_key: str,
    coach_report: Any | None,
    baseline: float,
) -> float:
    if coach_report is None:
        return 0.0
    comp_rates = getattr(coach_report, "competition_winrates", {}) or {}
    markets = comp_rates.get(competition_key) or {}
    rate = markets.get("1X2") or markets.get("1x2")
    if rate is None:
        return 0.0
    delta = float(rate) - baseline
    return round(_clamp(delta * 40.0, -6.0, 8.0), 1)


def _bucket_bonus(
    base_confidence: float,
    buckets: list[dict[str, Any]],
) -> float:
    label = _confidence_bucket(base_confidence)
    for bucket in buckets:
        if bucket.get("label") != label and bucket.get("bucket") != label:
            continue
        count = int(bucket.get("count") or bucket.get("total") or 0)
        if count < MIN_PATTERN_SAMPLES:
            return 0.0
        acc = bucket.get("one_x_two_accuracy") or bucket.get("winrate")
        avg_conf = bucket.get("average_confidence")
        if acc is None or avg_conf is None:
            return 0.0
        implied = float(avg_conf) / 100.0 if float(avg_conf) > 1 else float(avg_conf)
        calibration_delta = float(acc) - implied
        return round(_clamp(calibration_delta * 30.0, -5.0, 5.0), 1)
    return 0.0


def _build_reason(
    *,
    similar_samples: int,
    similar_winrate: float | None,
    total_bonus: float,
    baseline: float,
) -> str:
    if similar_samples >= MIN_SIMILAR_SAMPLES and similar_winrate is not None:
        pct = similar_winrate * 100
        return (
            f"{similar_samples} similar matches found. "
            f"Historical success rate: {pct:.0f}%."
        )
    if total_bonus > 0:
        return (
            f"Learning memory suggests stronger calibration "
            f"(baseline {baseline * 100:.0f}%)."
        )
    if total_bonus < 0:
        return "Historical patterns suggest caution for this situation."
    return "Insufficient verified history — using base model confidence only."


def _adaptive_prediction_quality(
    base_quality: float,
    *,
    similar_samples: int,
    similar_winrate: float | None,
    baseline: float,
    patterns_learned: int,
    competition_bonus: float,
) -> float:
    score = base_quality
    if similar_samples >= MIN_SIMILAR_SAMPLES and similar_winrate is not None:
        delta = similar_winrate - baseline
        score += delta * 100.0 * min(similar_samples / 60.0, 1.2) * 0.15
    if patterns_learned >= MIN_PATTERN_SAMPLES:
        score += min(patterns_learned * 0.08, 6.0)
    score += competition_bonus * 0.5
    return round(_clamp(score, 0.0, 100.0), 1)


def count_patterns_learned(pattern_report: Any | None) -> int:
    if pattern_report is None:
        return 0
    ids: set[str] = set()
    for attr in (
        "strongest_patterns",
        "weakest_patterns",
        "failure_causes",
        "success_causes",
    ):
        for pattern in getattr(pattern_report, attr, []) or []:
            ids.add(pattern.pattern_id)
    for patterns in (getattr(pattern_report, "competition_patterns", {}) or {}).values():
        for pattern in patterns:
            ids.add(pattern.pattern_id)
    return len(ids)


def calibration_label(buckets: list[dict[str, Any]], total_rows: int) -> CalibrationLabel:
    if total_rows < MIN_SIMILAR_SAMPLES:
        return "Limited"
    scored: list[float] = []
    for bucket in buckets:
        count = int(bucket.get("count") or 0)
        acc = bucket.get("one_x_two_accuracy")
        avg = bucket.get("average_confidence")
        if count < 5 or acc is None or avg is None:
            continue
        implied = float(avg) / 100.0 if float(avg) > 1 else float(avg)
        scored.append(abs(float(acc) - implied))
    if not scored:
        return "Fair"
    mean_gap = sum(scored) / len(scored)
    if mean_gap <= 0.08:
        return "Excellent"
    if mean_gap <= 0.15:
        return "Good"
    if mean_gap <= 0.22:
        return "Fair"
    return "Limited"


class AdaptiveConfidenceEngine:
    """Applies learning-informed confidence adjustments after base prediction scoring."""

    def __init__(self, knowledge: AdaptiveKnowledgeBase | None = None) -> None:
        self._knowledge = knowledge or AdaptiveKnowledgeBase()

    def snapshot(self, *, competition_key: str | None = None) -> AdaptiveKnowledgeSnapshot:
        return self._knowledge.snapshot(competition_key=competition_key)

    def model_experience(self, *, competition_key: str | None = None) -> ModelExperienceSummary:
        snap = self.snapshot(competition_key=competition_key)
        verified = len({r.fixture_id for r in snap.analysis_rows}) if snap.analysis_rows else 0
        if verified == 0 and snap.coach_report:
            verified = snap.coach_report.evaluated_matches
        patterns = count_patterns_learned(snap.pattern_report)
        return ModelExperienceSummary(
            verified_matches=verified,
            patterns_learned=patterns,
            confidence_calibration=calibration_label(
                snap.accuracy_confidence_buckets,
                len(snap.analysis_rows),
            ),
            baseline_winrate=snap.baseline_winrate if snap.analysis_rows else None,
            total_learning_rows=len(snap.analysis_rows),
        )

    def apply(
        self,
        prediction: MatchPrediction,
        report: MatchIntelligenceReport,
        *,
        base_prediction_quality: float,
        use_cache: bool = True,
    ) -> AdaptiveConfidenceAdjustment:
        snap = (
            get_knowledge_snapshot(prediction.competition_key)
            if use_cache
            else self.snapshot(competition_key=prediction.competition_key)
        )
        current = _situation_row_from_report(report, prediction)
        base_confidence = float(prediction.confidence_score)

        similar_rows = _similar_situation_rows(current, snap.analysis_rows)
        similar_bonus, similar_n, similar_wr = _similar_situation_bonus(
            similar_rows,
            snap.baseline_winrate,
        )
        pattern_bonus, matched_patterns = _pattern_bonus(current, snap.pattern_report)
        competition_bonus = _competition_bonus(
            prediction.competition_key,
            snap.coach_report,
            snap.baseline_winrate,
        )
        bucket_bonus = _bucket_bonus(base_confidence, snap.accuracy_confidence_buckets)

        total_bonus = round(
            _clamp(
                similar_bonus + pattern_bonus + competition_bonus + bucket_bonus,
                MAX_TOTAL_PENALTY,
                MAX_TOTAL_BONUS,
            ),
            1,
        )
        final_confidence = round(_clamp(base_confidence + total_bonus, 0.0, 100.0), 1)
        patterns_learned = count_patterns_learned(snap.pattern_report)
        final_pq = _adaptive_prediction_quality(
            base_prediction_quality,
            similar_samples=similar_n,
            similar_winrate=similar_wr,
            baseline=snap.baseline_winrate,
            patterns_learned=patterns_learned,
            competition_bonus=competition_bonus,
        )
        reason = _build_reason(
            similar_samples=similar_n,
            similar_winrate=similar_wr,
            total_bonus=total_bonus,
            baseline=snap.baseline_winrate,
        )

        return AdaptiveConfidenceAdjustment(
            base_confidence=base_confidence,
            final_confidence=final_confidence,
            total_bonus=total_bonus,
            pattern_bonus=pattern_bonus,
            competition_bonus=competition_bonus,
            similar_situation_bonus=similar_bonus,
            bucket_bonus=bucket_bonus,
            reason=reason,
            similar_sample_size=similar_n,
            similar_winrate=similar_wr,
            base_prediction_quality=base_prediction_quality,
            final_prediction_quality=final_pq,
            matched_pattern_ids=matched_patterns,
        )

    def enrich_prediction(
        self,
        prediction: MatchPrediction,
        report: MatchIntelligenceReport,
        *,
        base_prediction_quality: float,
    ) -> MatchPrediction:
        adjustment = self.apply(
            prediction,
            report,
            base_prediction_quality=base_prediction_quality,
        )
        new_level = _confidence_level_from_score(adjustment.final_confidence)
        if prediction.confidence_level == ConfidenceLevel.UNAVAILABLE:
            new_level = ConfidenceLevel.UNAVAILABLE

        return replace(
            prediction,
            confidence_score=adjustment.final_confidence,
            confidence_level=new_level,
            prediction_quality_score=adjustment.final_prediction_quality,
            adaptive_confidence=adjustment,
            metadata={
                **prediction.metadata,
                "base_confidence": f"{adjustment.base_confidence:.1f}",
                "learning_confidence_bonus": f"{adjustment.total_bonus:+.1f}",
                "base_prediction_quality": f"{adjustment.base_prediction_quality:.1f}",
            },
        )

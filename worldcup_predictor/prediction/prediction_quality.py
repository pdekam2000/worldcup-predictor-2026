"""Prediction quality score — separate from data quality."""

from __future__ import annotations

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction

CRITICAL_FIELDS = ("lineups", "odds", "home_statistics", "away_statistics", "injuries")


def compute_prediction_quality(
    prediction: MatchPrediction,
    report: MatchIntelligenceReport,
    *,
    consistency_ok: bool,
) -> float:
    score = prediction.confidence_score * 0.45

    if consistency_ok:
        score += 28.0
    elif prediction.consistency_notes:
        score += 12.0

    if prediction.scoreline_candidates and len(prediction.scoreline_candidates) >= 3:
        score += 8.0

    missing = set(report.missing_data or [])
    for field in CRITICAL_FIELDS:
        if field in missing or f"home_{field}" in missing or f"away_{field}" in missing:
            score -= 4.0

    if prediction.no_bet_flag:
        score -= 8.0

    if report.data_quality and report.data_quality.breakdown_total:
        score += min(report.data_quality.breakdown_total * 0.12, 12.0)

    rapid = (report.supplemental_sources or {}).get("rapid_football_stats") or {}
    if rapid:
        bonus = 0
        if rapid.get("xg") or rapid.get("npxg"):
            bonus += 2
        if rapid.get("player_statistics"):
            bonus += 2
        if rapid.get("prematch_odds") or rapid.get("live_odds"):
            bonus += 1.5
        if rapid.get("match_statistics"):
            bonus += 1.5
        score += min(bonus, 6.0)

    rapid_xg = (report.supplemental_sources or {}).get("rapid_xg_statistics") or {}
    if rapid_xg:
        xg_bonus = 0.0
        if rapid_xg.get("xg") or rapid_xg.get("npxg") or rapid_xg.get("fixture_detail"):
            xg_bonus += 2.0
        if rapid_xg.get("upcoming_odds"):
            xg_bonus += 1.5
        score += min(xg_bonus, 4.0)

    return round(max(0.0, min(score, 100.0)), 1)

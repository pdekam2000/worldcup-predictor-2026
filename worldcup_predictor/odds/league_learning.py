"""Competition-specific learning profiles from verified predictions — Phase 39."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.league_registry import LEARNING_PROFILE_KEYS, learning_profile_for
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.odds.models import LeagueLearningProfile

SMALL_SAMPLE = 30
MIN_MARKET_ROWS = 3

MARKET_LABELS = {
    "1x2": "1X2",
    "over_under_2_5": "Over/Under 2.5",
    "btts": "BTTS",
    "halftime_bucket": "Half Time Result",
    "halftime_result": "Half Time Result",
    "scoreline_exact": "Correct Score",
    "correct_score": "Correct Score",
    "first_goal_team": "First Goal Team",
    "first_goal_minute": "First Goal Minute",
    "first_goal_minute_band": "First Goal Minute",
    "goalscorer": "Likely Goalscorer",
    "likely_goalscorer": "Likely Goalscorer",
}


def _winrate(correct: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(correct / total, 4)


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


def _dq_bucket(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


class LeagueLearningEngine:
    """Build league-specific learning profiles from SQLite verification data."""

    def __init__(self, repository: FootballIntelligenceRepository | None = None) -> None:
        self._repo = repository or FootballIntelligenceRepository()

    def build_profile(self, competition_key: str) -> LeagueLearningProfile:
        profile_key = learning_profile_for(competition_key)
        rows = self._repo.fetch_pattern_analysis_rows(competition_key=competition_key)
        comp = get_competition(competition_key)
        comp_name = comp.display_name if comp else competition_key
        last_updated = self._repo.latest_learning_update(competition_key=competition_key)

        if not rows:
            return LeagueLearningProfile(
                competition_key=competition_key,
                competition_name=comp_name,
                learning_profile_key=profile_key,
                evaluated_matches=0,
                strongest_market=None,
                weakest_market=None,
                market_winrates={},
                confidence_reliability={},
                data_quality_reliability={},
                recommended_rules=["Insufficient verified data — continue collecting predictions."],
                recommended_confidence_thresholds={"watch_only_below": 45.0, "analysis_ready_above": 60.0},
                sample_size_warning=f"No verified rows for {comp_name}.",
                last_updated_at=last_updated,
                total_market_rows=0,
            )

        fixture_ids = {int(r["fixture_id"]) for r in rows}
        market_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
        conf_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
        dq_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})

        for row in rows:
            market = str(row["market"])
            result = str(row["result"])
            correct = 1 if result == "correct" else 0
            market_stats[market]["total"] += 1
            market_stats[market]["correct"] += correct

            conf_bucket = _confidence_bucket(float(row["confidence"] or 0))
            conf_stats[conf_bucket]["total"] += 1
            conf_stats[conf_bucket]["correct"] += correct

            dq_bucket = _dq_bucket(float(row["data_quality"] or 0))
            dq_stats[dq_bucket]["total"] += 1
            dq_stats[dq_bucket]["correct"] += correct

        market_winrates = {
            MARKET_LABELS.get(m, m): _winrate(v["correct"], v["total"])
            for m, v in market_stats.items()
            if v["total"] >= MIN_MARKET_ROWS
        }
        confidence_reliability = {
            bucket: _winrate(v["correct"], v["total"])
            for bucket, v in conf_stats.items()
            if v["total"] >= MIN_MARKET_ROWS
        }
        data_quality_reliability = {
            bucket: _winrate(v["correct"], v["total"])
            for bucket, v in dq_stats.items()
            if v["total"] >= MIN_MARKET_ROWS
        }

        ranked = sorted(
            (
                (m, _winrate(v["correct"], v["total"]) or 0.0)
                for m, v in market_stats.items()
                if v["total"] >= MIN_MARKET_ROWS
            ),
            key=lambda x: x[1],
            reverse=True,
        )
        strongest = MARKET_LABELS.get(ranked[0][0], ranked[0][0]) if ranked else None
        weakest = MARKET_LABELS.get(ranked[-1][0], ranked[-1][0]) if ranked else None

        rules: list[str] = []
        if len(fixture_ids) < SMALL_SAMPLE:
            rules.append(
                f"Small sample ({len(fixture_ids)} matches) — treat league insights as preliminary."
            )
        if strongest:
            rules.append(f"Prioritize analytical focus on {strongest} where historical winrate is strongest.")
        if weakest:
            rules.append(f"Apply extra caution on {weakest} — weakest historical market for this competition.")
        high_dq = data_quality_reliability.get("high")
        if high_dq is not None and high_dq >= 0.55:
            rules.append("High data-quality predictions show better reliability — prefer enriched fixtures.")
        if not rules:
            rules.append("Continue verification to refine competition-specific thresholds.")

        thresholds = {
            "watch_only_below": 45.0,
            "analysis_ready_above": 60.0,
        }
        low_conf = confidence_reliability.get("0-40")
        if low_conf is not None and low_conf < 0.35:
            thresholds["watch_only_below"] = 50.0
            rules.append("Raise watch-only threshold — low-confidence bucket underperforms in this league.")

        sample_warning = None
        if len(fixture_ids) < SMALL_SAMPLE:
            sample_warning = f"Only {len(fixture_ids)} evaluated matches — league profile is preliminary."

        return LeagueLearningProfile(
            competition_key=competition_key,
            competition_name=comp_name,
            learning_profile_key=profile_key,
            evaluated_matches=len(fixture_ids),
            strongest_market=strongest,
            weakest_market=weakest,
            market_winrates=market_winrates,
            confidence_reliability=confidence_reliability,
            data_quality_reliability=data_quality_reliability,
            recommended_rules=rules,
            recommended_confidence_thresholds=thresholds,
            sample_size_warning=sample_warning,
            last_updated_at=last_updated,
            total_market_rows=len(rows),
        )

    def build_all_profiles(self) -> list[LeagueLearningProfile]:
        profiles: list[LeagueLearningProfile] = []
        for key in LEARNING_PROFILE_KEYS:
            try:
                comp = get_competition(key)
            except KeyError:
                continue
            if not comp.enabled and key != "world_cup_2026":
                continue
            profile = self.build_profile(comp.key)
            profiles.append(profile)
        return profiles

    def build_profile_by_learning_key(self, learning_profile_key: str) -> LeagueLearningProfile | None:
        for comp_key in LEARNING_PROFILE_KEYS:
            try:
                comp = get_competition(comp_key)
            except KeyError:
                continue
            if (comp.learning_profile_key or comp.key) == learning_profile_key:
                return self.build_profile(comp.key)
        return None

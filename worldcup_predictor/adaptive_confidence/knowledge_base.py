"""Loads learning agent, pattern discovery, and verification history for adaptive confidence."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from worldcup_predictor.accuracy.service import AccuracyTrackerService
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.learning.model_coach_agent import ModelCoachAgent
from worldcup_predictor.learning.models import ModelCoachReport
from worldcup_predictor.learning.patterns.pattern_discovery import (
    AnalysisRow,
    PatternDiscoveryEngine,
)
from worldcup_predictor.learning.patterns.pattern_models import PatternDiscoveryReport


@dataclass
class AdaptiveKnowledgeSnapshot:
    pattern_report: PatternDiscoveryReport | None
    coach_report: ModelCoachReport | None
    analysis_rows: list[AnalysisRow]
    baseline_winrate: float
    accuracy_confidence_buckets: list[dict[str, Any]]


class AdaptiveKnowledgeBase:
    """Cached read-only view of learning + verification memory."""

    def __init__(
        self,
        *,
        repository: FootballIntelligenceRepository | None = None,
        pattern_engine: PatternDiscoveryEngine | None = None,
        coach_agent: ModelCoachAgent | None = None,
    ) -> None:
        self._repo = repository or FootballIntelligenceRepository()
        self._pattern_engine = pattern_engine or PatternDiscoveryEngine(repository=self._repo)
        self._coach = coach_agent or ModelCoachAgent(repository=self._repo)

    def snapshot(self, *, competition_key: str | None = None) -> AdaptiveKnowledgeSnapshot:
        pattern_report = self._pattern_engine.load_from_disk()
        coach_report = self._coach.load_from_disk()
        raw = self._repo.fetch_pattern_analysis_rows(competition_key=competition_key)
        rows = [PatternDiscoveryEngine._row_from_db(r) for r in raw]
        if not rows and competition_key is not None:
            raw = self._repo.fetch_pattern_analysis_rows(competition_key=None)
            rows = [PatternDiscoveryEngine._row_from_db(r) for r in raw]

        baseline = 0.5
        if rows:
            correct = sum(1 for r in rows if r.is_correct)
            baseline = round(correct / len(rows), 4)
        elif pattern_report and pattern_report.baseline_winrate:
            baseline = pattern_report.baseline_winrate

        buckets: list[dict[str, Any]] = []
        if coach_report and coach_report.confidence_bucket_performance:
            buckets = list(coach_report.confidence_bucket_performance)
        else:
            try:
                snapshot = AccuracyTrackerService(get_settings()).load_summary_from_disk()
                if snapshot:
                    buckets = [b.to_dict() for b in snapshot.metrics.confidence_buckets]
            except OSError:
                buckets = []

        return AdaptiveKnowledgeSnapshot(
            pattern_report=pattern_report,
            coach_report=coach_report,
            analysis_rows=rows,
            baseline_winrate=baseline,
            accuracy_confidence_buckets=buckets,
        )


@lru_cache(maxsize=4)
def get_knowledge_snapshot(competition_key: str | None = None) -> AdaptiveKnowledgeSnapshot:
    return AdaptiveKnowledgeBase().snapshot(competition_key=competition_key)


def clear_knowledge_cache() -> None:
    get_knowledge_snapshot.cache_clear()

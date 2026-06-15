"""Pattern Discovery Engine — analyzes SQLite history for success/failure patterns."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.learning.patterns.pattern_models import (
    PATTERN_DISCLAIMER,
    ConfidenceLevel,
    DecisionAgentAdvice,
    DiscoveredPattern,
    PatternDiscoveryReport,
    PatternKind,
)
from worldcup_predictor.learning.patterns.pattern_report_writer import PatternDiscoveryReportWriter

MIN_PATTERN_SAMPLES = 5
LOW_SAMPLE_THRESHOLD = 20
MEDIUM_SAMPLE_THRESHOLD = 50

MARKET_LABELS = {
    "1x2": "1X2",
    "over_under_2_5": "O/U 2.5",
    "halftime_bucket": "Halftime bucket",
    "scoreline_exact": "Exact scoreline",
    "first_goal_team": "First goal team",
    "first_goal_scorer": "First goal scorer",
}

COMPETITION_DISPLAY = {
    "world_cup_2026": "World Cup",
    "premier_league": "Premier League",
    "bundesliga": "Bundesliga",
    "serie_a": "Serie A",
    "la_liga": "La Liga",
    "champions_league": "Champions League",
}


@dataclass
class AnalysisRow:
    prediction_id: str
    fixture_id: int
    competition_key: str
    market: str
    result: str
    data_quality: float
    prediction_quality: float
    confidence: float
    lineups_available: bool
    is_preliminary: bool
    no_bet_flag: bool
    selected_by_engine: bool
    has_odds: bool
    has_xg: bool
    odds_disagreement: bool
    has_fixture_result: bool
    selection_level: str | None

    @property
    def is_correct(self) -> bool:
        return self.result == "correct"


@dataclass
class _PatternTemplate:
    pattern_id: str
    label: str
    kind: PatternKind
    conditions: list[str]
    market: str | None
    predicate: Callable[[AnalysisRow], bool]


def _confidence_level(sample_size: int) -> ConfidenceLevel:
    if sample_size < LOW_SAMPLE_THRESHOLD:
        return "low"
    if sample_size < MEDIUM_SAMPLE_THRESHOLD:
        return "medium"
    return "high"


def _winrate(correct: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(correct / total, 4)


def _statistical_strength(winrate: float, baseline: float, sample_size: int) -> float:
    delta = abs(winrate - baseline)
    if sample_size < LOW_SAMPLE_THRESHOLD:
        return round(delta * (sample_size / LOW_SAMPLE_THRESHOLD), 4)
    return round(delta * min(sample_size / MEDIUM_SAMPLE_THRESHOLD, 2.0), 4)


def _market_label(market: str | None) -> str:
    if not market:
        return "All markets"
    return MARKET_LABELS.get(market, market)


def _comp_label(key: str | None) -> str:
    if not key:
        return "All competitions"
    return COMPETITION_DISPLAY.get(key, key.replace("_", " ").title())


class PatternDiscoveryEngine:
    """Discovers advisory patterns from verified predictions in SQLite."""

    def __init__(
        self,
        *,
        repository: FootballIntelligenceRepository | None = None,
        report_writer: PatternDiscoveryReportWriter | None = None,
    ) -> None:
        self._repo = repository or FootballIntelligenceRepository()
        self._writer = report_writer or PatternDiscoveryReportWriter()

    def run(
        self,
        *,
        competition_key: str | None = None,
        write_reports: bool = True,
    ) -> PatternDiscoveryReport:
        rows = self._load_rows(competition_key=competition_key)
        report = self._discover(rows, competition_key=competition_key)
        report.generated_at_utc = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        report.disclaimer = PATTERN_DISCLAIMER
        if write_reports:
            self._writer.write(report)
        return report

    def run_all(self, *, write_reports: bool = True) -> PatternDiscoveryReport:
        rows = self._load_rows(competition_key=None)
        report = self._discover(rows, competition_key=None)
        comp_keys = sorted({r.competition_key for r in rows if r.competition_key})
        for ck in comp_keys:
            comp_rows = [r for r in rows if r.competition_key == ck]
            if len(comp_rows) < MIN_PATTERN_SAMPLES:
                continue
            comp_report = self._discover(comp_rows, competition_key=ck)
            report.competition_patterns[ck] = (
                comp_report.strongest_patterns[:5]
                + comp_report.failure_causes[:3]
                + comp_report.success_causes[:3]
            )
        report.generated_at_utc = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        report.disclaimer = PATTERN_DISCLAIMER
        if write_reports:
            self._writer.write(report)
        return report

    def load_from_disk(self) -> PatternDiscoveryReport | None:
        return self._writer.load_json()

    def _load_rows(self, *, competition_key: str | None) -> list[AnalysisRow]:
        raw = self._repo.fetch_pattern_analysis_rows(competition_key=competition_key)
        return [self._row_from_db(r) for r in raw]

    @staticmethod
    def _row_from_db(row: Any) -> AnalysisRow:
        return AnalysisRow(
            prediction_id=str(row["prediction_id"]),
            fixture_id=int(row["fixture_id"]),
            competition_key=str(row["competition_key"] or "unknown"),
            market=str(row["market"]),
            result=str(row["result"]),
            data_quality=float(row["data_quality"] or 0),
            prediction_quality=float(row["prediction_quality"] or 0),
            confidence=float(row["confidence"] or 0),
            lineups_available=bool(row["lineups_available"]),
            is_preliminary=bool(row["is_preliminary"]),
            no_bet_flag=bool(row["no_bet_flag"]),
            selected_by_engine=bool(row["selected_by_engine"]),
            has_odds=bool(row["has_odds"]),
            has_xg=bool(row["has_xg"]),
            odds_disagreement=bool(row["odds_disagreement"]),
            has_fixture_result=bool(row["has_fixture_result"]),
            selection_level=row["selection_level"],
        )

    def _discover(
        self,
        rows: list[AnalysisRow],
        *,
        competition_key: str | None,
    ) -> PatternDiscoveryReport:
        report = PatternDiscoveryReport(competition_key=competition_key)
        if not rows:
            return report

        correct = sum(1 for r in rows if r.is_correct)
        report.total_rows = len(rows)
        report.baseline_winrate = _winrate(correct, len(rows))

        templates = self._pattern_templates()
        discovered: list[DiscoveredPattern] = []

        for template in templates:
            matched = [r for r in rows if template.predicate(r)]
            if len(matched) < MIN_PATTERN_SAMPLES:
                continue
            c = sum(1 for r in matched if r.is_correct)
            n = len(matched)
            wr = _winrate(c, n)
            baseline = report.baseline_winrate
            kind = template.kind
            if kind == "failure":
                if wr >= baseline - 0.03:
                    continue
            elif kind == "success":
                if wr <= baseline + 0.03:
                    continue

            discovered.append(
                DiscoveredPattern(
                    pattern_id=template.pattern_id,
                    label=template.label,
                    kind=kind,
                    conditions=list(template.conditions),
                    market=template.market,
                    competition_key=competition_key,
                    sample_size=n,
                    winrate=wr,
                    baseline_winrate=baseline,
                    statistical_strength=_statistical_strength(wr, baseline, n),
                    confidence_level=_confidence_level(n),
                    correct_count=c,
                    wrong_count=n - c,
                )
            )

        failures = [p for p in discovered if p.kind == "failure"]
        successes = [p for p in discovered if p.kind == "success"]

        failures.sort(key=lambda p: (p.winrate, -p.sample_size))
        successes.sort(key=lambda p: (-p.winrate, -p.sample_size))

        report.failure_causes = failures
        report.success_causes = successes
        report.weakest_patterns = failures[:8]
        report.strongest_patterns = successes[:8]
        report.decision_agent_advice = self._build_advice(discovered, competition_key=competition_key)
        return report

    def _pattern_templates(self) -> list[_PatternTemplate]:
        return [
            _PatternTemplate(
                "ou25_no_xg",
                "O/U 2.5 without xG data",
                "failure",
                ["Market: O/U 2.5", "xG unavailable"],
                "over_under_2_5",
                lambda r: r.market == "over_under_2_5" and not r.has_xg,
            ),
            _PatternTemplate(
                "ou25_with_xg",
                "O/U 2.5 with xG enrichment",
                "success",
                ["Market: O/U 2.5", "xG available"],
                "over_under_2_5",
                lambda r: r.market == "over_under_2_5" and r.has_xg,
            ),
            _PatternTemplate(
                "before_lineups",
                "Predictions before lineups confirmed",
                "failure",
                ["Lineups unavailable", "Preliminary prediction"],
                None,
                lambda r: not r.lineups_available or r.is_preliminary,
            ),
            _PatternTemplate(
                "final_lineups",
                "Final lineup predictions",
                "success",
                ["Lineups available", "Not preliminary"],
                None,
                lambda r: r.lineups_available and not r.is_preliminary,
            ),
            _PatternTemplate(
                "odds_disagreement",
                "Odds disagreement detected",
                "failure",
                ["Odds disagreement signal", "Market conflict"],
                None,
                lambda r: r.odds_disagreement,
            ),
            _PatternTemplate(
                "low_dq_low_pq",
                "Low data quality and prediction quality",
                "failure",
                ["Data quality < 50", "Prediction quality < 45"],
                None,
                lambda r: r.data_quality < 50 and r.prediction_quality < 45,
            ),
            _PatternTemplate(
                "high_dq_1x2_odds_lineups",
                "1X2 with strong data, odds, and lineups",
                "success",
                ["Market: 1X2", "Data quality > 70", "Odds available", "Lineups available"],
                "1x2",
                lambda r: (
                    r.market == "1x2"
                    and r.data_quality > 70
                    and r.has_odds
                    and r.lineups_available
                ),
            ),
            _PatternTemplate(
                "high_dq_high_conf",
                "High data quality and confidence",
                "success",
                ["Data quality ≥ 70", "Confidence ≥ 60"],
                None,
                lambda r: r.data_quality >= 70 and r.confidence >= 60,
            ),
            _PatternTemplate(
                "no_odds_snapshot",
                "Predictions without odds snapshot",
                "failure",
                ["Odds snapshot missing"],
                None,
                lambda r: not r.has_odds,
            ),
            _PatternTemplate(
                "no_bet_flagged",
                "No-bet flagged predictions",
                "failure",
                ["no_bet flag active"],
                None,
                lambda r: r.no_bet_flag,
            ),
            _PatternTemplate(
                "1x2_low_confidence",
                "1X2 with low model confidence",
                "failure",
                ["Market: 1X2", "Confidence < 45"],
                "1x2",
                lambda r: r.market == "1x2" and r.confidence < 45,
            ),
            _PatternTemplate(
                "halftime_low_dq",
                "Halftime bucket with low data quality",
                "failure",
                ["Market: Halftime bucket", "Data quality < 50"],
                "halftime_bucket",
                lambda r: r.market == "halftime_bucket" and r.data_quality < 50,
            ),
            _PatternTemplate(
                "selected_by_engine",
                "Engine-selected matches",
                "success",
                ["Selected by match selection engine"],
                None,
                lambda r: r.selected_by_engine
                or r.selection_level in {"AUTO_PREDICT", "WATCHLIST"},
            ),
            _PatternTemplate(
                "with_fixture_result",
                "Verified against stored fixture results",
                "success",
                ["Fixture result recorded in database"],
                None,
                lambda r: r.has_fixture_result,
            ),
        ]

    def _build_advice(
        self,
        patterns: list[DiscoveredPattern],
        *,
        competition_key: str | None,
    ) -> list[DecisionAgentAdvice]:
        advice: list[DecisionAgentAdvice] = []
        by_id = {p.pattern_id: p for p in patterns}
        comp_suffix = f" ({_comp_label(competition_key)})" if competition_key else ""

        def add(
            advice_id: str,
            message: str,
            priority: str,
            pattern_ids: list[str],
        ) -> None:
            advice.append(
                DecisionAgentAdvice(
                    advice_id=advice_id,
                    message=message,
                    priority=priority,  # type: ignore[arg-type]
                    supporting_pattern_ids=pattern_ids,
                    competition_key=competition_key,
                )
            )

        if p := by_id.get("before_lineups"):
            if p.winrate < p.baseline_winrate - 0.05:
                add(
                    "wait_lineups",
                    f"Wait for confirmed lineups before trusting predictions{comp_suffix} "
                    f"(winrate {_pct(p.winrate)} vs baseline {_pct(p.baseline_winrate)}, n={p.sample_size}).",
                    "high" if p.confidence_level != "low" else "medium",
                    ["before_lineups"],
                )

        if p := by_id.get("final_lineups"):
            if p.winrate > p.baseline_winrate + 0.05:
                add(
                    "trust_lineups",
                    f"Trust predictions after final lineups are available{comp_suffix} "
                    f"(winrate {_pct(p.winrate)}, n={p.sample_size}).",
                    "high" if p.confidence_level != "low" else "medium",
                    ["final_lineups"],
                )

        if p := by_id.get("ou25_no_xg"):
            add(
                "reduce_ou_no_xg",
                f"Reduce O/U 2.5 confidence when xG data is unavailable{comp_suffix} "
                f"(winrate {_pct(p.winrate)}, n={p.sample_size}).",
                "high" if p.sample_size >= LOW_SAMPLE_THRESHOLD else "low",
                ["ou25_no_xg"],
            )

        if p := by_id.get("high_dq_1x2_odds_lineups"):
            if p.winrate >= 0.55:
                add(
                    "trust_1x2_strong",
                    f"Increase analytical trust in 1X2 when data quality > 70, odds, and lineups align{comp_suffix} "
                    f"(winrate {_pct(p.winrate)}, n={p.sample_size}).",
                    "high" if p.confidence_level == "high" else "medium",
                    ["high_dq_1x2_odds_lineups"],
                )

        if p := by_id.get("odds_disagreement"):
            drop = round((p.baseline_winrate - p.winrate) * 100)
            add(
                "caution_odds_disagreement",
                f"Treat predictions cautiously when odds disagreement is detected{comp_suffix} "
                f"(winrate drops ~{max(drop, 0)} pts to {_pct(p.winrate)}, n={p.sample_size}).",
                "medium",
                ["odds_disagreement"],
            )

        if p := by_id.get("low_dq_low_pq"):
            add(
                "skip_low_quality",
                f"Avoid strong conclusions when data quality < 50 and prediction quality < 45{comp_suffix} "
                f"(winrate {_pct(p.winrate)}, n={p.sample_size}).",
                "high",
                ["low_dq_low_pq"],
            )

        if p := by_id.get("ou25_with_xg"):
            if p.winrate > by_id.get("ou25_no_xg", p).winrate:
                add(
                    "prefer_ou_with_xg",
                    f"Prefer O/U analysis when xG enrichment is present{comp_suffix} "
                    f"(winrate {_pct(p.winrate)}, n={p.sample_size}).",
                    "medium",
                    ["ou25_with_xg"],
                )

        return advice


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"

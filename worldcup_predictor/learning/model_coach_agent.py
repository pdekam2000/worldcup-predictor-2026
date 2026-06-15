"""Learning agent that analyzes verification history and recommends model improvements."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from worldcup_predictor.accuracy.history_store import PredictionHistoryStore
from worldcup_predictor.accuracy.models import PredictionHistoryRecord
from worldcup_predictor.config.model_weights import (
    DEFAULT_FACTOR_WEIGHTS,
    MARKET_FACTOR_PRIORITIES,
    get_factor_weights,
    get_thresholds,
)
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.learning.models import APPLY_RECOMMENDATIONS_AFTER_USER_APPROVAL, ModelCoachReport
from worldcup_predictor.learning.report_writer import ModelCoachReportWriter
from worldcup_predictor.performance.grades import best_and_worst_market
from worldcup_predictor.results.match_results_store import MatchResultsStore
from worldcup_predictor.verification.store import VerificationStore
from worldcup_predictor.verification.models import VerificationMarketRecord

SMALL_SAMPLE_MATCH_THRESHOLD = 30
MIN_MARKET_ROWS = 3

MARKET_LABELS = {
    "1x2": "1X2",
    "over_under_2_5": "Over/Under 2.5",
    "halftime_bucket": "Halftime bucket",
    "scoreline_exact": "Exact scoreline",
    "first_goal_team": "First goal team",
    "first_goal_scorer": "First goal scorer",
}

FACTOR_PROXIES: dict[str, Callable[[PredictionHistoryRecord], bool]] = {
    "data_quality": lambda r: r.data_quality_score >= 50,
    "team_form": lambda r: r.data_quality_score >= 40,
    "lineup_strength": lambda r: r.lineups_available,
    "injuries_suspensions": lambda r: r.lineups_available and r.data_quality_score >= 55,
    "tactics_matchup": lambda r: r.data_quality_score >= 55,
    "player_quality": lambda r: r.data_quality_score >= 60 and r.source == "live",
    "odds_market_signal": lambda r: r.source == "live" and r.confidence_score >= 45,
    "motivation_psychology": lambda r: r.data_quality_score >= 45,
    "weather_referee_context": lambda r: r.data_quality_score >= 50 and r.source == "live",
    "xg_enrichment": lambda r: r.data_quality_score >= 60 and r.source == "live",
}


def _data_quality_level(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


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


def _winrate(correct: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(correct / total, 4)


@dataclass
class _JoinedRow:
    verification: VerificationMarketRecord
    prediction: PredictionHistoryRecord | None


class ModelCoachAgent:
    """Analyzes stored predictions vs results and recommends decision-engine improvements."""

    def __init__(
        self,
        *,
        history_store: PredictionHistoryStore | None = None,
        verification_store: VerificationStore | None = None,
        results_store: MatchResultsStore | None = None,
        report_writer: ModelCoachReportWriter | None = None,
        repository: FootballIntelligenceRepository | None = None,
    ) -> None:
        self._history = history_store or PredictionHistoryStore()
        self._verification = verification_store or VerificationStore()
        self._results = results_store or MatchResultsStore()
        self._writer = report_writer or ModelCoachReportWriter()
        self._repo = repository or FootballIntelligenceRepository()

    def run(
        self,
        *,
        competition_key: str | None = None,
        write_reports: bool = True,
    ) -> ModelCoachReport:
        rows = self._join_rows(competition_key=competition_key)
        report = self._analyze(rows)
        report.competition_key = competition_key
        report.competition_winrates = self._competition_winrates_from_db()
        report.apply_recommendations_after_user_approval = APPLY_RECOMMENDATIONS_AFTER_USER_APPROVAL
        if report.evaluated_matches < SMALL_SAMPLE_MATCH_THRESHOLD:
            report.sample_size_warning = (
                f"Sample size {report.evaluated_matches} matches is below {SMALL_SAMPLE_MATCH_THRESHOLD} "
                "— treat recommendations as exploratory."
            )
        report.generated_at_utc = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        if write_reports:
            self._writer.write(report)
            self._repo.save_coach_report(report.to_dict(), competition_key=competition_key)
        return report

    def run_all(self, *, write_reports: bool = True) -> list[ModelCoachReport]:
        from worldcup_predictor.config.competitions import list_competition_keys

        reports = [self.run(competition_key=None, write_reports=write_reports)]
        for key in list_competition_keys():
            reports.append(self.run(competition_key=key, write_reports=False))
        return reports

    def load_from_disk(self) -> ModelCoachReport | None:
        return self._writer.load_json()

    def _join_rows(self, *, competition_key: str | None = None) -> list[_JoinedRow]:
        db_rows = self._join_rows_from_db(competition_key)
        if db_rows:
            return db_rows
        predictions = {
            (r.fixture_id, r.prediction_id): r
            for r in self._history.load_all()
            if r.prediction_id
        }
        joined: list[_JoinedRow] = []
        for row in self._verification.latest_by_key().values():
            if row.result not in ("correct", "wrong"):
                continue
            key = (row.fixture_id, row.prediction_id)
            joined.append(_JoinedRow(verification=row, prediction=predictions.get(key)))
        return joined

    def _join_rows_from_db(self, competition_key: str | None) -> list[_JoinedRow]:
        try:
            query = """
                SELECT v.fixture_id, v.prediction_id, v.market, v.predicted, v.actual,
                       v.result, v.color, v.verified_at
                FROM verification_results v
                JOIN predictions p ON p.prediction_id = v.prediction_id
                WHERE v.result IN ('correct', 'wrong')
            """
            params: list[Any] = []
            if competition_key:
                query += " AND p.competition_key = ?"
                params.append(competition_key)
            rows = self._repo._conn.execute(query, params).fetchall()  # noqa: SLF001
        except Exception:
            return []

        if not rows:
            return []

        history_map = {
            (r.fixture_id, r.prediction_id): r
            for r in self._history.load_all()
            if r.prediction_id
        }
        joined: list[_JoinedRow] = []
        for row in rows:
            vrec = VerificationMarketRecord.from_dict(
                {
                    "fixture_id": row["fixture_id"],
                    "prediction_id": row["prediction_id"],
                    "market": row["market"],
                    "match_name": "",
                    "home_team": "",
                    "away_team": "",
                    "final_score": None,
                    "predicted": row["predicted"],
                    "actual": row["actual"],
                    "result": row["result"],
                    "color": row["color"],
                    "verified_at": row["verified_at"],
                }
            )
            pred = history_map.get((row["fixture_id"], row["prediction_id"]))
            joined.append(_JoinedRow(verification=vrec, prediction=pred))
        return joined

    def _competition_winrates_from_db(self) -> dict[str, dict[str, float | None]]:
        grouped: dict[str, dict[str, float | None]] = defaultdict(dict)
        for row in self._repo.performance_by_competition():
            grouped[row["competition_key"]][MARKET_LABELS.get(row["market"], row["market"])] = row["winrate"]
        return dict(grouped)

    def _analyze(self, rows: list[_JoinedRow]) -> ModelCoachReport:
        report = ModelCoachReport()
        if not rows:
            report.warnings_about_small_sample_size.append(
                "No verified market rows found. Run auto verification after matches finish."
            )
            report.suggested_focus_area = "Collect more finished-match predictions before coaching."
            report.decision_agent_advice.append(
                "Keep current default weights until at least a few finished matches are verified."
            )
            return report

        evaluated_matches = len({r.verification.fixture_id for r in rows})
        report.evaluated_matches = evaluated_matches
        report.total_market_rows = len(rows)

        if evaluated_matches < SMALL_SAMPLE_MATCH_THRESHOLD:
            report.warnings_about_small_sample_size.append(
                f"Only {evaluated_matches} evaluated match(es) — recommendations are preliminary "
                f"(minimum {SMALL_SAMPLE_MATCH_THRESHOLD} recommended for stable coaching)."
            )

        market_stats = self._market_winrates(rows)
        report.market_winrates = {MARKET_LABELS.get(k, k): v for k, v in market_stats.items()}
        report.mistakes_by_market = {
            MARKET_LABELS.get(k, k): v for k, v in self._mistakes_by_market(rows).items()
        }

        counts = self._market_counts(rows)
        league = [
            {
                "market": MARKET_LABELS.get(market, market),
                "accuracy": rate,
                "evaluated": counts.get(market, 0),
            }
            for market, rate in market_stats.items()
            if rate is not None
        ]
        strongest, weakest = best_and_worst_market(league)
        report.strongest_market = strongest
        report.weakest_market = weakest

        report.confidence_bucket_performance = self._confidence_buckets(rows)
        report.mistakes_by_data_quality_level = self._mistakes_by_data_quality(rows)
        report.mistakes_by_competition = self._mistakes_by_competition(rows)
        report.mistakes_by_prediction_version = self._mistakes_by_version(rows)
        report.factors_in_correct_predictions, report.factors_in_wrong_predictions = (
            self._factor_presence(rows)
        )

        self._load_supplemental_reports(report)
        self._build_recommendations(report, market_stats)
        return report

    def _market_counts(self, rows: list[_JoinedRow]) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for row in rows:
            counts[row.verification.market] += 1
        return counts

    def _market_winrates(self, rows: list[_JoinedRow]) -> dict[str, float | None]:
        totals: dict[str, int] = defaultdict(int)
        correct: dict[str, int] = defaultdict(int)
        for row in rows:
            market = row.verification.market
            totals[market] += 1
            if row.verification.result == "correct":
                correct[market] += 1
        return {market: _winrate(correct[market], totals[market]) for market in totals}

    def _mistakes_by_market(self, rows: list[_JoinedRow]) -> dict[str, int]:
        mistakes: dict[str, int] = defaultdict(int)
        for row in rows:
            if row.verification.result == "wrong":
                mistakes[row.verification.market] += 1
        return dict(mistakes)

    def _confidence_buckets(self, rows: list[_JoinedRow]) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, int | float]] = {}
        for row in rows:
            if row.prediction is None:
                continue
            label = _confidence_bucket(row.prediction.confidence_score)
            bucket = buckets.setdefault(label, {"label": label, "count": 0, "correct": 0})
            bucket["count"] = int(bucket["count"]) + 1
            if row.verification.result == "correct":
                bucket["correct"] = int(bucket["correct"]) + 1
        result = []
        for label in ("0-40", "40-60", "60-75", "75-90", "90-100"):
            bucket = buckets.get(label)
            if not bucket:
                continue
            count = int(bucket["count"])
            result.append(
                {
                    "label": label,
                    "count": count,
                    "winrate": _winrate(int(bucket["correct"]), count),
                }
            )
        return result

    def _mistakes_by_data_quality(self, rows: list[_JoinedRow]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "wrong": 0})
        for row in rows:
            if row.prediction is None:
                continue
            level = _data_quality_level(row.prediction.data_quality_score)
            grouped[level]["total"] += 1
            if row.verification.result == "wrong":
                grouped[level]["wrong"] += 1
        return {
            level: {
                "total": stats["total"],
                "wrong": stats["wrong"],
                "mistake_rate": round(stats["wrong"] / stats["total"], 4) if stats["total"] else None,
            }
            for level, stats in grouped.items()
        }

    def _mistakes_by_competition(self, rows: list[_JoinedRow]) -> dict[str, dict[str, Any]]:
        """Group by prediction source / results source as competition proxy."""
        results_by_fixture = self._results.by_fixture_id()
        grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "wrong": 0})
        for row in rows:
            source = "unknown"
            if row.prediction and row.prediction.source:
                source = row.prediction.source
            elif row.verification.fixture_id in results_by_fixture:
                source = results_by_fixture[row.verification.fixture_id].source
            grouped[source]["total"] += 1
            if row.verification.result == "wrong":
                grouped[source]["wrong"] += 1
        return {
            key: {
                "total": stats["total"],
                "wrong": stats["wrong"],
                "mistake_rate": round(stats["wrong"] / stats["total"], 4) if stats["total"] else None,
            }
            for key, stats in grouped.items()
        }

    def _mistakes_by_version(self, rows: list[_JoinedRow]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "wrong": 0})
        for row in rows:
            if row.prediction is None:
                continue
            version = row.prediction.prediction_version or "manual"
            grouped[version]["total"] += 1
            if row.verification.result == "wrong":
                grouped[version]["wrong"] += 1
        return {
            version: {
                "total": stats["total"],
                "wrong": stats["wrong"],
                "mistake_rate": round(stats["wrong"] / stats["total"], 4) if stats["total"] else None,
            }
            for version, stats in grouped.items()
        }

    def _factor_presence(self, rows: list[_JoinedRow]) -> tuple[dict[str, float], dict[str, float]]:
        correct_counts: dict[str, int] = defaultdict(int)
        wrong_counts: dict[str, int] = defaultdict(int)
        correct_total = 0
        wrong_total = 0

        for row in rows:
            if row.prediction is None:
                continue
            pred = row.prediction
            if row.verification.result == "correct":
                correct_total += 1
                for factor, probe in FACTOR_PROXIES.items():
                    if probe(pred):
                        correct_counts[factor] += 1
            elif row.verification.result == "wrong":
                wrong_total += 1
                for factor, probe in FACTOR_PROXIES.items():
                    if probe(pred):
                        wrong_counts[factor] += 1

        correct_rates = {
            factor: round(count / correct_total, 4)
            for factor, count in correct_counts.items()
            if correct_total > 0
        }
        wrong_rates = {
            factor: round(count / wrong_total, 4)
            for factor, count in wrong_counts.items()
            if wrong_total > 0
        }
        return correct_rates, wrong_rates

    def _load_supplemental_reports(self, report: ModelCoachReport) -> None:
        """Incorporate calibration / accuracy summaries when available."""
        calibration = _read_json(Path("reports/calibration/calibration_summary.json"))
        if calibration:
            sample = calibration.get("sample_size")
            if sample is not None and int(sample) < SMALL_SAMPLE_MATCH_THRESHOLD:
                report.warnings_about_small_sample_size.append(
                    f"Calibration backtest sample ({sample}) is below {SMALL_SAMPLE_MATCH_THRESHOLD} matches."
                )

        accuracy = _read_json(Path("reports/accuracy/accuracy_summary.json"))
        if accuracy and report.evaluated_matches < SMALL_SAMPLE_MATCH_THRESHOLD:
            metrics = accuracy.get("metrics", {})
            evaluated = metrics.get("total_evaluated")
            if evaluated is not None:
                report.warnings_about_small_sample_size.append(
                    f"Accuracy tracker has {evaluated} evaluated prediction(s) — treat coach advice as exploratory."
                )

    def _build_recommendations(
        self,
        report: ModelCoachReport,
        market_stats: dict[str, float | None],
    ) -> None:
        current_weights = get_factor_weights(use_calibrated=True)
        thresholds = get_thresholds(use_calibrated=True)
        adjustments: dict[str, str] = {}
        threshold_notes: dict[str, str] = {}
        market_rules: list[str] = []
        advice: list[str] = []

        ou_rate = market_stats.get("over_under_2_5")
        one_x_two_rate = market_stats.get("1x2")
        ht_rate = market_stats.get("halftime_bucket")
        scoreline_rate = market_stats.get("scoreline_exact")
        fg_rate = market_stats.get("first_goal_team")

        xg_in_wrong = report.factors_in_wrong_predictions.get("xg_enrichment", 0)
        xg_in_correct = report.factors_in_correct_predictions.get("xg_enrichment", 0)
        odds_in_correct = report.factors_in_correct_predictions.get("odds_market_signal", 0)
        lineup_in_wrong = report.factors_in_wrong_predictions.get("lineup_strength", 0)

        if ou_rate is not None and ou_rate < 0.45:
            adjustments["tactics_matchup"] = (
                "Recommend increase (+0.02 to +0.04) — O/U 2.5 winrate below 45%; "
                "lean on xG/tactics signals for totals."
            )
            adjustments["player_quality"] = (
                "Recommend increase (+0.02) — supplemental xG attack strength may improve totals modeling."
            )
            adjustments["team_form"] = (
                "Recommend decrease (-0.02) — simple form-goals weight may overfit when totals underperform."
            )
            market_rules.append("Require odds confirmation before surfacing O/U 2.5 picks when O/U winrate < 45%.")
            market_rules.append("Reduce O/U confidence when xG or supplemental stats are unavailable.")
            threshold_notes["over_under_confidence_minimum"] = (
                "Consider raising O/U confidence floor by 5 points until sample size grows."
            )
            advice.append(
                "Decision engine: cap Over/Under confidence when xG enrichment proxy is absent."
            )
        elif ou_rate is not None and ou_rate >= 0.55:
            adjustments["odds_market_signal"] = (
                "Hold current weight — O/U 2.5 performing adequately with market signals."
            )

        if one_x_two_rate is not None and one_x_two_rate >= 0.65:
            adjustments.setdefault(
                "team_form",
                "Hold or slight increase — 1X2 winrate above 65%; team strength/form weighting is working.",
            )
            adjustments.setdefault(
                "motivation_psychology",
                "Hold current weight — 1X2 outcomes align with motivation/form blend.",
            )
            market_rules.append("Use 1X2 as the primary strongest market in decision output.")
            advice.append("Decision engine: prioritize 1X2 narrative when confidence and data quality are aligned.")
        elif one_x_two_rate is not None and one_x_two_rate < 0.50:
            adjustments["odds_market_signal"] = (
                "Recommend increase (+0.02) — 1X2 winrate below 50%; add market confirmation."
            )
            adjustments["data_quality"] = (
                "Recommend increase (+0.01) — tighten picks when intelligence quality is low."
            )
            threshold_notes["analysis_ready_confidence_minimum"] = (
                "Consider raising analysis-ready minimum by 3–5 points while 1X2 winrate is weak."
            )
            advice.append("Decision engine: raise no-bet threshold for 1X2 when data quality is below 50%.")

        if ht_rate is not None and ht_rate < 0.45:
            adjustments["tactics_matchup"] = adjustments.get(
                "tactics_matchup",
                "Recommend increase (+0.02) — halftime bucket winrate weak; review first-half tempo signals.",
            )
            market_rules.append("Label halftime picks as moderate confidence when lineup data is missing.")

        if scoreline_rate is not None and scoreline_rate < 0.35:
            market_rules.append("Treat exact scoreline as secondary output — do not boost overall confidence from scoreline alone.")

        if fg_rate is not None and fg_rate < 0.40:
            market_rules.append("Suppress first-goal team confidence when event/scorer data was unavailable pre-match.")
            threshold_notes["missing_lineups_first_goal_cap"] = (
                f"Keep cap near {thresholds.get('missing_lineups_first_goal_cap', 30):.0f} "
                "when lineups/events are incomplete."
            )

        low_dq = report.mistakes_by_data_quality_level.get("low", {})
        if low_dq.get("mistake_rate") is not None and low_dq["mistake_rate"] > 0.55:
            adjustments["data_quality"] = (
                "Recommend increase (+0.03) — high mistake rate when data quality is low."
            )
            threshold_notes["data_quality_no_bet_threshold"] = (
                "Consider lowering no-bet trigger threshold to avoid weak-data picks."
            )
            advice.append("Decision engine: prefer watch-only mode when data quality score is below 50%.")

        if lineup_in_wrong > 0.5 and report.evaluated_matches >= 5:
            advice.append(
                "Wrong predictions often lacked official lineups — wait for lineup-final versions when possible."
            )

        if xg_in_wrong > xg_in_correct + 0.15:
            advice.append(
                "xG enrichment proxy appears more often in wrong O/U/totals contexts — verify supplemental API coverage."
            )
        elif xg_in_correct > xg_in_wrong + 0.10:
            advice.append("xG enrichment proxy correlates with correct picks — keep supplemental stats enabled.")

        if odds_in_correct > 0.6:
            advice.append("Odds market signal present in many correct picks — keep odds confirmation in conflict checks.")

        for version, stats in report.mistakes_by_prediction_version.items():
            rate = stats.get("mistake_rate")
            if rate is not None and rate > 0.55 and stats.get("total", 0) >= 3:
                advice.append(
                    f"Prediction version '{version}' shows elevated mistake rate — prefer later refresh versions when available."
                )

        if not adjustments:
            for factor, weight in sorted(current_weights.items(), key=lambda x: -x[1])[:3]:
                adjustments[factor] = f"Hold at {weight:.2f} — insufficient evidence for change yet."

        if not market_rules:
            market_rules.append("Continue monitoring all markets; no urgent rule changes suggested.")

        if not advice:
            advice.append(
                "Maintain current decision-engine thresholds until more finished matches are verified."
            )

        focus_parts: list[str] = []
        if report.weakest_market:
            focus_parts.append(f"Improve {report.weakest_market}")
        if ou_rate is not None and ou_rate < 0.45:
            focus_parts.append("O/U totals modeling")
        if report.evaluated_matches < SMALL_SAMPLE_MATCH_THRESHOLD:
            focus_parts.append("expand verified sample")
        report.suggested_focus_area = " · ".join(focus_parts) if focus_parts else "Maintain balanced monitoring"

        report.recommended_weight_adjustments = adjustments
        report.recommended_confidence_thresholds = threshold_notes
        report.recommended_market_rules = market_rules
        report.decision_agent_advice = advice

        market_recs: dict[str, list[str]] = {}
        if ou_rate is not None and ou_rate < 0.45:
            market_recs["Over/Under 2.5"] = [
                "Increase xG/tactics weight for totals.",
                "Require odds confirmation before O/U output.",
                "Reduce O/U confidence when supplemental xG unavailable.",
            ]
        if one_x_two_rate is not None and one_x_two_rate >= 0.65:
            market_recs.setdefault("1X2", []).append("Keep current team strength/form weighting — strongest market.")
        report.market_specific_recommendations = market_recs

        comp_recs: dict[str, list[str]] = {}
        for comp, stats in report.mistakes_by_competition.items():
            rate = stats.get("mistake_rate")
            if rate is not None and rate > 0.5:
                comp_recs[comp] = [f"Mistake rate {rate:.0%} — review data ingestion for this source/competition."]
        report.competition_specific_recommendations = comp_recs

        selection_rules: list[str] = []
        if ou_rate is not None and ou_rate < 0.45:
            selection_rules.append("League mode: do not auto-predict O/U-heavy fixtures without odds + xG snapshots.")
        selection_rules.append("World Cup mode: broader coverage allowed when data_readiness >= 45%.")
        selection_rules.append("European leagues: use Daily Shortlist top 5–10 AUTO_PREDICT matches only.")
        report.recommended_selection_rules = selection_rules

        priorities = MARKET_FACTOR_PRIORITIES
        if report.strongest_market and "1X2" in (report.strongest_market or ""):
            top = priorities.get("1x2", [])[:2]
            advice.append(f"Strong 1X2: continue emphasizing {', '.join(top)} in factor trace.")
        if report.weakest_market and "Over/Under" in (report.weakest_market or ""):
            top = priorities.get("over_under", [])[:2]
            advice.append(f"Weak O/U: review {', '.join(top)} contributions in audit pipeline.")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

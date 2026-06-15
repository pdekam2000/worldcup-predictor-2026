"""Compare stored predictions with finished match results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from worldcup_predictor.accuracy.evaluator import (
    _first_goal_team_from_scorers,
    _normalize_scoreline,
    actual_1x2,
    actual_over_under,
    evaluate_prediction,
    is_finished_fixture,
)
from worldcup_predictor.accuracy.history_store import PredictionHistoryStore
from worldcup_predictor.accuracy.models import PredictionHistoryRecord
from worldcup_predictor.backtesting.historical_loader import HistoricalMatchRow
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.performance.grades import compute_model_grade
from worldcup_predictor.results.match_results_store import MatchResultsStore
from worldcup_predictor.verification.models import (
    MatchVerificationSummary,
    VerificationMarketRecord,
    VerificationSummaryMetrics,
)
from worldcup_predictor.verification.report_writer import VerificationReportWriter
from worldcup_predictor.verification.store import VerificationStore


def _first_goal_scorer_from_events(goal_scorers: list[str]) -> str | None:
    if not goal_scorers:
        return None
    first = goal_scorers[0]
    if "'" in first:
        rest = first.split("'", 1)[-1].strip()
        if "(" in rest:
            return rest.split("(")[0].strip() or None
        return rest or None
    return None


def _market_row(
    *,
    record: PredictionHistoryRecord,
    fixture: TournamentFixture,
    market: str,
    predicted: str,
    actual: str,
    correct: bool | None,
    verified_at: str,
) -> VerificationMarketRecord:
    if correct is None:
        result: str = "unavailable"
        color: str = "gray"
    elif correct:
        result = "correct"
        color = "green"
    else:
        result = "wrong"
        color = "red"
    score = None
    if fixture.home_goals is not None and fixture.away_goals is not None:
        score = f"{fixture.home_goals}-{fixture.away_goals}"
    return VerificationMarketRecord(
        fixture_id=record.fixture_id,
        prediction_id=record.prediction_id,
        market=market,
        match_name=f"{record.home_team} vs {record.away_team}",
        home_team=record.home_team,
        away_team=record.away_team,
        final_score=score,
        predicted=predicted,
        actual=actual,
        result=result,  # type: ignore[arg-type]
        color=color,  # type: ignore[arg-type]
        verified_at=verified_at,
        prediction_created_at=record.created_at,
    )


def verify_prediction_record(
    record: PredictionHistoryRecord,
    fixture: TournamentFixture,
    *,
    verified_at: datetime | None = None,
) -> MatchVerificationSummary | None:
    if not is_finished_fixture(fixture):
        return None
    if fixture.home_goals is None or fixture.away_goals is None:
        return None

    stamp = (verified_at or datetime.now(timezone.utc).replace(tzinfo=None)).isoformat()
    home = fixture.home_goals
    away = fixture.away_goals
    evaluated = evaluate_prediction(record, fixture, evaluated_at=verified_at)

    markets: list[VerificationMarketRecord] = []
    if evaluated:
        markets.append(
            _market_row(
                record=record,
                fixture=fixture,
                market="1x2",
                predicted=record.predicted_1x2.replace("_", " "),
                actual=evaluated.actual_1x2.replace("_", " "),
                correct=evaluated.one_x_two_correct,
                verified_at=stamp,
            )
        )
        markets.append(
            _market_row(
                record=record,
                fixture=fixture,
                market="over_under_2_5",
                predicted=record.predicted_over_under_2_5.replace("_", " "),
                actual=evaluated.actual_over_under.replace("_", " "),
                correct=evaluated.over_under_correct,
                verified_at=stamp,
            )
        )
        pred_ht = HistoricalMatchRow.halftime_bucket(record.predicted_halftime_goals)
        pred_ht_label = f"{record.predicted_halftime_goals:.2f} expected / bucket {pred_ht}"
        if evaluated.halftime_evaluated:
            actual_ht = evaluated.actual_halftime_bucket or "—"
            actual_ht_label = f"{actual_ht} goal(s)"
            ht_correct = evaluated.halftime_bucket_correct
        else:
            actual_ht_label = "unavailable"
            ht_correct = None
        markets.append(
            _market_row(
                record=record,
                fixture=fixture,
                market="halftime_bucket",
                predicted=pred_ht_label,
                actual=actual_ht_label,
                correct=ht_correct,
                verified_at=stamp,
            )
        )
        if record.predicted_scoreline:
            markets.append(
                _market_row(
                    record=record,
                    fixture=fixture,
                    market="scoreline_exact",
                    predicted=_normalize_scoreline(record.predicted_scoreline) or record.predicted_scoreline,
                    actual=evaluated.actual_scoreline or f"{home}-{away}",
                    correct=evaluated.scoreline_exact_correct,
                    verified_at=stamp,
                )
            )
        if record.predicted_first_goal_team:
            if evaluated.first_goal_evaluated:
                markets.append(
                    _market_row(
                        record=record,
                        fixture=fixture,
                        market="first_goal_team",
                        predicted=record.predicted_first_goal_team,
                        actual=evaluated.actual_first_goal_team or "—",
                        correct=evaluated.first_goal_correct,
                        verified_at=stamp,
                    )
                )
            else:
                markets.append(
                    _market_row(
                        record=record,
                        fixture=fixture,
                        market="first_goal_team",
                        predicted=record.predicted_first_goal_team,
                        actual="unavailable",
                        correct=None,
                        verified_at=stamp,
                    )
                )

        scorer_pred = getattr(record, "predicted_first_goal_scorer", None)
        if scorer_pred:
            actual_scorer = _first_goal_scorer_from_events(fixture.goal_scorers)
            if actual_scorer:
                markets.append(
                    _market_row(
                        record=record,
                        fixture=fixture,
                        market="first_goal_scorer",
                        predicted=scorer_pred,
                        actual=actual_scorer,
                        correct=scorer_pred.lower() == actual_scorer.lower(),
                        verified_at=stamp,
                    )
                )
            else:
                markets.append(
                    _market_row(
                        record=record,
                        fixture=fixture,
                        market="first_goal_scorer",
                        predicted=scorer_pred,
                        actual="unavailable",
                        correct=None,
                        verified_at=stamp,
                    )
                )

    return MatchVerificationSummary(
        fixture_id=record.fixture_id,
        prediction_id=record.prediction_id,
        match_name=f"{record.home_team} vs {record.away_team}",
        final_score=f"{home}-{away}",
        home_team=record.home_team,
        away_team=record.away_team,
        markets=markets,
    )


def compute_verification_metrics(
    rows: list[VerificationMarketRecord],
    *,
    predictions_checked: int,
    evaluated_matches: int,
    pending_matches: int,
) -> VerificationSummaryMetrics:
    def _winrate(market: str) -> float | None:
        items = [r for r in rows if r.market == market and r.result != "unavailable"]
        if not items:
            return None
        hits = sum(1 for r in items if r.result == "correct")
        return round(hits / len(items), 4)

    metrics = VerificationSummaryMetrics(
        total_predictions_checked=predictions_checked,
        evaluated_matches=evaluated_matches,
        pending_matches=pending_matches,
        total_market_rows=len(rows),
        one_x_two_winrate=_winrate("1x2"),
        over_under_winrate=_winrate("over_under_2_5"),
        halftime_bucket_winrate=_winrate("halftime_bucket"),
        scoreline_winrate=_winrate("scoreline_exact"),
        first_goal_team_winrate=_winrate("first_goal_team"),
        first_goal_scorer_winrate=_winrate("first_goal_scorer"),
        model_grade=compute_model_grade(_winrate("1x2")),
    )
    market_rates = [
        ("1X2", metrics.one_x_two_winrate),
        ("Over/Under 2.5", metrics.over_under_winrate),
        ("Halftime bucket", metrics.halftime_bucket_winrate),
        ("Exact scoreline", metrics.scoreline_winrate),
        ("First goal team", metrics.first_goal_team_winrate),
    ]
    eligible = [(name, rate) for name, rate in market_rates if rate is not None]
    if eligible:
        metrics.strongest_market = max(eligible, key=lambda x: x[1])[0]
        metrics.weakest_market = min(eligible, key=lambda x: x[1])[0]
    return metrics


@dataclass
class VerificationRunResult:
    saved_rows: int = 0
    summaries: list[MatchVerificationSummary] = field(default_factory=list)
    metrics: VerificationSummaryMetrics = field(default_factory=VerificationSummaryMetrics)
    recent_correct: list[VerificationMarketRecord] = field(default_factory=list)
    recent_wrong: list[VerificationMarketRecord] = field(default_factory=list)


class AutoVerificationAgent:
    """Automatically verify stored predictions against finished fixtures."""

    def __init__(
        self,
        *,
        history_store: PredictionHistoryStore | None = None,
        verification_store: VerificationStore | None = None,
        results_store: MatchResultsStore | None = None,
        report_writer: VerificationReportWriter | None = None,
    ) -> None:
        self._history = history_store or PredictionHistoryStore()
        self._store = verification_store or VerificationStore()
        self._results = results_store or MatchResultsStore()
        self._writer = report_writer or VerificationReportWriter()

    def run(
        self,
        fixtures: list[TournamentFixture],
        *,
        all_predictions: bool = True,
    ) -> VerificationRunResult:
        fixture_map = {f.fixture_id: f for f in fixtures if is_finished_fixture(f)}
        if all_predictions:
            records = self._history.load_all()
        else:
            records = list(self._history.latest_by_fixture().values())

        summaries: list[MatchVerificationSummary] = []
        new_rows: list[VerificationMarketRecord] = []
        checked_ids: set[str] = set()

        for record in records:
            fixture = fixture_map.get(record.fixture_id)
            if fixture is None:
                continue
            checked_ids.add(record.prediction_id)
            summary = verify_prediction_record(record, fixture)
            if summary is None:
                continue
            summaries.append(summary)
            new_rows.extend(summary.markets)

        saved = self._store.upsert_many(new_rows)
        all_rows = list(self._store.latest_by_key().values())
        finished_fixture_ids = {f.fixture_id for f in fixture_map.values()}
        pending = len({r.fixture_id for r in self._history.latest_by_fixture().values() if r.fixture_id not in finished_fixture_ids})

        metrics = compute_verification_metrics(
            all_rows,
            predictions_checked=len(checked_ids),
            evaluated_matches=len({s.fixture_id for s in summaries}),
            pending_matches=pending,
        )
        recent_correct = [r for r in all_rows if r.result == "correct"][-20:]
        recent_wrong = [r for r in all_rows if r.result == "wrong"][-20:]
        self._writer.write(all_rows, metrics, summaries)

        return VerificationRunResult(
            saved_rows=saved,
            summaries=summaries,
            metrics=metrics,
            recent_correct=recent_correct,
            recent_wrong=recent_wrong,
        )

    def match_summaries(self) -> list[dict]:
        return self._store.match_summaries()

    def today_stats(self) -> dict[str, Any]:
        today = date.today().isoformat()
        rows = self._store.latest_by_key().values()
        today_rows = [r for r in rows if r.verified_at.startswith(today)]
        correct = sum(1 for r in today_rows if r.result == "correct")
        wrong = sum(1 for r in today_rows if r.result == "wrong")
        preds = len({(r.fixture_id, r.prediction_id) for r in today_rows})
        metrics = compute_verification_metrics(
            list(rows),
            predictions_checked=len({r.prediction_id for r in rows}),
            evaluated_matches=len({r.fixture_id for r in rows}),
            pending_matches=0,
        )
        return {
            "verified_predictions_today": preds,
            "correct_markets_today": correct,
            "wrong_markets_today": wrong,
            "strongest_market": metrics.strongest_market,
            "weakest_market": metrics.weakest_market,
            "model_grade": metrics.model_grade,
            "metrics": metrics,
        }

    def load_summary_from_disk(self) -> VerificationRunResult | None:
        payload = self._writer.load_json()
        if payload is None:
            return None
        metrics_dict = payload.get("metrics", {})
        metrics = VerificationSummaryMetrics(
            total_predictions_checked=int(metrics_dict.get("total_predictions_checked", 0)),
            evaluated_matches=int(metrics_dict.get("evaluated_matches", 0)),
            pending_matches=int(metrics_dict.get("pending_matches", 0)),
            total_market_rows=int(metrics_dict.get("total_market_rows", 0)),
            one_x_two_winrate=metrics_dict.get("one_x_two_winrate"),
            over_under_winrate=metrics_dict.get("over_under_winrate"),
            halftime_bucket_winrate=metrics_dict.get("halftime_bucket_winrate"),
            scoreline_winrate=metrics_dict.get("scoreline_winrate"),
            first_goal_team_winrate=metrics_dict.get("first_goal_team_winrate"),
            first_goal_scorer_winrate=metrics_dict.get("first_goal_scorer_winrate"),
            model_grade=str(metrics_dict.get("model_grade", "—")),
            strongest_market=metrics_dict.get("strongest_market"),
            weakest_market=metrics_dict.get("weakest_market"),
        )
        rows = self._store.load_all()
        summaries_raw = payload.get("match_summaries", [])
        summaries = []
        for item in summaries_raw:
            markets = [VerificationMarketRecord.from_dict(m) for m in item.get("markets", [])]
            if markets:
                summaries.append(
                    MatchVerificationSummary(
                        fixture_id=int(item["fixture_id"]),
                        prediction_id=str(item["prediction_id"]),
                        match_name=str(item["match_name"]),
                        final_score=str(item.get("final_score", "—")),
                        home_team=markets[0].home_team,
                        away_team=markets[0].away_team,
                        markets=markets,
                    )
                )
        return VerificationRunResult(
            saved_rows=0,
            summaries=summaries,
            metrics=metrics,
            recent_correct=[VerificationMarketRecord.from_dict(m) for m in payload.get("recent_correct", [])],
            recent_wrong=[VerificationMarketRecord.from_dict(m) for m in payload.get("recent_wrong", [])],
        )
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worldcup_predictor.backtesting.metrics import BacktestMetrics


@dataclass
class MatchBacktestResult:
    fixture_id: int
    match_name: str
    date: str
    competition: str
    predicted_1x2: str
    actual_1x2: str
    one_x_two_correct: bool
    predicted_over_under: str
    actual_over_under: str
    over_under_correct: bool
    predicted_halftime_bucket: str | None
    actual_halftime_bucket: str | None
    halftime_bucket_correct: bool | None
    halftime_evaluated: bool
    confidence_score: float
    no_bet_flag: bool
    first_goal_skipped: bool = True
    specialists_ran: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class BacktestRunResult:
    match_results: list[MatchBacktestResult]
    metrics: BacktestMetrics
    csv_path: str
    is_demo_data: bool
    source_label: str

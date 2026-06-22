"""Leakage-safe historical backtest runner (Phase 51F — DB-only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.egie.guards import backtest_mode
from worldcup_predictor.goal_timing.config import BACKTEST_DEFAULT_LOOKBACK_DAYS


class GoalTimingBacktestRunner:
    def __init__(self, *, lookback_days: int = BACKTEST_DEFAULT_LOOKBACK_DAYS) -> None:
        self.lookback_days = lookback_days

    def default_window(self) -> tuple[datetime, datetime]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.lookback_days)
        return start, end

    def run(self, *, competition_key: str = "premier_league") -> dict[str, Any]:
        start, end = self.default_window()
        with backtest_mode():
            return {
                "status": "not_started",
                "phase": "51F",
                "competition_key": competition_key,
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "data_policy": "db_only_no_external_api",
                "message": (
                    "Backtest pipeline is DB-only (SQLite + EGIE PostgreSQL). "
                    "Run EGIE ingest before historical backtest."
                ),
                "metrics": {},
            }

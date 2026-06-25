"""Admin autonomous performance certification service — Phase 61."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.autonomous.store import AutonomousStore
from worldcup_predictor.config.settings import get_settings


class AutonomousPerformanceService:
    def __init__(self) -> None:
        self.store = AutonomousStore()

    def certification_summary(self) -> dict[str, Any]:
        latest = self.store.latest_certification_report()
        report = (latest or {}).get("report") or {}
        latest_evals = self._latest_evaluated(limit=20)
        return {
            "overall": report.get("overall") or {},
            "engines": report.get("engines") or {},
            "markets": report.get("markets") or {},
            "rolling": report.get("rolling") or {},
            "certification_levels": report.get("certification_levels") or {},
            "latest_evaluated": latest_evals,
            "generated_at": report.get("generated_at"),
            "disclaimer": "Admin performance metrics. Elite remains experimental until certified.",
        }

    def _latest_evaluated(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.store._conn.execute(  # noqa: SLF001
            """
            SELECT e.*, s.home_team, s.away_team, s.kickoff_utc, s.competition_key
            FROM autonomous_snapshot_evaluations e
            JOIN autonomous_prediction_snapshots s ON s.id = e.snapshot_id
            WHERE e.status IN ('correct', 'wrong')
            ORDER BY e.evaluated_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

"""Part G — Result sync and evaluation for daily owner cycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.automation.worldcup_background.result_evaluation_job import run_evaluate_worldcup_results
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS, PHASE
from worldcup_predictor.research.ecse_live.evaluator import run_ecse_evaluations
from worldcup_predictor.research.ecse_live.result_sync import (
    SUPPORTED_ECSE_COMPETITIONS,
    sync_ecse_snapshot_results,
)


@dataclass
class DailyResultSyncOutcome:
    phase: str = PHASE
    result_synced: int = 0
    wde_evaluated: int = 0
    ecse_evaluated: int = 0
    errors: list[str] = field(default_factory=list)
    by_competition: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "result_synced": self.result_synced,
            "wde_evaluated": self.wde_evaluated,
            "ecse_evaluated": self.ecse_evaluated,
            "errors": self.errors,
            "by_competition": self.by_competition,
        }


def run_daily_result_sync_and_evaluation(
    *,
    competition_keys: list[str] | None = None,
    settings: Settings | None = None,
    dry_run: bool = False,
    force: bool = False,
    fixture_ids: list[int] | None = None,
) -> DailyResultSyncOutcome:
    settings = settings or get_settings()
    keys = list(competition_keys or DAILY_SUPPORTED_COMPETITIONS)
    outcome = DailyResultSyncOutcome()

    for key in keys:
        if key not in SUPPORTED_ECSE_COMPETITIONS and key != "premier_league" and key != "bundesliga":
            if key not in SUPPORTED_ECSE_COMPETITIONS:
                pass
        comp_stats = {"synced": 0, "wde_eval": 0, "ecse_eval": 0}
        try:
            if key in SUPPORTED_ECSE_COMPETITIONS:
                sync_out = sync_ecse_snapshot_results(
                    settings=settings,
                    competition_key=key,
                    fixture_ids=fixture_ids,
                    past_only=True,
                    dry_run=dry_run,
                    force=force,
                    run_ecse_backfill=False,
                )
                outcome.result_synced += sync_out.synced
                comp_stats["synced"] = sync_out.synced
        except Exception as exc:
            outcome.errors.append(f"{key}: result_sync: {exc}")

        if not dry_run:
            try:
                wde_out = run_evaluate_worldcup_results(
                    settings=settings,
                    competition_key=key,
                    limit=500,
                    skip_unchanged=True,
                )
                outcome.wde_evaluated += wde_out.evaluated
                comp_stats["wde_eval"] = wde_out.evaluated
            except Exception as exc:
                outcome.errors.append(f"{key}: wde_eval: {exc}")

        outcome.by_competition[key] = comp_stats

    if not dry_run:
        try:
            from worldcup_predictor.database.connection import connect

            conn = connect(settings.sqlite_path)
            ecse_out = run_ecse_evaluations(conn, settings=settings, limit=500)
            outcome.ecse_evaluated = ecse_out.evaluated
        except Exception as exc:
            outcome.errors.append(f"ecse_eval: {exc}")

    return outcome

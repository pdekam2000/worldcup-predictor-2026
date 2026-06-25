"""Orchestrate Phase API-F provider backfill (mapping → backfill → rebuild hooks)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.backfill.api_football_provider_backfill import run_api_football_pl_backfill
from worldcup_predictor.egie.backfill.fixture_mapping_audit import audit_pl_fixture_mapping
from worldcup_predictor.egie.backfill.sportmonks_provider_backfill import run_sportmonks_pl_backfill
from worldcup_predictor.egie.provider_features.audit import audit_egie_paid_provider_utilization
from worldcup_predictor.egie.survival.dataset_builder import SurvivalDatasetBuilder


@dataclass
class ProviderBackfillResult:
    mapping_audit: dict[str, Any] = field(default_factory=dict)
    sportmonks: dict[str, Any] = field(default_factory=dict)
    api_football: dict[str, Any] = field(default_factory=dict)
    utilization_before: dict[str, Any] | None = None
    utilization_after: dict[str, Any] | None = None
    survival_dataset_path: str | None = None
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "mapping_audit": self.mapping_audit,
            "sportmonks": self.sportmonks,
            "api_football": self.api_football,
            "utilization_before": self.utilization_before,
            "utilization_after": self.utilization_after,
            "survival_dataset_path": self.survival_dataset_path,
        }


class ProviderBackfillOrchestrator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(
        self,
        *,
        providers: tuple[str, ...] = ("sportmonks", "api_football"),
        limit_fixtures: int | None = 380,
        max_api_calls: int = 80,
        fixture_ids: list[int] | None = None,
        skip_backfill: bool = False,
        rebuild_survival: bool = True,
        audit_utilization: bool = True,
    ) -> ProviderBackfillResult:
        result = ProviderBackfillResult(started_at=datetime.now(timezone.utc).isoformat())

        if audit_utilization:
            result.utilization_before = audit_egie_paid_provider_utilization(
                competition_key="premier_league",
                limit=limit_fixtures or 400,
            )

        result.mapping_audit = audit_pl_fixture_mapping(
            settings=self.settings,
            limit=limit_fixtures,
        )

        if not skip_backfill:
            sm_budget = max_api_calls // 2 if "api_football" in providers else max_api_calls
            af_budget = max_api_calls - sm_budget if "sportmonks" in providers else max_api_calls

            if "sportmonks" in providers:
                result.sportmonks = run_sportmonks_pl_backfill(
                    fixture_ids=fixture_ids,
                    limit_fixtures=limit_fixtures,
                    max_api_calls=sm_budget,
                    settings=self.settings,
                )
            if "api_football" in providers:
                result.api_football = run_api_football_pl_backfill(
                    fixture_ids=fixture_ids,
                    limit_fixtures=limit_fixtures,
                    max_api_calls=af_budget,
                    settings=self.settings,
                )

        if rebuild_survival:
            builder = SurvivalDatasetBuilder(settings=self.settings)
            path = builder.build_and_save(competition_keys=["premier_league"], limit=limit_fixtures)
            result.survival_dataset_path = str(path)

        if audit_utilization:
            result.utilization_after = audit_egie_paid_provider_utilization(
                competition_key="premier_league",
                limit=limit_fixtures or 400,
            )

        result.finished_at = datetime.now(timezone.utc).isoformat()
        return result

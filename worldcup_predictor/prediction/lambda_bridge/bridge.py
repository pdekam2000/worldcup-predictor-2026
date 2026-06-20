"""SpecialistLambdaBridge — shadow-only λ adjustments (Phase 12B)."""

from __future__ import annotations

import logging

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.prediction.lambda_bridge.config import CONFIG_VERSION, FULL_AGENTS, LIMITED_AGENTS
from worldcup_predictor.prediction.lambda_bridge.models import (
    LambdaBridgeMode,
    LambdaBridgeResult,
    SpecialistLambdaContribution,
)
from worldcup_predictor.prediction.lambda_bridge.normalizers import collect_raw_contributions
from worldcup_predictor.prediction.lambda_bridge.safety import build_result

logger = logging.getLogger(__name__)


class SpecialistLambdaBridge:
    """Compute bounded shadow λ adjustments from specialist signals."""

    def __init__(self, *, config_version: str = CONFIG_VERSION) -> None:
        self._config_version = config_version

    def active_agents_for_mode(self, mode: LambdaBridgeMode) -> frozenset[str]:
        if mode == "off":
            return frozenset()
        if mode == "limited":
            return LIMITED_AGENTS
        return FULL_AGENTS

    def compute(
        self,
        *,
        report: MatchIntelligenceReport,
        specialist_report: MatchSpecialistReport | None,
        lambda_base_home: float,
        lambda_base_away: float,
        mode: LambdaBridgeMode,
        active_agents_override: frozenset[str] | None = None,
    ) -> LambdaBridgeResult:
        if mode == "off":
            return LambdaBridgeResult.fallback(lambda_base_home, lambda_base_away, mode=mode)

        dq_pct = 0.0
        if report.data_quality:
            dq_pct = float(report.data_quality.breakdown_total or report.data_quality.score * 100)

        try:
            active = (
                active_agents_override
                if active_agents_override is not None
                else self.active_agents_for_mode(mode)
            )
            raw_rows = collect_raw_contributions(specialist_report, active_agents=active)
            contributions = [
                SpecialistLambdaContribution(
                    agent_name=agent,
                    delta_home=dh,
                    delta_away=da,
                    included=included,
                    exclusion_reason=reason,
                    note=note or None,
                )
                for agent, dh, da, note, included, reason in raw_rows
            ]
            result = build_result(
                lambda_base_home=lambda_base_home,
                lambda_base_away=lambda_base_away,
                contributions=contributions,
                data_quality_pct=dq_pct,
                mode=mode,
                config_version=self._config_version,
            )
            self._log_summary(report.fixture_id, result)
            return result
        except Exception as exc:
            logger.exception("lambda_bridge failed fixture=%s", report.fixture_id)
            return LambdaBridgeResult.fallback(
                lambda_base_home,
                lambda_base_away,
                mode=mode,
                error=str(exc),
            )

    def _log_summary(self, fixture_id: int, result: LambdaBridgeResult) -> None:
        parts = []
        for c in result.contributions:
            if c.included and (abs(c.delta_home) > 0.001 or abs(c.delta_away) > 0.001):
                parts.append(
                    f"{c.agent_name}: dh={c.delta_home:+.3f} da={c.delta_away:+.3f}"
                )
        logger.info(
            "lambda_bridge fixture=%s mode=%s base=%.2f/%.2f adj=%.2f/%.2f cap=%s dq_scale=%.2f %s",
            fixture_id,
            result.mode,
            result.lambda_base_home,
            result.lambda_base_away,
            result.lambda_adjusted_home,
            result.lambda_adjusted_away,
            result.global_cap_applied,
            result.data_quality_scale,
            "; ".join(parts) if parts else "no_deltas",
        )

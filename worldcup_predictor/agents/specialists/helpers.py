from __future__ import annotations

from typing import TYPE_CHECKING, Any

from worldcup_predictor.agents.base import AgentContext
from worldcup_predictor.domain.specialist import SignalStatus, SpecialistSignal

if TYPE_CHECKING:
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport


def require_intelligence(
    context: AgentContext,
    fixture_id: int | None = None,
) -> MatchIntelligenceReport | None:
    reports: dict[int, MatchIntelligenceReport] = context.shared.get("intelligence_reports") or {}
    if fixture_id is not None:
        return reports.get(int(fixture_id))
    if len(reports) == 1:
        return next(iter(reports.values()))
    return None


def make_signal(
    agent_name: str,
    domain: str,
    status: SignalStatus,
    signals: dict[str, Any],
    *,
    warnings: list[str] | None = None,
    missing_data: list[str] | None = None,
    impact_score: float | None = None,
    notes: str | None = None,
) -> SpecialistSignal:
    return SpecialistSignal(
        agent_name=agent_name,
        domain=domain,
        status=status,
        signals=signals,
        warnings=warnings or [],
        missing_data=missing_data or [],
        impact_score=impact_score,
        notes=notes,
    )

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SignalStatus = Literal["available", "partial", "unavailable", "placeholder"]


@dataclass
class SpecialistSignal:
    """Structured output from a single specialist agent."""

    agent_name: str
    domain: str
    status: SignalStatus
    signals: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)
    impact_score: float | None = None
    notes: str | None = None

    @property
    def is_usable(self) -> bool:
        return self.status in ("available", "partial", "placeholder")


@dataclass
class MatchSpecialistReport:
    """Aggregated specialist signals for one fixture."""

    fixture_id: int
    signals: dict[str, SpecialistSignal] = field(default_factory=dict)
    master: SpecialistSignal | None = None
    source: Literal["live", "cache", "placeholder"] = "placeholder"

    @property
    def aggregated_signal_score(self) -> float | None:
        if self.master and self.master.impact_score is not None:
            return self.master.impact_score
        scores = [s.impact_score for s in self.signals.values() if s.impact_score is not None]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 1)

    def signal(self, agent_name: str) -> SpecialistSignal | None:
        return self.signals.get(agent_name)

    def statuses_summary(self) -> dict[str, str]:
        return {name: sig.status for name, sig in self.signals.items()}

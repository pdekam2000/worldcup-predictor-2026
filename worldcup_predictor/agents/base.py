from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.config.settings import Settings


@dataclass
class AgentContext:
    """Shared runtime context passed between agents in a pipeline."""

    settings: Settings
    competition_key: str = "world_cup_2026"
    locale: str = "en"
    shared: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Standard agent output envelope."""

    agent_name: str
    success: bool
    data: Any = None
    message: str = ""
    errors: list[str] = field(default_factory=list)


class BaseAgent(ABC):
    """Base class for all prediction pipeline agents."""

    name: str = "base"

    def __init__(self, context: AgentContext) -> None:
        self.context = context

    @abstractmethod
    def run(self, **kwargs: Any) -> AgentResult:
        """Execute the agent's primary task."""

    def _ok(self, data: Any = None, message: str = "") -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            success=True,
            data=data,
            message=message,
        )

    def _fail(self, message: str, errors: list[str] | None = None) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            success=False,
            message=message,
            errors=errors or [message],
        )

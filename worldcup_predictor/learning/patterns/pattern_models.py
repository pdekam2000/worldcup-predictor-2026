"""Pattern discovery dataclasses — advisory learning output only."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PatternKind = Literal["failure", "success"]
ConfidenceLevel = Literal["low", "medium", "high"]
AdvicePriority = Literal["high", "medium", "low"]

PATTERN_DISCLAIMER = (
    "Pattern discovery is analytical only. Recommendations do not change weights, "
    "thresholds, or ML models. Historical patterns do not guarantee future results."
)


@dataclass
class DiscoveredPattern:
    pattern_id: str
    label: str
    kind: PatternKind
    conditions: list[str]
    market: str | None
    competition_key: str | None
    sample_size: int
    winrate: float
    baseline_winrate: float
    statistical_strength: float
    confidence_level: ConfidenceLevel
    correct_count: int
    wrong_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveredPattern:
        return cls(
            pattern_id=str(data.get("pattern_id") or ""),
            label=str(data.get("label") or ""),
            kind=data.get("kind") or "failure",  # type: ignore[arg-type]
            conditions=list(data.get("conditions") or []),
            market=data.get("market"),
            competition_key=data.get("competition_key"),
            sample_size=int(data.get("sample_size") or 0),
            winrate=float(data.get("winrate") or 0),
            baseline_winrate=float(data.get("baseline_winrate") or 0),
            statistical_strength=float(data.get("statistical_strength") or 0),
            confidence_level=data.get("confidence_level") or "low",  # type: ignore[arg-type]
            correct_count=int(data.get("correct_count") or 0),
            wrong_count=int(data.get("wrong_count") or 0),
        )


@dataclass
class DecisionAgentAdvice:
    advice_id: str
    message: str
    priority: AdvicePriority
    supporting_pattern_ids: list[str] = field(default_factory=list)
    competition_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionAgentAdvice:
        return cls(
            advice_id=str(data.get("advice_id") or ""),
            message=str(data.get("message") or ""),
            priority=data.get("priority") or "medium",  # type: ignore[arg-type]
            supporting_pattern_ids=list(data.get("supporting_pattern_ids") or []),
            competition_key=data.get("competition_key"),
        )


@dataclass
class PatternDiscoveryReport:
    strongest_patterns: list[DiscoveredPattern] = field(default_factory=list)
    weakest_patterns: list[DiscoveredPattern] = field(default_factory=list)
    failure_causes: list[DiscoveredPattern] = field(default_factory=list)
    success_causes: list[DiscoveredPattern] = field(default_factory=list)
    decision_agent_advice: list[DecisionAgentAdvice] = field(default_factory=list)
    competition_patterns: dict[str, list[DiscoveredPattern]] = field(default_factory=dict)
    baseline_winrate: float = 0.0
    total_rows: int = 0
    competition_key: str | None = None
    generated_at_utc: str = ""
    disclaimer: str = PATTERN_DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return {
            "strongest_patterns": [p.to_dict() for p in self.strongest_patterns],
            "weakest_patterns": [p.to_dict() for p in self.weakest_patterns],
            "failure_causes": [p.to_dict() for p in self.failure_causes],
            "success_causes": [p.to_dict() for p in self.success_causes],
            "decision_agent_advice": [a.to_dict() for a in self.decision_agent_advice],
            "competition_patterns": {
                k: [p.to_dict() for p in v] for k, v in self.competition_patterns.items()
            },
            "baseline_winrate": self.baseline_winrate,
            "total_rows": self.total_rows,
            "competition_key": self.competition_key,
            "generated_at_utc": self.generated_at_utc,
            "disclaimer": self.disclaimer,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatternDiscoveryReport:
        return cls(
            strongest_patterns=[
                DiscoveredPattern.from_dict(p) for p in data.get("strongest_patterns") or []
            ],
            weakest_patterns=[
                DiscoveredPattern.from_dict(p) for p in data.get("weakest_patterns") or []
            ],
            failure_causes=[
                DiscoveredPattern.from_dict(p) for p in data.get("failure_causes") or []
            ],
            success_causes=[
                DiscoveredPattern.from_dict(p) for p in data.get("success_causes") or []
            ],
            decision_agent_advice=[
                DecisionAgentAdvice.from_dict(a) for a in data.get("decision_agent_advice") or []
            ],
            competition_patterns={
                k: [DiscoveredPattern.from_dict(p) for p in v]
                for k, v in (data.get("competition_patterns") or {}).items()
            },
            baseline_winrate=float(data.get("baseline_winrate") or 0),
            total_rows=int(data.get("total_rows") or 0),
            competition_key=data.get("competition_key"),
            generated_at_utc=str(data.get("generated_at_utc") or ""),
            disclaimer=str(data.get("disclaimer") or PATTERN_DISCLAIMER),
        )

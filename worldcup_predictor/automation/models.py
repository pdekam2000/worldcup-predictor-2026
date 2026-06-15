"""Pre-match automation models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

AutomationActionType = Literal["created", "skipped", "refreshed", "error"]


@dataclass
class AutomationLogEntry:
    fixture_id: int
    match_name: str
    action: AutomationActionType
    prediction_version: str | None
    message: str
    prediction_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PreMatchWindowCounts:
    within_24h: int = 0
    within_6h: int = 0
    within_90m: int = 0


@dataclass
class PreMatchAutomationResult:
    scan_mode: str
    window_hours: float | None
    lineup_final: bool
    matches_scanned: int
    predictions_created: int = 0
    predictions_skipped: int = 0
    predictions_refreshed: int = 0
    errors: int = 0
    window_counts: PreMatchWindowCounts = field(default_factory=PreMatchWindowCounts)
    log: list[AutomationLogEntry] = field(default_factory=list)
    disclaimer: str = (
        "Automated pre-match analysis only — not betting instruction. "
        "Preliminary predictions remain flagged when lineups are missing."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_mode": self.scan_mode,
            "window_hours": self.window_hours,
            "lineup_final": self.lineup_final,
            "matches_scanned": self.matches_scanned,
            "predictions_created": self.predictions_created,
            "predictions_skipped": self.predictions_skipped,
            "predictions_refreshed": self.predictions_refreshed,
            "errors": self.errors,
            "window_counts": asdict(self.window_counts),
            "log": [entry.to_dict() for entry in self.log],
            "disclaimer": self.disclaimer,
        }

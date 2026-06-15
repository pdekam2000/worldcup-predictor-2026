"""Structured models for Phase 47 — Professional Match Report Export V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ExportFormat = Literal["markdown", "json", "summary"]
ExportLocale = Literal["en", "de", "fa"]


@dataclass
class MatchReportBundle:
    fixture_id: int
    locale: ExportLocale
    match_name: str
    kickoff_utc: str | None
    stage: str | None
    prediction: dict[str, Any]
    explainability: dict[str, Any]
    fusion: dict[str, Any]
    intelligence_v2: dict[str, Any] = field(default_factory=dict)
    disclaimer: str = ""
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExportResult:
    fixture_id: int
    locale: ExportLocale
    markdown_path: str | None = None
    json_path: str | None = None
    summary_path: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def paths(self) -> list[str]:
        return [p for p in (self.markdown_path, self.json_path, self.summary_path) if p]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

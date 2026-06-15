from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ReportSource = Literal["openai", "local_rules"]


@dataclass
class ProfessionalMatchReport:
    """Narrative analytical report — explanation layer only; does not alter model outputs."""

    fixture_id: int
    match_name: str
    locale: str
    executive_summary: str
    key_factors: list[str] = field(default_factory=list)
    tactical_context: str = ""
    risk_notes: list[str] = field(default_factory=list)
    data_limitations: list[str] = field(default_factory=list)
    market_analysis_information_only: str = ""
    final_analytical_view: str = ""
    disclaimer: str = ""
    prediction_summary: dict[str, Any] = field(default_factory=dict)
    audit_highlights: list[str] = field(default_factory=list)
    safety_warnings: list[str] = field(default_factory=list)
    source: ReportSource = "local_rules"
    watch_only: bool = False
    generated_at_utc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "match_name": self.match_name,
            "locale": self.locale,
            "executive_summary": self.executive_summary,
            "key_factors": self.key_factors,
            "tactical_context": self.tactical_context,
            "risk_notes": self.risk_notes,
            "data_limitations": self.data_limitations,
            "market_analysis_information_only": self.market_analysis_information_only,
            "final_analytical_view": self.final_analytical_view,
            "disclaimer": self.disclaimer,
            "prediction_summary": self.prediction_summary,
            "audit_highlights": self.audit_highlights,
            "safety_warnings": self.safety_warnings,
            "source": self.source,
            "watch_only": self.watch_only,
            "generated_at_utc": self.generated_at_utc,
        }

    def copy_friendly_text(self) -> str:
        """Plain-text block suitable for clipboard export."""
        lines = [
            f"WorldCup Predictor Pro 2026 — Professional Match Report",
            f"Match: {self.match_name} (fixture {self.fixture_id})",
            f"Locale: {self.locale} | Source: {self.source}",
            "",
            "EXECUTIVE SUMMARY",
            self.executive_summary,
            "",
            "KEY FACTORS",
        ]
        lines.extend(f"  • {item}" for item in self.key_factors)
        lines.extend(["", "TACTICAL CONTEXT", self.tactical_context, "",            "RISK NOTES",
        ])
        lines.extend(f"  • {item}" for item in self.risk_notes)
        lines.extend(["", "DATA LIMITATIONS"])
        lines.extend(f"  • {item}" for item in self.data_limitations)
        lines.extend(
            [
                "",
                "MARKET ANALYSIS (INFORMATIONAL ONLY)",
                self.market_analysis_information_only,
                "",
                "FINAL ANALYTICAL VIEW",
                self.final_analytical_view,
                "",
                "PREDICTION SUMMARY (FROZEN — NOT MODIFIED)",
            ]
        )
        for key, value in self.prediction_summary.items():
            lines.append(f"  {key}: {value}")
        if self.audit_highlights:
            lines.extend(["", "AUDIT HIGHLIGHTS"])
            lines.extend(f"  • {item}" for item in self.audit_highlights)
        if self.safety_warnings:
            lines.extend(["", "SAFETY WARNINGS"])
            lines.extend(f"  • {item}" for item in self.safety_warnings)
        lines.extend(["", "DISCLAIMER", self.disclaimer])
        return "\n".join(lines)

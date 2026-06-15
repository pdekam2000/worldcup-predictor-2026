"""Write pattern discovery reports to disk."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.learning.patterns.pattern_models import PatternDiscoveryReport


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _confidence_badge(level: str) -> str:
    return {"low": "🔴 Low", "medium": "🟡 Medium", "high": "🟢 High"}.get(level, level)


class PatternDiscoveryReportWriter:
    def __init__(self, output_dir: Path | str = "reports/learning") -> None:
        self._output_dir = Path(output_dir)

    @property
    def json_path(self) -> Path:
        return self._output_dir / "pattern_discovery.json"

    @property
    def md_path(self) -> Path:
        return self._output_dir / "pattern_discovery.md"

    def load_json(self) -> PatternDiscoveryReport | None:
        if not self.json_path.exists():
            return None
        try:
            payload = json.loads(self.json_path.read_text(encoding="utf-8"))
            return PatternDiscoveryReport.from_dict(payload)
        except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
            return None

    def write(self, report: PatternDiscoveryReport) -> tuple[Path, Path]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        if not report.generated_at_utc:
            report.generated_at_utc = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        self.json_path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.md_path.write_text(self._build_markdown(report), encoding="utf-8")
        return self.json_path, self.md_path

    def _build_markdown(self, report: PatternDiscoveryReport) -> str:
        lines = [
            "# Pattern Discovery Report",
            "",
            f"Generated (UTC): {report.generated_at_utc}",
            "",
            "## Disclaimer",
            "",
            report.disclaimer,
            "",
            "## Overview",
            "",
            f"- Total verified rows: **{report.total_rows}**",
            f"- Baseline winrate: **{_pct(report.baseline_winrate)}**",
            f"- Scope: **{report.competition_key or 'all competitions'}**",
            "",
        ]

        lines.extend(self._pattern_section("Strongest patterns", report.strongest_patterns))
        lines.extend(self._pattern_section("Weakest patterns", report.weakest_patterns))
        lines.extend(self._pattern_section("Failure causes", report.failure_causes))
        lines.extend(self._pattern_section("Success causes", report.success_causes))

        if report.decision_agent_advice:
            lines.extend(["## Decision agent advice", ""])
            for item in report.decision_agent_advice:
                lines.append(f"- **[{item.priority.upper()}]** {item.message}")
            lines.append("")

        if report.competition_patterns:
            lines.extend(["## Competition-specific patterns", ""])
            for comp, patterns in sorted(report.competition_patterns.items()):
                lines.append(f"### {comp}")
                for p in patterns[:5]:
                    lines.append(
                        f"- {p.label}: {_pct(p.winrate)} (n={p.sample_size}, "
                        f"confidence: {_confidence_badge(p.confidence_level)})"
                    )
                lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _pattern_section(title: str, patterns: list) -> list[str]:
        if not patterns:
            return []
        lines = [f"## {title}", ""]
        for p in patterns:
            cond = "; ".join(p.conditions)
            lines.append(
                f"- **{p.label}** — winrate {_pct(p.winrate)} "
                f"(baseline {_pct(p.baseline_winrate)}, n={p.sample_size}, "
                f"confidence: {_confidence_badge(p.confidence_level)})"
            )
            lines.append(f"  - Conditions: {cond}")
        lines.append("")
        return lines

"""Write model coach learning reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.learning.models import ModelCoachReport


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


class ModelCoachReportWriter:
    def __init__(self, output_dir: Path | str = "reports/learning") -> None:
        self._output_dir = Path(output_dir)

    @property
    def json_path(self) -> Path:
        return self._output_dir / "model_coach_report.json"

    @property
    def md_path(self) -> Path:
        return self._output_dir / "model_coach_report.md"

    def load_json(self) -> ModelCoachReport | None:
        if not self.json_path.exists():
            return None
        try:
            payload = json.loads(self.json_path.read_text(encoding="utf-8"))
            return ModelCoachReport.from_dict(payload)
        except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
            return None

    def write(self, report: ModelCoachReport) -> tuple[Path, Path]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        if not report.generated_at_utc:
            report.generated_at_utc = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        self.json_path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.md_path.write_text(self._build_markdown(report), encoding="utf-8")
        return self.json_path, self.md_path

    def _build_markdown(self, report: ModelCoachReport) -> str:
        lines = [
            "# Model Coach Report",
            "",
            f"Generated (UTC): {report.generated_at_utc}",
            "",
            "## Disclaimer",
            "",
            report.disclaimer,
            "",
            "## Overview",
            "",
            f"- Evaluated matches: **{report.evaluated_matches}**",
            f"- Market rows analyzed: **{report.total_market_rows}**",
            f"- Strongest market: **{report.strongest_market or 'n/a'}**",
            f"- Weakest market: **{report.weakest_market or 'n/a'}**",
            f"- Suggested focus: **{report.suggested_focus_area or 'n/a'}**",
            "",
        ]

        if report.warnings_about_small_sample_size:
            lines.extend(["## Sample size warnings", ""])
            for warning in report.warnings_about_small_sample_size:
                lines.append(f"- ⚠ {warning}")
            lines.append("")

        lines.extend(["## Market winrates", ""])
        for market, rate in report.market_winrates.items():
            lines.append(f"- {market}: {_pct(rate)}")
        lines.append("")

        if report.confidence_bucket_performance:
            lines.extend(["## Confidence bucket performance", ""])
            for bucket in report.confidence_bucket_performance:
                lines.append(
                    f"- **{bucket.get('label', 'n/a')}** ({bucket.get('count', 0)} rows): "
                    f"winrate {_pct(bucket.get('winrate'))}"
                )
            lines.append("")

        if report.mistakes_by_market:
            lines.extend(["## Mistakes by market", ""])
            for market, count in sorted(report.mistakes_by_market.items(), key=lambda x: -x[1]):
                lines.append(f"- {market}: {count} wrong")
            lines.append("")

        if report.factors_in_correct_predictions or report.factors_in_wrong_predictions:
            lines.extend(["## Factor presence (proxy signals)", ""])
            lines.append("### More common in correct predictions")
            for factor, rate in sorted(
                report.factors_in_correct_predictions.items(), key=lambda x: -x[1]
            ):
                lines.append(f"- {factor}: {rate * 100:.0f}% presence")
            lines.append("")
            lines.append("### More common in wrong predictions")
            for factor, rate in sorted(
                report.factors_in_wrong_predictions.items(), key=lambda x: -x[1]
            ):
                lines.append(f"- {factor}: {rate * 100:.0f}% presence")
            lines.append("")

        if report.recommended_weight_adjustments:
            lines.extend(["## Recommended weight adjustments", ""])
            lines.append("*Recommendations only — not applied automatically.*")
            lines.append("")
            for factor, note in report.recommended_weight_adjustments.items():
                lines.append(f"- **{factor}**: {note}")
            lines.append("")

        if report.recommended_confidence_thresholds:
            lines.extend(["## Recommended confidence thresholds", ""])
            for key, note in report.recommended_confidence_thresholds.items():
                lines.append(f"- **{key}**: {note}")
            lines.append("")

        if report.recommended_market_rules:
            lines.extend(["## Recommended market rules", ""])
            for rule in report.recommended_market_rules:
                lines.append(f"- {rule}")
            lines.append("")

        if report.decision_agent_advice:
            lines.extend(["## Decision agent advice", ""])
            for advice in report.decision_agent_advice:
                lines.append(f"- {advice}")
            lines.append("")

        return "\n".join(lines)

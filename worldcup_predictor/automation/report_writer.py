from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.automation.models import PreMatchAutomationResult


class PreMatchAutomationReportWriter:
    """Write JSON and Markdown pre-match automation reports."""

    def __init__(self, output_dir: Path | str = "reports/automation") -> None:
        self._output_dir = Path(output_dir)

    def write(self, result: PreMatchAutomationResult) -> tuple[Path, Path]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self._output_dir / "prematch_automation_summary.json"
        md_path = self._output_dir / "prematch_automation_summary.md"

        payload = {
            "generated_at_utc": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            **result.to_dict(),
        }
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(self._build_markdown(result), encoding="utf-8")
        return json_path, md_path

    def _build_markdown(self, result: PreMatchAutomationResult) -> str:
        lines = [
            "# WorldCup Predictor Pro 2026 — Pre-Match Automation Summary",
            "",
            f"Generated (UTC): {datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}",
            f"Scan mode: **{result.scan_mode}**",
        ]
        if result.window_hours is not None:
            lines.append(f"Window: **{result.window_hours}h**")
        if result.lineup_final:
            lines.append("Mode: **Final lineup refresh**")

        lines.extend(
            [
                "",
                "## Disclaimer",
                "",
                result.disclaimer,
                "Historical automation output is for model evaluation only — not profit or betting advice.",
                "",
                "## Scan Overview",
                "",
                f"- Matches scanned: **{result.matches_scanned}**",
                f"- Predictions created: **{result.predictions_created}**",
                f"- Predictions skipped: **{result.predictions_skipped}**",
                f"- Predictions refreshed: **{result.predictions_refreshed}**",
                f"- Errors: **{result.errors}**",
                "",
                "### Upcoming window counts",
                "",
                f"- Within 24h: **{result.window_counts.within_24h}**",
                f"- Within 6h: **{result.window_counts.within_6h}**",
                f"- Within 90m: **{result.window_counts.within_90m}**",
                "",
                "## Automation Log",
                "",
            ]
        )

        for entry in result.log[:40]:
            version = entry.prediction_version or "—"
            lines.append(
                f"- [{entry.action.upper()}] **{entry.match_name}** (fixture {entry.fixture_id}) "
                f"· version `{version}` — {entry.message}"
            )
        if len(result.log) > 40:
            lines.append(f"- … and {len(result.log) - 40} more entries (see JSON).")

        lines.append("")
        return "\n".join(lines)

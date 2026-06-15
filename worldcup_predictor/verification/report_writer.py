from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.verification.models import (
    MatchVerificationSummary,
    VerificationMarketRecord,
    VerificationSummaryMetrics,
)


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


class VerificationReportWriter:
    def __init__(self, output_dir: Path | str = "reports/verification") -> None:
        self._output_dir = Path(output_dir)

    @property
    def json_path(self) -> Path:
        return self._output_dir / "verification_summary.json"

    def load_json(self) -> dict | None:
        if not self.json_path.exists():
            return None
        try:
            return json.loads(self.json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def write(
        self,
        rows: list[VerificationMarketRecord],
        metrics: VerificationSummaryMetrics,
        summaries: list[MatchVerificationSummary],
    ) -> tuple[Path, Path]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        md_path = self._output_dir / "verification_summary.md"
        generated = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

        payload = {
            "generated_at_utc": generated,
            "metrics": metrics.to_dict(),
            "recent_correct": [r.to_dict() for r in rows if r.result == "correct"][-25:],
            "recent_wrong": [r.to_dict() for r in rows if r.result == "wrong"][-25:],
            "match_summaries": [s.to_dict() for s in summaries[:50]],
        }
        self.json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(self._build_markdown(metrics, rows, summaries, generated), encoding="utf-8")
        return self.json_path, md_path

    def _build_markdown(
        self,
        metrics: VerificationSummaryMetrics,
        rows: list[VerificationMarketRecord],
        summaries: list[MatchVerificationSummary],
        generated: str,
    ) -> str:
        lines = [
            "# Prediction Verification Summary",
            "",
            f"Generated (UTC): {generated}",
            "",
            "## Disclaimer",
            "",
            metrics.disclaimer,
            "",
            "## Overview",
            "",
            f"- Total predictions checked: **{metrics.total_predictions_checked}**",
            f"- Evaluated matches: **{metrics.evaluated_matches}**",
            f"- Pending matches: **{metrics.pending_matches}**",
            f"- Model grade (1X2): **{metrics.model_grade}**",
            "",
            "## Market winrates",
            "",
            f"- 1X2: {_pct(metrics.one_x_two_winrate)}",
            f"- Over/Under 2.5: {_pct(metrics.over_under_winrate)}",
            f"- Halftime bucket: {_pct(metrics.halftime_bucket_winrate)}",
            f"- Exact scoreline: {_pct(metrics.scoreline_winrate)}",
            f"- First goal team: {_pct(metrics.first_goal_team_winrate)}",
            "",
            "## Recent correct / wrong",
            "",
        ]
        for row in [r for r in rows if r.result == "correct"][-10:]:
            lines.append(f"- ✅ {row.match_name} · {row.market}: {row.predicted} → {row.actual}")
        for row in [r for r in rows if r.result == "wrong"][-10:]:
            lines.append(f"- ❌ {row.match_name} · {row.market}: {row.predicted} → {row.actual}")
        lines.append("")
        lines.append("## Per-match verification")
        lines.append("")
        for summary in summaries[:15]:
            lines.append(f"### {summary.match_name} ({summary.final_score})")
            for market in summary.markets:
                icon = "✅" if market.result == "correct" else "❌" if market.result == "wrong" else "⚪"
                lines.append(
                    f"- {icon} **{market.market}**: predicted `{market.predicted}` · actual `{market.actual}`"
                )
            lines.append("")
        return "\n".join(lines)

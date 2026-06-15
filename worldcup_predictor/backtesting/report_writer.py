from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.backtesting.models import BacktestRunResult, MatchBacktestResult
from worldcup_predictor.backtesting.metrics import BacktestMetrics


class BacktestReportWriter:
    """Write JSON and Markdown backtest evaluation reports."""

    def __init__(
        self,
        output_dir: Path | str = "reports/backtests",
    ) -> None:
        self._output_dir = Path(output_dir)

    def write(self, result: BacktestRunResult) -> tuple[Path, Path]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self._output_dir / "backtest_summary.json"
        md_path = self._output_dir / "backtest_summary.md"

        payload = self._build_json_payload(result)
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(self._build_markdown(result), encoding="utf-8")
        return json_path, md_path

    def _build_json_payload(self, result: BacktestRunResult) -> dict:
        return {
            "generated_at_utc": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "csv_path": result.csv_path,
            "source": result.source_label,
            "is_demo_data": result.is_demo_data,
            "metrics": result.metrics.to_dict(),
            "matches": [self._match_to_dict(match) for match in result.match_results],
        }

    @staticmethod
    def _match_to_dict(match: MatchBacktestResult) -> dict:
        data = asdict(match)
        return data

    def _build_markdown(self, result: BacktestRunResult) -> str:
        metrics = result.metrics
        lines = [
            "# WorldCup Predictor Pro 2026 — Backtest Summary",
            "",
            f"Generated (UTC): {datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}",
            f"CSV: `{result.csv_path}`",
            f"Source: **{result.source_label}**",
        ]
        if result.is_demo_data:
            lines.append("")
            lines.append("> **Demo data** — illustrative sample only, not official historical feed.")

        lines.extend(
            [
                "",
                "## Disclaimer",
                "",
                "Historical backtest performance **does not guarantee** future results.",
                "This report is for **model evaluation and calibration only** — not betting advice.",
                "",
                "## Overview",
                "",
                f"- Total matches: **{metrics.total_matches}**",
                f"- Average confidence: **{metrics.average_confidence:.1f}**",
                f"- No-bet count: **{metrics.no_bet_count}** ({_pct(metrics.no_bet_rate)})",
                f"- Specialists ran: **{metrics.specialists_ran_count}** / {metrics.total_matches}",
                "",
                "## Market Accuracy",
                "",
                f"- **1X2 accuracy:** {_pct(metrics.one_x_two_accuracy)}",
                f"- **Over/Under 2.5 accuracy:** {_pct(metrics.over_under_2_5_accuracy)}",
                f"- **Halftime bucket accuracy:** {_pct(metrics.halftime_bucket_accuracy)} "
                f"({metrics.halftime_evaluated_count} evaluated)",
                f"- **High-confidence (≥75) 1X2 accuracy:** {_pct(metrics.high_confidence_accuracy)} "
                f"({metrics.high_confidence_count} matches)",
                "",
                f"**Strongest market:** {metrics.strongest_market or 'n/a'}",
                f"**Weakest market:** {metrics.weakest_market or 'n/a'}",
                "",
                "## Confidence Calibration Buckets",
                "",
                "| Bucket | Count | 1X2 Acc | O/U Acc | Avg Confidence |",
                "|--------|-------|---------|---------|----------------|",
            ]
        )

        for bucket in metrics.confidence_buckets:
            if bucket.count == 0:
                continue
            lines.append(
                f"| {bucket.label} | {bucket.count} | {_pct(bucket.one_x_two_accuracy)} | "
                f"{_pct(bucket.over_under_accuracy)} | {bucket.average_confidence:.1f} |"
            )

        lines.extend(["", "## Data Limitations", ""])
        for item in metrics.data_limitations:
            lines.append(f"- {item}")

        lines.extend(["", "## Weight Tuning Recommendations", ""])
        for item in metrics.weight_recommendations:
            lines.append(f"- {item}")

        if metrics.first_goal_skipped_count:
            lines.extend(
                [
                    "",
                    "## Skipped Evaluations",
                    "",
                    f"- First-goal fields skipped on **{metrics.first_goal_skipped_count}** matches "
                    "(no first-goal columns in CSV).",
                ]
            )

        lines.extend(["", "## Match Detail (sample)", ""])
        for match in result.match_results[:8]:
            ht = ""
            if match.halftime_evaluated:
                ht = (
                    f" | HT bucket pred `{match.predicted_halftime_bucket}` "
                    f"actual `{match.actual_halftime_bucket}` "
                    f"{'✓' if match.halftime_bucket_correct else '✗'}"
                )
            lines.append(
                f"- **{match.match_name}** ({match.date}): "
                f"1X2 `{match.predicted_1x2}` vs `{match.actual_1x2}` "
                f"{'✓' if match.one_x_two_correct else '✗'}; "
                f"O/U `{match.predicted_over_under}` vs `{match.actual_over_under}` "
                f"{'✓' if match.over_under_correct else '✗'}"
                f"{ht}; conf {match.confidence_score:.0f}"
            )

        if len(result.match_results) > 8:
            lines.append(f"- … and {len(result.match_results) - 8} more (see JSON).")

        lines.append("")
        return "\n".join(lines)


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"

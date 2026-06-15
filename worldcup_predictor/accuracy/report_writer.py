from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.accuracy.metrics import compute_accuracy_metrics
from worldcup_predictor.accuracy.models import AccuracySummaryMetrics, EvaluatedPrediction


class AccuracyReportWriter:
    """Write JSON and Markdown model evaluation reports."""

    def __init__(self, output_dir: Path | str = "reports/accuracy") -> None:
        self._output_dir = Path(output_dir)

    def write(
        self,
        evaluated: list[EvaluatedPrediction],
        *,
        pending_predictions: int = 0,
    ) -> tuple[Path, Path, AccuracySummaryMetrics]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        metrics = compute_accuracy_metrics(evaluated, pending_predictions=pending_predictions)
        json_path = self._output_dir / "accuracy_summary.json"
        md_path = self._output_dir / "accuracy_summary.md"

        payload = {
            "generated_at_utc": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "metrics": metrics.to_dict(),
            "evaluated_predictions": [item.to_dict() for item in evaluated],
        }
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(self._build_markdown(metrics, evaluated), encoding="utf-8")
        return json_path, md_path, metrics

    def _build_markdown(
        self,
        metrics: AccuracySummaryMetrics,
        evaluated: list[EvaluatedPrediction],
    ) -> str:
        lines = [
            "# WorldCup Predictor Pro 2026 — Model Evaluation Accuracy",
            "",
            f"Generated (UTC): {datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}",
            "",
            "## Disclaimer",
            "",
            "Historical model evaluation **does not guarantee** future results.",
            "This report is for **model calibration and learning memory only** — not profit or betting advice.",
            "",
            "## Overview",
            "",
            f"- Total evaluated predictions: **{metrics.total_evaluated}**",
            f"- Pending stored predictions (not yet finished): **{metrics.pending_predictions}**",
            f"- Average confidence: **{metrics.average_confidence:.1f}**",
            f"- No-bet flagged predictions: **{metrics.no_bet_count}**",
            "",
            "## Market Accuracy",
            "",
            f"- **1X2 accuracy:** {_pct(metrics.one_x_two_accuracy)}",
            f"- **Over/Under 2.5 accuracy:** {_pct(metrics.over_under_2_5_accuracy)}",
            f"- **Halftime bucket accuracy:** {_pct(metrics.halftime_bucket_accuracy)} "
            f"({metrics.halftime_evaluated_count} evaluated)",
            "",
            "## No-Bet Separation (1X2 / O/U)",
            "",
            f"- No-bet 1X2: {_pct(metrics.no_bet_one_x_two_accuracy)}",
            f"- Non-no-bet 1X2: {_pct(metrics.non_no_bet_one_x_two_accuracy)}",
            f"- No-bet O/U 2.5: {_pct(metrics.no_bet_over_under_accuracy)}",
            f"- Non-no-bet O/U 2.5: {_pct(metrics.non_no_bet_over_under_accuracy)}",
            "",
            "## Confidence Calibration Buckets",
            "",
            f"- **Best confidence range (1X2):** {metrics.best_confidence_range or 'n/a'}",
            f"- **Weakest confidence range (1X2):** {metrics.worst_confidence_range or 'n/a'}",
            "",
            "| Bucket | Count | 1X2 Acc | O/U Acc | Avg Confidence |",
            "|--------|-------|---------|---------|----------------|",
        ]

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

        lines.extend(["", "## Recent Evaluations", ""])
        for item in evaluated[:12]:
            ht = ""
            if item.halftime_evaluated:
                ht = (
                    f" | HT `{item.predicted_halftime_bucket}` vs `{item.actual_halftime_bucket}` "
                    f"{'✓' if item.halftime_bucket_correct else '✗'}"
                )
            lines.append(
                f"- **{item.match_name}** ({item.final_score}): "
                f"1X2 `{item.predicted_1x2}` vs `{item.actual_1x2}` "
                f"{'✓' if item.one_x_two_correct else '✗'}; "
                f"O/U `{item.predicted_over_under}` vs `{item.actual_over_under}` "
                f"{'✓' if item.over_under_correct else '✗'}"
                f"{ht}; conf {item.confidence_score:.0f}"
            )

        if len(evaluated) > 12:
            lines.append(f"- … and {len(evaluated) - 12} more (see JSON).")

        lines.append("")
        return "\n".join(lines)


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"

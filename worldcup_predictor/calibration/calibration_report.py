from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.calibration.models import CalibrationResult, MarketPerformance
from worldcup_predictor.calibration.threshold_tuner import ThresholdTuner
from worldcup_predictor.calibration.weight_tuner import WeightTuner
from worldcup_predictor.config.model_weights import (
    apply_calibrated,
    get_factor_weights,
    get_thresholds,
)
from worldcup_predictor.config.settings import Settings, get_settings

SMALL_SAMPLE_THRESHOLD = 100


class CalibrationRunner:
    """Orchestrate weight + threshold tuning and persist calibration reports."""

    def __init__(self, settings: Settings | None = None, *, locale: str = "en") -> None:
        self._settings = settings or get_settings()
        self._locale = locale

    def run(self, csv_path: Path | str, *, apply: bool = True) -> CalibrationResult:
        path = Path(csv_path)
        from worldcup_predictor.backtesting.historical_loader import HistoricalLoader

        rows = HistoricalLoader(path).load(create_sample_if_missing=True)
        sample_size = len(rows)
        is_demo = any(r.is_demo for r in rows) or _file_is_demo(path)

        current_weights = get_factor_weights(use_calibrated=False)
        current_thresholds = get_thresholds(use_calibrated=False)

        from worldcup_predictor.calibration.evaluator import CalibrationEvaluator

        evaluator = CalibrationEvaluator(path, self._settings, locale=self._locale)

        weight_tuner = WeightTuner(self._settings, locale=self._locale)
        weight_result = weight_tuner.tune(path, evaluator=evaluator)

        threshold_tuner = ThresholdTuner(self._settings, locale=self._locale)
        threshold_result = threshold_tuner.tune(
            path,
            factor_weights=weight_result.best_weights_overall,
            evaluator=evaluator,
        )

        recommended_weights = weight_result.best_weights_overall
        recommended_thresholds = threshold_result.recommended_thresholds

        market_comparison = _build_market_comparison(weight_result, threshold_result)
        overfitting_warnings = list(weight_result.warnings) + list(threshold_result.warnings)
        sample_warning = None
        if sample_size < SMALL_SAMPLE_THRESHOLD:
            sample_warning = (
                f"Sample size {sample_size} is below {SMALL_SAMPLE_THRESHOLD}. "
                "Calibration is exploratory only — do not overtrust results."
            )

        disclaimers = [
            "Calibrated weights and thresholds do not guarantee future World Cup 2026 results.",
            "Calibration is for model evaluation and improvement only — not betting advice.",
            "Overfitting risk is elevated on small historical samples.",
        ]

        result = CalibrationResult(
            csv_path=str(path),
            sample_size=sample_size,
            is_demo_data=is_demo,
            current_weights=current_weights,
            recommended_weights=recommended_weights,
            current_thresholds=current_thresholds,
            recommended_thresholds=recommended_thresholds,
            weight_tuning=weight_result,
            threshold_tuning=threshold_result,
            market_comparison=market_comparison,
            sample_size_warning=sample_warning,
            overfitting_warnings=overfitting_warnings,
            disclaimers=disclaimers,
        )

        if apply:
            apply_calibrated(recommended_weights, recommended_thresholds, persist=True)

        return result


class CalibrationReportWriter:
    """Write JSON and Markdown calibration summaries."""

    def __init__(self, output_dir: Path | str = "reports/calibration") -> None:
        self._output_dir = Path(output_dir)

    def write(self, result: CalibrationResult) -> tuple[Path, Path]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self._output_dir / "calibration_summary.json"
        md_path = self._output_dir / "calibration_summary.md"

        json_path.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        md_path.write_text(_build_markdown(result), encoding="utf-8")
        return json_path, md_path


def _build_market_comparison(weight_result, threshold_result) -> dict:
    before_w = weight_result.performance_before
    after_w = weight_result.performance_after
    before_t = threshold_result.performance_before
    after_t = threshold_result.performance_after

    return {
        "1x2": {
            "accuracy_before": before_w.one_x_two_accuracy,
            "accuracy_after_weights": after_w.one_x_two_accuracy,
            "accuracy_after_thresholds": after_t.one_x_two_accuracy,
            "recommended_weight_factors": weight_result.best_weights_1x2,
        },
        "over_under_2_5": {
            "accuracy_before": before_w.over_under_accuracy,
            "accuracy_after_weights": after_w.over_under_accuracy,
            "accuracy_after_thresholds": after_t.over_under_accuracy,
            "recommended_weight_factors": weight_result.best_weights_over_under,
        },
        "halftime_bucket": {
            "accuracy_before": before_w.halftime_bucket_accuracy,
            "accuracy_after_weights": after_w.halftime_bucket_accuracy,
            "accuracy_after_thresholds": after_t.halftime_bucket_accuracy,
            "recommended_weight_factors": weight_result.best_weights_halftime,
        },
        "no_bet_rate": {
            "before": before_t.no_bet_rate,
            "after_threshold_tuning": after_t.no_bet_rate,
        },
    }


def _build_markdown(result: CalibrationResult) -> str:
    wt = result.weight_tuning
    tt = result.threshold_tuning
    lines = [
        "# WorldCup Predictor Pro 2026 — Calibration Summary",
        "",
        f"Generated (UTC): {datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}",
        f"CSV: `{result.csv_path}`",
        f"Sample size: **{result.sample_size}**",
    ]
    if result.is_demo_data:
        lines.append("")
        lines.append("> **Demo data** — illustrative sample only.")
    if result.sample_size_warning:
        lines.append("")
        lines.append(f"> ⚠ {result.sample_size_warning}")

    lines.extend(["", "## Disclaimer", ""])
    for item in result.disclaimers:
        lines.append(f"- {item}")

    lines.extend(["", "## Current vs Recommended Weights", "", "| Factor | Current | Recommended |", "|--------|---------|---------------|"])
    for key in result.current_weights:
        cur = result.current_weights[key]
        rec = result.recommended_weights.get(key, cur)
        lines.append(f"| {key} | {cur:.2%} | {rec:.2%} |")

    lines.extend(["", "## Current vs Recommended Thresholds", "", "| Threshold | Current | Recommended |", "|-----------|---------|-------------|"])
    for key in sorted(result.current_thresholds):
        cur = result.current_thresholds[key]
        rec = result.recommended_thresholds.get(key, cur)
        lines.append(f"| {key} | {cur:g} | {rec:g} |")

    lines.extend(
        [
            "",
            "## Performance Before / After",
            "",
            "### Weight tuning",
            f"- 1X2: {_pct(wt.performance_before.one_x_two_accuracy)} → {_pct(wt.performance_after.one_x_two_accuracy)}",
            f"- O/U 2.5: {_pct(wt.performance_before.over_under_accuracy)} → {_pct(wt.performance_after.over_under_accuracy)}",
            f"- Halftime: {_pct(wt.performance_before.halftime_bucket_accuracy)} → {_pct(wt.performance_after.halftime_bucket_accuracy)}",
            "",
            "### Threshold tuning",
            f"- Combined accuracy: {_pct(tt.accuracy_before)} → {_pct(tt.accuracy_after)}",
            f"- No-bet rate: {_pct(tt.no_bet_rate_before)} → {_pct(tt.no_bet_rate_after)}",
            "",
            "## Market Comparison",
            "",
        ]
    )
    for market, data in result.market_comparison.items():
        if market == "no_bet_rate":
            continue
        lines.append(f"### {market}")
        lines.append(f"- Before: {_pct(data.get('accuracy_before'))}")
        lines.append(f"- After weights: {_pct(data.get('accuracy_after_weights'))}")
        lines.append(f"- After thresholds: {_pct(data.get('accuracy_after_thresholds'))}")
        lines.append("")

    if result.overfitting_warnings:
        lines.extend(["## Overfitting Warnings", ""])
        for w in result.overfitting_warnings:
            lines.append(f"- {w}")

    lines.extend(
        [
            "",
            "## Do Not Overtrust",
            "",
            "Calibrated parameters fit **this historical sample only**. Expand CSV coverage "
            "before relying on tuned weights for World Cup 2026 analysis.",
            "",
        ]
    )
    return "\n".join(lines)


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _file_is_demo(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return "DEMO DATA" in path.read_text(encoding="utf-8")[:200]
    except OSError:
        return False

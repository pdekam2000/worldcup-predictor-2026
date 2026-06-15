from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.backtesting.historical_loader import CSV_COLUMNS
from worldcup_predictor.data_quality.csv_validator import (
    REQUIRED_COLUMNS,
    OPTIONAL_COLUMNS,
    CsvValidator,
    column_fill_stats,
)
from worldcup_predictor.data_quality.models import (
    ColumnQualityReport,
    DataQualityValidationReport,
    DatasetHealthScore,
    HealthGrade,
    RowIssue,
)
from worldcup_predictor.data_quality.repair_suggestions import generate_repair_suggestions

HEALTH_EXCELLENT = 90.0
HEALTH_GOOD = 75.0
HEALTH_USABLE = 60.0
CALIBRATION_MIN_ROWS = 100


def validate_csv_file(
    csv_path: Path | str,
    *,
    write_report: bool = True,
) -> DataQualityValidationReport:
    """Run full validation pipeline and optionally write summary reports."""
    validator = CsvValidator()
    raw = validator.validate(csv_path)

    report = _build_report(raw)
    report.repair_suggestions = generate_repair_suggestions(report)

    if write_report:
        DataQualityReportWriter().write(report)

    return report


class DataQualityReportWriter:
    """Write JSON and Markdown data quality summaries."""

    def __init__(self, output_dir: Path | str = "reports/data_quality") -> None:
        self._output_dir = Path(output_dir)

    def write(self, report: DataQualityValidationReport) -> tuple[Path, Path]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self._output_dir / "data_quality_summary.json"
        md_path = self._output_dir / "data_quality_summary.md"
        json_path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        md_path.write_text(_build_markdown(report), encoding="utf-8")
        return json_path, md_path


def _build_report(raw) -> DataQualityValidationReport:
    fill_stats = column_fill_stats(raw.rows)
    column_reports: list[ColumnQualityReport] = []

    for col in CSV_COLUMNS:
        required = col in REQUIRED_COLUMNS
        present = col in raw.header_columns
        stats = fill_stats.get(col, {"missing": raw.row_count, "invalid": 0, "fill_rate_pct": 0.0})
        column_reports.append(
            ColumnQualityReport(
                column_name=col,
                present=present,
                required=required,
                missing_count=int(stats["missing"]),
                invalid_count=int(stats["invalid"]),
                fill_rate_pct=float(stats["fill_rate_pct"]),
                notes=[] if present else ["Column absent from header"],
            )
        )

    optional_missing = {
        col: float(fill_stats.get(col, {}).get("fill_rate_pct", 0.0))
        for col in OPTIONAL_COLUMNS
        if col in raw.header_columns
    }
    for col in OPTIONAL_COLUMNS:
        if col not in optional_missing:
            optional_missing[col] = 0.0

    critical_errors = list(raw.file_errors)
    if raw.missing_required_columns:
        critical_errors.extend(
            [f"Missing required column: {col}" for col in raw.missing_required_columns]
        )

    warnings: list[str] = []
    if raw.duplicate_fixture_ids:
        warnings.append(f"{len(raw.duplicate_fixture_ids)} duplicate fixture_id values.")
    if raw.duplicate_matches:
        warnings.append(f"{len(raw.duplicate_matches)} duplicate date/home/away matches.")
    if raw.is_demo_data:
        warnings.append("Demo/sample dataset detected — separate from API-Football imports.")

    health = _compute_health_score(raw, fill_stats, optional_missing)

    critical_count = sum(1 for issue in raw.row_issues if issue.severity == "critical")
    warning_count = sum(1 for issue in raw.row_issues if issue.severity == "warning")

    safe_backtest = (
        not raw.missing_required_columns
        and not raw.file_errors
        and raw.row_count > 0
        and critical_count == 0
    )
    safe_calibration = (
        safe_backtest
        and health.score >= HEALTH_GOOD
        and raw.row_count >= CALIBRATION_MIN_ROWS
        and not raw.is_demo_data
    )

    return DataQualityValidationReport(
        csv_path=raw.csv_path,
        source_label=raw.source_label,  # type: ignore[arg-type]
        row_count=raw.row_count,
        duplicate_fixture_id_count=len(raw.duplicate_fixture_ids),
        duplicate_match_count=len(raw.duplicate_matches),
        critical_error_count=critical_count + len(raw.missing_required_columns),
        warning_count=warning_count,
        missing_required_fields=list(raw.missing_required_columns),
        missing_optional_summary=optional_missing,
        column_reports=column_reports,
        row_issues=raw.row_issues,
        warnings=warnings,
        critical_errors=critical_errors,
        health=health,
        safe_for_backtest=safe_backtest,
        safe_for_calibration=safe_calibration,
        is_demo_data=raw.is_demo_data,
    )


def _compute_health_score(raw, fill_stats, optional_missing: dict[str, float]) -> DatasetHealthScore:
    score = 100.0

    score -= len(raw.missing_required_columns) * 25
    score -= min(sum(1 for i in raw.row_issues if i.severity == "critical") * 3, 30)
    score -= min(len(raw.duplicate_fixture_ids) * 3, 12)
    score -= min(len(raw.duplicate_matches) * 2, 8)
    score -= min(sum(1 for i in raw.row_issues if i.issue_type == "suspicious_scoreline") * 2, 6)

    odds_fill = optional_missing.get("odds_home", 100)
    if odds_fill < 50:
        score -= 10
    elif odds_fill < 80:
        score -= 4

    ht_fill = optional_missing.get("halftime_home_goals", 100)
    if ht_fill < 50:
        score -= 8
    elif ht_fill < 80:
        score -= 3

    venue_fill = optional_missing.get("venue", 100)
    if venue_fill < 70:
        score -= 4

    referee_fill = optional_missing.get("referee", 100)
    if referee_fill < 70:
        score -= 3

    if raw.row_count < 12:
        score -= 20
    elif raw.row_count < 50:
        score -= 12
    elif raw.row_count < CALIBRATION_MIN_ROWS:
        score -= 8

    if raw.is_demo_data:
        score -= 5

    if raw.row_count == 0:
        score = 0.0

    score = max(0.0, min(100.0, round(score, 1)))
    grade, label = _health_grade(score)
    summary = _health_summary(score, grade, raw.row_count)

    return DatasetHealthScore(score=score, grade=grade, label=label, summary=summary)


def _health_grade(score: float) -> tuple[HealthGrade, str]:
    if score >= HEALTH_EXCELLENT:
        return "excellent", "Excellent (90–100)"
    if score >= HEALTH_GOOD:
        return "good", "Good (75–89)"
    if score >= HEALTH_USABLE:
        return "usable_with_caution", "Usable with caution (60–74)"
    return "weak", "Weak / not recommended for calibration (<60)"


def _health_summary(score: float, grade: HealthGrade, row_count: int) -> str:
    if grade == "excellent":
        return f"Score {score:.0f}/100 — excellent dataset quality ({row_count} rows)."
    if grade == "good":
        return f"Score {score:.0f}/100 — good quality, suitable for backtest and calibration."
    if grade == "usable_with_caution":
        return f"Score {score:.0f}/100 — usable with caution; review warnings before calibration."
    return f"Score {score:.0f}/100 — weak quality; expand or repair before trusting calibration."


def print_preflight_warning(
    report: DataQualityValidationReport,
    out,
    translator,
    *,
    context: str = "backtest",
) -> None:
    """Print validation warning before backtest/calibrate (non-blocking unless critical)."""
    if report.has_critical_errors:
        out.write("\n" + "!" * 72 + "\n")
        out.write(f"  ⚠ {translator.t('cli.validate.critical_preflight')}\n")
        for err in report.critical_errors[:5]:
            out.write(f"    • {err}\n")
        out.write("!" * 72 + "\n\n")
        return

    if report.health and report.health.score < HEALTH_GOOD:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  ⚠ {translator.t('cli.validate.low_health_preflight')}\n")
        out.write(f"    {translator.t('cli.validate.health_score')}: {report.health.score:.0f}/100 ")
        out.write(f"({report.health.label})\n")
        if context == "calibration" and not report.safe_for_calibration:
            out.write(f"    {translator.t('cli.validate.calibration_not_recommended')}\n")
        out.write("-" * 72 + "\n\n")


def should_block_execution(report: DataQualityValidationReport) -> bool:
    """Block only when required columns or goals integrity fails."""
    return report.has_critical_errors or report.row_count == 0


def run_csv_quality_preflight(
    csv_path: Path | str,
    *,
    out,
    translator,
    context: str = "backtest",
) -> tuple[DataQualityValidationReport, bool]:
    """Validate CSV before backtest/calibrate. Returns (report, blocked)."""
    report = validate_csv_file(csv_path, write_report=False)
    if should_block_execution(report):
        print_preflight_warning(report, out, translator, context=context)
        out.write(f"  ✗ {translator.t('cli.validate.blocked')}\n\n")
        return report, True
    print_preflight_warning(report, out, translator, context=context)
    return report, False


def _build_markdown(report: DataQualityValidationReport) -> str:
    lines = [
        "# WorldCup Predictor Pro 2026 — Data Quality Summary",
        "",
        f"Generated (UTC): {datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}",
        f"CSV: `{report.csv_path}`",
        f"Source: **{report.source_label}**",
        f"Rows: **{report.row_count}**",
        "",
    ]
    if report.health:
        lines.extend(
            [
                "## Dataset Health",
                "",
                f"- Score: **{report.health.score:.0f}/100**",
                f"- Grade: {report.health.label}",
                f"- {report.health.summary}",
                f"- Safe for backtest: **{report.safe_for_backtest}**",
                f"- Safe for calibration: **{report.safe_for_calibration}**",
                "",
            ]
        )

    lines.extend(
        [
            "## Duplicates",
            "",
            f"- Duplicate fixture_id: {report.duplicate_fixture_id_count}",
            f"- Duplicate match keys: {report.duplicate_match_count}",
            "",
        ]
    )

    if report.missing_required_fields:
        lines.extend(["## Critical — Missing Required Columns", ""])
        for col in report.missing_required_fields:
            lines.append(f"- {col}")
        lines.append("")

    if report.missing_optional_summary:
        lines.extend(["## Optional Field Fill Rates", "", "| Column | Fill % |", "|--------|--------|"])
        for col, pct in sorted(report.missing_optional_summary.items()):
            lines.append(f"| {col} | {pct:.1f}% |")
        lines.append("")

    if report.warnings:
        lines.extend(["## Warnings", ""])
        for warning in report.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    if report.critical_errors:
        lines.extend(["## Critical Errors", ""])
        for err in report.critical_errors:
            lines.append(f"- {err}")
        lines.append("")

    sample_issues = [i for i in report.row_issues if i.severity == "critical"][:10]
    if sample_issues:
        lines.extend(["## Sample Row Issues (critical)", ""])
        for issue in sample_issues:
            lines.append(f"- Row {issue.row_number}: {issue.message}")
        lines.append("")

    if report.repair_suggestions:
        lines.extend(["## Repair Suggestions (manual only)", ""])
        for suggestion in report.repair_suggestions:
            lines.append(f"- {suggestion}")
        lines.append("")

    lines.extend(
        [
            "## Disclaimer",
            "",
            "Validation does not modify CSV files. Historical performance does not guarantee future results.",
            "",
        ]
    )
    return "\n".join(lines)

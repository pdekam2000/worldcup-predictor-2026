from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

IssueSeverity = Literal["critical", "warning", "info"]
HealthGrade = Literal["excellent", "good", "usable_with_caution", "weak"]
DataSourceLabel = Literal["demo", "api-football", "csv", "unknown"]


@dataclass
class RowIssue:
    row_number: int
    fixture_id: str | None
    issue_type: str
    message: str
    severity: IssueSeverity = "warning"
    field: str | None = None


@dataclass
class ColumnQualityReport:
    column_name: str
    present: bool
    required: bool
    missing_count: int = 0
    invalid_count: int = 0
    fill_rate_pct: float = 100.0
    notes: list[str] = field(default_factory=list)


@dataclass
class DatasetHealthScore:
    score: float
    grade: HealthGrade
    label: str
    summary: str


@dataclass
class DataQualityValidationReport:
    csv_path: str
    source_label: DataSourceLabel
    row_count: int = 0
    duplicate_fixture_id_count: int = 0
    duplicate_match_count: int = 0
    critical_error_count: int = 0
    warning_count: int = 0
    missing_required_fields: list[str] = field(default_factory=list)
    missing_optional_summary: dict[str, float] = field(default_factory=dict)
    column_reports: list[ColumnQualityReport] = field(default_factory=list)
    row_issues: list[RowIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    critical_errors: list[str] = field(default_factory=list)
    repair_suggestions: list[str] = field(default_factory=list)
    health: DatasetHealthScore | None = None
    safe_for_backtest: bool = False
    safe_for_calibration: bool = False
    is_demo_data: bool = False

    @property
    def has_critical_errors(self) -> bool:
        if self.critical_errors or self.missing_required_fields:
            return True
        return any(issue.severity == "critical" for issue in self.row_issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "csv_path": self.csv_path,
            "source_label": self.source_label,
            "row_count": self.row_count,
            "duplicate_fixture_id_count": self.duplicate_fixture_id_count,
            "duplicate_match_count": self.duplicate_match_count,
            "critical_error_count": self.critical_error_count,
            "warning_count": self.warning_count,
            "missing_required_fields": self.missing_required_fields,
            "missing_optional_summary": self.missing_optional_summary,
            "column_reports": [
                {
                    "column_name": col.column_name,
                    "present": col.present,
                    "required": col.required,
                    "missing_count": col.missing_count,
                    "invalid_count": col.invalid_count,
                    "fill_rate_pct": col.fill_rate_pct,
                    "notes": col.notes,
                }
                for col in self.column_reports
            ],
            "row_issues": [
                {
                    "row_number": issue.row_number,
                    "fixture_id": issue.fixture_id,
                    "issue_type": issue.issue_type,
                    "message": issue.message,
                    "severity": issue.severity,
                    "field": issue.field,
                }
                for issue in self.row_issues[:100]
            ],
            "warnings": self.warnings,
            "critical_errors": self.critical_errors,
            "repair_suggestions": self.repair_suggestions,
            "health": None
            if self.health is None
            else {
                "score": self.health.score,
                "grade": self.health.grade,
                "label": self.health.label,
                "summary": self.health.summary,
            },
            "safe_for_backtest": self.safe_for_backtest,
            "safe_for_calibration": self.safe_for_calibration,
            "is_demo_data": self.is_demo_data,
            "disclaimer": (
                "Validation reports data quality only. Does not modify CSV files. "
                "Historical performance does not guarantee future results."
            ),
        }

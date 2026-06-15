from __future__ import annotations

from worldcup_predictor.data_quality.models import DataQualityValidationReport


def generate_repair_suggestions(report: DataQualityValidationReport) -> list[str]:
    suggestions: list[str] = []

    if report.duplicate_fixture_id_count > 0 or report.duplicate_match_count > 0:
        suggestions.append(
            "Remove duplicate rows (keep one row per fixture_id or unique date/home/away combination)."
        )

    if any(issue.issue_type == "missing_goals" or issue.issue_type == "unfinished_match" for issue in report.row_issues):
        suggestions.append("Exclude rows with missing home_goals or away_goals — unfinished matches distort backtests.")

    if report.missing_optional_summary.get("odds_home", 100) < 50:
        suggestions.append(
            "Consider splitting into two datasets: with-odds rows for market-aware backtests "
            "and no-odds rows for form-only evaluation."
        )

    if report.missing_optional_summary.get("halftime_home_goals", 100) < 50:
        suggestions.append(
            "Halftime bucket accuracy will be limited — import halftime scores or exclude HT evaluation."
        )

    if report.missing_optional_summary.get("venue", 100) < 70:
        suggestions.append("Optional: fill venue from API re-import or external reference.")

    if report.missing_optional_summary.get("referee", 100) < 70:
        suggestions.append("Optional: referee is informational — low fill rate reduces specialist realism only.")

    if report.row_count < 100:
        suggestions.append(
            f"Sample size {report.row_count} is small — expand CSV before calibration (target 100+ matches)."
        )

    if report.is_demo_data:
        suggestions.append(
            "Demo CSV detected — use import-history with API_FOOTBALL_KEY for real historical expansion."
        )

    if report.health and report.health.score < 75:
        suggestions.append(
            "Health score below 75 — review warnings before trusting calibration output."
        )

    if not suggestions:
        suggestions.append("No critical repairs needed — dataset looks structurally sound for backtesting.")

    suggestions.append(
        "This tool does not modify CSV files automatically. Apply repairs manually or via a future --repair flag."
    )
    return suggestions

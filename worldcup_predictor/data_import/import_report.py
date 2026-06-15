from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.data_import.models import ExportResult, ImportResult


class ImportReportWriter:
    """Write import summary JSON and Markdown reports."""

    def __init__(self, output_dir: Path | str = "reports/imports") -> None:
        self._output_dir = Path(output_dir)

    def write(
        self,
        import_result: ImportResult,
        export_result: ExportResult | None = None,
    ) -> tuple[Path, Path]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self._output_dir / "import_summary.json"
        md_path = self._output_dir / "import_summary.md"

        payload = {
            "generated_at_utc": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "source": import_result.source_label,
            "success": import_result.success,
            "message": import_result.message,
            "requested_competitions": import_result.requested_competitions,
            "requested_seasons": import_result.requested_seasons,
            "imported_count": import_result.imported_count,
            "skipped_count": import_result.skipped_count,
            "missing_fields_summary": import_result.missing_fields_summary,
            "api_errors": import_result.api_errors,
            "cache_hits": import_result.stats.cache_hits,
            "live_requests": import_result.stats.live_requests,
            "odds_fetched": import_result.stats.odds_fetched,
            "odds_missing": import_result.stats.odds_missing,
            "data_quality_notes": import_result.data_quality_notes,
            "export": None if export_result is None else {
                "output_path": export_result.output_path,
                "rows_written": export_result.rows_written,
                "rows_merged": export_result.rows_merged,
                "overwritten": export_result.overwritten,
                "source_label": export_result.source_label,
                "validation_errors": export_result.validation_errors,
            },
            "disclaimer": (
                "Imported historical data does not guarantee future World Cup 2026 results. "
                "Demo CSV (worldcup_sample.csv) remains separate from API-Football imports."
            ),
        }

        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(_build_markdown(import_result, export_result), encoding="utf-8")
        return json_path, md_path


def _build_markdown(
    import_result: ImportResult,
    export_result: ExportResult | None,
) -> str:
    lines = [
        "# WorldCup Predictor Pro 2026 — Import Summary",
        "",
        f"Generated (UTC): {datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}",
        f"Source: **{import_result.source_label}**",
        f"Success: **{import_result.success}**",
        "",
        import_result.message,
        "",
        "## Request",
        "",
        f"- Competitions: {', '.join(import_result.requested_competitions) or 'n/a'}",
        f"- Seasons: {', '.join(str(s) for s in import_result.requested_seasons) or 'n/a'}",
        "",
        "## Counts",
        "",
        f"- Imported: **{import_result.imported_count}**",
        f"- Skipped: **{import_result.skipped_count}**",
        "",
        "## API / Cache",
        "",
        f"- Cache hits: {import_result.stats.cache_hits}",
        f"- Live requests: {import_result.stats.live_requests}",
        f"- Odds fetched: {import_result.stats.odds_fetched}",
        f"- Odds missing: {import_result.stats.odds_missing}",
        "",
    ]

    if import_result.missing_fields_summary:
        lines.extend(["## Missing Fields Summary", ""])
        for field_name, count in sorted(import_result.missing_fields_summary.items()):
            lines.append(f"- {field_name}: {count}")

    if import_result.api_errors:
        lines.extend(["", "## API Errors", ""])
        for error in import_result.api_errors:
            lines.append(f"- {error}")

    if import_result.data_quality_notes:
        lines.extend(["", "## Data Quality Notes", ""])
        for note in import_result.data_quality_notes:
            lines.append(f"- {note}")

    if export_result:
        lines.extend(
            [
                "",
                "## Export",
                "",
                f"- Output: `{export_result.output_path}`",
                f"- Rows written: {export_result.rows_written}",
                f"- Existing rows merged: {export_result.rows_merged}",
                f"- Overwrite mode: {export_result.overwritten}",
                f"- Export source label: {export_result.source_label}",
            ]
        )
        if export_result.validation_errors:
            lines.extend(["", "### Validation Errors", ""])
            for err in export_result.validation_errors:
                lines.append(f"- {err}")

    lines.extend(
        [
            "",
            "## Disclaimer",
            "",
            "Historical performance does not guarantee future results.",
            "Demo data (`worldcup_sample.csv`) is separate from imported API-Football data.",
            "This import is for backtest/calibration evaluation only — not betting advice.",
            "",
        ]
    )
    return "\n".join(lines)

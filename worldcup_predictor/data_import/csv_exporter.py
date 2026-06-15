from __future__ import annotations

import csv
from pathlib import Path

from worldcup_predictor.backtesting.historical_loader import CSV_COLUMNS
from worldcup_predictor.data_import.models import ExportResult, ImportResult, ImportedMatchRow, ImportSource

REQUIRED_CSV_FIELDS = (
    "fixture_id",
    "date",
    "competition",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
)

API_CSV_HEADER = (
    "# SOURCE: API-Football — real historical match data for backtest/calibration.\n"
    "# Not guaranteed complete. Historical performance does not guarantee future results.\n"
)


class CsvExporter:
    """Export imported matches to backtest-compatible CSV files."""

    WORLDCUP_PATH = Path("data/historical/worldcup_historical.csv")
    INTERNATIONAL_PATH = Path("data/historical/international_historical.csv")

    def export_worldcup(
        self,
        import_result: ImportResult,
        *,
        overwrite: bool = False,
        output_path: Path | str | None = None,
    ) -> ExportResult:
        path = Path(output_path) if output_path else self.WORLDCUP_PATH
        return self._export(import_result.rows, path, overwrite=overwrite, source="api-football")

    def export_international(
        self,
        import_result: ImportResult,
        *,
        overwrite: bool = False,
        output_path: Path | str | None = None,
    ) -> ExportResult:
        path = Path(output_path) if output_path else self.INTERNATIONAL_PATH
        return self._export(import_result.rows, path, overwrite=overwrite, source="api-football")

    def _export(
        self,
        rows: list[ImportedMatchRow],
        path: Path,
        *,
        overwrite: bool,
        source: ImportSource,
    ) -> ExportResult:
        validation_errors = _validate_rows(rows)
        if validation_errors:
            return ExportResult(
                output_path=str(path),
                rows_written=0,
                rows_merged=0,
                overwritten=overwrite,
                source_label=source,
                validation_errors=validation_errors,
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        merged_count = 0

        if path.exists() and not overwrite:
            existing = _read_existing_rows(path)
            existing_ids = {row.fixture_id for row in existing}
            new_rows = [row for row in rows if row.fixture_id not in existing_ids]
            merged = existing + new_rows
            merged_count = len(existing)
            final_rows = _sort_rows(_dedupe(merged))
        elif path.exists() and overwrite:
            final_rows = _sort_rows(_dedupe(rows))
        else:
            final_rows = _sort_rows(_dedupe(rows))

        _write_csv(path, final_rows, include_header_comment=True)
        return ExportResult(
            output_path=str(path),
            rows_written=len(final_rows),
            rows_merged=merged_count,
            overwritten=overwrite and path.exists(),
            source_label=source if not merged_count else "merged",
            validation_errors=[],
        )


def _validate_rows(rows: list[ImportedMatchRow]) -> list[str]:
    if not rows:
        return ["No rows to export."]
    errors: list[str] = []
    for row in rows[:50]:
        if row.fixture_id <= 0:
            errors.append(f"Invalid fixture_id: {row.fixture_id}")
        if not row.home_team or not row.away_team:
            errors.append(f"Missing team names for fixture {row.fixture_id}")
    return errors


def _read_existing_rows(path: Path) -> list[ImportedMatchRow]:
    from worldcup_predictor.backtesting.historical_loader import HistoricalLoader

    loader = HistoricalLoader(path)
    historical = loader.load(create_sample_if_missing=False)
    converted: list[ImportedMatchRow] = []
    for row in historical:
        converted.append(
            ImportedMatchRow(
                fixture_id=row.fixture_id,
                date=row.date,
                competition=row.competition,
                round=row.round,
                home_team=row.home_team,
                away_team=row.away_team,
                home_goals=row.home_goals,
                away_goals=row.away_goals,
                halftime_home_goals=row.halftime_home_goals,
                halftime_away_goals=row.halftime_away_goals,
                venue=row.venue,
                referee=row.referee,
                odds_home=row.odds_home,
                odds_draw=row.odds_draw,
                odds_away=row.odds_away,
                over_2_5_odds=row.over_2_5_odds,
                under_2_5_odds=row.under_2_5_odds,
                source="csv",
            )
        )
    return converted


def _dedupe(rows: list[ImportedMatchRow]) -> list[ImportedMatchRow]:
    seen: dict[int, ImportedMatchRow] = {}
    for row in rows:
        seen[row.fixture_id] = row
    return list(seen.values())


def _sort_rows(rows: list[ImportedMatchRow]) -> list[ImportedMatchRow]:
    return sorted(rows, key=lambda r: (r.date, r.fixture_id))


def _write_csv(path: Path, rows: list[ImportedMatchRow], *, include_header_comment: bool) -> None:
    lines: list[str] = []
    if include_header_comment:
        lines.append(API_CSV_HEADER.rstrip("\n"))
    lines.append(",".join(CSV_COLUMNS))
    for row in rows:
        data = row.to_csv_dict()
        lines.append(",".join(data[col] for col in CSV_COLUMNS))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

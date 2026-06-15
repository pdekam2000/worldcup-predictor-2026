from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from worldcup_predictor.backtesting.historical_loader import CSV_COLUMNS
from worldcup_predictor.data_quality.models import RowIssue

REQUIRED_COLUMNS = (
    "fixture_id",
    "date",
    "competition",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
)

OPTIONAL_COLUMNS = (
    "round",
    "halftime_home_goals",
    "halftime_away_goals",
    "venue",
    "referee",
    "odds_home",
    "odds_draw",
    "odds_away",
    "over_2_5_odds",
    "under_2_5_odds",
)

ODDS_COLUMNS = (
    "odds_home",
    "odds_draw",
    "odds_away",
    "over_2_5_odds",
    "under_2_5_odds",
)

SUSPICIOUS_TOTAL_GOALS = 12


@dataclass
class ParsedCsvRow:
    line_number: int
    raw: dict[str, str]
    fixture_id: str | None = None
    date_text: str | None = None
    home_team: str | None = None
    away_team: str | None = None


@dataclass
class CsvValidationResult:
    csv_path: str
    header_columns: list[str] = field(default_factory=list)
    missing_required_columns: list[str] = field(default_factory=list)
    rows: list[ParsedCsvRow] = field(default_factory=list)
    row_issues: list[RowIssue] = field(default_factory=list)
    duplicate_fixture_ids: list[str] = field(default_factory=list)
    duplicate_matches: list[str] = field(default_factory=list)
    is_demo_data: bool = False
    source_label: str = "unknown"
    file_errors: list[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)


class CsvValidator:
    """Validate historical backtest CSV structure and row integrity."""

    def validate(self, csv_path: Path | str) -> CsvValidationResult:
        path = Path(csv_path)
        result = CsvValidationResult(csv_path=str(path))

        if not path.exists():
            result.file_errors.append(f"CSV file not found: {path}")
            result.row_issues.append(
                RowIssue(
                    row_number=0,
                    fixture_id=None,
                    issue_type="file_missing",
                    message=str(result.file_errors[0]),
                    severity="critical",
                )
            )
            return result

        result.is_demo_data = _detect_demo(path)
        result.source_label = _detect_source(path, result.is_demo_data)

        raw_lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not raw_lines:
            result.file_errors.append("CSV file is empty.")
            return result

        reader = csv.DictReader(raw_lines)
        result.header_columns = list(reader.fieldnames or [])
        result.missing_required_columns = [
            col for col in REQUIRED_COLUMNS if col not in result.header_columns
        ]

        if result.missing_required_columns:
            for col in result.missing_required_columns:
                result.row_issues.append(
                    RowIssue(
                        row_number=1,
                        fixture_id=None,
                        issue_type="missing_column",
                        message=f"Required column missing: {col}",
                        severity="critical",
                        field=col,
                    )
                )
            return result

        fixture_ids_seen: dict[str, int] = {}
        match_keys_seen: dict[str, int] = {}

        for line_number, raw in enumerate(reader, start=2):
            parsed = ParsedCsvRow(line_number=line_number, raw=raw)
            result.rows.append(parsed)
            self._validate_row(parsed, result)

            fixture_id = (raw.get("fixture_id") or "").strip()
            if fixture_id:
                parsed.fixture_id = fixture_id
                fixture_ids_seen[fixture_id] = fixture_ids_seen.get(fixture_id, 0) + 1

            home = (raw.get("home_team") or "").strip()
            away = (raw.get("away_team") or "").strip()
            date_text = (raw.get("date") or "").strip()
            parsed.home_team = home or None
            parsed.away_team = away or None
            parsed.date_text = date_text or None

            if home and away and date_text:
                match_key = f"{date_text}|{home.lower()}|{away.lower()}"
                match_keys_seen[match_key] = match_keys_seen.get(match_key, 0) + 1

        result.duplicate_fixture_ids = [
            fid for fid, count in fixture_ids_seen.items() if count > 1
        ]
        result.duplicate_matches = [
            key for key, count in match_keys_seen.items() if count > 1
        ]

        for fixture_id in result.duplicate_fixture_ids:
            result.row_issues.append(
                RowIssue(
                    row_number=0,
                    fixture_id=fixture_id,
                    issue_type="duplicate_fixture_id",
                    message=f"Duplicate fixture_id: {fixture_id}",
                    severity="warning",
                    field="fixture_id",
                )
            )

        for match_key in result.duplicate_matches:
            result.row_issues.append(
                RowIssue(
                    row_number=0,
                    fixture_id=None,
                    issue_type="duplicate_match",
                    message=f"Duplicate match key: {match_key}",
                    severity="warning",
                )
            )

        return result

    def _validate_row(self, parsed: ParsedCsvRow, result: CsvValidationResult) -> None:
        raw = parsed.raw
        line = parsed.line_number
        fixture_id = (raw.get("fixture_id") or "").strip() or None

        if not fixture_id:
            result.row_issues.append(
                RowIssue(line, fixture_id, "missing_fixture_id", "fixture_id is empty", "critical", "fixture_id")
            )
        else:
            try:
                if int(fixture_id) <= 0:
                    raise ValueError
            except ValueError:
                result.row_issues.append(
                    RowIssue(line, fixture_id, "invalid_fixture_id", f"Invalid fixture_id: {fixture_id}", "critical", "fixture_id")
                )

        date_text = (raw.get("date") or "").strip()
        if not date_text:
            result.row_issues.append(
                RowIssue(line, fixture_id, "missing_date", "date is empty", "critical", "date")
            )
        elif not _is_valid_date(date_text):
            result.row_issues.append(
                RowIssue(line, fixture_id, "invalid_date", f"Invalid date: {date_text}", "critical", "date")
            )

        home = (raw.get("home_team") or "").strip()
        away = (raw.get("away_team") or "").strip()
        if not home:
            result.row_issues.append(
                RowIssue(line, fixture_id, "missing_home_team", "home_team is empty", "critical", "home_team")
            )
        if not away:
            result.row_issues.append(
                RowIssue(line, fixture_id, "missing_away_team", "away_team is empty", "critical", "away_team")
            )
        if home and away and home.lower() == away.lower():
            result.row_issues.append(
                RowIssue(line, fixture_id, "same_team", "home_team and away_team are identical", "warning")
            )

        home_goals_raw = (raw.get("home_goals") or "").strip()
        away_goals_raw = (raw.get("away_goals") or "").strip()
        if home_goals_raw == "" or away_goals_raw == "":
            result.row_issues.append(
                RowIssue(
                    line,
                    fixture_id,
                    "unfinished_match",
                    "Missing goals — row may be unfinished/not suitable for backtest",
                    "critical",
                    "home_goals",
                )
            )
        else:
            try:
                home_goals = int(home_goals_raw)
                away_goals = int(away_goals_raw)
                if home_goals < 0 or away_goals < 0:
                    raise ValueError
                total = home_goals + away_goals
                if total > SUSPICIOUS_TOTAL_GOALS:
                    result.row_issues.append(
                        RowIssue(
                            line,
                            fixture_id,
                            "suspicious_scoreline",
                            f"Suspicious total goals: {total}",
                            "warning",
                        )
                    )
            except ValueError:
                result.row_issues.append(
                    RowIssue(
                        line,
                        fixture_id,
                        "invalid_goals",
                        f"Invalid goals: {home_goals_raw}-{away_goals_raw}",
                        "critical",
                        "home_goals",
                    )
                )
                home_goals = away_goals = None

            if home_goals_raw != "" and away_goals_raw != "":
                ht_home_raw = (raw.get("halftime_home_goals") or "").strip()
                ht_away_raw = (raw.get("halftime_away_goals") or "").strip()
                if ht_home_raw and ht_away_raw:
                    try:
                        ht_home = int(ht_home_raw)
                        ht_away = int(ht_away_raw)
                        hg = int(home_goals_raw)
                        ag = int(away_goals_raw)
                        if ht_home > hg or ht_away > ag:
                            result.row_issues.append(
                                RowIssue(
                                    line,
                                    fixture_id,
                                    "halftime_exceeds_fulltime",
                                    f"Halftime goals exceed fulltime: HT {ht_home}-{ht_away}, FT {hg}-{ag}",
                                    "warning",
                                )
                            )
                    except ValueError:
                        result.row_issues.append(
                            RowIssue(
                                line,
                                fixture_id,
                                "invalid_halftime",
                                "Halftime goals are not numeric",
                                "warning",
                            )
                        )

        for odds_col in ODDS_COLUMNS:
            value = (raw.get(odds_col) or "").strip()
            if value and not _is_numeric(value):
                result.row_issues.append(
                    RowIssue(
                        line,
                        fixture_id,
                        "invalid_odds",
                        f"{odds_col} is not numeric: {value}",
                        "warning",
                        field=odds_col,
                    )
                )


def _is_valid_date(value: str) -> bool:
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            datetime.strptime(value[:19], fmt)
            return True
        except ValueError:
            continue
    try:
        datetime.strptime(value[:10], "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _detect_demo(path: Path) -> bool:
    try:
        head = path.read_text(encoding="utf-8")[:300]
    except OSError:
        return False
    return "DEMO DATA" in head or "demo" in path.name.lower() and "sample" in path.name.lower()


def _detect_source(path: Path, is_demo: bool) -> str:
    if is_demo:
        return "demo"
    try:
        head = path.read_text(encoding="utf-8")[:300]
    except OSError:
        return "unknown"
    if "API-Football" in head or "api-football" in head.lower():
        return "api-football"
    return "csv"


def column_fill_stats(rows: list[ParsedCsvRow]) -> dict[str, dict[str, int | float]]:
    if not rows:
        return {}
    stats: dict[str, dict[str, int | float]] = {}
    all_columns = list(CSV_COLUMNS)
    total = len(rows)
    for col in all_columns:
        missing = 0
        invalid = 0
        for parsed in rows:
            value = (parsed.raw.get(col) or "").strip()
            if not value:
                missing += 1
            elif col in ODDS_COLUMNS and not _is_numeric(value):
                invalid += 1
        stats[col] = {
            "missing": missing,
            "invalid": invalid,
            "fill_rate_pct": round((total - missing) / total * 100, 1),
        }
    return stats

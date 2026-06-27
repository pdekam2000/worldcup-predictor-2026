from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.domain.fixture import Fixture
from worldcup_predictor.domain.intelligence import (
    DataQualityReport,
    InjuryReport,
    MatchIntelligenceReport,
    OddsSnapshot,
    TeamIntelligence,
)

logger = logging.getLogger(__name__)

CSV_COLUMNS = (
    "fixture_id",
    "date",
    "competition",
    "round",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
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

DEMO_CSV_HEADER = ",".join(CSV_COLUMNS)

DEMO_CSV_ROWS = [
    "900001,2022-11-20,FIFA World Cup 2022,Group A - Matchday 1,Qatar,Ecuador,0,2,0,2,Al Bayt Stadium,Enrique Caceres,3.40,3.20,2.25,2.10,1.75",
    "900002,2022-11-21,FIFA World Cup 2022,Group B - Matchday 1,England,Iran,6,2,3,0,Khalifa International Stadium,Slavko Vincic,1.35,5.00,9.00,1.65,2.25",
    "900003,2022-11-21,FIFA World Cup 2022,Group A - Matchday 1,Senegal,Netherlands,0,2,0,0,Al Thumama Stadium,Stephanie Frappart,4.50,3.40,1.85,2.05,1.80",
    "900004,2022-11-22,FIFA World Cup 2022,Group B - Matchday 1,USA,Wales,1,1,1,0,Ahmad bin Ali Stadium,Abdulrahman Al Jassim,2.30,3.10,3.40,2.20,1.70",
    "900005,2022-11-22,FIFA World Cup 2022,Group C - Matchday 1,Argentina,Saudi Arabia,1,2,1,0,Lusail Stadium,Michael Oliver,1.22,6.50,15.00,1.45,2.75",
    "900006,2022-11-23,FIFA World Cup 2022,Group D - Matchday 1,France,Australia,4,1,2,1,Al Janoub Stadium,Antonio Mateu,1.18,7.00,17.00,1.40,3.00",
    "900007,2022-11-23,FIFA World Cup 2022,Group C - Matchday 1,Mexico,Poland,0,0,0,0,Stadium 974,Said Martinez,2.60,3.00,2.90,2.35,1.60",
    "900008,2022-11-24,FIFA World Cup 2022,Group E - Matchday 1,Germany,Japan,1,2,1,0,Khalifa International Stadium,Ivan Barton,1.45,4.50,7.00,1.55,2.45",
    "900009,2022-11-24,FIFA World Cup 2022,Group F - Matchday 1,Morocco,Croatia,0,0,0,0,Al Bayt Stadium,Facundo Tello,3.20,3.10,2.40,2.30,1.62",
    "900010,2022-11-25,FIFA World Cup 2022,Group G - Matchday 1,Brazil,Serbia,2,0,0,0,Lusail Stadium,Alireza Faghani,1.50,4.20,6.50,1.70,2.15",
    "900011,2022-11-26,FIFA World Cup 2022,Group A - Matchday 2,Netherlands,Ecuador,1,1,1,0,Khalifa International Stadium,Mustapha Ghorbal,1.75,3.50,5.00,2.00,1.85",
    "900012,2022-11-26,FIFA World Cup 2022,Group B - Matchday 2,England,USA,0,0,0,0,Al Bayt Stadium,Jesús Valenzuela,1.65,3.60,5.50,1.90,1.95",
]

DEMO_CSV_COMMENT = (
    "# DEMO DATA — illustrative World Cup 2022 sample rows for model evaluation only.\n"
    "# Not official feed. Historical performance does not guarantee future results.\n"
)


@dataclass
class HistoricalMatchRow:
    """One completed historical match with optional pre-match odds."""

    fixture_id: int
    date: datetime
    competition: str
    round: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    halftime_home_goals: int | None = None
    halftime_away_goals: int | None = None
    venue: str = "Unknown"
    referee: str | None = None
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None
    over_2_5_odds: float | None = None
    under_2_5_odds: float | None = None
    source: Literal["csv", "api", "demo"] = "csv"
    is_demo: bool = False

    @property
    def total_goals(self) -> int:
        return self.home_goals + self.away_goals

    @property
    def halftime_total_goals(self) -> int | None:
        if self.halftime_home_goals is None or self.halftime_away_goals is None:
            return None
        return self.halftime_home_goals + self.halftime_away_goals

    @property
    def actual_1x2(self) -> str:
        if self.home_goals > self.away_goals:
            return "home_win"
        if self.home_goals < self.away_goals:
            return "away_win"
        return "draw"

    @property
    def actual_over_under(self) -> str:
        return "over_2_5" if self.total_goals > 2 else "under_2_5"

    @staticmethod
    def halftime_bucket(total: float | int) -> str:
        value = int(round(float(total)))
        if value <= 0:
            return "0"
        if value == 1:
            return "1"
        if value == 2:
            return "2"
        return "3+"


class HistoricalLoader:
    """Load historical matches from CSV (API hook reserved for later)."""

    def __init__(self, csv_path: Path | str | None = None) -> None:
        self._csv_path = Path(csv_path) if csv_path else None

    def load(self, *, create_sample_if_missing: bool = True) -> list[HistoricalMatchRow]:
        if self._csv_path is None:
            raise FileNotFoundError("No CSV path configured for historical loader.")

        path = self._csv_path
        created_demo = False
        if not path.exists():
            if create_sample_if_missing:
                self.ensure_sample_csv(path)
                created_demo = True
            else:
                raise FileNotFoundError(f"Historical CSV not found: {path}")

        rows = self._read_csv(path)
        if created_demo:
            for row in rows:
                row.is_demo = True
                row.source = "demo"
        return rows

    @staticmethod
    def ensure_sample_csv(path: Path | str) -> Path:
        """Create a small demo CSV when the requested file does not exist."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = DEMO_CSV_COMMENT + DEMO_CSV_HEADER + "\n" + "\n".join(DEMO_CSV_ROWS) + "\n"
        target.write_text(content, encoding="utf-8")
        logger.info("Created demo historical CSV at %s", target)
        return target

    def _read_csv(self, path: Path) -> list[HistoricalMatchRow]:
        rows: list[HistoricalMatchRow] = []
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(
                (line for line in handle if line.strip() and not line.strip().startswith("#")),
            )
            if reader.fieldnames is None:
                return rows
            for raw in reader:
                row = self._parse_row(raw)
                if row is not None:
                    rows.append(row)
        return sorted(rows, key=lambda item: (item.date, item.fixture_id))

    @staticmethod
    def _parse_row(raw: dict[str, str]) -> HistoricalMatchRow | None:
        try:
            fixture_id = int(raw.get("fixture_id", "0"))
            if fixture_id <= 0:
                return None
            date = HistoricalLoader._parse_date(raw.get("date", ""))
            home_goals = int(raw.get("home_goals", "0"))
            away_goals = int(raw.get("away_goals", "0"))
        except (TypeError, ValueError):
            return None

        return HistoricalMatchRow(
            fixture_id=fixture_id,
            date=date,
            competition=raw.get("competition", "Unknown").strip(),
            round=raw.get("round", "Unknown").strip(),
            home_team=raw.get("home_team", "Unknown").strip(),
            away_team=raw.get("away_team", "Unknown").strip(),
            home_goals=home_goals,
            away_goals=away_goals,
            halftime_home_goals=_optional_int(raw.get("halftime_home_goals")),
            halftime_away_goals=_optional_int(raw.get("halftime_away_goals")),
            venue=raw.get("venue", "Unknown").strip() or "Unknown",
            referee=_optional_str(raw.get("referee")),
            odds_home=_optional_float(raw.get("odds_home")),
            odds_draw=_optional_float(raw.get("odds_draw")),
            odds_away=_optional_float(raw.get("odds_away")),
            over_2_5_odds=_optional_float(raw.get("over_2_5_odds")),
            under_2_5_odds=_optional_float(raw.get("under_2_5_odds")),
            source="csv",
        )

    @staticmethod
    def _parse_date(value: str) -> datetime:
        value = value.strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return datetime.strptime(value[:10], "%Y-%m-%d")


def build_form_history(
    rows: list[HistoricalMatchRow],
) -> dict[int, tuple[list[str], list[str]]]:
    """Rolling W/D/L form for each fixture from prior matches in the dataset."""
    team_results: dict[str, list[str]] = {}
    form_by_fixture: dict[int, tuple[list[str], list[str]]] = {}

    for row in rows:
        home_form = _last_n(team_results.get(row.home_team, []), 5)
        away_form = _last_n(team_results.get(row.away_team, []), 5)
        form_by_fixture[row.fixture_id] = (home_form, away_form)

        home_result = _result_for_team(row.home_goals, row.away_goals, side="home")
        away_result = _result_for_team(row.home_goals, row.away_goals, side="away")
        team_results.setdefault(row.home_team, []).append(home_result)
        team_results.setdefault(row.away_team, []).append(away_result)

    return form_by_fixture


def build_intelligence_report(
    row: HistoricalMatchRow,
    *,
    home_form: list[str] | None = None,
    away_form: list[str] | None = None,
) -> MatchIntelligenceReport:
    """Build pre-match intelligence from historical row (no outcome leakage)."""
    fixture = Fixture(
        id=row.fixture_id,
        competition_key=_competition_key(row.competition),
        home_team=row.home_team,
        away_team=row.away_team,
        kickoff_utc=row.date,
        venue=row.venue,
        stage=row.round,
        league_id=1,
        season=row.date.year,
        status="FT",
        source="historical",
        referee=row.referee,
    )

    odds = _build_odds_snapshot(row)
    available_fields: list[str] = ["home_form", "away_form"]
    missing_data: list[str] = []

    if odds.available:
        available_fields.append("odds")
    else:
        missing_data.append("odds")

    if row.referee:
        available_fields.append("referee")
    else:
        missing_data.append("referee")

    missing_data.extend(["injuries", "lineups", "fixture_statistics", "head_to_head"])

    home_stats = _default_team_stats(home_form or [])
    away_stats = _default_team_stats(away_form or [])
    if home_form:
        available_fields.append("home_statistics")
    if away_form:
        available_fields.append("away_statistics")

    quality_score = len(set(available_fields)) / 10.0
    data_quality = DataQualityReport(
        score=round(min(quality_score, 1.0), 2),
        available_fields=sorted(set(available_fields)),
        missing_fields=sorted(set(missing_data)),
        errors=[],
    )

    return MatchIntelligenceReport(
        fixture_id=row.fixture_id,
        fixture=fixture,
        home_team=TeamIntelligence(
            team_name=row.home_team,
            form=home_form or None,
            statistics=home_stats,
            injuries=InjuryReport(team_name=row.home_team, team_id=None, available=False),
            source="live",
        ),
        away_team=TeamIntelligence(
            team_name=row.away_team,
            form=away_form or None,
            statistics=away_stats,
            injuries=InjuryReport(team_name=row.away_team, team_id=None, available=False),
            source="live",
        ),
        head_to_head={"count": 0, "meetings": []},
        fixture_events=[],
        fixture_statistics={"items": []},
        lineups={"available": False, "items": []},
        odds=odds,
        missing_data=sorted(set(missing_data)),
        data_quality=data_quality,
        source="live",
        is_placeholder=False,
    )


def _build_odds_snapshot(row: HistoricalMatchRow) -> OddsSnapshot:
    if not all([row.odds_home, row.odds_draw, row.odds_away]):
        return OddsSnapshot(
            fixture_id=row.fixture_id,
            available=False,
            source="placeholder",
            note="Historical odds unavailable — backtest uses reduced odds signal.",
        )

    bets: list[dict[str, Any]] = [
        {
            "name": "Match Winner",
            "values": [
                {"value": "Home", "odd": str(row.odds_home)},
                {"value": "Draw", "odd": str(row.odds_draw)},
                {"value": "Away", "odd": str(row.odds_away)},
            ],
        }
    ]
    if row.over_2_5_odds and row.under_2_5_odds:
        bets.append(
            {
                "name": "Goals Over/Under",
                "values": [
                    {"value": "Over 2.5", "odd": str(row.over_2_5_odds)},
                    {"value": "Under 2.5", "odd": str(row.under_2_5_odds)},
                ],
            }
        )

    return OddsSnapshot(
        fixture_id=row.fixture_id,
        bookmakers=[{"name": "Historical CSV", "bets": bets}],
        source="live",
        available=True,
        note="Historical odds snapshot for backtesting — informational only.",
    )


def _default_team_stats(form: list[str]) -> dict[str, Any]:
    wins = sum(1 for r in form if r == "W")
    played = max(len(form), 1)
    avg_for = 1.2 + wins * 0.15
    return {
        "fixtures": {"played": {"total": played}},
        "goals": {
            "for": {"total": {"total": int(avg_for * played)}, "average": {"total": str(round(avg_for, 2))}},
            "against": {"total": {"total": played}, "average": {"total": "1.0"}},
        },
    }


def _competition_key(competition: str) -> str:
    lowered = competition.lower()
    if "world cup" in lowered or "world_cup" in lowered:
        return "world_cup_2026"
    if "bundesliga" in lowered:
        return "bundesliga"
    if "premier" in lowered or "premier_league" in lowered:
        return "premier_league"
    if "champions" in lowered or "champions_league" in lowered:
        return "champions_league"
    if "europa" in lowered or "europa_league" in lowered:
        return "europa_league"
    return lowered.replace(" ", "_")


def _result_for_team(home_goals: int, away_goals: int, *, side: str) -> str:
    if home_goals == away_goals:
        return "D"
    if side == "home":
        return "W" if home_goals > away_goals else "L"
    return "W" if away_goals > home_goals else "L"


def _last_n(items: list[str], n: int) -> list[str]:
    return items[-n:] if items else []


def _optional_int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _optional_float(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None

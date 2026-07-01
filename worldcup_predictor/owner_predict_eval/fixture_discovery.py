"""Part A — Today fixture discovery with data availability flags."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.owner_daily.fixture_discovery import discover_daily_fixtures
from worldcup_predictor.owner_predict_eval.constants import ARTIFACTS_DIR, PHASE, with_safety_labels
from worldcup_predictor.owner_predict_eval.dates import date_tag
from worldcup_predictor.owner_predict_eval.db_helpers import (
    has_ecse_oddalerts_shadow,
    has_ecse_production_snapshot,
    has_fixture_result,
    has_oddalerts_csv_policy_snapshot,
    has_wde_prediction,
    latest_odds_snapshot,
)


@dataclass
class TodayFixtureRecord:
    fixture_id: int
    home_team: str
    away_team: str
    competition: str
    kickoff: str
    status: str
    available_data: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition": self.competition,
            "kickoff": self.kickoff,
            "status": self.status,
            "available_data": self.available_data,
        }


@dataclass
class TodayFixtureDiscoveryResult:
    phase: str = PHASE
    target_date: str = ""
    timezone: str = ""
    fixture_count: int = 0
    fixtures: list[TodayFixtureRecord] = field(default_factory=list)
    artifact_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return with_safety_labels(
            {
                "phase": self.phase,
                "target_date": self.target_date,
                "timezone": self.timezone,
                "fixture_count": self.fixture_count,
                "artifact_path": self.artifact_path,
                "fixtures": [f.to_dict() for f in self.fixtures],
            }
        )


def artifact_path_for(target: date) -> Path:
    return ARTIFACTS_DIR / f"owner_today_fixtures_{date_tag(target)}.json"


def discover_today_fixtures(
    *,
    date_arg: str = "today",
    timezone: str = "Europe/Vienna",
    limit: int = 50,
    settings: Settings | None = None,
    fetch_if_missing: bool = False,
) -> TodayFixtureDiscoveryResult:
    settings = settings or get_settings()
    discovery = discover_daily_fixtures(
        date_arg=date_arg,
        timezone=timezone,
        limit=limit,
        settings=settings,
        fetch_if_missing=fetch_if_missing,
        dry_run=not fetch_if_missing,
    )
    conn = connect(settings.sqlite_path)
    records: list[TodayFixtureRecord] = []

    for fx in discovery.fixtures:
        fid = fx.provider_fixture_id
        snap_exists = latest_odds_snapshot(conn, fid) is not None
        comp = get_competition(fx.competition_key)
        records.append(
            TodayFixtureRecord(
                fixture_id=fid,
                home_team=fx.home_team,
                away_team=fx.away_team,
                competition=comp.name if comp else fx.competition_key,
                kickoff=fx.kickoff_utc,
                status=fx.status,
                available_data={
                    "wde_prediction": has_wde_prediction(conn, fid),
                    "odds_snapshot": snap_exists,
                    "oddalerts_csv_policy_snapshot": has_oddalerts_csv_policy_snapshot(conn, fid),
                    "ecse_production_snapshot": has_ecse_production_snapshot(conn, fid),
                    "ecse_oddalerts_shadow_or_monitor": has_ecse_oddalerts_shadow(conn, fid),
                    "result": has_fixture_result(conn, fid),
                },
            )
        )

    target = discovery.target_date
    out = TodayFixtureDiscoveryResult(
        target_date=target,
        timezone=timezone,
        fixture_count=len(records),
        fixtures=records,
    )
    path = artifact_path_for(date.fromisoformat(target))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    out.artifact_path = str(path)
    return out


def load_today_fixtures_artifact(target: date) -> dict[str, Any] | None:
    path = artifact_path_for(target)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

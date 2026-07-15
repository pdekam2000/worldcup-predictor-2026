"""Persist daily pipeline manifests under artifacts/daily_pipeline/YYYY-MM-DD/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.owner_daily.pipeline.constants import day_dir


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def write_fixture_discovery(
    report_date: str,
    fixtures: list[DailyFixture],
    *,
    timezone: str,
    discovery_meta: dict[str, Any] | None = None,
) -> Path:
    d = day_dir(report_date)
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "report_date": report_date,
        "timezone": timezone,
        "generated_at_utc": _utc_now(),
        "fixture_count": len(fixtures),
        "discovery": discovery_meta or {},
        "fixtures": [
            {
                "fixture_id": int(f.fixture_id),
                "provider_fixture_id": int(f.provider_fixture_id),
                "competition": f.competition_key,
                "home_team": f.home_team,
                "away_team": f.away_team,
                "kickoff_utc": f.kickoff_utc,
                "status": f.status,
                "season": f.season,
                "coverage_sources": list(f.coverage_sources or []),
                "provider_ids": dict(f.provider_ids or {}),
            }
            for f in fixtures
        ],
    }
    path = d / "fixture_discovery.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_eligibility_decisions(report_date: str, rows: list[dict[str, Any]]) -> Path:
    d = day_dir(report_date)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "eligibility_decisions.json"
    path.write_text(
        json.dumps(
            {
                "report_date": report_date,
                "generated_at_utc": _utc_now(),
                "count": len(rows),
                "decisions": rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def write_freeze_manifest(report_date: str, rows: list[dict[str, Any]]) -> Path:
    d = day_dir(report_date)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "freeze_manifest.json"
    path.write_text(
        json.dumps(
            {
                "report_date": report_date,
                "generated_at_utc": _utc_now(),
                "count": len(rows),
                "freezes": rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def write_pipeline_status(report_date: str, status: dict[str, Any]) -> Path:
    d = day_dir(report_date)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "pipeline_status.json"
    path.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    return path

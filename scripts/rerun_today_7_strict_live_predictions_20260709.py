#!/usr/bin/env python3
"""Strict live refresh + isolated WDE/ECSE rerun for the 2026-07-09 seven-match batch."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings  # noqa: E402
from worldcup_predictor.database.connection import connect  # noqa: E402
from worldcup_predictor.database.repository import FootballIntelligenceRepository  # noqa: E402
from worldcup_predictor.odds.freshness_metadata import build_fixture_freshness_metadata  # noqa: E402
from worldcup_predictor.odds.freshness_refresh import run_odds_freshness_refresh  # noqa: E402
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture  # noqa: E402
from worldcup_predictor.owner_daily.predictions import run_daily_predictions  # noqa: E402
from worldcup_predictor.research.ecse_live.store import get_snapshot  # noqa: E402

FIXTURE_IDS = (
    1578539,  # France vs Morocco
    1554444,  # Qarabag vs Vestri
    1554445,  # Sheriff vs Aluminij
    1554442,  # Dynamo Kyiv vs Universitatea Cluj
    1554443,  # Hajduk Split vs Zilina
    1554441,  # CSKA Sofia vs Derry City
    1554446,  # Vojvodina vs Ferencvaros
)

RUN_DATE = "2026-07-09"
TIMEZONE = "Europe/Vienna"
ARTIFACT_DIR = Path("artifacts/today_7_strict_live_rerun_20260709")
REPORT_JSON = ARTIFACT_DIR / "rerun_result.json"
REPORT_MD = ARTIFACT_DIR / "rerun_result.md"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fixture_from_db(repo: FootballIntelligenceRepository, fixture_id: int) -> DailyFixture | None:
    row = repo.get_fixture_row(fixture_id)
    if not row:
        return None
    return DailyFixture(
        fixture_id=int(row["fixture_id"]),
        provider_fixture_id=int(row["fixture_id"]),
        competition_key=str(row.get("competition_key") or "world_cup_2026"),
        home_team=str(row.get("home_team") or "Home"),
        away_team=str(row.get("away_team") or "Away"),
        kickoff_utc=str(row.get("kickoff_utc") or ""),
        status=str(row.get("status") or "NS"),
        season=int(row["season"]) if row.get("season") is not None else None,
        coverage_sources=["local_db"],
    )


def _freshness(conn, repo: FootballIntelligenceRepository, fixture: DailyFixture) -> dict[str, Any]:
    row = repo.get_fixture_row(fixture.provider_fixture_id) or {}
    return build_fixture_freshness_metadata(
        conn,
        fixture_id=fixture.provider_fixture_id,
        kickoff_utc=fixture.kickoff_utc,
        round_name=row.get("round_name"),
        status=fixture.status,
        prediction_generated_at=_utc_now(),
    )


def _wde_summary(repo: FootballIntelligenceRepository, fixture_id: int) -> dict[str, Any] | None:
    row = repo.get_worldcup_stored_prediction(fixture_id)
    if not row:
        return None
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError, KeyError):
        return {"status": "unreadable_payload"}
    one_x_two = payload.get("one_x_two") or {}
    return {
        "selection": one_x_two.get("selection"),
        "probabilities": one_x_two.get("probabilities"),
        "confidence": payload.get("confidence_score") or payload.get("confidence"),
        "odds_freshness_status": payload.get("odds_freshness_status"),
        "odds_snapshot_at": payload.get("odds_snapshot_at"),
    }


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# TODAY-7 Strict Live Rerun — 2026-07-09",
        "",
        f"- Started: `{report['started_at']}`",
        f"- Finished: `{report['finished_at']}`",
        f"- Overall status: **{report['status']}**",
        "",
        "| Fixture | Refresh | Freshness | WDE | ECSE Top1 | Prediction status |",
        "|---|---|---|---|---|---|",
    ]
    for item in report["fixtures"]:
        lines.append(
            "| {match} | {refresh} | {freshness} | {wde} | {ecse} | {status} |".format(
                match=item.get("match", item["fixture_id"]),
                refresh=item.get("refresh_status", "—"),
                freshness=item.get("freshness_status", "—"),
                wde=(item.get("wde") or {}).get("selection", "—"),
                ecse=(item.get("ecse") or {}).get("top_1_score", "—"),
                status=item.get("prediction_status", "—"),
            )
        )
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {err}" for err in report["errors"])
    return "\n".join(lines) + "\n"


def main() -> int:
    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    conn = connect(settings.sqlite_path)

    report: dict[str, Any] = {
        "phase": "TODAY-7-STRICT-LIVE-RERUN-20260709",
        "started_at": _utc_now(),
        "fixtures": [],
        "errors": [],
    }

    for fixture_id in FIXTURE_IDS:
        fixture = _fixture_from_db(repo, fixture_id)
        if fixture is None:
            report["errors"].append(f"fixture {fixture_id}: missing from local DB")
            report["fixtures"].append(
                {
                    "fixture_id": fixture_id,
                    "prediction_status": "blocked_missing_fixture",
                }
            )
            continue

        item: dict[str, Any] = {
            "fixture_id": fixture_id,
            "match": f"{fixture.home_team} vs {fixture.away_team}",
            "competition_key": fixture.competition_key,
        }

        refresh = run_odds_freshness_refresh(
            date_arg=RUN_DATE,
            timezone=TIMEZONE,
            competition_keys=[fixture.competition_key],
            fixture_id=fixture_id,
            mode="refresh",
            max_provider_calls=1,
            dry_run=False,
            settings=settings,
        )
        refresh_fixture = next(
            (entry for entry in refresh.fixtures if int(entry["fixture_id"]) == fixture_id),
            {},
        )
        refresh_result = refresh_fixture.get("refresh_result") or {}
        item["refresh_status"] = refresh_result.get("status") or (
            "already_fresh" if refresh.fresh_count else "not_refreshed"
        )
        item["refresh"] = refresh.to_dict()

        freshness = _freshness(conn, repo, fixture)
        item["freshness"] = freshness
        item["freshness_status"] = freshness.get("odds_freshness_status") or freshness.get("freshness_flag")

        if freshness.get("requires_fresh_odds"):
            item["prediction_status"] = "blocked_not_fresh"
            report["errors"].append(
                f"fixture {fixture_id}: blocked because odds are not fresh ({item['freshness_status']})"
            )
            report["fixtures"].append(item)
            continue

        prediction = run_daily_predictions(
            [fixture],
            mode="wde_and_ecse",
            dry_run=False,
            force=True,
            strict_fresh_odds=True,
            settings=settings,
        )
        item["prediction_run"] = prediction.to_dict()
        item["prediction_status"] = (
            "generated"
            if prediction.wde_generated > 0 and prediction.ecse_generated > 0
            else "partial_or_blocked"
        )
        item["wde"] = _wde_summary(repo, fixture_id)
        item["ecse"] = get_snapshot(conn, fixture_id)

        if item["prediction_status"] != "generated":
            report["errors"].append(
                f"fixture {fixture_id}: prediction rerun incomplete; "
                f"WDE={prediction.wde_generated}, ECSE={prediction.ecse_generated}"
            )
        report["fixtures"].append(item)

    conn.close()
    report["finished_at"] = _utc_now()
    report["status"] = "PASSED" if not report["errors"] else "PARTIAL_OR_BLOCKED"

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    REPORT_MD.write_text(_render_md(report), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": report["status"],
                "fixtures": len(report["fixtures"]),
                "errors": report["errors"],
                "report_json": str(REPORT_JSON),
                "report_md": str(REPORT_MD),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

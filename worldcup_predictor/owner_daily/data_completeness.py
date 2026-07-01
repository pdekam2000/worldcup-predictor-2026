"""Part B — Per-fixture data completeness checker."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner.euro_b_fixture_selector import _odds_flags
from worldcup_predictor.owner_daily.constants import GENERATED_BY, PHASE
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.quota.local_first import UNFINISHED_LOCAL_STATUSES, should_bypass_stale_local_fixture

Priority = Literal["HIGH", "MEDIUM", "LOW"]


@dataclass
class MissingFieldReport:
    missing_field: str
    provider_candidate: str
    can_fetch_now: bool
    priority: Priority
    quota_cost_estimate: int
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "missing_field": self.missing_field,
            "provider_candidate": self.provider_candidate,
            "can_fetch_now": self.can_fetch_now,
            "priority": self.priority,
            "quota_cost_estimate": self.quota_cost_estimate,
            "reason": self.reason,
        }


@dataclass
class FixtureCompletenessReport:
    fixture_id: int
    competition_key: str
    complete: bool = False
    wde_ready: bool = False
    ecse_ready: bool = False
    missing: list[MissingFieldReport] = field(default_factory=list)
    present: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "competition_key": self.competition_key,
            "complete": self.complete,
            "wde_ready": self.wde_ready,
            "ecse_ready": self.ecse_ready,
            "missing": [m.to_dict() for m in self.missing],
            "present": self.present,
        }


def _has_enrichment(repo: FootballIntelligenceRepository, fixture_id: int, key: str) -> bool:
    row = repo.get_fixture_enrichment_row(fixture_id)
    if not row:
        return False
    blob = row.get("payload_json") or row.get("enrichment_json")
    if not blob:
        return False
    try:
        data = json.loads(blob) if isinstance(blob, str) else blob
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    return key in data and data[key] is not None


def _missing(
    reports: list[MissingFieldReport],
    *,
    field_name: str,
    provider: str,
    can_fetch: bool,
    priority: Priority,
    cost: int = 1,
    reason: str = "",
) -> None:
    reports.append(
        MissingFieldReport(
            missing_field=field_name,
            provider_candidate=provider,
            can_fetch_now=can_fetch,
            priority=priority,
            quota_cost_estimate=cost,
            reason=reason,
        )
    )


def check_fixture_completeness(
    conn: sqlite3.Connection,
    repo: FootballIntelligenceRepository,
    fixture: DailyFixture,
    *,
    api_football_configured: bool = True,
    sportmonks_configured: bool = False,
    oddalerts_configured: bool = False,
) -> FixtureCompletenessReport:
    fid = fixture.provider_fixture_id
    report = FixtureCompletenessReport(fixture_id=fid, competition_key=fixture.competition_key)
    missing: list[MissingFieldReport] = []
    present: list[str] = []

    row = repo.get_fixture_row(fid) or {}
    if row.get("fixture_id"):
        present.append("fixture_id")
    else:
        _missing(missing, field_name="fixture_id", provider="api_football", can_fetch=True, priority="HIGH")

    if fixture.provider_ids:
        present.append("provider_fixture_ids")
    else:
        _missing(missing, field_name="provider_fixture_ids", provider="api_football", can_fetch=True, priority="HIGH")

    if fixture.competition_key:
        present.append("competition_key")
    if fixture.season or row.get("season"):
        present.append("season")
    else:
        _missing(missing, field_name="season", provider="api_football", can_fetch=True, priority="MEDIUM")

    if fixture.kickoff_utc:
        present.append("kickoff_utc")
    if fixture.home_team and fixture.away_team:
        present.append("teams")
    if fixture.status:
        present.append("status")

    odds = _odds_flags(conn, fid)
    if odds.get("has_odds"):
        present.append("odds_snapshot")
        if odds.get("odds_1x2"):
            present.append("odds_1x2")
        else:
            _missing(
                missing,
                field_name="odds_1x2",
                provider="api_football" if api_football_configured else "oddalerts",
                can_fetch=api_football_configured or oddalerts_configured,
                priority="HIGH",
            )
        for line, prov in (
            ("odds_ou_1_5", "api_football"),
            ("odds_ou_2_5", "api_football"),
            ("odds_ou_3_5", "api_football"),
        ):
            if odds.get("odds_ou"):
                present.append(line)
            else:
                _missing(
                    missing,
                    field_name=line,
                    provider=prov,
                    can_fetch=api_football_configured or oddalerts_configured,
                    priority="HIGH" if "2_5" in line else "MEDIUM",
                )
        if odds.get("odds_btts"):
            present.append("odds_btts")
        else:
            _missing(
                missing,
                field_name="odds_btts",
                provider="api_football",
                can_fetch=api_football_configured or oddalerts_configured,
                priority="HIGH",
            )
        if odds.get("odds_correct_score"):
            present.append("odds_correct_score")
        else:
            _missing(
                missing,
                field_name="odds_correct_score",
                provider="oddalerts",
                can_fetch=oddalerts_configured,
                priority="LOW",
                reason="optional market",
            )
        if odds.get("odds_snapshot_at"):
            present.append("odds_timestamp")
        if odds.get("odds_source"):
            present.append("odds_source")
    else:
        for fld, pri in (
            ("odds_1x2", "HIGH"),
            ("odds_ou_2_5", "HIGH"),
            ("odds_btts", "HIGH"),
            ("odds_bookmaker_count", "MEDIUM"),
            ("odds_timestamp", "MEDIUM"),
            ("odds_source", "MEDIUM"),
        ):
            _missing(
                missing,
                field_name=fld,
                provider="api_football",
                can_fetch=api_football_configured or oddalerts_configured,
                priority=pri,  # type: ignore[arg-type]
            )

    intel_checks = [
        ("recent_form", "api_football", "MEDIUM"),
        ("standings", "api_football", "MEDIUM"),
        ("head_to_head", "api_football", "MEDIUM"),
        ("injuries", "api_football", "MEDIUM"),
        ("lineups", "api_football", "MEDIUM"),
        ("formations", "api_football", "MEDIUM"),
        ("referee", "api_football", "MEDIUM"),
        ("team_statistics", "api_football", "MEDIUM"),
        ("xg", "sportmonks", "LOW"),
        ("pressure_index", "sportmonks", "LOW"),
        ("events", "api_football", "LOW"),
    ]
    for key, prov, pri in intel_checks:
        if key == "xg" and repo.has_xg_snapshot(fid):
            present.append("xg")
        elif key == "pressure_index" and _has_enrichment(repo, fid, "pressure"):
            present.append("pressure_index")
        elif key in ("lineups", "formations") and _has_enrichment(repo, fid, key):
            present.append(key)
        elif key == "injuries" and _has_enrichment(repo, fid, "injuries"):
            present.append("injuries")
        else:
            can = api_football_configured if prov == "api_football" else sportmonks_configured
            _missing(
                missing,
                field_name=key,
                provider=prov,
                can_fetch=can,
                priority=pri,  # type: ignore[arg-type]
                reason="optional enrichment",
            )

    wde_row = repo.get_worldcup_stored_prediction(fid)
    has_wde = bool(wde_row and wde_row.get("payload_json"))
    if has_wde:
        present.append("wde_prediction")
    else:
        _missing(
            missing,
            field_name="wde_prediction",
            provider="internal",
            can_fetch=True,
            priority="HIGH",
            cost=0,
            reason="generate via PredictPipeline",
        )

    ecse_row = conn.execute(
        "SELECT id FROM ecse_prediction_snapshots WHERE fixture_id = ? ORDER BY id DESC LIMIT 1",
        (fid,),
    ).fetchone()
    if ecse_row:
        present.append("ecse_snapshot")
    else:
        _missing(
            missing,
            field_name="ecse_snapshot",
            provider="internal",
            can_fetch=True,
            priority="HIGH",
            cost=0,
            reason="requires odds lambda inputs",
        )

    shadow = None
    try:
        shadow = conn.execute(
            """
            SELECT id FROM ecse_x2_m6_shadow_shortlists
            WHERE fixture_id = ? ORDER BY id DESC LIMIT 1
            """,
            (fid,),
        ).fetchone()
    except Exception:
        shadow = None
    if shadow:
        present.append("owner_shadow_lab")
    else:
        _missing(
            missing,
            field_name="owner_shadow_lab",
            provider="internal",
            can_fetch=False,
            priority="LOW",
            cost=0,
            reason="optional shadow shortlist",
        )

    result_row = repo.get_fixture_result_row(fid)
    status = str(fixture.status or row.get("status") or "NS").upper()
    kickoff_passed = False
    if fixture.kickoff_utc:
        try:
            ko = datetime.fromisoformat(str(fixture.kickoff_utc).replace("Z", "+00:00"))
            if ko.tzinfo is None:
                ko = ko.replace(tzinfo=timezone.utc)
            kickoff_passed = ko < datetime.now(timezone.utc)
        except ValueError:
            pass
    if kickoff_passed and status in UNFINISHED_LOCAL_STATUSES:
        _missing(
            missing,
            field_name="fixture_status_refresh",
            provider="api_football",
            can_fetch=api_football_configured,
            priority="HIGH",
            reason="kickoff passed but status stale",
        )
    if result_row:
        present.append("result")
        eval_row = repo.get_worldcup_prediction_evaluation(fid)
        if eval_row:
            present.append("wde_evaluation")
        ecse_eval = conn.execute(
            "SELECT id FROM ecse_prediction_evaluations WHERE fixture_id = ? LIMIT 1",
            (fid,),
        ).fetchone()
        if ecse_eval:
            present.append("ecse_evaluation")
    elif kickoff_passed and status not in UNFINISHED_LOCAL_STATUSES:
        _missing(
            missing,
            field_name="result",
            provider="api_football",
            can_fetch=api_football_configured,
            priority="HIGH",
        )

    report.missing = missing
    report.present = present
    high_missing = [m for m in missing if m.priority == "HIGH" and m.missing_field.startswith("odds")]
    report.wde_ready = has_wde or (
        api_football_configured
        and "teams" in present
        and "kickoff_utc" in present
        and not any(m.missing_field == "fixture_id" for m in missing)
    )
    report.ecse_ready = bool(ecse_row) or (
        odds.get("has_odds")
        and odds.get("odds_1x2")
        and odds.get("odds_ou")
        and not high_missing
    )
    report.complete = len([m for m in missing if m.priority == "HIGH"]) == 0
    return report


def check_all_fixtures_completeness(
    conn: sqlite3.Connection,
    repo: FootballIntelligenceRepository,
    fixtures: list[DailyFixture],
    *,
    api_football_configured: bool = True,
    sportmonks_configured: bool = False,
    oddalerts_configured: bool = False,
) -> list[FixtureCompletenessReport]:
    return [
        check_fixture_completeness(
            conn,
            repo,
            fx,
            api_football_configured=api_football_configured,
            sportmonks_configured=sportmonks_configured,
            oddalerts_configured=oddalerts_configured,
        )
        for fx in fixtures
    ]


def summarize_completeness(
    reports: list[FixtureCompletenessReport],
    *,
    provider_calls: dict[str, int],
    fetched_counts: dict[str, int] | None = None,
    skipped_reasons: dict[str, int] | None = None,
    result_sync_count: int = 0,
    evaluation_count: int = 0,
) -> dict[str, Any]:
    by_comp: dict[str, int] = {}
    missing_by_field: dict[str, int] = {}
    missing_by_provider: dict[str, int] = {}
    for r in reports:
        by_comp[r.competition_key] = by_comp.get(r.competition_key, 0) + 1
        for m in r.missing:
            missing_by_field[m.missing_field] = missing_by_field.get(m.missing_field, 0) + 1
            missing_by_provider[m.provider_candidate] = missing_by_provider.get(m.provider_candidate, 0) + 1
    return {
        "phase": PHASE,
        "fixture_count": len(reports),
        "fixture_count_by_competition": by_comp,
        "missing_data_by_field": missing_by_field,
        "missing_data_by_provider": missing_by_provider,
        "fetched_data_counts": fetched_counts or {},
        "skipped_reasons": skipped_reasons or {},
        "provider_calls_used": provider_calls,
        "ecse_ready_count": sum(1 for r in reports if r.ecse_ready),
        "wde_ready_count": sum(1 for r in reports if r.wde_ready),
        "result_sync_count": result_sync_count,
        "evaluation_count": evaluation_count,
    }

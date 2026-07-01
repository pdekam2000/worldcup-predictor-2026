"""Part E — Owner daily WDE/ECSE prediction generation (no logic changes)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from worldcup_predictor.automation.worldcup_background.prediction_runner import build_api_payload
from worldcup_predictor.config.provider_readiness import stamp_provider_readiness
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
from worldcup_predictor.owner.euro_b_fixture_selector import UefaFixtureSelection, odds_readiness_audit
from worldcup_predictor.owner_daily.constants import GENERATED_BY, PHASE
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.research.ecse_live.prediction_builder import build_ecse_live_prediction
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables, has_snapshot, insert_snapshot


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@dataclass
class DailyPredictionResult:
    phase: str = PHASE
    dry_run: bool = False
    selected: int = 0
    wde_generated: int = 0
    wde_skipped: int = 0
    ecse_generated: int = 0
    ecse_skipped: int = 0
    wde_skip_reasons: dict[str, int] = field(default_factory=dict)
    ecse_skip_reasons: dict[str, int] = field(default_factory=dict)
    generated: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "dry_run": self.dry_run,
            "selected": self.selected,
            "wde_generated": self.wde_generated,
            "wde_skipped": self.wde_skipped,
            "ecse_generated": self.ecse_generated,
            "ecse_skipped": self.ecse_skipped,
            "wde_skip_reasons": self.wde_skip_reasons,
            "ecse_skip_reasons": self.ecse_skip_reasons,
            "generated_sample": self.generated[:20],
            "skipped_sample": self.skipped[:50],
            "completed_at_utc": _utc_now_iso(),
        }


def _inc(bucket: dict[str, int], key: str) -> None:
    bucket[key] = bucket.get(key, 0) + 1


def _to_selection(fixture: DailyFixture) -> UefaFixtureSelection:
    return UefaFixtureSelection(
        fixture_id=fixture.fixture_id,
        provider_fixture_id=fixture.provider_fixture_id,
        competition_key=fixture.competition_key,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        kickoff_utc=fixture.kickoff_utc,
        status=fixture.status,
        provider_source="api-football",
        crosswalk_confidence=1.0,
        crosswalk_status="canonical_api",
        has_odds=False,
        has_wde=False,
        has_ecse=False,
    )


def _existing_wde(repo: FootballIntelligenceRepository, fixture_id: int, competition_key: str) -> bool:
    row = repo.get_worldcup_stored_prediction(fixture_id)
    if not row:
        return False
    if str(row.get("competition_key") or "") != competition_key:
        return False
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return True
    gen = str(payload.get("generated_by") or "")
    return gen != GENERATED_BY and bool(payload)


def run_daily_wde(
    fixture: DailyFixture,
    *,
    settings: Settings,
    repo: FootballIntelligenceRepository,
    dry_run: bool,
    force: bool,
) -> tuple[str, dict[str, Any]]:
    sel = _to_selection(fixture)
    fid = sel.provider_fixture_id
    comp_key = sel.competition_key
    detail: dict[str, Any] = {"fixture_id": fid, "competition_key": comp_key, "engine": "wde"}

    if not force and _existing_wde(repo, fid, comp_key):
        detail["reason"] = "existing_prediction"
        return "skipped", detail

    if not settings.api_football_configured:
        detail["reason"] = "missing_fixture_context"
        return "skipped", detail

    if dry_run:
        detail["reason"] = "dry_run_would_generate"
        return "dry_run", detail

    try:
        pipeline = PredictPipeline(settings, competition_key=comp_key, locale="en")
        result = pipeline.run(fixture_id=fid, record_history=False)
    except Exception as exc:
        detail["reason"] = "engine_error"
        detail["error"] = str(exc)
        return "skipped", detail

    if not result.success:
        detail["reason"] = "missing_team_data"
        return "skipped", detail

    from worldcup_predictor.api.prediction_metadata import stamp_prediction_engine_metadata

    payload = build_api_payload(
        result,
        intelligence_report=result.intelligence_report,
        specialist_report=result.specialist_report,
    )
    payload = stamp_prediction_engine_metadata(
        payload, prediction=result.prediction, generated_by=GENERATED_BY
    )
    payload = stamp_provider_readiness(payload, settings=settings)
    payload["owner_only"] = True
    payload["competition_key"] = comp_key
    payload["data_source_trace"] = {
        "phase": PHASE,
        "provider_fixture_id": fid,
        "provider_source": sel.provider_source,
        "crosswalk_status": sel.crosswalk_status,
    }

    repo.upsert_worldcup_stored_prediction(
        fixture_id=fid,
        payload=payload,
        kickoff_utc=payload.get("kickoff_utc") or sel.kickoff_utc,
        source=GENERATED_BY,
        competition_key=comp_key,
    )
    detail.update(
        {
            "confidence": payload.get("confidence_score") or payload.get("confidence"),
            "no_bet_flag": payload.get("no_bet_flag"),
            "predicted_1x2": (payload.get("one_x_two") or {}).get("selection"),
        }
    )
    return "generated", detail


def run_daily_ecse(
    fixture: DailyFixture,
    *,
    settings: Settings,
    conn,
    dry_run: bool,
    force: bool,
) -> tuple[str, dict[str, Any]]:
    sel = _to_selection(fixture)
    fid = sel.provider_fixture_id
    comp_key = sel.competition_key
    detail: dict[str, Any] = {"fixture_id": fid, "competition_key": comp_key, "engine": "ecse"}

    audit = odds_readiness_audit(conn, sel)
    detail["odds_audit"] = audit
    if not audit.get("lambda_inputs_available"):
        if not audit.get("has_odds"):
            detail["reason"] = "missing_odds"
        else:
            detail["reason"] = "missing_lambda_inputs"
        return "skipped", detail

    if has_snapshot(conn, fid) and not force:
        detail["reason"] = "existing_snapshot"
        return "skipped", detail

    if dry_run:
        detail["reason"] = "dry_run_would_generate"
        return "dry_run", detail

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    fx_row = {
        "fixture_id": fid,
        "competition_key": comp_key,
        "home_team": sel.home_team,
        "away_team": sel.away_team,
        "kickoff_utc": sel.kickoff_utc,
        "status": sel.status,
    }
    try:
        prediction = build_ecse_live_prediction(conn, fid, fx_row)
    except Exception as exc:
        detail["reason"] = "engine_error"
        detail["error"] = str(exc)
        return "skipped", detail

    if not prediction:
        detail["reason"] = "missing_team_strength"
        return "skipped", detail

    prediction["prediction_source"] = GENERATED_BY
    raw = prediction.get("raw_features") or {}
    if isinstance(raw, dict):
        raw["owner_only"] = True
        raw["generated_by"] = GENERATED_BY
        prediction["raw_features"] = raw

    sid, reason = insert_snapshot(conn, prediction)
    if reason != "inserted":
        detail["reason"] = reason
        return "skipped", detail

    detail.update(
        {
            "snapshot_id": sid,
            "top_1_score": prediction.get("top_1_score"),
            "confidence_score": prediction.get("confidence_score"),
        }
    )
    return "generated", detail


def run_daily_predictions(
    fixtures: list[DailyFixture],
    *,
    mode: Literal["wde_only", "ecse_only", "wde_and_ecse"] = "wde_and_ecse",
    dry_run: bool = False,
    force: bool = False,
    settings: Settings | None = None,
) -> DailyPredictionResult:
    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    ensure_ecse_live_tables(conn)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    result = DailyPredictionResult(dry_run=dry_run, selected=len(fixtures))
    for fixture in fixtures:
        if mode in ("wde_only", "wde_and_ecse"):
            status, detail = run_daily_wde(
                fixture, settings=settings, repo=repo, dry_run=dry_run, force=force
            )
            if status in ("generated", "dry_run"):
                result.wde_generated += 1
                result.generated.append(detail)
            else:
                result.wde_skipped += 1
                _inc(result.wde_skip_reasons, str(detail.get("reason") or "skipped"))
                result.skipped.append(detail)

        if mode in ("ecse_only", "wde_and_ecse"):
            status, detail = run_daily_ecse(
                fixture, settings=settings, conn=conn, dry_run=dry_run, force=force
            )
            if status in ("generated", "dry_run"):
                result.ecse_generated += 1
                result.generated.append(detail)
            else:
                result.ecse_skipped += 1
                _inc(result.ecse_skip_reasons, str(detail.get("reason") or "skipped"))
                result.skipped.append(detail)

    return result

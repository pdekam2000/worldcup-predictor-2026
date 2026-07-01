"""PHASE EURO-B — Owner-only UEFA WDE/ECSE prediction wiring (no logic changes)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.automation.worldcup_background.prediction_runner import build_api_payload
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.provider_readiness import stamp_provider_readiness
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
from worldcup_predictor.owner.euro_b_fixture_selector import (
    UefaFixtureSelection,
    build_duplicate_candidate_report,
    odds_readiness_audit,
    select_upcoming_uefa_fixtures,
)
from worldcup_predictor.research.ecse_live.prediction_builder import build_ecse_live_prediction
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables, has_snapshot, insert_snapshot

PHASE = "EURO-B"
GENERATED_BY = "owner_euro_b"
ARTIFACTS = Path("artifacts")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@dataclass
class OwnerUefaRunResult:
    phase: str = PHASE
    dry_run: bool = False
    mode: str = "wde_and_ecse"
    selected: int = 0
    wde_generated: int = 0
    wde_skipped: int = 0
    ecse_generated: int = 0
    ecse_skipped: int = 0
    wde_skip_reasons: dict[str, int] = field(default_factory=dict)
    ecse_skip_reasons: dict[str, int] = field(default_factory=dict)
    generated: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    odds_audit: list[dict[str, Any]] = field(default_factory=list)
    by_competition: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "dry_run": self.dry_run,
            "mode": self.mode,
            "selected": self.selected,
            "wde_generated": self.wde_generated,
            "wde_skipped": self.wde_skipped,
            "ecse_generated": self.ecse_generated,
            "ecse_skipped": self.ecse_skipped,
            "wde_skip_reasons": self.wde_skip_reasons,
            "ecse_skip_reasons": self.ecse_skip_reasons,
            "by_competition": self.by_competition,
            "generated_sample": self.generated[:20],
            "skipped_sample": self.skipped[:50],
            "completed_at_utc": _utc_now_iso(),
        }


def _inc(bucket: dict[str, int], key: str) -> None:
    bucket[key] = bucket.get(key, 0) + 1


def _fixture_row_for_selection(
    repo: FootballIntelligenceRepository,
    selection: UefaFixtureSelection,
) -> dict[str, Any]:
    row = repo.get_fixture_row(selection.provider_fixture_id) or {}
    return {
        "fixture_id": selection.provider_fixture_id,
        "competition_key": selection.competition_key,
        "home_team": row.get("home_team") or selection.home_team,
        "away_team": row.get("away_team") or selection.away_team,
        "kickoff_utc": row.get("kickoff_utc") or selection.kickoff_utc,
        "status": row.get("status") or selection.status,
    }


def _existing_wde(
    repo: FootballIntelligenceRepository,
    fixture_id: int,
    competition_key: str,
) -> bool:
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


def run_owner_wde(
    selection: UefaFixtureSelection,
    *,
    settings: Settings,
    repo: FootballIntelligenceRepository,
    dry_run: bool,
    force: bool,
) -> tuple[str, dict[str, Any]]:
    fid = selection.provider_fixture_id
    comp_key = selection.competition_key
    detail: dict[str, Any] = {
        "fixture_id": fid,
        "competition_key": comp_key,
        "engine": "wde",
    }

    if selection.skip_reason:
        detail["reason"] = selection.skip_reason
        return "skipped", detail
    if selection.duplicate_risk:
        detail["reason"] = "duplicate_risk"
        return "skipped", detail
    if selection.crosswalk_status == "sportmonks_only":
        detail["reason"] = "provider_mapping_missing"
        return "skipped", detail

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
        "provider_source": selection.provider_source,
        "crosswalk_status": selection.crosswalk_status,
    }

    repo.upsert_worldcup_stored_prediction(
        fixture_id=fid,
        payload=payload,
        kickoff_utc=payload.get("kickoff_utc") or selection.kickoff_utc,
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


def run_owner_ecse(
    selection: UefaFixtureSelection,
    *,
    settings: Settings,
    conn,
    dry_run: bool,
    force: bool,
) -> tuple[str, dict[str, Any]]:
    fid = selection.provider_fixture_id
    comp_key = selection.competition_key
    detail: dict[str, Any] = {
        "fixture_id": fid,
        "competition_key": comp_key,
        "engine": "ecse",
    }

    if selection.skip_reason:
        detail["reason"] = selection.skip_reason
        return "skipped", detail
    if selection.duplicate_risk:
        detail["reason"] = "duplicate_provider_match_risk"
        return "skipped", detail
    if selection.crosswalk_status == "sportmonks_only":
        detail["reason"] = "provider_mapping_missing"
        return "skipped", detail

    audit = odds_readiness_audit(conn, selection)
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
    fx_row = _fixture_row_for_selection(repo, selection)
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


def run_owner_uefa_predictions(
    *,
    competition_keys: list[str] | None = None,
    days_ahead: int = 30,
    mode: Literal["wde_only", "ecse_only", "wde_and_ecse"] = "wde_and_ecse",
    dry_run: bool = False,
    force: bool = False,
    settings: Settings | None = None,
) -> OwnerUefaRunResult:
    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    ensure_ecse_live_tables(conn)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    keys = competition_keys or list(UEFA_CUP_KEYS)
    selections = [
        s
        for s in select_upcoming_uefa_fixtures(conn, competition_keys=keys, days_ahead=days_ahead)
        if s.crosswalk_status != "sportmonks_only" or s.crosswalk_confidence >= 0.95
    ]
    # Prefer one row per canonical provider_fixture_id
    seen_provider: set[int] = set()
    deduped: list[UefaFixtureSelection] = []
    for sel in selections:
        if sel.provider_fixture_id in seen_provider:
            continue
        seen_provider.add(sel.provider_fixture_id)
        deduped.append(sel)

    result = OwnerUefaRunResult(dry_run=dry_run, mode=mode, selected=len(deduped))
    for key in keys:
        result.by_competition[key] = {
            "selected": 0,
            "wde_generated": 0,
            "ecse_generated": 0,
            "wde_skipped": 0,
            "ecse_skipped": 0,
        }

    for sel in deduped:
        comp_stats = result.by_competition.setdefault(
            sel.competition_key,
            {"selected": 0, "wde_generated": 0, "ecse_generated": 0, "wde_skipped": 0, "ecse_skipped": 0},
        )
        comp_stats["selected"] += 1
        result.odds_audit.append(odds_readiness_audit(conn, sel))

        if mode in ("wde_only", "wde_and_ecse"):
            status, detail = run_owner_wde(
                sel, settings=settings, repo=repo, dry_run=dry_run, force=force
            )
            if status == "generated":
                result.wde_generated += 1
                comp_stats["wde_generated"] += 1
                result.generated.append(detail)
            elif status == "dry_run":
                result.wde_generated += 1
                comp_stats["wde_generated"] += 1
                result.generated.append(detail)
            else:
                result.wde_skipped += 1
                comp_stats["wde_skipped"] += 1
                reason = str(detail.get("reason") or "skipped")
                _inc(result.wde_skip_reasons, reason)
                result.skipped.append(detail)

        if mode in ("ecse_only", "wde_and_ecse"):
            status, detail = run_owner_ecse(
                sel, settings=settings, conn=conn, dry_run=dry_run, force=force
            )
            if status == "generated":
                result.ecse_generated += 1
                comp_stats["ecse_generated"] += 1
                result.generated.append(detail)
            elif status == "dry_run":
                result.ecse_generated += 1
                comp_stats["ecse_generated"] += 1
                result.generated.append(detail)
            else:
                result.ecse_skipped += 1
                comp_stats["ecse_skipped"] += 1
                reason = str(detail.get("reason") or "skipped")
                _inc(result.ecse_skip_reasons, reason)
                result.skipped.append(detail)

    dup_report = build_duplicate_candidate_report(conn, competition_keys=keys, days_ahead=days_ahead)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "euro_b_provider_duplicate_candidates.json").write_text(
        json.dumps(dup_report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    summary = result.to_dict()
    summary["odds_readiness"] = result.odds_audit
    summary["duplicate_candidates"] = dup_report
    (ARTIFACTS / "euro_b_owner_prediction_wiring_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    gen_path = ARTIFACTS / "euro_b_generated_predictions.jsonl"
    skip_path = ARTIFACTS / "euro_b_skipped_fixtures.jsonl"
    with gen_path.open("w", encoding="utf-8") as fh:
        for item in result.generated:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    with skip_path.open("w", encoding="utf-8") as fh:
        for item in result.skipped:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    return result


def verify_uefa_result_sync_readiness(
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Part G — scanner supports UEFA; future fixtures should not appear as past candidates."""
    from worldcup_predictor.research.ecse_live.result_sync import scan_ecse_snapshot_result_candidates

    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    out: dict[str, Any] = {"competitions": {}}
    for key in UEFA_CUP_KEYS:
        get_competition(key)
        future = scan_ecse_snapshot_result_candidates(
            conn, competition_key=key, past_only=False, min_hours_since_kickoff=0
        )
        upcoming = [c for c in future if _parse_kickoff_safe(c.kickoff_time) and _parse_kickoff_safe(c.kickoff_time) > datetime.now(timezone.utc)]  # type: ignore[arg-type]
        out["competitions"][key] = {
            "scanner_supported": True,
            "future_candidate_count": len(future),
            "upcoming_in_scan": len(upcoming),
        }
    return out


def _parse_kickoff_safe(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

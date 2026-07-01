"""Owner-only WDE/ECSE production snapshot generation for resolved knockout fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.automation.worldcup_background.prediction_runner import build_api_payload
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.provider_readiness import stamp_provider_readiness
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
from worldcup_predictor.owner.euro_b_fixture_selector import UefaFixtureSelection, odds_readiness_audit
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.owner_manual_exact.constants import ARTIFACTS_DIR, PHASE, REPORTS_DIR, with_safety_labels
from worldcup_predictor.owner_manual_exact.knockout_ecse_common import (
    compute_ecse_layers,
    minimum_ecse_inputs_met,
)
from worldcup_predictor.owner_manual_exact.resolver import _date_tag, load_resolution_artifact
from worldcup_predictor.owner_manual_exact.score_engine import estimate_lambdas_from_1x2, markets_from_odds, poisson_score_distribution
from worldcup_predictor.research.ecse_live.prediction_builder import build_ecse_live_prediction, build_odds_feature_row
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables, has_snapshot, insert_snapshot
from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas

GENERATED_BY = "owner_knockout_production"
KNOCKOUT_SAFETY: dict[str, bool] = {
    "PUBLIC_PUBLISH": False,
    "WDE_RETRAINED": False,
    "EGIE_RETRAINED": False,
    "HISTORICAL_CSV_PROMOTED": False,
    "FRONTEND_PUBLISH": False,
    "PUBLIC_ARCHIVE_PUBLISH": False,
    "OWNER_ONLY": True,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _inc(bucket: dict[str, int], key: str) -> None:
    bucket[key] = bucket.get(key, 0) + 1


def _screenshot_odds_payload(
    *,
    odds_1x2: dict[str, float],
    btts_odds: dict[str, float],
) -> dict[str, Any]:
    markets = markets_from_odds(odds_1x2, btts_odds)
    ou_over_prob = 0.0
    for s in markets.get("top_scores") or []:
        parts = str(s.get("scoreline", "0-0")).split("-")
        if len(parts) == 2:
            try:
                if int(parts[0]) + int(parts[1]) > 2:
                    ou_over_prob += float(s.get("probability") or 0)
            except ValueError:
                pass
    ou_over_prob = min(max(ou_over_prob, 0.08), 0.92)
    over_odd = round(1.0 / ou_over_prob, 2)
    under_odd = round(1.0 / (1.0 - ou_over_prob), 2)
    return {
        "snapshot_at": _utc_now_iso(),
        "source": "owner_manual_screenshot",
        "owner_only": True,
        "generated_by": GENERATED_BY,
        "api_sports": {
            "bookmakers": [
                {
                    "name": "screenshot",
                    "bets": [
                        {
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": odds_1x2.get("home")},
                                {"value": "Draw", "odd": odds_1x2.get("draw")},
                                {"value": "Away", "odd": odds_1x2.get("away")},
                            ],
                        },
                        {
                            "name": "Goals Over/Under",
                            "values": [
                                {"value": "Over 2.5", "odd": over_odd},
                                {"value": "Under 2.5", "odd": under_odd},
                            ],
                        },
                        {
                            "name": "Both Teams Score",
                            "values": [
                                {"value": "Yes", "odd": btts_odds.get("yes")},
                                {"value": "No", "odd": btts_odds.get("no")},
                            ],
                        },
                    ],
                }
            ]
        },
    }


def _fetch_api_odds_payload(client: ApiFootballClient, fixture_id: int) -> dict[str, Any] | None:
    if not client.is_configured:
        return None
    res = client.get_odds(int(fixture_id))
    if not res.ok:
        return None
    odds_items = res.data if isinstance(res.data, list) else []
    bookmakers: list[dict[str, Any]] = []
    for item in odds_items:
        if isinstance(item, dict):
            bookmakers.extend(item.get("bookmakers") or [])
    if not bookmakers:
        return None
    return {
        "snapshot_at": _utc_now_iso(),
        "source": "api_football",
        "owner_only": True,
        "generated_by": GENERATED_BY,
        "api_sports": {"bookmakers": bookmakers},
    }


def ensure_owner_odds_snapshot(
    repo: FootballIntelligenceRepository,
    conn,
    *,
    fixture_id: int,
    competition_key: str,
    odds_1x2: dict[str, float] | None,
    btts_odds: dict[str, float] | None,
    settings: Settings,
    force: bool,
) -> tuple[str, dict[str, Any]]:
    """Bootstrap odds_snapshots for ECSE when missing (owner-only)."""
    detail: dict[str, Any] = {"fixture_id": fixture_id, "step": "odds_bootstrap"}
    existing = repo.has_odds_snapshot(fixture_id)
    if existing and not force:
        row = build_odds_feature_row(conn, fixture_id)
        if row and extract_lambdas(row):
            detail["reason"] = "existing_odds_snapshot"
            return "skipped", detail

    payload: dict[str, Any] | None = None
    source = "none"
    client = ApiFootballClient(settings)
    if client.is_configured:
        payload = _fetch_api_odds_payload(client, fixture_id)
        if payload:
            source = "api_football"

    if not payload and odds_1x2 and btts_odds:
        payload = _screenshot_odds_payload(odds_1x2=odds_1x2, btts_odds=btts_odds)
        source = "owner_manual_screenshot"

    if not payload:
        detail["reason"] = "missing_odds"
        return "skipped", detail

    if not existing or force:
        repo.save_snapshot(
            "odds_snapshots",
            fixture_id=fixture_id,
            competition_key=competition_key,
            payload=payload,
        )

    row = build_odds_feature_row(conn, fixture_id)
    if not row or extract_lambdas(row) is None:
        detail["reason"] = "missing_lambda_inputs"
        detail["odds_source_attempted"] = source
        return "skipped", detail

    detail.update({"reason": "inserted", "odds_source": source})
    return "bootstrapped", detail


def _has_wde_prediction(repo: FootballIntelligenceRepository, fixture_id: int, competition_key: str) -> bool:
    row = repo.get_worldcup_stored_prediction(fixture_id)
    if not row:
        return False
    return str(row.get("competition_key") or "") == competition_key


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


def _fixture_from_resolution_row(conn, row: dict[str, Any]) -> DailyFixture | None:
    res = row.get("resolution") or {}
    fid = res.get("fixture_id")
    if not fid:
        return None
    fx = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, status, competition_key
        FROM fixtures WHERE fixture_id = ?
        """,
        (int(fid),),
    ).fetchone()
    if not fx:
        return None
    fx = dict(fx)
    return DailyFixture(
        fixture_id=int(fx["fixture_id"]),
        provider_fixture_id=int(fx["fixture_id"]),
        competition_key=str(fx.get("competition_key") or "world_cup_2026"),
        home_team=str(fx.get("home_team") or row.get("home_team_input") or ""),
        away_team=str(fx.get("away_team") or row.get("away_team_input") or ""),
        kickoff_utc=str(fx.get("kickoff_utc") or ""),
        status=str(fx.get("status") or "NS"),
        season=2026,
        coverage_sources=["local_db"],
    )


def run_knockout_wde(
    fixture: DailyFixture,
    *,
    settings: Settings,
    repo: FootballIntelligenceRepository,
    force: bool,
) -> tuple[str, dict[str, Any]]:
    sel = _to_selection(fixture)
    fid = sel.provider_fixture_id
    comp_key = sel.competition_key
    detail: dict[str, Any] = {
        "fixture_id": fid,
        "home_team": sel.home_team,
        "away_team": sel.away_team,
        "competition_key": comp_key,
        "engine": "wde",
    }

    if not force and _has_wde_prediction(repo, fid, comp_key):
        detail["reason"] = "skipped_existing"
        return "skipped", detail

    if not settings.api_football_configured:
        detail["reason"] = "missing_fixture_context"
        return "skipped", detail

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
        "generated_by": GENERATED_BY,
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
            "reason": "generated",
            "confidence": payload.get("confidence_score") or payload.get("confidence"),
            "predicted_1x2": (payload.get("one_x_two") or {}).get("selection"),
            "predicted_scoreline": payload.get("predicted_scoreline"),
        }
    )
    return "generated", detail


def _classify_ecse_skip(
    audit: dict[str, Any],
    *,
    prediction: dict[str, Any] | None,
    minimum_met: bool = False,
) -> str:
    if prediction is None and not minimum_met:
        if not audit.get("has_odds"):
            return "missing_odds"
        if not audit.get("lambda_inputs_available"):
            return "missing_lambda_inputs"
        return "insufficient_minimum_inputs"
    if prediction is None:
        return "engine_error"
    return "engine_error"


def _build_partial_ecse_from_manual_odds(
    *,
    fixture_id: int,
    fixture_row: dict[str, Any],
    odds_1x2: dict[str, float],
    btts_odds: dict[str, float] | None,
    layers_used: list[str],
    layers_missing: list[str],
    completeness_score: float,
) -> dict[str, Any] | None:
    """Fallback ECSE from screenshot/manual odds when lambda pipeline unavailable."""
    markets = markets_from_odds(odds_1x2, btts_odds or {})
    lh, la = estimate_lambdas_from_1x2(
        markets["implied_prob_home"],
        markets["implied_prob_draw"],
        markets["implied_prob_away"],
    )
    dist = poisson_score_distribution(lh, la, top_n=10)
    if not dist:
        return None
    top_10 = [
        {
            "scoreline": e["scoreline"],
            "probability": float(e["probability"]),
            "rank": i + 1,
            "home_goals": e["home_goals"],
            "away_goals": e["away_goals"],
        }
        for i, e in enumerate(dist)
    ]
    return {
        "fixture_id": fixture_id,
        "registry_fixture_id": fixture_id,
        "competition_key": fixture_row.get("competition_key"),
        "home_team": fixture_row.get("home_team"),
        "away_team": fixture_row.get("away_team"),
        "kickoff_utc": fixture_row.get("kickoff_utc"),
        "generated_at": _utc_now_iso(),
        "model_version": "OWNER-KNOCKOUT-PARTIAL|manual_odds_poisson",
        "lambda_home": lh,
        "lambda_away": la,
        "top_10_scorelines": top_10,
        "top_1_score": top_10[0]["scoreline"],
        "top_3_scores": [s["scoreline"] for s in top_10[:3]],
        "top_5_scores": [s["scoreline"] for s in top_10[:5]],
        "confidence_score": float(top_10[0]["probability"]),
        "data_quality_score": round(completeness_score, 4),
        "prediction_source": GENERATED_BY,
        "raw_features": {
            "owner_only": True,
            "generated_by": GENERATED_BY,
            "source": "partial_manual_odds",
            "ecse_layers_used": layers_used,
            "ecse_layers_missing": layers_missing,
            "ecse_completeness_score": completeness_score,
            "partial_snapshot": True,
        },
    }


def run_knockout_ecse(
    fixture: DailyFixture,
    *,
    settings: Settings,
    conn,
    repo: FootballIntelligenceRepository,
    odds_1x2: dict[str, float] | None,
    btts_odds: dict[str, float] | None,
    force: bool,
) -> tuple[str, dict[str, Any]]:
    sel = _to_selection(fixture)
    fid = sel.provider_fixture_id
    comp_key = sel.competition_key
    detail: dict[str, Any] = {
        "fixture_id": fid,
        "home_team": sel.home_team,
        "away_team": sel.away_team,
        "competition_key": comp_key,
        "engine": "ecse",
    }

    if has_snapshot(conn, fid) and not force:
        detail["reason"] = "skipped_existing"
        return "skipped", detail

    if has_snapshot(conn, fid) and force:
        conn.execute("DELETE FROM ecse_prediction_snapshots WHERE fixture_id = ?", (fid,))
        conn.commit()

    odds_status, odds_detail = ensure_owner_odds_snapshot(
        repo,
        conn,
        fixture_id=fid,
        competition_key=comp_key,
        odds_1x2=odds_1x2,
        btts_odds=btts_odds,
        settings=settings,
        force=force,
    )
    detail["odds_bootstrap"] = odds_detail

    audit = odds_readiness_audit(conn, sel)
    detail["odds_audit"] = audit

    layers_used, layers_missing, completeness_score = compute_ecse_layers(conn, repo, fixture_id=fid)
    detail["ecse_layers_used"] = layers_used
    detail["ecse_layers_missing"] = layers_missing
    detail["ecse_completeness_score"] = completeness_score

    min_ok, min_reason = minimum_ecse_inputs_met(
        conn,
        repo,
        fixture_id=fid,
        home_team=sel.home_team,
        away_team=sel.away_team,
        kickoff_utc=sel.kickoff_utc,
    )
    detail["minimum_inputs_met"] = min_ok
    detail["minimum_inputs_reason"] = min_reason

    if not min_ok:
        detail["reason"] = f"insufficient_minimum_inputs:{min_reason}"
        return "skipped", detail

    fx_row = {
        "fixture_id": fid,
        "competition_key": comp_key,
        "home_team": sel.home_team,
        "away_team": sel.away_team,
        "kickoff_utc": sel.kickoff_utc,
        "status": sel.status,
    }
    prediction: dict[str, Any] | None = None
    try:
        prediction = build_ecse_live_prediction(conn, fid, fx_row)
    except Exception as exc:
        detail["build_error"] = str(exc)

    if not prediction and odds_1x2:
        prediction = _build_partial_ecse_from_manual_odds(
            fixture_id=fid,
            fixture_row=fx_row,
            odds_1x2=odds_1x2,
            btts_odds=btts_odds,
            layers_used=layers_used,
            layers_missing=layers_missing,
            completeness_score=completeness_score,
        )
        if prediction:
            detail["partial_snapshot"] = True

    if not prediction:
        detail["reason"] = _classify_ecse_skip(audit, prediction=None, minimum_met=min_ok)
        return "skipped", detail

    raw = prediction.get("raw_features") or {}
    if isinstance(raw, dict):
        raw["owner_only"] = True
        raw["generated_by"] = GENERATED_BY
        raw["ecse_layers_used"] = layers_used
        raw["ecse_layers_missing"] = layers_missing
        raw["ecse_completeness_score"] = completeness_score
        raw["partial_snapshot"] = not audit.get("lambda_inputs_available")
        prediction["raw_features"] = raw

    prediction["prediction_source"] = GENERATED_BY
    prediction["data_quality_score"] = completeness_score

    sid, reason = insert_snapshot(conn, prediction)
    if reason != "inserted":
        detail["reason"] = reason
        return "skipped", detail

    detail.update(
        {
            "reason": "generated",
            "snapshot_id": sid,
            "top_1_score": prediction.get("top_1_score"),
            "confidence_score": prediction.get("confidence_score"),
            "odds_bootstrap_status": odds_status,
            "ecse_layers_used": layers_used,
            "ecse_completeness_score": completeness_score,
        }
    )
    return "generated", detail


@dataclass
class KnockoutProductionResult:
    phase: str = PHASE
    process_date: str = ""
    selected: int = 0
    wde_generated: int = 0
    wde_skipped: int = 0
    ecse_generated: int = 0
    ecse_skipped: int = 0
    skipped_existing_wde: int = 0
    skipped_existing_ecse: int = 0
    wde_skip_reasons: dict[str, int] = field(default_factory=dict)
    ecse_skip_reasons: dict[str, int] = field(default_factory=dict)
    per_fixture: list[dict[str, Any]] = field(default_factory=list)
    fixture_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return with_safety_labels(
            {
                **KNOCKOUT_SAFETY,
                "phase": self.phase,
                "generated_by": GENERATED_BY,
                "process_date": self.process_date,
                "selected": self.selected,
                "wde_generated": self.wde_generated,
                "wde_skipped": self.wde_skipped,
                "ecse_generated": self.ecse_generated,
                "ecse_skipped": self.ecse_skipped,
                "skipped_existing_wde": self.skipped_existing_wde,
                "skipped_existing_ecse": self.skipped_existing_ecse,
                "wde_skip_reasons": self.wde_skip_reasons,
                "ecse_skip_reasons": self.ecse_skip_reasons,
                "fixture_ids": self.fixture_ids,
                "per_fixture": self.per_fixture,
                "completed_at_utc": _utc_now_iso(),
            }
        )


def load_resolved_fixture_ids(
    *,
    process_date: date,
    fixture_ids: list[int] | None = None,
    resolution: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if resolution is None:
        resolution = load_resolution_artifact(process_date)
    if resolution is None:
        return []
    rows = []
    for row in resolution.get("matches") or []:
        res = row.get("resolution") or {}
        if res.get("resolution_status") != "RESOLVED":
            continue
        fid = res.get("fixture_id")
        if not fid:
            continue
        if fixture_ids and int(fid) not in fixture_ids:
            continue
        rows.append(row)
    return rows


def generate_owner_knockout_ecse_only(
    *,
    process_date: date,
    fixture_ids: list[int] | None = None,
    force: bool = False,
    settings: Settings | None = None,
    resolution: dict[str, Any] | None = None,
) -> KnockoutProductionResult:
    """Generate owner-only ECSE snapshots (no WDE, no public publish)."""
    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    ensure_ecse_live_tables(conn)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    match_rows = load_resolved_fixture_ids(
        process_date=process_date, fixture_ids=fixture_ids, resolution=resolution
    )
    result = KnockoutProductionResult(
        process_date=process_date.isoformat(),
        selected=len(match_rows),
    )

    for row in match_rows:
        fixture = _fixture_from_resolution_row(conn, row)
        res = row.get("resolution") or {}
        fid = int(res["fixture_id"])
        result.fixture_ids.append(fid)
        odds_1x2 = row.get("odds_1x2") or {}
        btts = row.get("btts_odds") or row.get("btts") or {}

        entry: dict[str, Any] = {
            "match_no": row.get("match_no"),
            "fixture_id": fid,
            "home_team": row.get("home_team_input"),
            "away_team": row.get("away_team_input"),
            "ecse": {},
        }

        if not fixture:
            entry["ecse"] = {"status": "skipped", "reason": "missing_provider_fixture_mapping"}
            result.ecse_skipped += 1
            _inc(result.ecse_skip_reasons, "missing_provider_fixture_mapping")
            result.per_fixture.append(entry)
            continue

        ecse_status, ecse_detail = run_knockout_ecse(
            fixture,
            settings=settings,
            conn=conn,
            repo=repo,
            odds_1x2=odds_1x2,
            btts_odds=btts,
            force=force,
        )
        entry["ecse"] = {"status": ecse_status, **ecse_detail}
        if ecse_status == "generated":
            result.ecse_generated += 1
        else:
            result.ecse_skipped += 1
            reason = str(ecse_detail.get("reason") or "skipped")
            if reason == "skipped_existing":
                result.skipped_existing_ecse += 1
            _inc(result.ecse_skip_reasons, reason)

        result.per_fixture.append(entry)

    conn.close()
    return result


def generate_knockout_production_snapshots(
    *,
    process_date: date,
    fixture_ids: list[int] | None = None,
    force: bool = False,
    settings: Settings | None = None,
    resolution: dict[str, Any] | None = None,
) -> KnockoutProductionResult:
    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    ensure_ecse_live_tables(conn)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    match_rows = load_resolved_fixture_ids(
        process_date=process_date, fixture_ids=fixture_ids, resolution=resolution
    )
    result = KnockoutProductionResult(
        process_date=process_date.isoformat(),
        selected=len(match_rows),
    )

    for row in match_rows:
        fixture = _fixture_from_resolution_row(conn, row)
        res = row.get("resolution") or {}
        fid = int(res["fixture_id"])
        result.fixture_ids.append(fid)
        odds_1x2 = row.get("odds_1x2") or {}
        btts = row.get("btts_odds") or row.get("btts") or {}

        entry: dict[str, Any] = {
            "match_no": row.get("match_no"),
            "fixture_id": fid,
            "home_team": row.get("home_team_input"),
            "away_team": row.get("away_team_input"),
            "wde": {},
            "ecse": {},
        }

        if not fixture:
            entry["wde"] = {"status": "skipped", "reason": "missing_provider_fixture_mapping"}
            entry["ecse"] = {"status": "skipped", "reason": "missing_provider_fixture_mapping"}
            result.wde_skipped += 1
            result.ecse_skipped += 1
            _inc(result.wde_skip_reasons, "missing_provider_fixture_mapping")
            _inc(result.ecse_skip_reasons, "missing_provider_fixture_mapping")
            result.per_fixture.append(entry)
            continue

        wde_status, wde_detail = run_knockout_wde(fixture, settings=settings, repo=repo, force=force)
        entry["wde"] = {"status": wde_status, **wde_detail}
        if wde_status == "generated":
            result.wde_generated += 1
        else:
            result.wde_skipped += 1
            reason = str(wde_detail.get("reason") or "skipped")
            if reason == "skipped_existing":
                result.skipped_existing_wde += 1
            _inc(result.wde_skip_reasons, reason)

        ecse_status, ecse_detail = run_knockout_ecse(
            fixture,
            settings=settings,
            conn=conn,
            repo=repo,
            odds_1x2=odds_1x2,
            btts_odds=btts,
            force=force,
        )
        entry["ecse"] = {"status": ecse_status, **ecse_detail}
        if ecse_status == "generated":
            result.ecse_generated += 1
        else:
            result.ecse_skipped += 1
            reason = str(ecse_detail.get("reason") or "skipped")
            if reason == "skipped_existing":
                result.skipped_existing_ecse += 1
            _inc(result.ecse_skip_reasons, reason)

        result.per_fixture.append(entry)

    conn.close()
    return result


def write_knockout_production_artifacts(
    result: KnockoutProductionResult,
    *,
    process_date: date,
) -> dict[str, str]:
    tag = _date_tag(process_date)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    gen_path = ARTIFACTS_DIR / f"owner_knockout_production_snapshot_generation_{tag}.json"
    audit_path = ARTIFACTS_DIR / f"owner_knockout_wde_ecse_attachment_audit_{tag}.json"
    report_path = REPORTS_DIR / f"owner_knockout_production_attachment_report_{tag}.md"

    payload = result.to_dict()
    gen_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    audit = {
        **KNOCKOUT_SAFETY,
        "phase": PHASE,
        "generated_by": GENERATED_BY,
        "process_date": process_date.isoformat(),
        "fixture_ids": result.fixture_ids,
        "summary": {
            "wde_generated": result.wde_generated,
            "ecse_generated": result.ecse_generated,
            "skipped_existing_wde": result.skipped_existing_wde,
            "skipped_existing_ecse": result.skipped_existing_ecse,
            "wde_skip_reasons": result.wde_skip_reasons,
            "ecse_skip_reasons": result.ecse_skip_reasons,
        },
        "per_fixture": result.per_fixture,
    }
    audit_path.write_text(json.dumps(with_safety_labels(audit), indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Owner Knockout WDE/ECSE Production Attachment Report",
        "",
        f"**Date:** {process_date.isoformat()} | **Fixtures:** {result.selected}",
        "",
        "Owner/internal only. No public publish.",
        "",
        "## Summary",
        "",
        f"- WDE generated: **{result.wde_generated}**",
        f"- ECSE generated: **{result.ecse_generated}**",
        f"- WDE skipped (existing): **{result.skipped_existing_wde}**",
        f"- ECSE skipped (existing): **{result.skipped_existing_ecse}**",
        "",
        "## Per fixture",
        "",
        "| fixture_id | Match | WDE | ECSE | WDE reason | ECSE reason |",
        "| ---------- | ----- | --- | ---- | ---------- | ----------- |",
    ]
    for row in result.per_fixture:
        wde = row.get("wde") or {}
        ecse = row.get("ecse") or {}
        lines.append(
            f"| {row.get('fixture_id')} | {row.get('home_team')} vs {row.get('away_team')} | "
            f"{wde.get('status', '—')} | {ecse.get('status', '—')} | "
            f"{wde.get('reason', '—')} | {ecse.get('reason', '—')} |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- PUBLIC_PUBLISH: false",
            "- OWNER_ONLY: true",
            "- No WDE/EGIE retrain, no CSV promotion, no frontend publish",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "generation_artifact": str(gen_path),
        "audit_artifact": str(audit_path),
        "report_path": str(report_path),
    }

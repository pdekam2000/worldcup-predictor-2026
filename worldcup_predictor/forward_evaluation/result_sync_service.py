"""Phase 2D — Canonical result sync (DB-first, provider fallback)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.forward_evaluation.result_record import (
    CONFIRMED_RESULT_QUALITIES,
    RESULT_QUALITY_CONFLICT,
    RESULT_QUALITY_NOT_AVAILABLE,
    RESULT_QUALITY_NOT_TERMINAL,
    build_canonical_result_record,
    result_content_hash,
)
from worldcup_predictor.forward_evaluation.results import is_evaluable_status, sync_actual_result
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.outcomes.evaluation_score_policy import regulation_score_for_evaluation
from worldcup_predictor.outcomes.outcome_persistence import normalize_match_outcome_type
from worldcup_predictor.outcomes.provider_score_truth import parse_provider_fixture_item
from worldcup_predictor.research.ecse_live.result_sync import (
    _penalty_score_from_item,
    final_score_type_from_status,
    provider_status_is_finished,
)
from worldcup_predictor.schedule.match_center import classify_status


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _load_fixture(prod_conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = prod_conn.execute(
        """
        SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status, season, league_id
        FROM fixtures WHERE fixture_id=? AND (is_placeholder IS NULL OR is_placeholder=0)
        LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else None


def _load_result_row(prod_conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    try:
        row = prod_conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (int(fixture_id),)).fetchone()
    except sqlite3.OperationalError:
        return None
    return dict(row) if row else None


def _existing_eval_result(eval_conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = eval_conn.execute("SELECT * FROM actual_results WHERE fixture_id=?", (int(fixture_id),)).fetchone()
    return dict(row) if row else None


def _provider_fetch_and_persist(
    *,
    fixture_id: int,
    competition_key: str,
    settings: Settings,
    repo: FootballIntelligenceRepository,
    dry_run: bool,
) -> dict[str, Any]:
    api = ApiFootballClient(settings)
    if not api.is_configured:
        return {"fetched": False, "reason": "api_football_not_configured"}
    call = api._safe_get(
        "fixtures",
        {"id": int(fixture_id)},
        placeholder_factory=lambda: None,
        force_refresh=True,
    )
    if not call.data:
        return {"fetched": False, "reason": "no_provider_data", "provider": call.source}
    item = call.data[0] if isinstance(call.data, list) else call.data
    if not isinstance(item, dict):
        return {"fetched": False, "reason": "invalid_payload"}

    fixture_meta = item.get("fixture") or {}
    status_obj = fixture_meta.get("status") or {}
    provider_short = str(status_obj.get("short") or "NS")
    provider_long = str(status_obj.get("long") or "")
    if not provider_status_is_finished(provider_short) and not provider_status_is_finished(provider_long):
        return {
            "fetched": False,
            "reason": "provider_not_finished",
            "provider_status": provider_short,
        }

    fixture = parse_api_fixture_item(item, source=str(call.source or "api-football"))
    if fixture is None or fixture.home_goals is None or fixture.away_goals is None:
        return {"fetched": False, "reason": "parse_failed_or_missing_goals"}

    score_type = final_score_type_from_status(fixture.status)
    penalty_score = _penalty_score_from_item(item)
    stage_truth = parse_provider_fixture_item(item, source=str(call.source or "api-football"))

    if dry_run:
        return {
            "fetched": True,
            "dry_run": True,
            "provider": str(call.source or "api-football"),
            "regulation_score": stage_truth.regulation_score if stage_truth else None,
        }

    repo.upsert_fixture(fixture, competition_key=competition_key)
    ok = repo.upsert_fixture_result(
        fixture,
        competition_key=competition_key,
        match_outcome_type=score_type,
        penalty_score=penalty_score,
        outcome_source=str(call.source or "api-football"),
        stage_truth=stage_truth,
    )
    return {
        "fetched": ok,
        "inserted": ok,
        "provider": str(call.source or "api-football"),
        "regulation_score": stage_truth.regulation_score if stage_truth else None,
    }


def sync_result_for_fixture(
    fixture_id: int,
    *,
    prod_conn: sqlite3.Connection | None = None,
    eval_conn: sqlite3.Connection | None = None,
    settings: Settings | None = None,
    dry_run: bool = False,
    allow_provider_fetch: bool = True,
) -> dict[str, Any]:
    """Sync confirmed regulation result for one fixture (production DB + eval actual_results)."""
    from worldcup_predictor.config.env_loading import project_root
    from worldcup_predictor.database.connection import connect
    from worldcup_predictor.forward_evaluation.db import connect_eval_db

    settings = settings or get_settings()
    own_prod = prod_conn is None
    own_eval = eval_conn is None
    prod = prod_conn or connect(settings.sqlite_path)
    ev = eval_conn or connect_eval_db(project_root())
    fid = int(fixture_id)

    try:
        fixture = _load_fixture(prod, fid)
        if not fixture:
            return {
                "fixture_id": fid,
                "status": "error",
                "result_available": False,
                "safe_to_store": False,
                "reason": "fixture_not_found",
            }

        existing_eval = _existing_eval_result(ev, fid)
        if existing_eval:
            return {
                "fixture_id": fid,
                "provider": existing_eval.get("result_source"),
                "status": "reused",
                "result_available": True,
                "safe_to_store": True,
                "inserted": False,
                "reused": True,
                "conflict": False,
                "regulation_score": existing_eval.get("actual_score"),
                "result_quality_status": existing_eval.get("result_quality_status"),
                "reason": "eval_actual_result_exists",
            }

        result_row = _load_result_row(prod, fid)
        status = str(
            (result_row or {}).get("final_stage")
            or (result_row or {}).get("match_outcome_type")
            or fixture.get("status")
            or "NS"
        ).upper()

        if not result_row and allow_provider_fetch and not dry_run:
            repo = FootballIntelligenceRepository(settings.sqlite_path or None)
            fetch = _provider_fetch_and_persist(
                fixture_id=fid,
                competition_key=str(fixture.get("competition_key") or ""),
                settings=settings,
                repo=repo,
                dry_run=dry_run,
            )
            if fetch.get("inserted"):
                result_row = _load_result_row(prod, fid)
                status = str((result_row or {}).get("final_stage") or fixture.get("status") or "NS").upper()
        elif not result_row and allow_provider_fetch and dry_run:
            repo = FootballIntelligenceRepository(settings.sqlite_path or None)
            _provider_fetch_and_persist(
                fixture_id=fid,
                competition_key=str(fixture.get("competition_key") or ""),
                settings=settings,
                repo=repo,
                dry_run=True,
            )

        if not is_evaluable_status(status) and classify_status(status) != "finished":
            record = build_canonical_result_record(
                fixture_id=fid,
                provider_fixture_id=fid,
                competition=fixture.get("competition_key"),
                kickoff_utc=fixture.get("kickoff_utc"),
                terminal_status=status,
                regulation_home=None,
                regulation_away=None,
                provider=(result_row or {}).get("source"),
                result_provenance="fixture_results",
            )
            return {
                "fixture_id": fid,
                "status": "blocked",
                "result_available": False,
                "safe_to_store": False,
                "inserted": False,
                "reused": False,
                "conflict": False,
                "result_quality_status": record["result_quality_status"],
                "reason": RESULT_QUALITY_NOT_TERMINAL,
            }

        home, away, scoreline, basis = regulation_score_for_evaluation(result_row, fixture)
        if home is None or away is None or not scoreline:
            return {
                "fixture_id": fid,
                "status": "blocked",
                "result_available": False,
                "safe_to_store": False,
                "reason": RESULT_QUALITY_NOT_AVAILABLE,
                "terminal_status": status,
            }

        provider = (result_row or {}).get("source") or (result_row or {}).get("outcome_source") or "fixture_results"
        r_hash = result_content_hash(
            fixture_id=fid,
            regulation_home=int(home),
            regulation_away=int(away),
            final_stage=status,
            provider=str(provider),
        )

        if result_row:
            reg_h = result_row.get("regulation_home_goals")
            reg_a = result_row.get("regulation_away_goals")
            ft_h = result_row.get("home_goals")
            ft_a = result_row.get("away_goals")
            if reg_h is not None and reg_a is not None and ft_h is not None and ft_a is not None:
                if (int(reg_h), int(reg_a)) != (int(ft_h), int(ft_a)):
                    return {
                        "fixture_id": fid,
                        "status": "conflict",
                        "result_available": True,
                        "safe_to_store": False,
                        "inserted": False,
                        "reused": False,
                        "conflict": True,
                        "regulation_score": scoreline,
                        "result_quality_status": RESULT_QUALITY_CONFLICT,
                        "reason": "internal_regulation_ft_mismatch",
                    }

        if result_row and result_row.get("regulation_home_goals") is not None:
            existing_reg = (
                int(result_row["regulation_home_goals"]),
                int(result_row["regulation_away_goals"]),
            )
            if existing_reg != (int(home), int(away)):
                return {
                    "fixture_id": fid,
                    "status": "conflict",
                    "result_available": True,
                    "safe_to_store": False,
                    "inserted": False,
                    "reused": False,
                    "conflict": True,
                    "regulation_score": scoreline,
                    "result_quality_status": RESULT_QUALITY_CONFLICT,
                    "reason": "regulation_score_conflict",
                }

        canonical = build_canonical_result_record(
            fixture_id=fid,
            provider_fixture_id=fid,
            competition=fixture.get("competition_key"),
            kickoff_utc=fixture.get("kickoff_utc"),
            terminal_status=status,
            regulation_home=int(home),
            regulation_away=int(away),
            halftime_home=result_row.get("ht_home_goals") if result_row else None,
            halftime_away=result_row.get("ht_away_goals") if result_row else None,
            extra_time_home=result_row.get("extra_time_home_goals") if result_row else None,
            extra_time_away=result_row.get("extra_time_away_goals") if result_row else None,
            penalty_home=result_row.get("penalties_home_goals") if result_row else None,
            penalty_away=result_row.get("penalties_away_goals") if result_row else None,
            provider=str(provider),
            provider_result_timestamp=(result_row or {}).get("finished_at"),
            synced_at_utc=_utc_now(),
            result_provenance="fixture_results",
        )

        if dry_run:
            return {
                "fixture_id": fid,
                "provider": provider,
                "status": "dry_run",
                "result_available": True,
                "safe_to_store": canonical["evaluable"],
                "inserted": False,
                "reused": False,
                "conflict": False,
                "regulation_score": scoreline,
                "result_quality_status": canonical["result_quality_status"],
                "result_content_hash": r_hash,
            }

        if not canonical["evaluable"]:
            return {
                "fixture_id": fid,
                "status": "blocked",
                "result_available": False,
                "safe_to_store": False,
                "result_quality_status": canonical["result_quality_status"],
                "reason": "not_confirmed",
            }

        sync_out = sync_actual_result(ev, prod, fid)
        if sync_out.get("synced"):
            ev.execute(
                """
                UPDATE actual_results SET
                    result_quality_status=?,
                    result_content_hash=?,
                    provider=?,
                    synced_at_utc=?,
                    first_synced_at=COALESCE(first_synced_at, ?),
                    last_verified_at=?,
                    regulation_result=?
                WHERE fixture_id=?
                """,
                (
                    canonical["result_quality_status"],
                    r_hash,
                    str(provider),
                    _utc_now(),
                    _utc_now(),
                    _utc_now(),
                    canonical["regulation_result"],
                    fid,
                ),
            )
            ev.commit()

        return {
            "fixture_id": fid,
            "provider": provider,
            "status": "synced" if sync_out.get("synced") else sync_out.get("reason", "unknown"),
            "result_available": bool(sync_out.get("synced") or sync_out.get("reason") == "already_synced"),
            "safe_to_store": True,
            "inserted": bool(sync_out.get("synced")),
            "reused": sync_out.get("reason") == "already_synced",
            "conflict": False,
            "regulation_score": scoreline,
            "result_quality_status": canonical["result_quality_status"],
            "result_content_hash": r_hash,
            "score_basis": basis,
        }
    finally:
        if own_prod:
            prod.close()
        if own_eval:
            ev.close()

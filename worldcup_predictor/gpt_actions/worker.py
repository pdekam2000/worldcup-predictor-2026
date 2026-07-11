"""Background prediction job worker (async semantics, single heavy job)."""

from __future__ import annotations

import threading
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.gpt_actions.config import GptActionsConfig
from worldcup_predictor.gpt_actions.delegation import (
    _fixture_from_db,
    filter_matches_by_odds,
    format_fixture_evidence,
    rank_best_matches,
)
from worldcup_predictor.gpt_actions.jobs import JobStore
from worldcup_predictor.gpt_actions.owner_odds import OwnerOddsBudget, controlled_owner_odds_lookup
from worldcup_predictor.gpt_actions.owner_scope import (
    PredictionScope,
    display_labels_for_tier,
    fixture_allowed_for_prediction,
    fixture_tier,
    validate_discovery_scope,
    validate_prediction_scope,
)
from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
from worldcup_predictor.gpt_actions.policies import validate_fixture_id_list
from worldcup_predictor.gpt_actions.shadow_storage import freeze_tier_b_shadow_prediction
from worldcup_predictor.mcp_server import runtime as mcp_runtime


def _resolve_fixture_ids(request: dict[str, Any], *, max_count: int) -> list[int]:
    explicit = request.get("fixture_ids") or []
    if explicit:
        return validate_fixture_id_list(list(explicit), max_count=max_count)

    scope = str(request.get("scope") or "production")
    discovery_scope = validate_discovery_scope(scope)
    filtered = filter_matches_by_odds(
        target_date=str(request["date"]),
        timezone=str(request.get("timezone") or "Europe/Vienna"),
        home_odds_gt=(request.get("filter") or {}).get("home_odds_gt"),
        away_odds_gt=(request.get("filter") or {}).get("away_odds_gt"),
        scope=discovery_scope,
    )
    ids = [int(m["fixture_id"]) for m in filtered.get("matches") or []]
    return ids[:max_count]


def _effective_prediction_scope(request: dict[str, Any]) -> PredictionScope:
    explicit = request.get("prediction_scope")
    if explicit:
        return validate_prediction_scope(str(explicit))
    scope = str(request.get("scope") or "production").strip().lower()
    if scope in ("owner", "trusted", "test_phase"):
        return "owner"
    return "production"


def _per_fixture_prediction_scope(global_scope: PredictionScope, tier: str | None) -> PredictionScope:
    if global_scope == "owner":
        return "owner_shadow" if tier == "B" else "production"
    return global_scope


def _aggregate_status(predictions: list[dict[str, Any]]) -> str:
    if not predictions:
        return "failed"
    statuses = {str(p.get("quality") or "unknown") for p in predictions}
    if statuses == {"OK"}:
        return "completed"
    if "OK" in statuses or "PARTIAL" in statuses:
        return "partial"
    return "failed"


def _build_tier_meta(fixture_id: int, competition_key: str, prediction_scope: PredictionScope) -> dict[str, Any]:
    canon = normalize_competition_key(competition_key) or competition_key
    tier = fixture_tier(competition_key)
    labels = display_labels_for_tier(tier)
    return {
        "tier": tier,
        "validation_tier": tier,
        "competition": canon,
        "owner_shadow": tier == "B",
        "prediction_scope": prediction_scope,
        "mapping_quality": "canonical" if canon == competition_key else "alias_resolved",
        **labels,
    }


def execute_prediction_job(
    job_id: str,
    *,
    store: JobStore,
    config: GptActionsConfig,
) -> None:
    record = store.get(job_id)
    if not record:
        return
    store.update(job_id, status="running")
    request = record.get("request") or {}
    try:
        prediction_scope = _effective_prediction_scope(request)
        fixture_ids = _resolve_fixture_ids(request, max_count=config.max_fixture_ids_per_job)
        if not fixture_ids:
            store.update(
                job_id,
                status="failed",
                error="no_fixtures_matched_filter",
                result={"fixture_count": 0, "predictions": [], "all_match_ranking": [], "best_3": []},
            )
            return

        timezone = str(request.get("timezone") or "Europe/Vienna")
        refresh = bool(request.get("refresh_if_stale", True))
        select_best = int(request.get("select_best") or 3)
        include_all = bool(request.get("include_all_predictions", True))

        settings = get_settings()
        conn = connect(settings.sqlite_path)
        budget = OwnerOddsBudget()
        predictions: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        try:
            for fixture_id in fixture_ids:
                daily = _fixture_from_db(conn, fixture_id)
                if not daily:
                    rejected.append({"fixture_id": fixture_id, "reason": "fixture_not_found"})
                    continue
                tier = fixture_tier(daily.competition_key)
                allowed, reason = fixture_allowed_for_prediction(
                    daily.competition_key,
                    prediction_scope=_per_fixture_prediction_scope(prediction_scope, tier),
                )
                if not allowed:
                    rejected.append({"fixture_id": fixture_id, "reason": reason})
                    continue
                if tier == "B":
                    odds_meta = controlled_owner_odds_lookup(
                        daily, tier="B", settings=settings, budget=budget, allow_provider=True
                    )
                    if not odds_meta.get("odds_found"):
                        rejected.append(
                            {
                                "fixture_id": fixture_id,
                                "reason": odds_meta.get("failure_reason") or "no_legitimate_odds",
                                "odds_diagnostics": {
                                    "refresh_attempted": odds_meta.get("refresh_attempted"),
                                    "refresh_success": odds_meta.get("refresh_success"),
                                    "provider_used": odds_meta.get("provider_used"),
                                    "freshness_status": odds_meta.get("freshness_status"),
                                },
                            }
                        )
                        continue
                meta = _build_tier_meta(
                    fixture_id,
                    daily.competition_key,
                    _per_fixture_prediction_scope(prediction_scope, tier),
                )
                raw = mcp_runtime.run_fixture_prediction(
                    int(fixture_id),
                    refresh_if_stale=refresh,
                )
                evidence = format_fixture_evidence(raw, timezone=timezone, tier_meta=meta)
                predictions.append(evidence)
                if tier == "B":
                    wde = evidence.get("wde") or {}
                    ecse = evidence.get("ecse") or {}
                    freeze_tier_b_shadow_prediction(
                        fixture_id=fixture_id,
                        competition=str(meta.get("competition")),
                        kickoff=daily.kickoff_utc,
                        odds_timestamp=(evidence.get("odds") or {}).get("freshness"),
                        wde_version=wde.get("model_version"),
                        ecse_version=(raw.get("ecse") or {}).get("model_version"),
                        evidence=evidence,
                    )
        finally:
            conn.close()

        ranking = rank_best_matches(predictions, select_best=select_best)
        contains_test = any((p.get("validation_tier") or p.get("tier")) == "B" for p in predictions)
        result = {
            "date": request.get("date"),
            "timezone": timezone,
            "scope": request.get("scope") or "production",
            "prediction_scope": prediction_scope,
            "fixture_count": len(fixture_ids),
            "fixture_ids": fixture_ids,
            "accepted_count": len(predictions),
            "rejected": rejected,
            "provider_calls": budget.provider_calls,
            "predictions": predictions if include_all else [],
            "all_match_ranking": ranking["all_match_ranking"],
            "best_3": ranking["best_3"][: min(3, select_best)],
            "contains_test_phase_fixture": contains_test,
            "test_phase_warning": (
                "This package contains one or more Test Phase competitions under forward evaluation."
                if contains_test
                else None
            ),
        }
        status = _aggregate_status(predictions) if predictions else "failed"
        if not predictions and rejected:
            store.update(job_id, status="failed", error="all_fixtures_rejected", result=result)
        else:
            store.update(job_id, status=status, result=result)
    except Exception as exc:
        store.update(job_id, status="failed", error=str(exc)[:500])
    finally:
        store.release_active(job_id)


def enqueue_prediction_job(
    job_id: str,
    *,
    store: JobStore,
    config: GptActionsConfig,
) -> None:
    thread = threading.Thread(
        target=execute_prediction_job,
        kwargs={"job_id": job_id, "store": store, "config": config},
        name=f"gpt-actions-job-{job_id[:8]}",
        daemon=True,
    )
    thread.start()

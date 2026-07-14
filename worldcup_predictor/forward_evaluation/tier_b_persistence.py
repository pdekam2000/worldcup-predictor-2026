"""Tier B owner_shadow structured persistence for forward evaluation."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.forward_evaluation.bridge import ForwardEvalBridgeContext
from worldcup_predictor.forward_evaluation.context import mass_from_scores
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.gpt_actions.bridge_semantics import extract_wde_semantics
from worldcup_predictor.gpt_actions.owner_scope import fixture_tier
from worldcup_predictor.research.ecse_live.store import get_snapshot

TIER_B_SCOPE = "owner_shadow"
TIER_B_VALIDATION = "B"


@dataclass
class TierBPersistenceContext:
    fixture_id: int
    prediction_scope: str = TIER_B_SCOPE
    validation_tier: str = TIER_B_VALIDATION
    source_runtime: str = "mcp"
    source_job_id: str | None = None
    public_visible: bool = False


def resolve_tier_b_bridge_context(
    competition_key: str,
    *,
    bridge_context: ForwardEvalBridgeContext | dict[str, Any] | None = None,
    bridge_origin: str = "mcp",
    source_job_id: str | None = None,
    worldcup_stored_prediction_id: int | None = None,
    ecse_snapshot_id: int | None = None,
) -> ForwardEvalBridgeContext:
    """Resolve bridge context with Tier B owner_shadow defaults when appropriate."""
    tier = fixture_tier(competition_key)
    explicit = ForwardEvalBridgeContext.from_mapping(bridge_context) if bridge_context else None

    if explicit is not None:
        ctx = explicit
        if tier == "B":
            if ctx.prediction_scope == "production" and not _explicit_scope(bridge_context):
                ctx.prediction_scope = TIER_B_SCOPE
            if ctx.validation_tier is None:
                ctx.validation_tier = TIER_B_VALIDATION
            if ctx.public_visible is None:
                ctx.public_visible = False
        return ctx

    scope = TIER_B_SCOPE if tier == "B" else "production"
    return ForwardEvalBridgeContext(
        prediction_scope=scope,
        validation_tier=tier,
        public_visible=False if tier == "B" else None,
        source_job_id=source_job_id,
        bridge_origin=bridge_origin,
        worldcup_stored_prediction_id=worldcup_stored_prediction_id,
        ecse_snapshot_id=ecse_snapshot_id,
    )


def _explicit_scope(bridge_context: ForwardEvalBridgeContext | dict[str, Any] | None) -> bool:
    if bridge_context is None:
        return False
    if isinstance(bridge_context, ForwardEvalBridgeContext):
        return bool(bridge_context.prediction_scope and bridge_context.prediction_scope != "production")
    return bool(bridge_context.get("prediction_scope"))


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(r[1]) == column for r in rows)


def stamp_structured_scope(
    conn: sqlite3.Connection,
    fixture_id: int,
    *,
    prediction_scope: str,
    validation_tier: str,
    source_runtime: str,
) -> dict[str, bool]:
    """Stamp additive scope columns on WSP + ECSE rows (idempotent UPDATE)."""
    fid = int(fixture_id)
    out = {"wsp_stamped": False, "ecse_stamped": False}
    if _column_exists(conn, "worldcup_stored_predictions", "prediction_scope"):
        conn.execute(
            """
            UPDATE worldcup_stored_predictions
            SET prediction_scope = ?, validation_tier = ?, source_runtime = ?
            WHERE fixture_id = ? AND (is_active IS NULL OR is_active = 1)
            """,
            (prediction_scope, validation_tier, source_runtime, fid),
        )
        out["wsp_stamped"] = conn.total_changes > 0
    if _column_exists(conn, "ecse_prediction_snapshots", "prediction_scope"):
        conn.execute(
            """
            UPDATE ecse_prediction_snapshots
            SET prediction_scope = ?, validation_tier = ?, source_runtime = ?
            WHERE fixture_id = ?
            """,
            (prediction_scope, validation_tier, source_runtime, fid),
        )
        out["ecse_stamped"] = conn.total_changes > 0 or out["ecse_stamped"]
    conn.commit()
    return out


def _parse_json(raw: Any) -> dict[str, Any] | list[Any] | None:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return None


def _ecse_top_scores(ecse: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("top_5_scores", "top_5_scores_json"):
        raw = ecse.get(key.replace("_json", "")) if not key.endswith("_json") else ecse.get(key)
        parsed = _parse_json(raw) if not isinstance(raw, list) else raw
        if isinstance(parsed, list):
            for idx, item in enumerate(parsed[:5], start=1):
                if isinstance(item, dict):
                    rows.append(
                        {
                            "rank": int(item.get("rank") or idx),
                            "score": item.get("scoreline") or item.get("score"),
                            "probability": item.get("probability"),
                        }
                    )
            break
    return rows


def read_tier_b_structured_record(
    fixture_id: int,
    *,
    prod_conn: sqlite3.Connection,
    eval_conn: sqlite3.Connection | None = None,
    prediction_scope: str = TIER_B_SCOPE,
) -> dict[str, Any] | None:
    """Read canonical structured Tier B record from WSP + ECSE + freeze."""
    fid = int(fixture_id)
    wsp = prod_conn.execute(
        """
        SELECT * FROM worldcup_stored_predictions
        WHERE fixture_id = ? AND (is_active IS NULL OR is_active = 1)
        LIMIT 1
        """,
        (fid,),
    ).fetchone()
    if not wsp:
        return None
    wsp_row = dict(wsp)
    payload = _parse_json(wsp_row.get("payload_json"))
    if not isinstance(payload, dict):
        payload = {}

    ecse = get_snapshot(prod_conn, fid)
    if not ecse:
        return None

    fx = prod_conn.execute(
        """
        SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, season, league_id
        FROM fixtures WHERE fixture_id = ? LIMIT 1
        """,
        (fid,),
    ).fetchone()
    fx_row = dict(fx) if fx else {}

    wde = extract_wde_semantics(payload)
    ext = payload.get("extended_markets") or {}
    btts = ext.get("btts") or {}
    ou = ext.get("over_under_25") or ext.get("ou25") or {}
    freshness = payload.get("odds_freshness") or payload.get("freshness_metadata") or {}
    canonical_odds = freshness.get("canonical_odds_snapshot") or {}

    top5 = _ecse_top_scores(ecse)
    top3_mass = mass_from_scores(top5, 3) if top5 else None
    top5_mass = mass_from_scores(top5, 5) if top5 else None

    own_eval = eval_conn is None
    ev = eval_conn or connect_eval_db(project_root())
    try:
        freeze = ev.execute(
            """
            SELECT * FROM frozen_predictions
            WHERE fixture_id = ? AND prediction_scope = ?
            ORDER BY frozen_at DESC
            LIMIT 1
            """,
            (fid, prediction_scope),
        ).fetchone()
        rankings = []
        if freeze:
            rankings = [
                dict(r)
                for r in ev.execute(
                    """
                    SELECT rank, score, probability FROM exact_score_rankings
                    WHERE prediction_id = ? ORDER BY rank
                    """,
                    (freeze["prediction_id"],),
                ).fetchall()
            ]
    finally:
        if own_eval:
            ev.close()

    freeze_row = dict(freeze) if freeze else None
    scope_col = wsp_row.get("prediction_scope") or prediction_scope

    record: dict[str, Any] = {
        "fixture_id": fid,
        "provider_fixture_id": fx_row.get("fixture_id"),
        "competition": fx_row.get("competition_key") or wsp_row.get("competition_key"),
        "competition_key": wsp_row.get("competition_key"),
        "league_id": fx_row.get("league_id"),
        "season": fx_row.get("season"),
        "home_team_name": fx_row.get("home_team") or ecse.get("home_team"),
        "away_team_name": fx_row.get("away_team") or ecse.get("away_team"),
        "kickoff_utc": wsp_row.get("kickoff_utc") or ecse.get("kickoff_utc"),
        "prediction_generated_at_utc": wsp_row.get("predicted_at") or ecse.get("generated_at"),
        "validation_tier": wsp_row.get("validation_tier") or TIER_B_VALIDATION,
        "prediction_scope": scope_col,
        "public_visible": bool(int(freeze_row.get("public_visible") or 0)) if freeze_row else False,
        "source_runtime": wsp_row.get("source_runtime") or wsp_row.get("source"),
        "generated_by": payload.get("generated_by"),
        "model_environment": payload.get("model_environment"),
        "wde_decision": wde.get("decision_pick") or wde.get("effective_pick"),
        "ft_marginal_direction": wde.get("probability_argmax"),
        "probability_home": wde.get("home_prob"),
        "probability_draw": wde.get("draw_prob"),
        "probability_away": wde.get("away_prob"),
        "wde_confidence": wde.get("confidence") or payload.get("confidence_score"),
        "wde_execution_status": payload.get("wde_execution_status") or "executed",
        "wde_result_source": payload.get("wde_result_source") or "fresh_engine",
        "btts_selection": btts.get("prediction") or btts.get("selection"),
        "btts_yes_probability": btts.get("yes_probability"),
        "btts_no_probability": btts.get("no_probability"),
        "btts_execution_status": "OK" if btts else "UNAVAILABLE",
        "ou_2_5_selection": ou.get("prediction") or ou.get("selection"),
        "over_2_5_probability": ou.get("over_probability"),
        "under_2_5_probability": ou.get("under_probability"),
        "ou_execution_status": "OK" if ou else "UNAVAILABLE",
        "ecse_top1": top5[0]["score"] if len(top5) > 0 else ecse.get("top_1_score"),
        "ecse_top2": top5[1]["score"] if len(top5) > 1 else None,
        "ecse_top3": top5[2]["score"] if len(top5) > 2 else None,
        "ecse_top4": top5[3]["score"] if len(top5) > 3 else None,
        "ecse_top5": top5[4]["score"] if len(top5) > 4 else None,
        "ecse_top5_probabilities": top5,
        "top3_mass": top3_mass,
        "top5_mass": top5_mass,
        "entropy": freeze_row.get("entropy") if freeze_row else None,
        "lambda_home": ecse.get("lambda_home"),
        "lambda_away": ecse.get("lambda_away"),
        "total_lambda": (
            float(ecse.get("lambda_home") or 0) + float(ecse.get("lambda_away") or 0)
            if ecse.get("lambda_home") is not None
            else None
        ),
        "ecse_model_version": ecse.get("model_version"),
        "ecse_snapshot_id": ecse.get("id"),
        "worldcup_stored_prediction_id": fid,
        "odds_source": canonical_odds.get("provider") or freshness.get("provider"),
        "bookmaker_count": canonical_odds.get("bookmaker_count") or freshness.get("bookmaker_count"),
        "odds_fetched_at_utc": canonical_odds.get("fetched_at_utc") or freshness.get("odds_snapshot_at"),
        "odds_age_seconds": freshness.get("age_seconds") or freshness.get("odds_age_seconds"),
        "allowed_ttl_seconds": freshness.get("allowed_ttl_seconds"),
        "odds_freshness_status": freshness.get("odds_freshness_class") or freshness.get("freshness_class"),
        "data_quality": payload.get("data_quality") or ecse.get("data_quality_score"),
        "warnings": payload.get("warnings") or [],
        "model_agreement": payload.get("model_agreement"),
        "content_hash": freeze_row.get("content_hash") if freeze_row else None,
        "freeze_id": freeze_row.get("prediction_id") if freeze_row else None,
        "frozen_at_utc": freeze_row.get("frozen_at") if freeze_row else None,
        "freeze_status": freeze_row.get("freeze_status") if freeze_row else None,
        "result_status": "pending",
        "evaluation_status": freeze_row.get("evaluation_status") if freeze_row else "pending",
        "exact_score_rankings": rankings,
        "persistence_complete": bool(wsp_row and ecse and freeze_row and len(rankings) >= 5),
    }
    return record


def verify_tier_b_record(record: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """Validate structured Tier B record completeness."""
    if not record:
        return False, ["record_missing"]
    issues: list[str] = []
    if record.get("prediction_scope") != TIER_B_SCOPE:
        issues.append(f"prediction_scope={record.get('prediction_scope')}")
    if record.get("validation_tier") != TIER_B_VALIDATION:
        issues.append(f"validation_tier={record.get('validation_tier')}")
    if record.get("public_visible") is True:
        issues.append("public_visible_not_false")
    for field in (
        "wde_decision",
        "probability_home",
        "probability_draw",
        "probability_away",
        "ecse_top1",
        "ecse_snapshot_id",
        "freeze_id",
        "content_hash",
    ):
        if record.get(field) is None:
            issues.append(f"missing_{field}")
    if not record.get("exact_score_rankings") or len(record["exact_score_rankings"]) < 5:
        issues.append("exact_score_rankings_incomplete")
    return len(issues) == 0, issues


def finalize_tier_b_structured_persistence(
    fixture_id: int,
    *,
    prod_conn: sqlite3.Connection,
    persistence_ctx: TierBPersistenceContext,
    forward_evaluation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stamp scope columns and return structured persistence metadata."""
    if persistence_ctx.validation_tier != TIER_B_VALIDATION:
        return {"status": "skipped", "reason": "not_tier_b", "fixture_id": int(fixture_id)}
    if persistence_ctx.prediction_scope != TIER_B_SCOPE:
        return {
            "status": "skipped",
            "reason": "not_owner_shadow_scope",
            "fixture_id": int(fixture_id),
            "prediction_scope": persistence_ctx.prediction_scope,
        }

    stamped = stamp_structured_scope(
        prod_conn,
        int(fixture_id),
        prediction_scope=persistence_ctx.prediction_scope,
        validation_tier=persistence_ctx.validation_tier,
        source_runtime=persistence_ctx.source_runtime,
    )

    record = read_tier_b_structured_record(
        int(fixture_id),
        prod_conn=prod_conn,
        prediction_scope=persistence_ctx.prediction_scope,
    )
    ok, issues = verify_tier_b_record(record)

    return {
        "status": "complete" if ok else "partial",
        "fixture_id": int(fixture_id),
        "prediction_scope": persistence_ctx.prediction_scope,
        "validation_tier": persistence_ctx.validation_tier,
        "public_visible": False,
        "source_runtime": persistence_ctx.source_runtime,
        "scope_stamped": stamped,
        "forward_evaluation": forward_evaluation,
        "structured_record": record,
        "verification_pass": ok,
        "verification_issues": issues,
        "freeze_id": (forward_evaluation or {}).get("freeze_id") or (record or {}).get("freeze_id"),
        "content_hash": (forward_evaluation or {}).get("content_hash") or (record or {}).get("content_hash"),
    }

"""Canonical prediction-to-freeze bridge — post-persistence hook only."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.forward_evaluation.freeze_service import create_or_reuse_freeze
from worldcup_predictor.gpt_actions.owner_scope import fixture_tier
from worldcup_predictor.research.ecse_live.store import get_snapshot

BRIDGE_ORIGINS = frozenset({"owner_daily", "mcp", "gpt_actions"})


@dataclass
class ForwardEvalBridgeContext:
    prediction_scope: str = "production"
    validation_tier: str | None = None
    public_visible: bool | None = None
    source_job_id: str | None = None
    bridge_origin: str = "mcp"
    worldcup_stored_prediction_id: int | None = None
    ecse_snapshot_id: int | None = None

    def to_source_context(self) -> dict[str, Any]:
        ctx: dict[str, Any] = {
            "prediction_scope": self.prediction_scope,
            "bridge_origin": self.bridge_origin,
        }
        if self.validation_tier is not None:
            ctx["validation_tier"] = self.validation_tier
        if self.public_visible is not None:
            ctx["public_visible"] = self.public_visible
        if self.source_job_id:
            ctx["source_job_id"] = self.source_job_id
        return ctx

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> ForwardEvalBridgeContext | None:
        if not data:
            return None
        return cls(
            prediction_scope=str(data.get("prediction_scope") or "production"),
            validation_tier=data.get("validation_tier"),
            public_visible=data.get("public_visible"),
            source_job_id=data.get("source_job_id"),
            bridge_origin=str(data.get("bridge_origin") or "mcp"),
            worldcup_stored_prediction_id=data.get("worldcup_stored_prediction_id"),
            ecse_snapshot_id=data.get("ecse_snapshot_id"),
        )


@dataclass
class ForwardEvalBridgeResult:
    status: str
    fixture_id: int
    freeze_id: str | None = None
    reused: bool = False
    created: bool = False
    quarantined: bool = False
    conflict_detected: bool = False
    content_hash: str | None = None
    source_payload_hash: str | None = None
    source_prediction_id: int | None = None
    source_ecse_snapshot_id: int | None = None
    reason_code: str | None = None
    warnings: list[str] = field(default_factory=list)
    bridge_origin: str | None = None
    prediction_scope: str | None = None
    capture_error: str | None = None

    @classmethod
    def skipped(cls, fixture_id: int, reason_code: str, *, bridge_origin: str | None = None) -> ForwardEvalBridgeResult:
        return cls(
            status="skipped",
            fixture_id=int(fixture_id),
            reason_code=reason_code,
            bridge_origin=bridge_origin,
        )

    @classmethod
    def from_capture(cls, capture: dict[str, Any], *, bridge_origin: str | None = None) -> ForwardEvalBridgeResult:
        return cls(
            status=str(capture.get("status") or "failed"),
            fixture_id=int(capture.get("fixture_id") or 0),
            freeze_id=capture.get("freeze_id"),
            reused=bool(capture.get("reused")),
            created=bool(capture.get("created")),
            quarantined=bool(capture.get("quarantined")),
            conflict_detected=bool(capture.get("conflict_detected")),
            content_hash=capture.get("content_hash"),
            source_payload_hash=capture.get("source_payload_hash"),
            source_prediction_id=capture.get("source_prediction_id"),
            source_ecse_snapshot_id=capture.get("source_ecse_snapshot_id"),
            reason_code=capture.get("reason_code"),
            warnings=list(capture.get("warnings") or []),
            bridge_origin=bridge_origin,
        )

    def to_metadata_block(self) -> dict[str, Any]:
        evaluation_ready = None
        if self.status in {"created", "reused"} and not self.quarantined and not self.conflict_detected:
            evaluation_ready = "pending_result"
        return {
            "capture_status": self.status,
            "freeze_id": self.freeze_id,
            "fixture_id": self.fixture_id,
            "reused": self.reused,
            "created": self.created,
            "quarantined": self.quarantined,
            "conflict_detected": self.conflict_detected,
            "content_hash": self.content_hash,
            "source_payload_hash": self.source_payload_hash,
            "source_prediction_id": self.source_prediction_id,
            "source_ecse_snapshot_id": self.source_ecse_snapshot_id,
            "reason_code": self.reason_code,
            "warnings": self.warnings,
            "bridge_origin": self.bridge_origin,
            "prediction_scope": self.prediction_scope,
            "evaluation_ready": evaluation_ready,
        }


def forward_evaluation_metadata_block(result: ForwardEvalBridgeResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, dict):
        return ForwardEvalBridgeResult.from_capture(result).to_metadata_block()
    return result.to_metadata_block()


def _resolve_ecse_snapshot_id(
    prod_conn: sqlite3.Connection,
    fixture_id: int,
    explicit_id: int | None,
) -> int | None:
    if explicit_id is not None:
        return int(explicit_id)
    snap = get_snapshot(prod_conn, int(fixture_id))
    if snap and snap.get("id") is not None:
        return int(snap["id"])
    return None


def _has_wsp(prod_conn: sqlite3.Connection, fixture_id: int) -> bool:
    row = prod_conn.execute(
        """
        SELECT 1 FROM worldcup_stored_predictions
        WHERE fixture_id = ? AND (is_active IS NULL OR is_active = 1)
        LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    return row is not None


def capture_forward_eval_freeze_from_stored(
    fixture_id: int,
    *,
    prod_conn: sqlite3.Connection | None = None,
    eval_conn: sqlite3.Connection | None = None,
    worldcup_stored_prediction_id: int | None = None,
    ecse_snapshot_id: int | None = None,
    source_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Facade over create_or_reuse_freeze with optional connection management."""
    settings = get_settings()
    own_prod = prod_conn is None
    own_eval = eval_conn is None
    prod = prod_conn or connect(settings.sqlite_path)
    ev = eval_conn or connect_eval_db(project_root())
    try:
        wsp_id = int(worldcup_stored_prediction_id or fixture_id)
        ecse_id = _resolve_ecse_snapshot_id(prod, int(fixture_id), ecse_snapshot_id)
        return create_or_reuse_freeze(
            int(fixture_id),
            prod_conn=prod,
            eval_conn=ev,
            worldcup_stored_prediction_id=wsp_id,
            ecse_snapshot_id=ecse_id,
            source_context=source_context,
        )
    finally:
        if own_prod:
            prod.close()
        if own_eval:
            ev.close()


def maybe_capture_after_prediction_persistence(
    fixture_id: int,
    *,
    prod_conn: sqlite3.Connection,
    bridge_context: ForwardEvalBridgeContext | dict[str, Any] | None = None,
    quality_status: str | None = None,
    ecse_snapshot_id: int | None = None,
) -> ForwardEvalBridgeResult:
    """Canonical post-persistence hook — never reruns prediction or calls providers."""
    ctx = (
        bridge_context
        if isinstance(bridge_context, ForwardEvalBridgeContext)
        else ForwardEvalBridgeContext.from_mapping(bridge_context)
    ) or ForwardEvalBridgeContext(bridge_origin="mcp")

    fid = int(fixture_id)
    if quality_status == "BLOCKED":
        out = ForwardEvalBridgeResult.skipped(fid, "PREDICTION_BLOCKED", bridge_origin=ctx.bridge_origin)
        out.prediction_scope = ctx.prediction_scope
        return out

    if not _has_wsp(prod_conn, fid):
        out = ForwardEvalBridgeResult.skipped(fid, "MISSING_WSP", bridge_origin=ctx.bridge_origin)
        out.prediction_scope = ctx.prediction_scope
        return out

    resolved_ecse_id = _resolve_ecse_snapshot_id(prod_conn, fid, ecse_snapshot_id or ctx.ecse_snapshot_id)
    if resolved_ecse_id is None:
        out = ForwardEvalBridgeResult.skipped(fid, "MISSING_ECSE", bridge_origin=ctx.bridge_origin)
        out.prediction_scope = ctx.prediction_scope
        return out

    tier = ctx.validation_tier
    if tier is None:
        row = prod_conn.execute(
            "SELECT competition_key FROM fixtures WHERE fixture_id=? LIMIT 1",
            (fid,),
        ).fetchone()
        tier = fixture_tier(str(row["competition_key"])) if row else None
    public_visible = ctx.public_visible
    if public_visible is None:
        public_visible = tier == "A" and ctx.prediction_scope != "owner_shadow"

    source_ctx = ctx.to_source_context()
    source_ctx["validation_tier"] = tier
    source_ctx["public_visible"] = public_visible

    try:
        capture = capture_forward_eval_freeze_from_stored(
            fid,
            prod_conn=prod_conn,
            eval_conn=None,
            worldcup_stored_prediction_id=int(ctx.worldcup_stored_prediction_id or fid),
            ecse_snapshot_id=resolved_ecse_id,
            source_context=source_ctx,
        )
    except Exception as exc:
        out = ForwardEvalBridgeResult(
            status="failed",
            fixture_id=fid,
            reason_code="BRIDGE_CAPTURE_ERROR",
            capture_error=f"{type(exc).__name__}: {exc}"[:300],
            bridge_origin=ctx.bridge_origin,
            prediction_scope=ctx.prediction_scope,
        )
        return out

    out = ForwardEvalBridgeResult.from_capture(capture, bridge_origin=ctx.bridge_origin)
    out.prediction_scope = ctx.prediction_scope
    return out

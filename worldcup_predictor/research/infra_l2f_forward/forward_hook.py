"""Non-blocking L2-F / Exact V2 forward-shadow hook for owner daily lifecycle.

Runs AFTER successful canonical freeze. Never raises to the caller.
Never writes canonical prediction/freeze tables.
"""

from __future__ import annotations

import logging
import sqlite3
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.football_strength_foundation.historical_match_service import (
    HistoricalMatchService,
)
from worldcup_predictor.research.football_strength_foundation.team_strength_engine import (
    TeamStrengthEngine,
)
from worldcup_predictor.research.infra_l2f_forward.job_store import get_job, upsert_job
from worldcup_predictor.research.infra_l2f_forward.shadow_orchestrator import run_shadow_pipeline

logger = logging.getLogger(__name__)

OWNER_SCOPES = frozenset({"production", "owner_shadow", "owner_daily"})
LAMBDA_PREFIX = "LAMBDA_V2_"
EXACT_PREFIX = "EXACT_V2_"
RUN_ID = "l2f-forward-v1"
COHORT_TRUE_FORWARD = "true_forward"
COHORT_HISTORICAL = "historical_replay"
COHORT_RECOVERED = "historical_replay_result_recovered"

CLASS_SUCCESS = "true_forward_success"
CLASS_SKIPPED_NOT_OWNER = "true_forward_skipped_not_owner"
CLASS_SKIPPED_POSTKICKOFF = "true_forward_skipped_postkickoff"
CLASS_BLOCKED_MISSING_FREEZE = "true_forward_blocked_missing_freeze"
CLASS_BLOCKED_INVALID_INPUTS = "true_forward_blocked_invalid_inputs"
CLASS_FAILED_INTERNAL = "true_forward_failed_internal"
CLASS_ALREADY_SUCCESS = "already_success_idempotent"
CLASS_HISTORICAL_SUCCESS = "historical_shadow_success"
CLASS_HISTORICAL_SKIPPED = "historical_shadow_skipped"
CLASS_HISTORICAL_BLOCKED = "historical_shadow_blocked"
CLASS_HISTORICAL_FAILED = "historical_shadow_failed"

_HIST_CACHE: dict[str, HistoricalMatchService] = {}


def _get_history_service(fi_path: str) -> HistoricalMatchService:
    svc = _HIST_CACHE.get(fi_path)
    if svc is None:
        svc = HistoricalMatchService(fi_path=fi_path)
        _HIST_CACHE[fi_path] = svc
    return svc


def _settings_flags(settings: Any | None) -> dict[str, Any]:
    if settings is None:
        try:
            from worldcup_predictor.config.settings import get_settings

            settings = get_settings()
        except Exception:  # noqa: BLE001
            return {
                "mode": "shadow",
                "kill_switch": False,
                "timeout_sec": 90.0,
                "fi_path": "data/football_intelligence.db",
            }
    return {
        "mode": str(getattr(settings, "l2f_forward_shadow_mode", "shadow") or "shadow"),
        "kill_switch": bool(getattr(settings, "l2f_forward_shadow_kill_switch", False)),
        "timeout_sec": float(getattr(settings, "l2f_forward_shadow_timeout_sec", 90.0) or 90.0),
        "fi_path": str(getattr(settings, "sqlite_path", "data/football_intelligence.db")),
    }


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace(" ", "T")
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


def _naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def resolve_cohort_type(*, backfill: bool, freeze_meta: dict[str, Any] | None) -> str:
    """Backfill/historical modes must never label rows as true_forward."""
    meta = freeze_meta or {}
    explicit = str(meta.get("cohort_type") or "").strip()
    if backfill:
        if explicit == COHORT_RECOVERED:
            return COHORT_RECOVERED
        if explicit == COHORT_TRUE_FORWARD:
            # Guard: backfill cannot claim true_forward.
            return COHORT_HISTORICAL
        return explicit or COHORT_HISTORICAL
    if explicit and explicit != COHORT_TRUE_FORWARD:
        # Non-backfill owner path is true_forward unless explicitly historical recovered.
        if explicit == COHORT_RECOVERED:
            return COHORT_RECOVERED
    return COHORT_TRUE_FORWARD


def classify_outcome(
    *,
    status: str,
    reason: str | None,
    cohort_type: str,
) -> str:
    st = str(status or "")
    rs = str(reason or "")
    is_tf = cohort_type == COHORT_TRUE_FORWARD
    if rs == "already_success_idempotent" or st == "already_success_idempotent":
        return CLASS_ALREADY_SUCCESS
    if not is_tf:
        if st == "success":
            return CLASS_HISTORICAL_SUCCESS
        if st == "skipped":
            return CLASS_HISTORICAL_SKIPPED
        if st == "blocked":
            return CLASS_HISTORICAL_BLOCKED
        return CLASS_HISTORICAL_FAILED
    if st == "success":
        return CLASS_SUCCESS
    if st == "skipped":
        if rs in {"scope_not_owner_production", "kill_switch"} or rs.startswith("mode_"):
            return CLASS_SKIPPED_NOT_OWNER if "scope" in rs or rs == "scope_not_owner_production" else CLASS_SKIPPED_NOT_OWNER
        if rs == "post_kickoff" or "postkickoff" in rs.replace("-", "").replace("_", ""):
            return CLASS_SKIPPED_POSTKICKOFF
        return CLASS_SKIPPED_NOT_OWNER if "scope" in rs else CLASS_BLOCKED_INVALID_INPUTS
    if st == "blocked":
        if rs in {"missing_freeze_id", "freeze_status_none", "freeze_status_None"} or rs.startswith("freeze_status_"):
            return CLASS_BLOCKED_MISSING_FREEZE
        if rs in {"post_kickoff", "frozen_at_not_before_kickoff", "prediction_not_before_kickoff"}:
            return CLASS_SKIPPED_POSTKICKOFF
        if rs in {"missing_canonical_lambdas", "fixture_not_found", "freeze_quarantined_or_conflict"}:
            return CLASS_BLOCKED_INVALID_INPUTS if rs != "missing_freeze_id" else CLASS_BLOCKED_MISSING_FREEZE
        if "freeze" in rs and ("missing" in rs or "status" in rs):
            return CLASS_BLOCKED_MISSING_FREEZE
        return CLASS_BLOCKED_INVALID_INPUTS
    return CLASS_FAILED_INTERNAL


def _load_fixture(conn, fixture_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, competition_key, kickoff_utc, status
        FROM fixtures WHERE fixture_id=?
        """,
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else None


def _canonical_lambdas(conn, fixture_id: int) -> tuple[float | None, float | None]:
    try:
        row = conn.execute(
            """
            SELECT lambda_home, lambda_away FROM ecse_prediction_snapshots
            WHERE fixture_id=? ORDER BY id DESC LIMIT 1
            """,
            (int(fixture_id),),
        ).fetchone()
        if row and row["lambda_home"] is not None and row["lambda_away"] is not None:
            return float(row["lambda_home"]), float(row["lambda_away"])
    except Exception:  # noqa: BLE001
        pass
    return None, None


def _odds_row(conn, fixture_id: int) -> dict[str, Any] | None:
    try:
        from worldcup_predictor.research.ecse_live.prediction_builder import build_odds_feature_row

        return build_odds_feature_row(conn, int(fixture_id))
    except Exception as exc:  # noqa: BLE001
        logger.info("l2f_shadow odds_row unavailable fixture=%s err=%s", fixture_id, type(exc).__name__)
        return None


def _count_rows(conn, fixture_id: int, prefix: str) -> int:
    try:
        from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE

        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM {SHADOW_TABLE} WHERE fixture_id=? AND model_id LIKE ?",
            (int(fixture_id), f"{prefix}%"),
        ).fetchone()
        return int(row["n"] if row and "n" in row.keys() else row[0])
    except Exception:  # noqa: BLE001
        return 0


def _persist(
    conn,
    *,
    job_id: str,
    fixture_id: int,
    freeze_id: str | None,
    run_id: str,
    status: str,
    reason: str | None,
    cohort_type: str,
    classification: str,
    prediction_scope: str | None = None,
    kickoff_utc: str | None = None,
    frozen_at_utc: str | None = None,
    retry_count: int = 0,
    stages: list[dict[str, Any]] | None = None,
    lambda_rows: int = 0,
    exact_rows: int = 0,
    duration_ms: float | None = None,
    started_at_utc: str | None = None,
    completed_at_utc: str | None = None,
) -> None:
    upsert_job(
        conn,
        job_id=job_id,
        fixture_id=int(fixture_id),
        freeze_id=freeze_id,
        run_id=run_id,
        status=status,
        reason=reason,
        retry_count=retry_count,
        stages=stages,
        lambda_rows=lambda_rows,
        exact_rows=exact_rows,
        duration_ms=duration_ms,
        cohort_type=cohort_type,
        classification=classification,
        kickoff_utc=kickoff_utc,
        frozen_at_utc=frozen_at_utc,
        prediction_scope=prediction_scope,
        started_at_utc=started_at_utc,
        completed_at_utc=completed_at_utc,
    )


def maybe_run_l2f_forward_shadow(
    *,
    conn,
    fixture_id: int,
    freeze_meta: dict[str, Any] | None,
    prediction_scope: str | None = None,
    settings: Any | None = None,
    backfill: bool = False,
) -> dict[str, Any]:
    """
    Invoke after successful freeze. Never raises. Never blocks canonical.

    Returns a metadata dict suitable for attaching to owner-daily detail payloads.
    """
    flags = _settings_flags(settings)
    freeze_id = None if not freeze_meta else freeze_meta.get("freeze_id")
    run_id = RUN_ID if not backfill else f"{RUN_ID}-backfill"
    job_id = f"l2f-{fixture_id}-{freeze_id or 'nofreeze'}-{run_id}"
    cohort_type = resolve_cohort_type(backfill=backfill, freeze_meta=freeze_meta)
    frozen_at_raw = None if not freeze_meta else (freeze_meta.get("frozen_at") or freeze_meta.get("frozen_at_utc"))
    scope = str(prediction_scope or (freeze_meta or {}).get("prediction_scope") or "")
    base = {
        "shadow_system": "l2f_forward",
        "canonical_unaffected": True,
        "fixture_id": int(fixture_id),
        "freeze_id": freeze_id,
        "run_id": run_id,
        "job_id": job_id,
        "cohort_type": cohort_type,
        "backfill": bool(backfill),
    }

    def _out(status: str, reason: str | None, **extra: Any) -> dict[str, Any]:
        classification = classify_outcome(status=status, reason=reason, cohort_type=cohort_type)
        payload = {**base, "status": status, "reason": reason, "classification": classification, **extra}
        return payload

    try:
        if flags["kill_switch"]:
            out = _out("skipped", "kill_switch")
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="skipped",
                reason="kill_switch",
                cohort_type=cohort_type,
                classification=out["classification"],
                prediction_scope=scope or None,
                frozen_at_utc=str(frozen_at_raw) if frozen_at_raw else None,
            )
            return out

        if flags["mode"] != "shadow":
            out = _out("skipped", f"mode_{flags['mode']}")
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="skipped",
                reason=out["reason"],
                cohort_type=cohort_type,
                classification=out["classification"],
                prediction_scope=scope or None,
            )
            return out

        if scope not in OWNER_SCOPES:
            out = _out("skipped", "scope_not_owner_production", scope=scope)
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="skipped",
                reason=out["reason"],
                cohort_type=cohort_type,
                classification=CLASS_SKIPPED_NOT_OWNER,
                prediction_scope=scope or None,
            )
            out["classification"] = CLASS_SKIPPED_NOT_OWNER
            return out

        if not freeze_id:
            out = _out("blocked", "missing_freeze_id")
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="blocked",
                reason=out["reason"],
                cohort_type=cohort_type,
                classification=CLASS_BLOCKED_MISSING_FREEZE,
                prediction_scope=scope or None,
            )
            out["classification"] = CLASS_BLOCKED_MISSING_FREEZE
            return out

        capture_status = (freeze_meta or {}).get("capture_status")
        if capture_status not in ("created", "reused"):
            out = _out("blocked", f"freeze_status_{capture_status}")
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="blocked",
                reason=out["reason"],
                cohort_type=cohort_type,
                classification=CLASS_BLOCKED_MISSING_FREEZE,
                prediction_scope=scope or None,
            )
            out["classification"] = CLASS_BLOCKED_MISSING_FREEZE
            return out

        if (freeze_meta or {}).get("quarantined") or (freeze_meta or {}).get("conflict_detected"):
            out = _out("blocked", "freeze_quarantined_or_conflict")
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="blocked",
                reason=out["reason"],
                cohort_type=cohort_type,
                classification=CLASS_BLOCKED_INVALID_INPUTS,
                prediction_scope=scope or None,
            )
            out["classification"] = CLASS_BLOCKED_INVALID_INPUTS
            return out

        existing = get_job(conn, fixture_id=int(fixture_id), freeze_id=freeze_id, run_id=run_id)
        if existing and existing.get("status") == "success":
            return {
                **base,
                "status": "skipped",
                "reason": "already_success_idempotent",
                "classification": CLASS_ALREADY_SUCCESS,
                "lambda_rows": existing.get("lambda_rows"),
                "exact_rows": existing.get("exact_rows"),
                "retry_count": existing.get("retry_count") or 0,
            }

        retry_count = int((existing or {}).get("retry_count") or 0)
        if existing and existing.get("status") in ("failed", "blocked"):
            retry_count += 1

        fx = _load_fixture(conn, int(fixture_id))
        if not fx:
            out = _out("blocked", "fixture_not_found", retry_count=retry_count)
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="blocked",
                reason=out["reason"],
                cohort_type=cohort_type,
                classification=CLASS_BLOCKED_INVALID_INPUTS,
                prediction_scope=scope or None,
                retry_count=retry_count,
            )
            out["classification"] = CLASS_BLOCKED_INVALID_INPUTS
            return out

        kickoff = _parse_dt(fx.get("kickoff_utc"))
        kickoff_raw = fx.get("kickoff_utc")
        frozen_at = _parse_dt(str(frozen_at_raw) if frozen_at_raw else None)
        now = datetime.now(timezone.utc)

        # Prematch boundary: freeze/prediction timestamps must be before kickoff.
        if kickoff is not None and frozen_at is not None and _naive(frozen_at) >= _naive(kickoff):
            out = _out("blocked", "frozen_at_not_before_kickoff", retry_count=retry_count)
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="blocked",
                reason=out["reason"],
                cohort_type=cohort_type,
                classification=CLASS_SKIPPED_POSTKICKOFF,
                prediction_scope=scope or None,
                kickoff_utc=str(kickoff_raw) if kickoff_raw else None,
                frozen_at_utc=str(frozen_at_raw) if frozen_at_raw else None,
                retry_count=retry_count,
            )
            out["classification"] = CLASS_SKIPPED_POSTKICKOFF
            return out

        if kickoff is not None and _naive(now) >= _naive(kickoff) and not backfill:
            out = _out("blocked", "post_kickoff", retry_count=retry_count)
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="blocked",
                reason=out["reason"],
                cohort_type=cohort_type,
                classification=CLASS_SKIPPED_POSTKICKOFF,
                prediction_scope=scope or None,
                kickoff_utc=str(kickoff_raw) if kickoff_raw else None,
                frozen_at_utc=str(frozen_at_raw) if frozen_at_raw else None,
                retry_count=retry_count,
            )
            out["classification"] = CLASS_SKIPPED_POSTKICKOFF
            return out

        # True-forward path: wall-clock prediction time must also be before kickoff.
        if not backfill and kickoff is not None and _naive(now) >= _naive(kickoff):
            out = _out("blocked", "prediction_not_before_kickoff", retry_count=retry_count)
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="blocked",
                reason=out["reason"],
                cohort_type=cohort_type,
                classification=CLASS_SKIPPED_POSTKICKOFF,
                prediction_scope=scope or None,
                kickoff_utc=str(kickoff_raw) if kickoff_raw else None,
                retry_count=retry_count,
            )
            out["classification"] = CLASS_SKIPPED_POSTKICKOFF
            return out

        lh, la = _canonical_lambdas(conn, int(fixture_id))
        if freeze_meta:
            if freeze_meta.get("canonical_lambda_home") is not None:
                try:
                    lh = float(freeze_meta["canonical_lambda_home"])
                except (TypeError, ValueError):
                    pass
            if freeze_meta.get("canonical_lambda_away") is not None:
                try:
                    la = float(freeze_meta["canonical_lambda_away"])
                except (TypeError, ValueError):
                    pass
        if lh is None or la is None:
            out = _out("blocked", "missing_canonical_lambdas", retry_count=retry_count)
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="blocked",
                reason=out["reason"],
                cohort_type=cohort_type,
                classification=CLASS_BLOCKED_INVALID_INPUTS,
                prediction_scope=scope or None,
                kickoff_utc=str(kickoff_raw) if kickoff_raw else None,
                retry_count=retry_count,
            )
            out["classification"] = CLASS_BLOCKED_INVALID_INPUTS
            return out

        odds_row = _odds_row(conn, int(fixture_id))
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        if kickoff is not None:
            ko = _naive(kickoff)
            cutoff = min(now_naive, ko) if ko else now_naive
        else:
            cutoff = now_naive
        timeout = float(flags["timeout_sec"])
        fi_path = str(flags["fi_path"])
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

        def _work() -> dict[str, Any]:
            wconn = sqlite3.connect(fi_path, timeout=60.0)
            wconn.row_factory = sqlite3.Row
            try:
                hist = _get_history_service(fi_path)
                engine = TeamStrengthEngine(hist)
                res = run_shadow_pipeline(
                    conn=wconn,
                    fixture_id=int(fixture_id),
                    home_team=str(fx.get("home_team") or ""),
                    away_team=str(fx.get("away_team") or ""),
                    league=str(fx.get("competition_key") or "unknown"),
                    cutoff=cutoff,
                    engine=engine,
                    odds_row=odds_row,
                    canonical_lh=float(lh),
                    canonical_la=float(la),
                    canonical_prediction_id=str(freeze_id) if freeze_id else None,
                    odds_fresh=True if odds_row else False,
                )
                return {
                    "canonical_blocked": res.canonical_blocked,
                    "stages": [
                        {"stage": s.stage, "ok": s.ok, "detail": s.detail[:240]} for s in res.stages
                    ],
                }
            finally:
                wconn.close()

        t0 = datetime.now(timezone.utc)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_work)
                work = fut.result(timeout=timeout)
        except FuturesTimeout:
            out = _out("failed", "timeout", retry_count=retry_count, timeout_sec=timeout)
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="failed",
                reason="timeout",
                cohort_type=cohort_type,
                classification=CLASS_FAILED_INTERNAL if cohort_type == COHORT_TRUE_FORWARD else CLASS_HISTORICAL_FAILED,
                prediction_scope=scope or None,
                kickoff_utc=str(kickoff_raw) if kickoff_raw else None,
                frozen_at_utc=str(frozen_at_raw) if frozen_at_raw else None,
                retry_count=retry_count,
                duration_ms=(datetime.now(timezone.utc) - t0).total_seconds() * 1000.0,
                started_at_utc=started_at,
                completed_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            )
            out["classification"] = (
                CLASS_FAILED_INTERNAL if cohort_type == COHORT_TRUE_FORWARD else CLASS_HISTORICAL_FAILED
            )
            logger.warning("l2f_shadow timeout fixture=%s", fixture_id)
            return out

        if work.get("canonical_blocked"):
            out = _out("failed", "canonical_blocked_flag", retry_count=retry_count)
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="failed",
                reason=out["reason"],
                cohort_type=cohort_type,
                classification=CLASS_FAILED_INTERNAL,
                prediction_scope=scope or None,
                retry_count=retry_count,
                stages=work.get("stages"),
                started_at_utc=started_at,
            )
            out["classification"] = CLASS_FAILED_INTERNAL
            return out

        lambda_rows = _count_rows(conn, int(fixture_id), LAMBDA_PREFIX)
        exact_rows = _count_rows(conn, int(fixture_id), EXACT_PREFIX)
        stage_fail = [s for s in (work.get("stages") or []) if not s.get("ok")]
        status = "success" if not stage_fail else "failed"
        reason = None if status == "success" else ",".join(f"{s['stage']}:{s['detail']}" for s in stage_fail)[:500]
        duration_ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000.0
        completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        classification = classify_outcome(status=status, reason=reason, cohort_type=cohort_type)
        _persist(
            conn,
            job_id=job_id,
            fixture_id=int(fixture_id),
            freeze_id=freeze_id,
            run_id=run_id,
            status=status,
            reason=reason,
            cohort_type=cohort_type,
            classification=classification,
            prediction_scope=scope or None,
            kickoff_utc=str(kickoff_raw) if kickoff_raw else None,
            frozen_at_utc=str(frozen_at_raw) if frozen_at_raw else None,
            retry_count=retry_count,
            stages=work.get("stages"),
            lambda_rows=lambda_rows,
            exact_rows=exact_rows,
            duration_ms=duration_ms,
            started_at_utc=started_at,
            completed_at_utc=completed_at,
        )
        logger.info(
            "l2f_shadow fixture=%s status=%s cohort=%s class=%s lambda_rows=%s exact_rows=%s duration_ms=%.1f",
            fixture_id,
            status,
            cohort_type,
            classification,
            lambda_rows,
            exact_rows,
            duration_ms,
        )
        return {
            **base,
            "status": status,
            "reason": reason,
            "classification": classification,
            "retry_count": retry_count,
            "stages": work.get("stages"),
            "lambda_rows": lambda_rows,
            "exact_rows": exact_rows,
            "duration_ms": duration_ms,
            "started_at_utc": started_at,
            "completed_at_utc": completed_at,
        }
    except Exception as exc:  # noqa: BLE001 — hard isolation
        logger.warning("l2f_shadow exception fixture=%s err=%s", fixture_id, type(exc).__name__)
        classification = CLASS_FAILED_INTERNAL if cohort_type == COHORT_TRUE_FORWARD else CLASS_HISTORICAL_FAILED
        try:
            _persist(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="failed",
                reason=f"{type(exc).__name__}: {exc}"[:400],
                cohort_type=cohort_type,
                classification=classification,
                prediction_scope=scope or None,
            )
        except Exception:  # noqa: BLE001
            pass
        return {
            **base,
            "status": "failed",
            "reason": f"{type(exc).__name__}: {exc}"[:400],
            "classification": classification,
            "traceback_tail": traceback.format_exc()[-500:],
        }


def run_l2f_forward_shadow_safe(**kwargs: Any) -> dict[str, Any]:
    try:
        return maybe_run_l2f_forward_shadow(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return {
            "shadow_system": "l2f_forward",
            "status": "failed",
            "reason": f"outer_{type(exc).__name__}",
            "classification": CLASS_FAILED_INTERNAL,
            "canonical_unaffected": True,
        }

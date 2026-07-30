"""Non-blocking L2-F / Exact V2 forward-shadow hook for owner daily lifecycle.

Runs AFTER successful canonical freeze. Never raises to the caller.
Never writes canonical prediction/freeze tables.
"""

from __future__ import annotations

import logging
import sqlite3
import traceback
import uuid
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
_HIST_CACHE: dict[str, HistoricalMatchService] = {}


def _get_history_service(fi_path: str) -> HistoricalMatchService:
    """Process-level cache — avoid reloading the FI strength store per fixture."""
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


def _parse_kickoff(raw: str | None) -> datetime | None:
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
    base = {
        "shadow_system": "l2f_forward",
        "canonical_unaffected": True,
        "fixture_id": int(fixture_id),
        "freeze_id": freeze_id,
        "run_id": run_id,
        "job_id": job_id,
    }

    try:
        if flags["kill_switch"]:
            out = {**base, "status": "skipped", "reason": "kill_switch"}
            upsert_job(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="skipped",
                reason="kill_switch",
            )
            return out

        if flags["mode"] != "shadow":
            out = {**base, "status": "skipped", "reason": f"mode_{flags['mode']}"}
            upsert_job(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="skipped",
                reason=out["reason"],
            )
            return out

        scope = str(prediction_scope or (freeze_meta or {}).get("prediction_scope") or "")
        if scope not in OWNER_SCOPES:
            out = {**base, "status": "skipped", "reason": "scope_not_owner_production", "scope": scope}
            upsert_job(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="skipped",
                reason=out["reason"],
            )
            return out

        capture_status = (freeze_meta or {}).get("capture_status")
        if capture_status not in ("created", "reused"):
            out = {**base, "status": "skipped", "reason": f"freeze_status_{capture_status}"}
            upsert_job(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="skipped",
                reason=out["reason"],
            )
            return out

        if (freeze_meta or {}).get("quarantined") or (freeze_meta or {}).get("conflict_detected"):
            out = {**base, "status": "blocked", "reason": "freeze_quarantined_or_conflict"}
            upsert_job(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="blocked",
                reason=out["reason"],
            )
            return out

        existing = get_job(conn, fixture_id=int(fixture_id), freeze_id=freeze_id, run_id=run_id)
        if existing and existing.get("status") == "success":
            return {
                **base,
                "status": "skipped",
                "reason": "already_success_idempotent",
                "lambda_rows": existing.get("lambda_rows"),
                "exact_rows": existing.get("exact_rows"),
                "retry_count": existing.get("retry_count") or 0,
            }

        retry_count = int((existing or {}).get("retry_count") or 0)
        if existing and existing.get("status") in ("failed", "blocked"):
            retry_count += 1

        fx = _load_fixture(conn, int(fixture_id))
        if not fx:
            out = {**base, "status": "blocked", "reason": "fixture_not_found", "retry_count": retry_count}
            upsert_job(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="blocked",
                reason=out["reason"],
                retry_count=retry_count,
            )
            return out

        kickoff = _parse_kickoff(fx.get("kickoff_utc"))
        now = datetime.now(timezone.utc)
        if kickoff is not None and kickoff <= now and not backfill:
            out = {**base, "status": "blocked", "reason": "post_kickoff", "retry_count": retry_count}
            upsert_job(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="blocked",
                reason=out["reason"],
                retry_count=retry_count,
            )
            return out

        lh, la = _canonical_lambdas(conn, int(fixture_id))
        # Prefer immutable freeze lambdas when provided (historical replay safety).
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
            out = {**base, "status": "blocked", "reason": "missing_canonical_lambdas", "retry_count": retry_count}
            upsert_job(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="blocked",
                reason=out["reason"],
                retry_count=retry_count,
            )
            return out

        odds_row = _odds_row(conn, int(fixture_id))
        # Strength store uses naive UTC timestamps — keep cutoff naive.
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        if kickoff is not None:
            ko = kickoff.replace(tzinfo=None) if kickoff.tzinfo else kickoff
            cutoff = min(now_naive, ko)
        else:
            cutoff = now_naive
        timeout = float(flags["timeout_sec"])
        fi_path = str(flags["fi_path"])

        def _work() -> dict[str, Any]:
            # Dedicated connection: SQLite objects are not thread-safe across threads.
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
            out = {
                **base,
                "status": "failed",
                "reason": "timeout",
                "retry_count": retry_count,
                "timeout_sec": timeout,
            }
            upsert_job(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="failed",
                reason="timeout",
                retry_count=retry_count,
                duration_ms=(datetime.now(timezone.utc) - t0).total_seconds() * 1000.0,
            )
            logger.warning("l2f_shadow timeout fixture=%s", fixture_id)
            return out

        if work.get("canonical_blocked"):
            # Defensive: orchestrator must never set this; treat as failed isolation breach.
            out = {**base, "status": "failed", "reason": "canonical_blocked_flag", "retry_count": retry_count}
            upsert_job(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="failed",
                reason=out["reason"],
                retry_count=retry_count,
                stages=work.get("stages"),
            )
            return out

        lambda_rows = _count_rows(conn, int(fixture_id), LAMBDA_PREFIX)
        exact_rows = _count_rows(conn, int(fixture_id), EXACT_PREFIX)
        stage_fail = [s for s in (work.get("stages") or []) if not s.get("ok")]
        status = "success" if not stage_fail else "failed"
        reason = None if status == "success" else ",".join(f"{s['stage']}:{s['detail']}" for s in stage_fail)[:500]
        duration_ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000.0
        upsert_job(
            conn,
            job_id=job_id,
            fixture_id=int(fixture_id),
            freeze_id=freeze_id,
            run_id=run_id,
            status=status,
            reason=reason,
            retry_count=retry_count,
            stages=work.get("stages"),
            lambda_rows=lambda_rows,
            exact_rows=exact_rows,
            duration_ms=duration_ms,
        )
        logger.info(
            "l2f_shadow fixture=%s status=%s lambda_rows=%s exact_rows=%s duration_ms=%.1f",
            fixture_id,
            status,
            lambda_rows,
            exact_rows,
            duration_ms,
        )
        return {
            **base,
            "status": status,
            "reason": reason,
            "retry_count": retry_count,
            "stages": work.get("stages"),
            "lambda_rows": lambda_rows,
            "exact_rows": exact_rows,
            "duration_ms": duration_ms,
        }
    except Exception as exc:  # noqa: BLE001 — hard isolation
        logger.warning(
            "l2f_shadow exception fixture=%s err=%s",
            fixture_id,
            type(exc).__name__,
        )
        try:
            upsert_job(
                conn,
                job_id=job_id,
                fixture_id=int(fixture_id),
                freeze_id=freeze_id,
                run_id=run_id,
                status="failed",
                reason=f"{type(exc).__name__}: {exc}"[:400],
            )
        except Exception:  # noqa: BLE001
            pass
        return {
            **base,
            "status": "failed",
            "reason": f"{type(exc).__name__}: {exc}"[:400],
            "traceback_tail": traceback.format_exc()[-500:],
        }


def run_l2f_forward_shadow_safe(**kwargs: Any) -> dict[str, Any]:
    """Alias used by callers that expect a *_safe naming pattern."""
    try:
        return maybe_run_l2f_forward_shadow(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return {
            "shadow_system": "l2f_forward",
            "status": "failed",
            "reason": f"outer_{type(exc).__name__}",
            "canonical_unaffected": True,
        }

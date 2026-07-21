"""Per-fixture daily drain: sequential predict+freeze with failure isolation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.gpt_actions.competition_normalize import (
    is_friendly_competition,
    normalize_competition_key,
)
from worldcup_predictor.gpt_actions.owner_scope import fixture_tier
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.owner_daily.odds_import import scan_fixture_odds_readiness
from worldcup_predictor.owner_daily.pipeline.drain_ledger import (
    BLOCKED,
    COMPLETED,
    ELIGIBLE,
    FAILED_FINAL,
    FAILED_RETRYABLE,
    FROZEN,
    POST_KICKOFF_SKIPPED,
    QUEUED,
    RUNNING,
    DrainLedger,
    idempotency_key,
)
from worldcup_predictor.owner_daily.pipeline.eligibility import prediction_scope_for_tier
from worldcup_predictor.owner_daily.predictions import run_daily_predictions
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

BUSY_FAILURE_CODES = frozenset(
    {
        "job_concurrency_limit",
        "PIPELINE_LOCK_BUSY",
        "busy",
        "lock busy",
    }
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00").replace(" UTC", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class DrainConfig:
    report_date: str
    concurrency: int = 1
    max_attempts: int = 3
    busy_wait_sec: float = 15.0
    busy_max_waits: int = 40
    dry_run: bool = False
    simulate_only: bool = False  # historical / Jul 16 acceptance — no predict/freeze writes
    eligibility_as_of: datetime | None = None  # freeze clock for post-kickoff / sim
    strict_fresh_odds: bool = False
    force_predictions: bool = False
    ledger_path: Path | None = None


@dataclass
class DrainResult:
    report_date: str
    enqueued: int = 0
    processed: int = 0
    reconcile: dict[str, int] = field(default_factory=dict)
    items: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_date": self.report_date,
            "enqueued": self.enqueued,
            "processed": self.processed,
            "reconcile": self.reconcile,
            "items": self.items,
            "errors": self.errors,
        }


def _classify_pre_queue(
    fixture: DailyFixture,
    *,
    conn,
    settings: Settings,
    sm: SportmonksProvider,
    oa: OddAlertsClient,
    now: datetime,
    simulate_odds_relaxed: bool = False,
) -> tuple[str, str | None, str, dict[str, Any]]:
    """Return (queue_state, block_reason, scope, meta)."""
    canon = normalize_competition_key(fixture.competition_key) or fixture.competition_key
    tier = fixture_tier(fixture.competition_key)
    scope = prediction_scope_for_tier(tier) or "owner_shadow"
    meta: dict[str, Any] = {
        "tier": tier,
        "competition_key": canon,
        "public_visible": tier == "A",
        "simulate_odds_relaxed": simulate_odds_relaxed,
    }

    if is_friendly_competition(fixture.competition_key):
        return BLOCKED, "friendly_excluded", scope, meta
    if tier is None:
        return BLOCKED, "unsupported_competition", scope, meta

    kickoff = _parse_kickoff(fixture.kickoff_utc)
    status = str(fixture.status or "").upper()
    if kickoff and kickoff <= now and status not in ("NS", "TBD", "SCHEDULED"):
        return POST_KICKOFF_SKIPPED, "post_kickoff", scope, meta
    if kickoff and kickoff <= now and status in ("NS", "TBD", "SCHEDULED"):
        # kickoff passed but status stale — still skip predict/freeze for safety
        return POST_KICKOFF_SKIPPED, "kickoff_passed", scope, meta

    ready = scan_fixture_odds_readiness(conn, fixture, settings=settings, sm=sm, oa=oa)
    meta["odds"] = {
        "has_1x2": ready.get("has_1x2"),
        "has_ou25": ready.get("has_ou25"),
        "has_btts": ready.get("has_btts"),
        "odds_freshness": ready.get("odds_freshness"),
    }
    # Historical simulation: accept any pre-kickoff snapshot with 1X2 (do not require live freshness)
    if meta.get("simulate_odds_relaxed"):
        n = conn.execute(
            "SELECT COUNT(*) FROM odds_snapshots WHERE fixture_id=? AND snapshot_at<=?",
            (int(fixture.provider_fixture_id), fixture.kickoff_utc or "9999"),
        ).fetchone()[0]
        if int(n) > 0 or ready.get("has_1x2"):
            return ELIGIBLE, None, scope, meta
        return BLOCKED, "missing_odds", scope, meta

    if ready.get("odds_freshness") == "stale":
        return BLOCKED, "stale_odds", scope, meta
    if not (ready.get("has_1x2") and ready.get("has_ou25") and ready.get("has_btts")):
        return BLOCKED, "missing_odds", scope, meta

    return ELIGIBLE, None, scope, meta


def enqueue_discovered_fixtures(
    fixtures: list[DailyFixture],
    *,
    report_date: str,
    ledger: DrainLedger,
    settings: Settings | None = None,
    as_of: datetime | None = None,
    simulate_odds_relaxed: bool = False,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    now = as_of or _utc_now()
    conn = connect(settings.sqlite_path)
    sm = SportmonksProvider(settings)
    oa = OddAlertsClient()
    rows: list[dict[str, Any]] = []
    try:
        # Deterministic order: kickoff then fixture_id
        ordered = sorted(
            fixtures,
            key=lambda f: (str(f.kickoff_utc or ""), int(f.provider_fixture_id)),
        )
        for fx in ordered:
            state, reason, scope, meta = _classify_pre_queue(
                fx,
                conn=conn,
                settings=settings,
                sm=sm,
                oa=oa,
                now=now,
                simulate_odds_relaxed=simulate_odds_relaxed,
            )
            row = ledger.upsert_discovered(
                report_date=report_date,
                fixture_id=int(fx.provider_fixture_id),
                scope=scope,
                competition_key=fx.competition_key,
                kickoff_utc=fx.kickoff_utc,
                queue_state=QUEUED if state == ELIGIBLE else state,
                block_reason=reason,
                meta=meta,
            )
            if state == ELIGIBLE and row.get("queue_state") not in (
                FROZEN,
                BLOCKED,
                FAILED_FINAL,
                POST_KICKOFF_SKIPPED,
                COMPLETED,
            ):
                key = idempotency_key(report_date, int(fx.provider_fixture_id), scope)
                row = ledger.mark(key, queue_state=QUEUED) or row
            rows.append(row)
    finally:
        conn.close()
    return rows


def _is_busy_error(exc: BaseException | str | None) -> bool:
    text = str(exc or "").lower()
    if not text:
        return False
    if "job_concurrency_limit" in text or "lock busy" in text or "pipeline_lock_busy" in text:
        return True
    return "busy" in text and "timeout" not in text


def _process_one(
    fixture: DailyFixture,
    row: dict[str, Any],
    *,
    config: DrainConfig,
    ledger: DrainLedger,
    settings: Settings,
) -> dict[str, Any]:
    key = str(row["idempotency_key"])
    scope = str(row["scope"])
    fid = int(row["fixture_id"])

    if config.simulate_only or config.dry_run:
        ledger.mark(
            key,
            queue_state=COMPLETED,
            prediction_status="SIMULATED_NO_WRITE",
            finished=True,
            component_status={"simulate_only": True, "would_scope": scope},
        )
        return ledger.get_by_key(key) or row

    ledger.mark(key, queue_state=RUNNING, started=True, increment_attempt=True, job_id=f"drain:{key}")

    waits = 0
    while True:
        try:
            pred = run_daily_predictions(
                [fixture],
                dry_run=False,
                force=config.force_predictions,
                strict_fresh_odds=config.strict_fresh_odds,
                settings=settings,
            )
            captures = pred.forward_eval_captures or []
            cap = next((c for c in captures if int(c.get("fixture_id") or 0) == fid), None)
            wde_ok = pred.wde_generated > 0 or any(
                (s.get("engine") == "wde" and s.get("reason") == "existing_prediction") for s in pred.skipped
            )
            ecse_ok = pred.ecse_generated > 0 or any(
                (s.get("engine") == "ecse" and s.get("reason") == "existing_snapshot") for s in pred.skipped
            )
            component = {
                "wde": "ok" if wde_ok else "missing",
                "ecse": "ok" if ecse_ok else "missing",
                "wde_skip": pred.wde_skip_reasons,
                "ecse_skip": pred.ecse_skip_reasons,
                "capture": cap,
            }
            freeze_id = (cap or {}).get("freeze_id")
            cap_status = str((cap or {}).get("capture_status") or "")
            partial = not (wde_ok and ecse_ok)

            if freeze_id and cap_status in ("created", "reused") and not (cap or {}).get("quarantined"):
                return (
                    ledger.mark(
                        key,
                        queue_state=FROZEN,
                        prediction_status="PARTIAL" if partial else "OK",
                        freeze_id=str(freeze_id),
                        finished=True,
                        component_status=component,
                    )
                    or row
                )

            if partial:
                return (
                    ledger.mark(
                        key,
                        queue_state=COMPLETED,
                        prediction_status="PARTIAL",
                        freeze_id=str(freeze_id) if freeze_id else None,
                        block_reason="partial_prediction",
                        finished=True,
                        component_status=component,
                    )
                    or row
                )

            # prediction ran but freeze missing — retryable until attempts exhausted
            attempt = int((ledger.get_by_key(key) or {}).get("attempt_count") or 0)
            if attempt >= int(row.get("max_attempts") or config.max_attempts):
                return (
                    ledger.mark(
                        key,
                        queue_state=FAILED_FINAL,
                        prediction_status="OK_NO_FREEZE",
                        failure_code="FREEZE_MISSING",
                        finished=True,
                        component_status=component,
                    )
                    or row
                )
            return (
                ledger.mark(
                    key,
                    queue_state=FAILED_RETRYABLE,
                    prediction_status="OK_NO_FREEZE",
                    failure_code="FREEZE_MISSING",
                    component_status=component,
                )
                or row
            )
        except Exception as exc:
            if _is_busy_error(exc) and waits < config.busy_max_waits:
                waits += 1
                ledger.mark(
                    key,
                    queue_state=QUEUED,
                    failure_code="BUSY_WAIT",
                    next_retry_at=None,
                )
                time.sleep(config.busy_wait_sec)
                continue
            attempt_row = ledger.get_by_key(key) or row
            attempt = int(attempt_row.get("attempt_count") or 0)
            if _is_busy_error(exc) or attempt < int(row.get("max_attempts") or config.max_attempts):
                return (
                    ledger.mark(
                        key,
                        queue_state=FAILED_RETRYABLE,
                        failure_code=type(exc).__name__,
                        block_reason=str(exc)[:300],
                    )
                    or row
                )
            return (
                ledger.mark(
                    key,
                    queue_state=FAILED_FINAL,
                    failure_code=type(exc).__name__,
                    block_reason=str(exc)[:300],
                    finished=True,
                )
                or row
            )


def drain_daily_queue(
    fixtures: list[DailyFixture],
    *,
    config: DrainConfig,
    ledger: DrainLedger | None = None,
    settings: Settings | None = None,
) -> DrainResult:
    """Enqueue all fixtures then process pending items with concurrency=1."""
    settings = settings or get_settings()
    own_ledger = ledger is None
    ledger = ledger or DrainLedger(config.ledger_path)
    result = DrainResult(report_date=config.report_date)
    try:
        as_of = config.eligibility_as_of or _utc_now()
        enqueued = enqueue_discovered_fixtures(
            fixtures,
            report_date=config.report_date,
            ledger=ledger,
            settings=settings,
            as_of=as_of,
            simulate_odds_relaxed=bool(config.simulate_only),
        )
        result.enqueued = len(enqueued)

        fx_by_id = {int(f.provider_fixture_id): f for f in fixtures}
        # concurrency=1 sequential drain; resume picks FAILED_RETRYABLE + QUEUED + RUNNING
        pending = ledger.list_pending(config.report_date)
        # Reset stale RUNNING from prior crash back to QUEUED
        for row in list(pending):
            if row["queue_state"] == RUNNING:
                ledger.mark(str(row["idempotency_key"]), queue_state=QUEUED)
        pending = ledger.list_pending(config.report_date)

        for row in pending:
            fid = int(row["fixture_id"])
            fx = fx_by_id.get(fid)
            if not fx:
                ledger.mark(
                    str(row["idempotency_key"]),
                    queue_state=FAILED_FINAL,
                    failure_code="FIXTURE_NOT_IN_DISCOVERY",
                    finished=True,
                )
                continue
            # Re-check post-kickoff immediately before work (skipped in simulate_only)
            kickoff = _parse_kickoff(fx.kickoff_utc)
            if kickoff and kickoff <= _utc_now() and not config.simulate_only:
                ledger.mark(
                    str(row["idempotency_key"]),
                    queue_state=POST_KICKOFF_SKIPPED,
                    block_reason="kickoff_passed_before_run",
                    finished=True,
                )
                result.processed += 1
                continue
            updated = _process_one(fx, row, config=config, ledger=ledger, settings=settings)
            result.processed += 1
            result.items.append(
                {
                    "fixture_id": fid,
                    "queue_state": updated.get("queue_state"),
                    "prediction_status": updated.get("prediction_status"),
                    "freeze_id": updated.get("freeze_id"),
                    "failure_code": updated.get("failure_code"),
                    "block_reason": updated.get("block_reason"),
                    "attempt_count": updated.get("attempt_count"),
                }
            )

        result.reconcile = ledger.reconcile(config.report_date)
        result.items = [
            {
                "fixture_id": r["fixture_id"],
                "scope": r["scope"],
                "queue_state": r["queue_state"],
                "attempt_count": r["attempt_count"],
                "job_id": r["job_id"],
                "prediction_status": r["prediction_status"],
                "freeze_id": r["freeze_id"],
                "block_reason": r["block_reason"],
                "failure_code": r["failure_code"],
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
            }
            for r in ledger.export_day(config.report_date)
        ]
    except Exception as exc:
        result.errors.append(str(exc))
    finally:
        if own_ledger:
            ledger.close()
    return result

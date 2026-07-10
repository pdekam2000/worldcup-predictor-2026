"""Phase 7B — Daily forward evaluation orchestrator."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.forward_evaluation.batch import (
    batch_id_for,
    store_excluded,
    upsert_batch_record,
    write_batch_manifest,
)
from worldcup_predictor.forward_evaluation.constants import DEFAULT_TIMEZONE, ELIGIBLE
from worldcup_predictor.forward_evaluation.context import build_prediction_context
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.forward_evaluation.discovery import discover_forward_evaluation_fixtures, production_conn
from worldcup_predictor.forward_evaluation.evaluate import evaluate_frozen_prediction
from worldcup_predictor.forward_evaluation.freeze import capture_canonical_prediction, store_frozen_prediction
from worldcup_predictor.forward_evaluation.gates import classify_candidate
from worldcup_predictor.forward_evaluation.results import sync_actual_result
from worldcup_predictor.gpt_actions.delegation import _match_odds


def run_daily_forward_evaluation(
    *,
    target_date: str | date | None = None,
    timezone: str = DEFAULT_TIMEZONE,
    dry_run: bool = False,
) -> dict[str, Any]:
    d = (target_date or date.today()).isoformat() if isinstance(target_date, date) else str(target_date or date.today())
    settings = get_settings()
    discovery = discover_forward_evaluation_fixtures(target_date=d, timezone=timezone)
    batch_id = batch_id_for(d)

    eval_conn = connect_eval_db()
    prod_conn = production_conn()
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    frozen_rows: list[dict[str, Any]] = []
    evaluated_rows: list[dict[str, Any]] = []

    try:
        for fixture in discovery.get("fixtures") or []:
            status, detail = classify_candidate(prod_conn, fixture=fixture, settings=settings)
            if status != ELIGIBLE:
                excluded.append({"fixture_id": fixture["fixture_id"], "reason": status, "detail": detail})
                if not dry_run:
                    store_excluded(
                        eval_conn,
                        batch_id=batch_id,
                        fixture=fixture,
                        reason=status,
                        detail=detail,
                    )
                continue
            eligible.append({**fixture, "gate_detail": detail})
            if dry_run:
                continue

            tier = str(fixture.get("tier") or "A")
            frozen = capture_canonical_prediction(prod_conn=prod_conn, fixture=fixture, tier=tier)
            odds = _match_odds(prod_conn, int(fixture["fixture_id"]))
            frozen["odds_home"] = odds.get("home")
            frozen["odds_draw"] = odds.get("draw")
            frozen["odds_away"] = odds.get("away")
            frozen["bookmaker_count"] = odds.get("bookmaker_count")

            store_result = store_frozen_prediction(eval_conn, batch_id=batch_id, frozen=frozen)
            if store_result.get("stored"):
                frozen["prediction_id"] = store_result["prediction_id"]
                ctx = build_prediction_context(frozen)
                eval_conn.execute(
                    """
                    INSERT OR REPLACE INTO prediction_context (
                        prediction_id, competition, tier, odds_regime, entropy_bucket, top3_mass_bucket,
                        top5_mass_bucket, conflict_class, market_agreement_class, data_quality_class,
                        freshness_class, bookmaker_count_bucket, lambda_bucket, favorite_class
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        store_result["prediction_id"],
                        ctx.get("competition"),
                        ctx.get("tier"),
                        ctx.get("odds_regime"),
                        ctx.get("entropy_bucket"),
                        ctx.get("top3_mass_bucket"),
                        ctx.get("top5_mass_bucket"),
                        ctx.get("conflict_class"),
                        ctx.get("market_agreement_class"),
                        ctx.get("data_quality_class"),
                        ctx.get("freshness_class"),
                        ctx.get("bookmaker_count_bucket"),
                        ctx.get("lambda_bucket"),
                        ctx.get("favorite_class"),
                    ),
                )
                eval_conn.commit()
                frozen_rows.append(frozen)
            elif store_result.get("prediction_id"):
                existing = eval_conn.execute(
                    "SELECT * FROM frozen_predictions WHERE prediction_id=?",
                    (store_result["prediction_id"],),
                ).fetchone()
                if existing:
                    frozen_rows.append(dict(existing))

        if not dry_run:
            for row in frozen_rows:
                pid = row.get("prediction_id")
                if not pid:
                    continue
                sync_actual_result(eval_conn, prod_conn, int(row["fixture_id"]))
                ev = evaluate_frozen_prediction(eval_conn, prediction_id=str(pid))
                if ev.get("evaluated"):
                    evaluated_rows.append(ev)

        manifest = write_batch_manifest(
            evaluation_date=d,
            timezone=timezone,
            discovered=discovery.get("fixtures") or [],
            eligible=eligible,
            excluded=excluded,
            frozen=frozen_rows,
            evaluated=evaluated_rows,
        )
        if not dry_run:
            upsert_batch_record(eval_conn, manifest)

        return {
            "batch_id": batch_id,
            "date": d,
            "dry_run": dry_run,
            "discovered_count": discovery.get("discovered_count"),
            "eligible_count": len(eligible),
            "frozen_count": len(frozen_rows),
            "excluded_count": len(excluded),
            "evaluated_count": len(evaluated_rows),
            "manifest": manifest,
            "excluded": excluded,
        }
    finally:
        eval_conn.close()
        prod_conn.close()


def sync_and_evaluate_pending(*, dry_run: bool = False) -> dict[str, Any]:
    eval_conn = connect_eval_db()
    prod_conn = production_conn()
    synced = 0
    evaluated = 0
    try:
        pending = eval_conn.execute(
            "SELECT prediction_id, fixture_id FROM frozen_predictions WHERE evaluation_status='PENDING'"
        ).fetchall()
        for row in pending:
            fid = int(row["fixture_id"])
            if dry_run:
                continue
            sr = sync_actual_result(eval_conn, prod_conn, fid)
            if sr.get("synced"):
                synced += 1
            ev = evaluate_frozen_prediction(eval_conn, prediction_id=str(row["prediction_id"]))
            if ev.get("evaluated"):
                evaluated += 1
        return {"synced": synced, "evaluated": evaluated, "pending_checked": len(pending)}
    finally:
        eval_conn.close()
        prod_conn.close()

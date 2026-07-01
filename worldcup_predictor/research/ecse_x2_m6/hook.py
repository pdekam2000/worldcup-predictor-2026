"""PHASE ECSE-X2-M6 — ECSE live generation shadow hook (never changes public output)."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_x2_m6.lift_model import get_lift_model
from worldcup_predictor.research.ecse_x2_m6.odds import build_probs_for_fixture
from worldcup_predictor.research.ecse_x2_m6.runtime import compute_shadow_live_shortlist
from worldcup_predictor.research.ecse_x2_m6.store import append_shadow_shortlist

logger = logging.getLogger(__name__)


def attach_shadow_live_shortlist(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    prediction: dict[str, Any],
    snapshot_id: int | None = None,
) -> dict[str, Any] | None:
    """
    Compute and persist shadow shortlist alongside ECSE live snapshot.
    Safe to call from ECSE-LIVE path; failures are swallowed by caller.
    """
    settings = get_settings()
    if not settings.ecse_x2_m6_shadow_live_enabled:
        return None

    baseline_top10 = prediction.get("top_10_scorelines") or []
    if not baseline_top10:
        return None

    probs, coverage, odds_snapshot_id = build_probs_for_fixture(conn, fixture_id, prediction)
    lift_model = get_lift_model(conn)

    meta = {
        "kickoff_utc": prediction.get("kickoff_utc"),
        "competition_key": prediction.get("competition_key"),
        "league": prediction.get("competition_key"),
        "home_team": prediction.get("home_team"),
        "away_team": prediction.get("away_team"),
    }

    result = compute_shadow_live_shortlist(
        fixture_id=fixture_id,
        baseline_top10=baseline_top10,
        probs=probs,
        lift_model=lift_model,
        coverage=coverage,
        fixture_metadata=meta,
    )

    storage_row = {
        **result,
        "snapshot_id": snapshot_id,
        "odds_snapshot_id": odds_snapshot_id,
        "evaluation_status": "pending",
    }
    appended, reason = append_shadow_shortlist(storage_row)
    storage_row["storage_reason"] = reason
    storage_row["storage_appended"] = appended

    from worldcup_predictor.research.ecse_x3_b.hook import safe_attach_x3_owner_shadow

    safe_attach_x3_owner_shadow(
        conn,
        fixture_id=fixture_id,
        prediction=prediction,
        m5_shadow=storage_row,
        odds_snapshot_id=odds_snapshot_id,
    )
    return storage_row


def safe_attach_shadow_live_shortlist(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    prediction: dict[str, Any],
    snapshot_id: int | None = None,
) -> None:
    try:
        attach_shadow_live_shortlist(
            conn,
            fixture_id=fixture_id,
            prediction=prediction,
            snapshot_id=snapshot_id,
        )
    except Exception:
        logger.exception("ECSE-X2-M6 shadow attach failed fixture_id=%s", fixture_id)

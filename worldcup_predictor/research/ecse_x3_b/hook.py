"""PHASE ECSE-X3-B — ECSE live shadow hook (owner lab only)."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_x2_m6.odds import build_probs_for_fixture
from worldcup_predictor.research.ecse_x3_b.runtime import compute_x3_owner_shadow_row
from worldcup_predictor.research.ecse_x3_b.store import append_owner_shadow_row

logger = logging.getLogger(__name__)


def attach_x3_owner_shadow(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    prediction: dict[str, Any],
    m5_shadow: dict[str, Any] | None = None,
    odds_snapshot_id: int | None = None,
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.ecse_x3_b_owner_shadow_lab_enabled:
        return None

    baseline_top10 = prediction.get("top_10_scorelines") or []
    if not baseline_top10:
        return None

    probs, _coverage, snap_id = build_probs_for_fixture(conn, fixture_id, prediction)
    snap_id = odds_snapshot_id or snap_id

    meta = {
        "kickoff_utc": prediction.get("kickoff_utc"),
        "competition_key": prediction.get("competition_key"),
        "league": prediction.get("competition_key"),
        "home_team": prediction.get("home_team"),
        "away_team": prediction.get("away_team"),
    }

    row = compute_x3_owner_shadow_row(
        fixture_id=fixture_id,
        baseline_top10=baseline_top10,
        probs=probs,
        odds_snapshot_id=snap_id,
        m5_shadow=m5_shadow,
        fixture_metadata=meta,
    )
    appended, reason = append_owner_shadow_row(row)
    row["storage_appended"] = appended
    row["storage_reason"] = reason
    return row


def safe_attach_x3_owner_shadow(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    prediction: dict[str, Any],
    m5_shadow: dict[str, Any] | None = None,
    odds_snapshot_id: int | None = None,
) -> None:
    try:
        attach_x3_owner_shadow(
            conn,
            fixture_id=fixture_id,
            prediction=prediction,
            m5_shadow=m5_shadow,
            odds_snapshot_id=odds_snapshot_id,
        )
    except Exception:
        logger.exception("ECSE-X3-B owner shadow attach failed fixture_id=%s", fixture_id)

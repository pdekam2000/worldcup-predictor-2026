"""PHASE GT-1 — Smoke runner for goal timing split predictions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.research.ecse_live.smoke_targets import WIN2DAY_SMOKE_TARGETS
from worldcup_predictor.research.goal_timing_split.features import load_fixture_context
from worldcup_predictor.research.goal_timing_split.predictor import MODEL_VERSION, predict_goal_timing_split
from worldcup_predictor.research.goal_timing_split.store import (
    ensure_goal_timing_split_tables,
    get_prediction,
    insert_prediction,
)

PHASE = "GT-1"


def _norm_team(name: str) -> str:
    return (name or "").lower().strip()


def resolve_smoke_fixture_id(
    conn: sqlite3.Connection,
    home_team: str,
    away_team: str,
) -> int | None:
    """Resolve fixture_id from ECSE live snapshots or fixtures table."""
    rows = conn.execute(
        """
        SELECT fixture_id, home_team, away_team
        FROM ecse_prediction_snapshots
        ORDER BY id DESC
        """
    ).fetchall()
    for row in rows:
        if _norm_team(row["home_team"]) == _norm_team(home_team) and _norm_team(
            row["away_team"]
        ) == _norm_team(away_team):
            return int(row["fixture_id"])

    fx = conn.execute(
        """
        SELECT fixture_id, home_team, away_team FROM fixtures
        WHERE lower(home_team) = lower(?) AND lower(away_team) = lower(?)
        ORDER BY kickoff_utc DESC LIMIT 1
        """,
        (home_team, away_team),
    ).fetchone()
    if fx:
        return int(fx["fixture_id"])
    return None


@dataclass
class SmokeRunResult:
    phase: str = PHASE
    status: str = "ok"
    model_version: str = MODEL_VERSION
    targets: int = 0
    predicted: int = 0
    inserted: int = 0
    already_exists: int = 0
    insufficient: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "status": self.status,
            "model_version": self.model_version,
            "targets": self.targets,
            "predicted": self.predicted,
            "inserted": self.inserted,
            "already_exists": self.already_exists,
            "insufficient": self.insufficient,
            "results": self.results,
            "errors": self.errors[:20],
        }


def run_goal_timing_split_smoke(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
) -> SmokeRunResult:
    ensure_goal_timing_split_tables(conn)
    result = SmokeRunResult(targets=len(WIN2DAY_SMOKE_TARGETS))

    for target in WIN2DAY_SMOKE_TARGETS:
        fid = resolve_smoke_fixture_id(conn, target.home_team, target.away_team)
        if fid is None:
            result.errors.append(f"unresolved:{target.display}")
            result.results.append(
                {
                    "match": target.display,
                    "fixture_id": None,
                    "status": "unresolved",
                }
            )
            continue

        try:
            ctx = load_fixture_context(
                conn, fid, home_team=target.home_team, away_team=target.away_team
            )
            pred = predict_goal_timing_split(ctx)
            result.predicted += 1
            if pred.get("status") == "insufficient_data":
                result.insufficient += 1

            row = {
                "match": target.display,
                "fixture_id": fid,
                "status": pred.get("status", "ok"),
                "recommended_side": pred.get("recommended_side"),
                "recommended_window": pred.get("recommended_window"),
                "confidence_tier": pred.get("confidence_tier"),
                "p_home_0_30": pred.get("p_home_0_30"),
                "p_away_0_30": pred.get("p_away_0_30"),
                "p_home_31_plus": pred.get("p_home_31_plus"),
                "p_away_31_plus": pred.get("p_away_31_plus"),
                "p_no_goal": pred.get("p_no_goal"),
                "data_quality_score": pred.get("data_quality_score"),
            }
            result.results.append(row)

            if dry_run:
                continue

            if get_prediction(conn, fid, MODEL_VERSION):
                result.already_exists += 1
                row["storage"] = "already_exists"
                continue

            ok, reason = insert_prediction(conn, pred)
            if ok:
                result.inserted += 1
                row["storage"] = "inserted"
            else:
                result.already_exists += int(reason == "already_exists")
                row["storage"] = reason
        except Exception as exc:
            result.errors.append(f"{target.display}:{exc}")
            result.results.append(
                {"match": target.display, "fixture_id": fid, "status": "error", "error": str(exc)}
            )

    if not dry_run:
        conn.commit()

    if result.errors and result.predicted == 0:
        result.status = "error"
    elif result.insufficient == result.targets:
        result.status = "insufficient_data"

    return result

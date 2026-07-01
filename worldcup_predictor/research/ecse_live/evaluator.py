"""PHASE ECSE-LIVE-1 — Evaluate frozen ECSE snapshots against final results."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.research.ecse_live.store import (
    ensure_ecse_live_tables,
    insert_evaluation,
    list_snapshots_needing_evaluation,
)
from worldcup_predictor.research.ecse_score_distribution import OTHER_SCORELINE, generate_score_distribution
from worldcup_predictor.schedule.match_center import FINISHED_STATUSES

PHASE = "ECSE-LIVE-1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _minutes_since_kickoff(kickoff_utc: str | None) -> float | None:
    kickoff = _parse_kickoff(kickoff_utc)
    if kickoff is None:
        return None
    return (datetime.now(timezone.utc) - kickoff).total_seconds() / 60.0


def rank_from_frozen_snapshot(
    snapshot: dict[str, Any],
    actual_home: int,
    actual_away: int,
) -> int | None:
    """Rank actual score using frozen snapshot data only (not a fresh prediction)."""
    scoreline = f"{actual_home}-{actual_away}"
    top_10 = snapshot.get("top_10_scorelines") or []
    if isinstance(top_10, str):
        import json

        try:
            top_10 = json.loads(top_10)
        except json.JSONDecodeError:
            top_10 = []

    for item in top_10:
        if str(item.get("scoreline")) == scoreline:
            return int(item["rank"])

    dist = generate_score_distribution(
        float(snapshot["lambda_home"]),
        float(snapshot["lambda_away"]),
    )
    for entry in dist:
        if entry["scoreline"] == scoreline:
            return int(entry["rank"])
        if entry["scoreline"] == OTHER_SCORELINE:
            break
    return None


def evaluate_frozen_snapshot(
    snapshot: dict[str, Any],
    outcome: Any,
) -> dict[str, Any] | None:
    """Compare actual result to frozen top-N lists on the snapshot."""
    if not outcome or not getattr(outcome, "is_finished", False):
        return None

    final_score = outcome.final_score
    if not final_score or "-" not in str(final_score):
        return None

    try:
        home_g, away_g = [int(x.strip()) for x in str(final_score).split("-", 1)]
    except ValueError:
        return None

    actual = f"{home_g}-{away_g}"
    top_1 = str(snapshot.get("top_1_score") or "")
    top_3 = snapshot.get("top_3_scores") or []
    top_5 = snapshot.get("top_5_scores") or []
    top_10_lines = snapshot.get("top_10_scorelines") or []
    top_10 = [str(x.get("scoreline") if isinstance(x, dict) else x) for x in top_10_lines]

    if isinstance(top_3, str):
        import json

        try:
            top_3 = json.loads(top_3)
        except json.JSONDecodeError:
            top_3 = []
    if isinstance(top_5, str):
        import json

        try:
            top_5 = json.loads(top_5)
        except json.JSONDecodeError:
            top_5 = []

    return {
        "snapshot_id": int(snapshot["id"]),
        "fixture_id": int(snapshot["fixture_id"]),
        "final_score": actual,
        "top1_correct": actual == top_1,
        "top3_correct": actual in top_3,
        "top5_correct": actual in top_5,
        "top10_correct": actual in top_10,
        "rank_of_actual_score": rank_from_frozen_snapshot(snapshot, home_g, away_g),
        "actual_home_goals": home_g,
        "actual_away_goals": away_g,
        "status": "evaluated",
        "evaluated_at": _utc_now(),
    }


@dataclass
class EcseEvaluationResult:
    scanned: int = 0
    evaluated: int = 0
    pending: int = 0
    skipped_timing: int = 0
    unable: int = 0
    duplicate: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": PHASE,
            "scanned": self.scanned,
            "evaluated": self.evaluated,
            "pending": self.pending,
            "skipped_timing": self.skipped_timing,
            "unable": self.unable,
            "duplicate": self.duplicate,
            "details": self.details[:50],
        }


def run_ecse_evaluations(
    conn: sqlite3.Connection,
    *,
    settings: Settings | None = None,
    limit: int = 200,
    eval_minutes_after_ft: int | None = None,
) -> EcseEvaluationResult:
    settings = settings or get_settings()
    ensure_ecse_live_tables(conn)
    minutes_after = (
        eval_minutes_after_ft
        if eval_minutes_after_ft is not None
        else settings.ecse_live_eval_minutes_after_ft
    )
    resolver = FixtureOutcomeResolver(settings)
    result = EcseEvaluationResult()

    pending = list_snapshots_needing_evaluation(conn, limit=limit)
    result.scanned = len(pending)

    for snap in pending:
        fid = int(snap["fixture_id"])
        sid = int(snap["id"])
        outcome = resolver.resolve(fid)

        if outcome is None or not outcome.is_finished:
            result.pending += 1
            continue

        status = str(outcome.fixture_status or "").upper()
        if status not in FINISHED_STATUSES:
            result.pending += 1
            continue

        elapsed = _minutes_since_kickoff(snap.get("kickoff_utc"))
        if elapsed is not None and elapsed < (90 + minutes_after):
            result.skipped_timing += 1
            result.pending += 1
            continue

        eval_payload = evaluate_frozen_snapshot(snap, outcome)
        if not eval_payload:
            result.unable += 1
            continue

        _, reason = insert_evaluation(conn, eval_payload)
        if reason == "inserted":
            result.evaluated += 1
            result.details.append(
                {
                    "fixture_id": fid,
                    "snapshot_id": sid,
                    "final_score": eval_payload["final_score"],
                    "top1_correct": eval_payload["top1_correct"],
                    "rank": eval_payload["rank_of_actual_score"],
                }
            )
            try:
                from worldcup_predictor.research.ecse_x2_m6.evaluator import evaluate_fixture_shadow

                evaluate_fixture_shadow(
                    fid,
                    actual_score=str(eval_payload["final_score"]),
                    snapshot_id=sid,
                )
            except Exception:
                pass
        else:
            result.duplicate += 1

    return result

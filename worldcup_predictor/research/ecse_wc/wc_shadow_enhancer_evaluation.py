"""PHASE ECSE-WC-1 — World Cup ECSE baseline vs shadow enhancer evaluation."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_live.store import _hydrate_snapshot, ensure_ecse_live_tables
from worldcup_predictor.research.ecse_x2_m5.metrics import hit_positions
from worldcup_predictor.research.ecse_x2_m6.evaluator import evaluate_shadow_shortlist_row
from worldcup_predictor.research.ecse_x2_m6.lift_model import get_lift_model
from worldcup_predictor.research.ecse_x2_m6.odds import build_probs_for_fixture
from worldcup_predictor.research.ecse_x2_m6.runtime import compute_shadow_live_shortlist

PHASE = "ECSE-WC-1"
DEFAULT_COMPETITION_KEY = "world_cup_2026"

WC_EVAL_JSONL = Path("artifacts/ecse_wc_shadow_enhancer_evaluation.jsonl")
WC_EVAL_SUMMARY = Path("artifacts/ecse_wc_shadow_enhancer_summary.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _is_knockout_round(round_name: str | None) -> bool:
    text = str(round_name or "").lower()
    return any(
        token in text
        for token in (
            "round of",
            "knockout",
            "quarter",
            "semi",
            "final",
            "last 16",
            "last 32",
        )
    )


def _score_in_top10(top10: list[dict[str, Any]], scoreline: str) -> tuple[bool, int | None]:
    for row in top10:
        if str(row.get("scoreline")) == scoreline:
            return True, int(row.get("rank"))
    return False, None


def _prediction_from_snapshot(snap: dict[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": snap["fixture_id"],
        "kickoff_utc": snap.get("kickoff_utc"),
        "competition_key": snap.get("competition_key"),
        "home_team": snap.get("home_team"),
        "away_team": snap.get("away_team"),
        "top_10_scorelines": snap.get("top_10_scorelines") or [],
        "top_1_score": snap.get("top_1_score"),
        "lambda_home": snap.get("lambda_home"),
        "lambda_away": snap.get("lambda_away"),
        "raw_features": snap.get("raw_features") or {},
    }


def _owner_note_wc(
    *,
    row: dict[str, Any],
    baseline_rank: int | None,
    enhanced_rank: int | None,
    actual_score: str,
    match_outcome_type: str | None,
    penalty_score: str | None,
) -> str:
    notes: list[str] = []
    if not row.get("applied"):
        reason = row.get("exclusion_reason") or "not_eligible"
        if reason == "missing_ft_home":
            notes.append("Skipped: ft_home odds missing")
        elif reason == "balanced_match":
            notes.append("Skipped: balanced match — no unsafe reorder")
        elif reason == "home_prob_below_55":
            notes.append("Skipped: home probability below 55%")
        else:
            notes.append(f"Skipped: {str(reason).replace('_', ' ')}")

    if baseline_rank is not None and baseline_rank <= 10:
        notes.append("Actual score was inside Top-10 but rank needs improvement")

    if baseline_rank is not None and enhanced_rank is not None:
        if enhanced_rank < baseline_rank:
            notes.append(f"Enhanced improved rank from {baseline_rank} to {enhanced_rank}")
        elif enhanced_rank > baseline_rank:
            notes.append(f"Enhanced worsened rank from {baseline_rank} to {enhanced_rank}")
        else:
            notes.append("Enhanced rank unchanged")

    mot = str(match_outcome_type or "").upper()
    if mot == "PEN" or penalty_score:
        notes.append("Knockout 1-1/PEN pattern — consider 1-1 as cover score (owner warning only)")

    if actual_score == "1-1" and (mot == "PEN" or penalty_score):
        notes.append("Draw/PEN risk — 1-1 should be considered as cover score")

    return " | ".join(notes) if notes else "Owner research only — no public prediction change"


def load_wc_evaluated_snapshots(
    conn: sqlite3.Connection,
    *,
    competition_key: str = DEFAULT_COMPETITION_KEY,
) -> list[dict[str, Any]]:
    """Load WC ECSE snapshots with provider-backed finished results."""
    ensure_ecse_live_tables(conn)
    rows = conn.execute(
        """
        SELECT
            s.*,
            e.id AS evaluation_id,
            e.final_score,
            e.rank_of_actual_score AS baseline_rank_stored,
            e.top1_correct,
            e.top3_correct,
            e.top5_correct,
            e.top10_correct,
            r.match_outcome_type,
            r.penalty_score,
            r.home_goals,
            r.away_goals,
            f.status AS fixture_status,
            f.round_name
        FROM ecse_prediction_snapshots s
        INNER JOIN ecse_prediction_evaluations e ON e.snapshot_id = s.id
        INNER JOIN fixture_results r ON r.fixture_id = s.fixture_id
        LEFT JOIN fixtures f ON f.fixture_id = s.fixture_id
        WHERE COALESCE(s.competition_key, ?) = ?
        ORDER BY s.kickoff_utc ASC
        """,
        (competition_key, competition_key),
    ).fetchall()

    out: list[dict[str, Any]] = []
    for raw in rows:
        snap = _hydrate_snapshot(dict(raw))
        mot = str(
            snap.get("match_outcome_type")
            or snap.get("fixture_status")
            or ""
        ).upper()
        if mot not in {"FT", "AET", "PEN"}:
            continue
        if not snap.get("final_score"):
            continue
        snap["match_outcome_type"] = mot
        out.append(snap)
    return out


def evaluate_wc_fixture_shadow(
    conn: sqlite3.Connection,
    snap: dict[str, Any],
    *,
    lift_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay shadow enhancer for one evaluated WC fixture."""
    fixture_id = int(snap["fixture_id"])
    prediction = _prediction_from_snapshot(snap)
    baseline_top10 = list(prediction["top_10_scorelines"])

    probs, coverage, odds_snapshot_id = build_probs_for_fixture(conn, fixture_id, prediction)
    model = lift_model if lift_model is not None else get_lift_model(conn)

    meta = {
        "kickoff_utc": snap.get("kickoff_utc"),
        "competition_key": snap.get("competition_key"),
        "league": snap.get("competition_key"),
        "home_team": snap.get("home_team"),
        "away_team": snap.get("away_team"),
        "round_name": snap.get("round_name"),
    }

    shadow = compute_shadow_live_shortlist(
        fixture_id=fixture_id,
        baseline_top10=baseline_top10,
        probs=probs,
        lift_model=model,
        coverage=coverage,
        fixture_metadata=meta,
    )

    actual_score = str(snap["final_score"])
    eval_payload = evaluate_shadow_shortlist_row(
        shadow,
        actual_score=actual_score,
        snapshot_id=int(snap["id"]),
    )

    baseline = shadow["baseline_top10"]
    enhanced = shadow["enhanced_top10"]
    base_hits = eval_payload["baseline_hits"]
    enh_hits = eval_payload["enhanced_hits"]
    baseline_rank = base_hits.get("actual_rank")
    enhanced_rank = enh_hits.get("actual_rank")
    rank_delta = (
        (baseline_rank - enhanced_rank)
        if baseline_rank is not None and enhanced_rank is not None
        else None
    )

    outcome = str(
        snap.get("match_outcome_type") or snap.get("fixture_status") or ""
    ).upper()
    penalty_score = snap.get("penalty_score")
    knockout = _is_knockout_round(snap.get("round_name"))
    labels = list(shadow.get("segment_labels") or [])
    if knockout:
        labels.append("knockout")
    if outcome == "PEN":
        labels.append("pen_aet")
    if outcome == "AET":
        labels.append("aet")

    in_11, rank_11_baseline = _score_in_top10(baseline, "1-1")
    _, rank_11_enhanced = _score_in_top10(enhanced, "1-1")
    move_11 = (shadow.get("rank_movements") or {}).get("1-1")

    movement = "same"
    if rank_delta is not None:
        if rank_delta > 0:
            movement = "improved"
        elif rank_delta < 0:
            movement = "worse"

    row = {
        "phase": PHASE,
        "fixture_id": fixture_id,
        "snapshot_id": int(snap["id"]),
        "match": f"{snap.get('home_team')} vs {snap.get('away_team')}",
        "kickoff_time": snap.get("kickoff_utc"),
        "competition_key": snap.get("competition_key") or DEFAULT_COMPETITION_KEY,
        "match_outcome_type": outcome,
        "penalty_score": penalty_score,
        "pen_draw_label": "PEN draw" if outcome == "PEN" and actual_score == "1-1" else None,
        "knockout_round": knockout,
        "round_name": snap.get("round_name"),
        "prediction_top1": snap.get("top_1_score"),
        "actual_score": actual_score,
        "lambda_home": snap.get("lambda_home"),
        "lambda_away": snap.get("lambda_away"),
        "home_prob": shadow.get("home_prob"),
        "equation_value": shadow.get("equation_value"),
        "odds_snapshot_id": odds_snapshot_id,
        "odds_coverage": coverage,
        "baseline_top10": baseline,
        "enhanced_top10": enhanced,
        "baseline_top10_membership": sorted(str(r["scoreline"]) for r in baseline),
        "enhanced_top10_membership": sorted(str(r["scoreline"]) for r in enhanced),
        "membership_unchanged": shadow.get("membership_unchanged"),
        "applied": shadow.get("applied"),
        "exclusion_reason": shadow.get("exclusion_reason"),
        "segment_labels": labels,
        "rank_movements": shadow.get("rank_movements") or {},
        "baseline_rank": baseline_rank,
        "enhanced_rank": enhanced_rank,
        "rank_delta": rank_delta,
        "rank_movement": movement,
        "baseline_hits": base_hits,
        "enhanced_hits": enh_hits,
        "delta": eval_payload.get("delta"),
        "score_1_1_analysis": {
            "in_baseline_top10": in_11,
            "baseline_rank_1_1": rank_11_baseline,
            "enhanced_rank_1_1": rank_11_enhanced,
            "enhancer_move_1_1": move_11,
            "draw_pen_warning": outcome == "PEN" and actual_score == "1-1",
        },
        "owner_note": _owner_note_wc(
            row=shadow,
            baseline_rank=baseline_rank,
            enhanced_rank=enhanced_rank,
            actual_score=actual_score,
            match_outcome_type=outcome,
            penalty_score=penalty_score,
        ),
        "public_output_changed": False,
        "evaluated_at": _utc_now(),
    }
    return row


@dataclass
class WcShadowEvaluationResult:
    phase: str = PHASE
    competition_key: str = DEFAULT_COMPETITION_KEY
    fixture_count: int = 0
    rows: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "competition_key": self.competition_key,
            "fixture_count": self.fixture_count,
            "summary": self.summary,
            "rows": self.rows,
        }


def _aggregate_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}

    def _rates(prefix: str) -> dict[str, float | None]:
        n = len(rows)
        return {
            f"{prefix}_top1": round(
                sum(1 for r in rows if r[f"{prefix}_hits"]["hit_top1"]) / n, 4
            ),
            f"{prefix}_top3": round(
                sum(1 for r in rows if r[f"{prefix}_hits"]["hit_top3"]) / n, 4
            ),
            f"{prefix}_top5": round(
                sum(1 for r in rows if r[f"{prefix}_hits"]["hit_top5"]) / n, 4
            ),
            f"{prefix}_top10": round(
                sum(1 for r in rows if r[f"{prefix}_hits"]["hit_top10"]) / n, 4
            ),
        }

    improved = sum(1 for r in rows if r.get("rank_movement") == "improved")
    worse = sum(1 for r in rows if r.get("rank_movement") == "worse")
    same = sum(1 for r in rows if r.get("rank_movement") == "same")
    applied = sum(1 for r in rows if r.get("applied"))
    rank_deltas = [r["rank_delta"] for r in rows if r.get("rank_delta") is not None]
    baseline_ranks = [r["baseline_rank"] for r in rows if r.get("baseline_rank")]
    enhanced_ranks = [r["enhanced_rank"] for r in rows if r.get("enhanced_rank")]

    by_outcome: dict[str, dict[str, Any]] = {}
    by_segment: dict[str, dict[str, Any]] = {}
    pen_cases: list[dict[str, Any]] = []

    for r in rows:
        mot = str(r.get("match_outcome_type") or "UNKNOWN")
        bucket = by_outcome.setdefault(mot, {"count": 0, "improved": 0, "worse": 0, "applied": 0})
        bucket["count"] += 1
        if r.get("rank_movement") == "improved":
            bucket["improved"] += 1
        if r.get("rank_movement") == "worse":
            bucket["worse"] += 1
        if r.get("applied"):
            bucket["applied"] += 1

        for label in r.get("segment_labels") or []:
            seg = by_segment.setdefault(label, {"count": 0, "improved": 0, "worse": 0})
            seg["count"] += 1
            if r.get("rank_movement") == "improved":
                seg["improved"] += 1
            if r.get("rank_movement") == "worse":
                seg["worse"] += 1

        if r.get("match_outcome_type") == "PEN":
            pen_cases.append(r.get("score_1_1_analysis") or {})

    return {
        "n": len(rows),
        "applied_count": applied,
        "excluded_count": len(rows) - applied,
        "improved_count": improved,
        "same_count": same,
        "worse_count": worse,
        "avg_rank_delta": round(sum(rank_deltas) / len(rank_deltas), 4) if rank_deltas else None,
        "avg_baseline_rank": round(sum(baseline_ranks) / len(baseline_ranks), 4) if baseline_ranks else None,
        "avg_enhanced_rank": round(sum(enhanced_ranks) / len(enhanced_ranks), 4) if enhanced_ranks else None,
        "baseline": _rates("baseline"),
        "enhanced": _rates("enhanced"),
        "by_outcome_type": by_outcome,
        "by_segment": by_segment,
        "pen_knockout_1_1_analysis": {
            "cases": pen_cases,
            "owner_warning": (
                "Draw/PEN risk — for knockout fixtures ending 1-1 after ET, "
                "consider 1-1 as a cover score in owner research (no prediction change)."
            ),
        },
    }


def run_wc_shadow_enhancer_evaluation(
    conn: sqlite3.Connection,
    *,
    competition_key: str = DEFAULT_COMPETITION_KEY,
    jsonl_path: Path | None = None,
    summary_path: Path | None = None,
) -> WcShadowEvaluationResult:
    """Run full WC shadow enhancer replay evaluation."""
    snapshots = load_wc_evaluated_snapshots(conn, competition_key=competition_key)
    lift_model = get_lift_model(conn)

    rows: list[dict[str, Any]] = []
    for snap in snapshots:
        rows.append(evaluate_wc_fixture_shadow(conn, snap, lift_model=lift_model))

    comparison = _aggregate_metrics(rows)
    baseline_ecse = {
        "top1": round(sum(1 for r in rows if r["baseline_hits"]["hit_top1"]) / max(len(rows), 1), 4),
        "top3": round(sum(1 for r in rows if r["baseline_hits"]["hit_top3"]) / max(len(rows), 1), 4),
        "top5": round(sum(1 for r in rows if r["baseline_hits"]["hit_top5"]) / max(len(rows), 1), 4),
        "top10": round(sum(1 for r in rows if r["baseline_hits"]["hit_top10"]) / max(len(rows), 1), 4),
        "avg_actual_rank": comparison.get("avg_baseline_rank"),
    }

    summary = {
        "phase": PHASE,
        "generated_at": _utc_now(),
        "competition_key": competition_key,
        "fixture_count": len(rows),
        "ecse_baseline_summary": baseline_ecse,
        "comparison": comparison,
        "fixture_table": [
            {
                "fixture_id": r["fixture_id"],
                "match": r["match"],
                "prediction_top1": r["prediction_top1"],
                "actual_score": r["actual_score"],
                "baseline_rank": r["baseline_rank"],
                "enhanced_rank": r["enhanced_rank"],
                "rank_delta": r["rank_delta"],
                "applied": r["applied"],
                "exclusion_reason": r["exclusion_reason"],
                "match_outcome_type": r["match_outcome_type"],
                "penalty_score": r["penalty_score"],
                "pen_draw_label": r.get("pen_draw_label"),
                "owner_note": r["owner_note"],
            }
            for r in rows
        ],
        "public_output_changed": False,
        "disclaimer": "Owner/internal evaluation only. No public prediction changes.",
    }

    target_jsonl = jsonl_path or WC_EVAL_JSONL
    target_summary = summary_path or WC_EVAL_SUMMARY
    target_jsonl.parent.mkdir(parents=True, exist_ok=True)
    target_summary.parent.mkdir(parents=True, exist_ok=True)

    lines = "\n".join(json.dumps(r, default=str) for r in rows)
    target_jsonl.write_text(lines + ("\n" if lines else ""), encoding="utf-8")
    target_summary.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    return WcShadowEvaluationResult(
        competition_key=competition_key,
        fixture_count=len(rows),
        rows=rows,
        summary=summary,
    )


def load_wc_shadow_evaluation_summary(path: Path | None = None) -> dict[str, Any] | None:
    target = path or WC_EVAL_SUMMARY
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_wc_shadow_evaluation_rows(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or WC_EVAL_JSONL
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows

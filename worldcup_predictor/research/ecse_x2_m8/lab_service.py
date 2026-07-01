"""PHASE ECSE-X2-M8 — Owner shadow lab service."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from worldcup_predictor.research.ecse_x2_m6.constants import EVAL_ARTIFACT, SHADOW_ARTIFACT
from worldcup_predictor.research.ecse_x2_m6.store import _artifact_path, read_shadow_shortlists
from worldcup_predictor.research.ecse_x2_m7.watch import aggregate_evaluation_watch
from worldcup_predictor.research.ecse_x3_b.owner_summary import build_summary as build_x3_summary
from worldcup_predictor.research.ecse_x3_b.registry import get_registry
from worldcup_predictor.research.ecse_x3_b.store import get_owner_shadow_for_fixture, read_owner_shadow_rows
from worldcup_predictor.research.ecse_wc.knockout_draw_pen_risk import (
    evaluate_fixture_knockout_risk,
    load_knockout_draw_pen_risk_rows,
    load_knockout_draw_pen_risk_summary,
)
from worldcup_predictor.research.ecse_wc.wc_shadow_enhancer_evaluation import (
    load_wc_shadow_evaluation_rows,
    load_wc_shadow_evaluation_summary,
)


def _load_evaluations() -> dict[int, dict[str, Any]]:
    path = _artifact_path(EVAL_ARTIFACT)
    out: dict[int, dict[str, Any]] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            fid = int(row.get("fixture_id") or 0)
            if fid:
                out[fid] = row
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return out


def _top1(scorelines: list[dict[str, Any]] | None) -> str | None:
    if not scorelines:
        return None
    return str(scorelines[0].get("scoreline"))


def _rank_for_actual(top10: list[dict[str, Any]] | None, actual: str | None) -> int | None:
    if not actual or not top10:
        return None
    for row in top10:
        if str(row.get("scoreline")) == actual:
            return int(row.get("rank"))
    return None


def _movement_summary(rank_movements: dict[str, int] | None) -> str:
    moves = rank_movements or {}
    if not moves:
        return "No rank changes"
    ups = sum(1 for v in moves.values() if v > 0)
    downs = sum(1 for v in moves.values() if v < 0)
    return f"{ups} up, {downs} down"


def _owner_note(
    *,
    row: dict[str, Any],
    eval_row: dict[str, Any] | None,
    baseline_rank: int | None,
    enhanced_rank: int | None,
) -> str:
    if not row.get("applied"):
        reason = row.get("exclusion_reason") or "not_eligible"
        if reason == "missing_ft_home":
            return "Skipped: ft_home odds missing"
        if reason == "balanced_match":
            return "Skipped: balanced match"
        if reason == "home_prob_below_55":
            return "Skipped: home probability below 55%"
        return f"Skipped: {reason.replace('_', ' ')}"

    if eval_row and baseline_rank and enhanced_rank:
        if enhanced_rank < baseline_rank:
            return f"Enhanced improved rank from {baseline_rank} to {enhanced_rank}"
        if enhanced_rank > baseline_rank:
            return f"Enhanced worsened rank from {baseline_rank} to {enhanced_rank}"
        return "No useful rank change"

    if row.get("evaluation_status") == "pending":
        b1 = _top1(row.get("baseline_top10"))
        e1 = _top1(row.get("enhanced_top10"))
        if b1 and e1 and b1 != e1:
            return f"Enhanced changed Top-1 from {b1} to {e1}. Pending result."
        if row.get("strong_segment"):
            return "Strong home favorite segment. Pending result."
        return "Pending result. Use only as research signal, not final betting advice."

    return "Use only as research signal, not final betting advice."


def _enrich_row(row: dict[str, Any], eval_row: dict[str, Any] | None) -> dict[str, Any]:
    baseline = row.get("baseline_top10") or []
    enhanced = row.get("enhanced_top10") or []
    actual = (eval_row or {}).get("actual_score")
    baseline_rank = (eval_row or {}).get("baseline_hits", {}).get("actual_rank")
    enhanced_rank = (eval_row or {}).get("enhanced_hits", {}).get("actual_rank")
    if baseline_rank is None and actual:
        baseline_rank = _rank_for_actual(baseline, actual)
    if enhanced_rank is None and actual:
        enhanced_rank = _rank_for_actual(enhanced, actual)

    delta_rank = None
    enhanced_better = False
    enhanced_worse = False
    unchanged = False
    if baseline_rank is not None and enhanced_rank is not None:
        delta_rank = int(baseline_rank) - int(enhanced_rank)
        if delta_rank > 0:
            enhanced_better = True
        elif delta_rank < 0:
            enhanced_worse = True
        else:
            unchanged = True

    labels = row.get("segment_labels") or []
    segment_summary = ", ".join(labels) if labels else "—"

    return {
        "fixture_id": row.get("fixture_id"),
        "kickoff_time": row.get("kickoff_time"),
        "league": row.get("league") or row.get("tournament"),
        "tournament": row.get("tournament") or row.get("league"),
        "home_prob": row.get("home_prob"),
        "segment_labels": labels,
        "segment_summary": segment_summary,
        "strong_segment": bool(row.get("strong_segment")),
        "applied": bool(row.get("applied")),
        "exclusion_reason": row.get("exclusion_reason"),
        "baseline_top1": _top1(baseline),
        "enhanced_top1": _top1(enhanced),
        "baseline_top10": baseline,
        "enhanced_top10": enhanced,
        "rank_movements": row.get("rank_movements") or {},
        "rank_movement_summary": _movement_summary(row.get("rank_movements")),
        "evaluation_status": row.get("evaluation_status"),
        "actual_score": actual,
        "baseline_hit_rank": baseline_rank,
        "enhanced_hit_rank": enhanced_rank,
        "delta_rank": delta_rank,
        "enhanced_better": enhanced_better,
        "enhanced_worse": enhanced_worse,
        "unchanged": unchanged,
        "delta_result": (eval_row or {}).get("delta"),
        "public_output_changed": row.get("public_output_changed", False),
        "odds_snapshot_id": row.get("odds_snapshot_id"),
        "audit_trace": row.get("audit_trace"),
        "owner_note": _owner_note(
            row=row,
            eval_row=eval_row,
            baseline_rank=baseline_rank,
            enhanced_rank=enhanced_rank,
        ),
        "generated_at": row.get("generated_at"),
    }


def _merge_x3(item: dict[str, Any], x3_row: dict[str, Any] | None) -> dict[str, Any]:
    if not x3_row:
        item["x3_candidate"] = "ecse_x3_j2_g_slope"
        item["x3_status"] = "unavailable"
        item["x3_display_label"] = "ECSE X3 — J2/G/OU Slope"
        item["x3_promotion_status"] = "not_promoted"
        item["x3_recommendation"] = "USE_ONLY_HI_J2_G_SLOPE"
        return item

    baseline_rank = item.get("baseline_hit_rank")
    x3_top10 = x3_row.get("x3_top10") or []
    actual = item.get("actual_score")
    x3_rank = _rank_for_actual(x3_top10, actual) if x3_row.get("x3_status") == "available" else None

    item.update(
        {
            "x3_candidate": x3_row.get("x3_candidate"),
            "x3_display_label": "ECSE X3 — J2/G/OU Slope",
            "x3_status": x3_row.get("x3_status"),
            "x3_mode": "shadow_only",
            "x3_promotion_status": "not_promoted",
            "x3_recommendation": "USE_ONLY_HI_J2_G_SLOPE",
            "x3_top1": x3_row.get("x3_top1"),
            "x3_top3": x3_row.get("x3_top3"),
            "x3_top5": x3_row.get("x3_top5"),
            "x3_top10": x3_top10,
            "x3_hit_rank": x3_rank,
            "x3_delta_rank": (baseline_rank - x3_rank) if baseline_rank and x3_rank else None,
            "x3_j2": x3_row.get("j2"),
            "x3_g": x3_row.get("g"),
            "x3_ou_slope": x3_row.get("ou_slope"),
            "x3_missing_fields": x3_row.get("missing_fields") or [],
            "x3_odds_coverage": x3_row.get("odds_coverage_fields") or {},
            "x3_rejection_reason": x3_row.get("rejection_reason"),
            "m5_shadow_top1": x3_row.get("m5_shadow_top1"),
            "m5_shadow_result": x3_row.get("m5_shadow_result"),
            "public_prediction_changed": False,
        }
    )
    if x3_rank and baseline_rank:
        if x3_rank < baseline_rank:
            item["x3_vs_baseline"] = "Enhanced better"
        elif x3_rank > baseline_rank:
            item["x3_vs_baseline"] = "Enhanced worse"
        else:
            item["x3_vs_baseline"] = "No change"
    elif x3_row.get("x3_status") == "unavailable":
        item["x3_vs_baseline"] = "Skipped: missing odds"
    elif x3_row.get("x3_status") == "rejected":
        item["x3_vs_baseline"] = f"Skipped: {x3_row.get('rejection_reason') or 'rejected'}"
    return item


def _fixture_label(conn: sqlite3.Connection | None, fixture_id: int) -> str:
    if conn is None:
        return f"Fixture {fixture_id}"
    try:
        row = conn.execute(
            "SELECT home_team, away_team FROM fixtures WHERE fixture_id = ?",
            (int(fixture_id),),
        ).fetchone()
        if row:
            return f"{row['home_team']} vs {row['away_team']}"
    except sqlite3.Error:
        pass
    snap = conn.execute(
        "SELECT home_team, away_team FROM ecse_prediction_snapshots WHERE fixture_id = ? LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    if snap:
        return f"{snap['home_team']} vs {snap['away_team']}"
    return f"Fixture {fixture_id}"


def _knockout_risk_map() -> dict[int, dict[str, Any]]:
    return {
        int(r["fixture_id"]): r
        for r in load_knockout_draw_pen_risk_rows()
        if r.get("fixture_id")
    }


def _merge_knockout_draw_pen_risk(
    item: dict[str, Any],
    conn: sqlite3.Connection | None,
    risk_map: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    fid = int(item.get("fixture_id") or 0)
    if not fid:
        return item
    risk_map = risk_map if risk_map is not None else _knockout_risk_map()
    row = risk_map.get(fid)
    if row is None and conn is not None:
        try:
            row = evaluate_fixture_knockout_risk(conn, fid)
        except Exception:
            row = None
    if not row:
        item.update(
            {
                "knockout_draw_pen_risk": False,
                "risk_level": "NONE",
                "rank_1_1": None,
                "rank_0_0": None,
                "recommended_cover_scores": [],
                "draw_pen_risk_label": None,
                "knockout_draw_pen_owner_note": "No knockout draw/PEN risk detected.",
            }
        )
        return item
    item.update(
        {
            "knockout_draw_pen_risk": bool(row.get("knockout_draw_pen_risk")),
            "risk_level": row.get("risk_level"),
            "rank_1_1": row.get("rank_1_1"),
            "rank_0_0": row.get("rank_0_0"),
            "recommended_cover_scores": row.get("recommended_cover_scores") or [],
            "draw_pen_risk_label": row.get("draw_pen_risk_label"),
            "knockout_draw_pen_support_signals": row.get("support_signals") or [],
            "knockout_draw_pen_owner_note": row.get("owner_note"),
            "match_outcome_type": row.get("match_outcome_type") or item.get("match_outcome_type"),
            "penalty_score": row.get("penalty_score") if row.get("penalty_score") is not None else item.get("penalty_score"),
            "pen_draw_label": row.get("pen_draw_label") or item.get("pen_draw_label"),
        }
    )
    base_note = str(item.get("owner_note") or "").strip()
    risk_note = str(row.get("owner_note") or "").strip()
    if risk_note and risk_note not in base_note:
        item["owner_note"] = f"{base_note} | {risk_note}" if base_note else risk_note
    return item


def _wc_owner_note(row: dict[str, Any]) -> str:
    return str(row.get("owner_note") or "WC shadow replay — owner research only")


def _wc_row_to_lab_item(row: dict[str, Any], conn: sqlite3.Connection | None) -> dict[str, Any]:
    fid = int(row.get("fixture_id") or 0)
    baseline_rank = row.get("baseline_rank")
    enhanced_rank = row.get("enhanced_rank")
    delta_rank = row.get("rank_delta")
    return {
        "fixture_id": fid,
        "fixture_label": row.get("match") or _fixture_label(conn, fid),
        "kickoff_time": row.get("kickoff_time"),
        "league": row.get("competition_key"),
        "tournament": row.get("competition_key"),
        "source": "ecse_wc_shadow_replay",
        "home_prob": row.get("home_prob"),
        "segment_labels": row.get("segment_labels") or [],
        "segment_summary": ", ".join(row.get("segment_labels") or []) or "—",
        "strong_segment": "home_ge_60" in (row.get("segment_labels") or []),
        "applied": bool(row.get("applied")),
        "exclusion_reason": row.get("exclusion_reason"),
        "baseline_top1": row.get("prediction_top1"),
        "enhanced_top1": (row.get("enhanced_top10") or [{}])[0].get("scoreline"),
        "baseline_top10": row.get("baseline_top10") or [],
        "enhanced_top10": row.get("enhanced_top10") or [],
        "rank_movements": row.get("rank_movements") or {},
        "rank_movement_summary": _movement_summary(row.get("rank_movements")),
        "evaluation_status": "evaluated",
        "actual_score": row.get("actual_score"),
        "baseline_hit_rank": baseline_rank,
        "enhanced_hit_rank": enhanced_rank,
        "delta_rank": delta_rank,
        "enhanced_better": (delta_rank or 0) > 0,
        "enhanced_worse": (delta_rank or 0) < 0,
        "unchanged": delta_rank == 0,
        "match_outcome_type": row.get("match_outcome_type"),
        "penalty_score": row.get("penalty_score"),
        "pen_draw_label": row.get("pen_draw_label"),
        "knockout_round": row.get("knockout_round"),
        "score_1_1_analysis": row.get("score_1_1_analysis"),
        "public_output_changed": False,
        "owner_note": _wc_owner_note(row),
        "generated_at": row.get("evaluated_at"),
    }


class EcseOwnerShadowLabService:
    def summary(self, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
        rows = read_shadow_shortlists(limit=50_000)
        evals = _load_evaluations()
        exclusions: dict[str, int] = {}
        for r in rows:
            if not r.get("applied"):
                key = str(r.get("exclusion_reason") or "unknown")
                exclusions[key] = exclusions.get(key, 0) + 1

        eval_watch = aggregate_evaluation_watch()
        public_changed = sum(1 for r in rows if r.get("public_output_changed") is True)
        x3_summary = build_x3_summary(conn)
        wc_summary = load_wc_shadow_evaluation_summary()
        wc_rows = load_wc_shadow_evaluation_rows()
        knockout_risk_summary = load_knockout_draw_pen_risk_summary()

        payload = {
            "phase": "ECSE-X2-M8",
            "total_shadow_rows": len(rows),
            "applied_count": sum(1 for r in rows if r.get("applied")),
            "excluded_count": sum(1 for r in rows if not r.get("applied")),
            "missing_ft_home_count": exclusions.get("missing_ft_home", 0),
            "balanced_excluded_count": exclusions.get("balanced_match", 0),
            "pending_evaluations": sum(1 for r in rows if r.get("evaluation_status") == "pending"),
            "completed_evaluations": len(evals),
            "public_output_changed_count": public_changed,
            "strong_home_segment_count": sum(1 for r in rows if r.get("strong_segment")),
            "exclusion_reasons": exclusions,
            "evaluation_metrics": {
                "top1": eval_watch.get("top1"),
                "top3": eval_watch.get("top3"),
                "top5": eval_watch.get("top5"),
                "top10": eval_watch.get("top10"),
            },
            "artifact": SHADOW_ARTIFACT,
            "disclaimer": "Owner research lab only. Not public. Does not change live predictions.",
            "shadow_registry": get_registry(),
            "x3_b": x3_summary,
            "wc_shadow_evaluation": wc_summary,
            "wc_evaluated_fixture_count": len(wc_rows),
            "knockout_draw_pen_risk": knockout_risk_summary,
        }
        return payload

    def list_fixtures(
        self,
        conn: sqlite3.Connection | None = None,
        *,
        filter_key: str = "all",
        league: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows = read_shadow_shortlists(limit=50_000)
        evals = _load_evaluations()
        x3_by_fixture = {int(r["fixture_id"]): r for r in read_owner_shadow_rows(limit=50_000) if r.get("fixture_id")}
        wc_by_fixture = {int(r["fixture_id"]): r for r in load_wc_shadow_evaluation_rows() if r.get("fixture_id")}
        risk_map = _knockout_risk_map()
        enriched = []
        seen: set[int] = set()
        for row in rows:
            fid = int(row.get("fixture_id") or 0)
            seen.add(fid)
            item = _enrich_row(row, evals.get(fid))
            item["fixture_label"] = _fixture_label(conn, fid)
            _merge_x3(item, x3_by_fixture.get(fid))
            _merge_knockout_draw_pen_risk(item, conn, risk_map)
            enriched.append(item)

        for fid, wc_row in wc_by_fixture.items():
            if fid in seen:
                continue
            item = _wc_row_to_lab_item(wc_row, conn)
            _merge_x3(item, x3_by_fixture.get(fid))
            _merge_knockout_draw_pen_risk(item, conn, risk_map)
            enriched.append(item)

        filtered = [r for r in enriched if self._passes_filter(r, filter_key)]
        if league:
            filtered = [
                r
                for r in filtered
                if league.lower() in str(r.get("league") or "").lower()
                or league.lower() in str(r.get("tournament") or "").lower()
            ]
        if date_from:
            filtered = [r for r in filtered if (r.get("kickoff_time") or "") >= date_from]
        if date_to:
            filtered = [r for r in filtered if (r.get("kickoff_time") or "") <= date_to]

        total = len(filtered)
        page = filtered[offset : offset + limit]
        return {"total": total, "limit": limit, "offset": offset, "items": page, "filter": filter_key}

    def get_fixture(self, conn: sqlite3.Connection | None, fixture_id: int) -> dict[str, Any] | None:
        row = None
        for r in read_shadow_shortlists(limit=50_000):
            if int(r.get("fixture_id") or 0) == int(fixture_id):
                row = r
                break
        if row:
            eval_row = _load_evaluations().get(int(fixture_id))
            detail = _enrich_row(row, eval_row)
            detail["fixture_label"] = _fixture_label(conn, fixture_id)
            detail["evaluation"] = eval_row
            _merge_x3(detail, get_owner_shadow_for_fixture(fixture_id))
            _merge_knockout_draw_pen_risk(detail, conn)
            return detail

        for wc in load_wc_shadow_evaluation_rows():
            if int(wc.get("fixture_id") or 0) == int(fixture_id):
                detail = _wc_row_to_lab_item(wc, conn)
                detail["evaluation"] = {
                    "actual_score": wc.get("actual_score"),
                    "baseline_hits": wc.get("baseline_hits"),
                    "enhanced_hits": wc.get("enhanced_hits"),
                    "delta": wc.get("delta"),
                }
                _merge_x3(detail, get_owner_shadow_for_fixture(fixture_id))
                _merge_knockout_draw_pen_risk(detail, conn)
                return detail
        risk_only = evaluate_fixture_knockout_risk(conn, fixture_id) if conn is not None else None
        if risk_only and risk_only.get("knockout_draw_pen_risk"):
            detail = {
                "fixture_id": fixture_id,
                "fixture_label": _fixture_label(conn, fixture_id),
                "source": "ecse_wc_knockout_draw_pen_risk",
                "public_output_changed": False,
            }
            return _merge_knockout_draw_pen_risk(detail, conn)
        return None

    @staticmethod
    def _passes_filter(row: dict[str, Any], filter_key: str) -> bool:
        f = (filter_key or "all").lower()
        if f == "all":
            return True
        if f == "applied":
            return bool(row.get("applied"))
        if f == "evaluated":
            return row.get("evaluation_status") == "evaluated" or row.get("actual_score")
        if f == "pending":
            return row.get("evaluation_status") == "pending" and not row.get("actual_score")
        if f == "strong_home":
            return bool(row.get("strong_segment")) or (float(row.get("home_prob") or 0) >= 0.60)
        if f == "home_favorite":
            return float(row.get("home_prob") or 0) >= 0.55
        if f == "missing_odds":
            return row.get("exclusion_reason") in ("missing_ft_home", "invalid_odds_snapshot")
        if f == "balanced":
            return row.get("exclusion_reason") == "balanced_match"
        if f == "enhanced_better":
            return bool(row.get("enhanced_better"))
        if f == "enhanced_worse":
            return bool(row.get("enhanced_worse"))
        if f == "no_change":
            return bool(row.get("unchanged")) or (
                row.get("applied") and not row.get("enhanced_better") and not row.get("enhanced_worse")
            )
        if f == "x3_available":
            return row.get("x3_status") == "available"
        if f == "x3_unavailable":
            return row.get("x3_status") in ("unavailable", "rejected", None)
        if f == "world_cup":
            return row.get("source") == "ecse_wc_shadow_replay" or (
                "world_cup" in str(row.get("league") or "").lower()
            )
        if f == "pen_draw":
            return bool(row.get("pen_draw_label")) or row.get("match_outcome_type") == "PEN"
        if f in ("knockout_draw_pen", "draw_pen_risk"):
            return bool(row.get("knockout_draw_pen_risk"))
        return True

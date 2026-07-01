"""PHASE ECSE-ODDALERTS-3 — Owner lab service for ECSE OddAlerts shadow predictions."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from typing import Any

from worldcup_predictor.research.oddalerts_ecse_segment_calibration import extract_features_from_row
from worldcup_predictor.research.oddalerts_ecse_segments import (
    SEGMENT_MODEL_V1,
    SEGMENT_MODEL_V2,
    implied_1x2_pick,
    load_v2_calibration_context,
    score_shadow_segment,
    score_shadow_segment_v2,
    score_to_outcome,
    segment_recommendation_filter_match,
)
from worldcup_predictor.research.oddalerts_ecse_shadow import DEFAULT_RUN_ID

PHASE = "ECSE-ODDALERTS-4"

_V2_CONTEXT: dict[str, Any] | None = None


def _get_v2_context() -> dict[str, Any]:
    global _V2_CONTEXT
    if _V2_CONTEXT is not None:
        return _V2_CONTEXT
    _V2_CONTEXT = load_v2_calibration_context()
    return _V2_CONTEXT


def _parse_json(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _top_scorelines(raw: str | None, *, limit: int) -> list[str]:
    items = _parse_json(raw) or []
    if not items:
        return []
    if isinstance(items[0], dict):
        return [str(x.get("scoreline", "")) for x in items[:limit] if x.get("scoreline")]
    return [str(x) for x in items[:limit]]


def _wde_direction(payload: dict[str, Any]) -> str | None:
    for key in ("result_market", "match_result", "1x2"):
        block = payload.get(key)
        if isinstance(block, dict):
            pick = block.get("pick") or block.get("prediction")
            if pick:
                return str(pick).lower()
    preds = payload.get("predictions") or payload.get("market_predictions") or {}
    if isinstance(preds, dict):
        mr = preds.get("match_result") or preds.get("1x2") or {}
        if isinstance(mr, dict):
            pick = mr.get("pick") or mr.get("prediction")
            if pick:
                return str(pick).lower()
    return None


def _batch_results(conn: sqlite3.Connection, fixture_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not fixture_ids:
        return {}
    placeholders = ",".join("?" * len(fixture_ids))
    rows = conn.execute(
        f"""
        SELECT f.fixture_id, f.status, r.home_goals, r.away_goals
        FROM fixtures f
        LEFT JOIN fixture_results r ON r.fixture_id = f.fixture_id
        WHERE f.fixture_id IN ({placeholders})
        """,
        fixture_ids,
    ).fetchall()
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        r = dict(row)
        out[int(r["fixture_id"])] = r
    return out


def _batch_ecse(conn: sqlite3.Connection, fixture_ids: list[int]) -> dict[int, str]:
    if not fixture_ids:
        return {}
    placeholders = ",".join("?" * len(fixture_ids))
    rows = conn.execute(
        f"SELECT fixture_id, top_1_score FROM ecse_prediction_snapshots WHERE fixture_id IN ({placeholders})",
        fixture_ids,
    ).fetchall()
    return {int(r["fixture_id"]): str(r["top_1_score"]) for r in rows}


def _batch_wde(conn: sqlite3.Connection, fixture_ids: list[int]) -> dict[int, str | None]:
    if not fixture_ids:
        return {}
    placeholders = ",".join("?" * len(fixture_ids))
    rows = conn.execute(
        f"SELECT fixture_id, payload_json FROM worldcup_stored_predictions WHERE fixture_id IN ({placeholders})",
        fixture_ids,
    ).fetchall()
    out: dict[int, str | None] = {}
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
            out[int(row["fixture_id"])] = _wde_direction(payload)
        except (KeyError, json.JSONDecodeError, TypeError):
            out[int(row["fixture_id"])] = None
    return out


class EcseOddalertsOwnerLabService:
    def list_shadow_predictions(
        self,
        conn: sqlite3.Connection,
        *,
        shadow_run_id: str = DEFAULT_RUN_ID,
        date_from: str | None = None,
        date_to: str | None = None,
        competition: str | None = None,
        team: str | None = None,
        promotion_action: str | None = None,
        status: str = "all",
        top1_score: str | None = None,
        top1_outcome: str | None = None,
        lambda_home_min: float | None = None,
        lambda_home_max: float | None = None,
        lambda_away_min: float | None = None,
        lambda_away_max: float | None = None,
        top3_contains_actual: bool | None = None,
        top5_contains_actual: bool | None = None,
        bookmaker_agreement_min: float | None = None,
        crosswalk_confidence_min: str | None = None,
        segment_recommendation: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT * FROM ecse_oddalerts_shadow_predictions
            WHERE shadow_run_id = ?
            ORDER BY kickoff_utc DESC, fixture_id ASC
            """,
            (shadow_run_id,),
        ).fetchall()
        raw = [dict(r) for r in rows]
        fixture_ids = [int(r["fixture_id"]) for r in raw]

        results = _batch_results(conn, fixture_ids)
        ecse_map = _batch_ecse(conn, fixture_ids)
        wde_map = _batch_wde(conn, fixture_ids)
        v2_ctx = _get_v2_context()
        calibration = v2_ctx.get("calibration")
        utility_percentiles = v2_ctx.get("utility_percentiles")

        enriched: list[dict[str, Any]] = []
        for row in raw:
            fid = int(row["fixture_id"])
            fx = results.get(fid, {})
            hg, ag = fx.get("home_goals"), fx.get("away_goals")
            fx_status = str(fx.get("status") or "").upper()
            finished = hg is not None and ag is not None and fx_status in ("FT", "AET", "PEN", "FINISHED")
            final_score = f"{int(hg)}-{int(ag)}" if finished else None

            top3 = _top_scorelines(row.get("top_3_scores_json"), limit=3)
            top5 = _top_scorelines(row.get("top_5_scores_json"), limit=5)
            top10 = _parse_json(row.get("top_10_scores_json")) or []

            ecse_top1 = ecse_map.get(fid)
            wde_dir = wde_map.get(fid)
            ecse_dir = score_to_outcome(ecse_top1) if ecse_top1 else None

            segment = score_shadow_segment(row, wde_direction=wde_dir, ecse_direction=ecse_dir)
            feat = extract_features_from_row(row, fx=fx, wde_dir=wde_dir)
            segment_v2 = score_shadow_segment_v2(
                row,
                feat,
                calibration=calibration,
                wde_direction=wde_dir,
                utility_percentiles=utility_percentiles,
            )
            probs = _parse_json(row.get("input_market_probabilities_json")) or {}
            book_pick = segment.get("bookmaker_implied_direction")
            shadow_outcome = segment.get("shadow_outcome")
            book_agrees = (
                1.0 if book_pick and shadow_outcome and book_pick == shadow_outcome else 0.0
            )

            item = {
                "fixture_id": fid,
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "competition": row.get("competition"),
                "kickoff_utc": row.get("kickoff_utc"),
                "final_score": final_score,
                "finished": finished,
                "top_1_score": row.get("top_1_score"),
                "top_3_scores": top3,
                "top_5_scores": top5,
                "top_10_scores": top10,
                "top1_hit": final_score == row.get("top_1_score") if finished else None,
                "top3_hit": final_score in top3 if finished else None,
                "top5_hit": final_score in top5 if finished else None,
                "lambda_home": row.get("lambda_home"),
                "lambda_away": row.get("lambda_away"),
                "shadow_outcome": shadow_outcome,
                "bookmaker_implied_direction": book_pick,
                "bookmaker_agreement": book_agrees,
                "wde_direction": wde_dir,
                "wde_agrees": wde_dir == shadow_outcome if wde_dir and shadow_outcome else None,
                "ecse_production_top1": ecse_top1,
                "ecse_production_direction": ecse_dir,
                "promotion_action": row.get("promotion_action"),
                "source_provider": row.get("source_provider"),
                "source_detail": row.get("source_detail"),
                "odds_snapshot_id": row.get("odds_snapshot_id"),
                "crosswalk_confidence": row.get("crosswalk_confidence"),
                "input_market_probabilities": probs,
                "warning_flags": _parse_json(row.get("warning_flags_json")) or [],
                "normalization_notes": _parse_json(row.get("normalization_notes_json")) or [],
                "source_bookmakers": _parse_json(row.get("source_bookmakers_json")) or [],
                "source_row_hashes": _parse_json(row.get("source_row_hashes_json")) or [],
                "source_files": _parse_json(row.get("source_files_json")) or [],
                "segment_score": segment["segment_score"],
                "segment_badge": segment["segment_badge"],
                "segment_reasons": segment["reasons"],
                "segment_cautions": segment["cautions"],
                "promotion_eligibility": segment["promotion_eligibility"],
                "segment_model_version": SEGMENT_MODEL_V2,
                "segment_model_version_v1": SEGMENT_MODEL_V1,
                "segment_score_v2": segment_v2.get("segment_score_v2"),
                "segment_badge_v2": segment_v2.get("segment_badge_v2"),
                "segment_reasons_v2": segment_v2.get("reasons_v2"),
                "segment_cautions_v2": segment_v2.get("cautions_v2"),
                "promotion_eligibility_v2": segment_v2.get("promotion_eligibility_v2"),
                "expected_top3_rate": segment_v2.get("expected_top3_rate"),
                "expected_top5_rate": segment_v2.get("expected_top5_rate"),
                "top5_value_signal": segment_v2.get("top5_value_signal"),
            }
            enriched.append(item)

        filtered = self._apply_filters(
            enriched,
            date_from=date_from,
            date_to=date_to,
            competition=competition,
            team=team,
            promotion_action=promotion_action,
            status=status,
            top1_score=top1_score,
            top1_outcome=top1_outcome,
            lambda_home_min=lambda_home_min,
            lambda_home_max=lambda_home_max,
            lambda_away_min=lambda_away_min,
            lambda_away_max=lambda_away_max,
            top3_contains_actual=top3_contains_actual,
            top5_contains_actual=top5_contains_actual,
            bookmaker_agreement_min=bookmaker_agreement_min,
            crosswalk_confidence_min=crosswalk_confidence_min,
            segment_recommendation=segment_recommendation,
        )

        total = len(filtered)
        page = filtered[offset : offset + limit]
        summary = self._build_summary(enriched, filtered)
        segment_stats = self._segment_stats(filtered)
        evaluation_stats = self._evaluation_stats(filtered)

        return {
            "phase": PHASE,
            "shadow_run_id": shadow_run_id,
            "segment_model_version": SEGMENT_MODEL_V2,
            "segment_model_version_v1": SEGMENT_MODEL_V1,
            "total": total,
            "offset": offset,
            "limit": limit,
            "summary": summary,
            "evaluation_stats": evaluation_stats,
            "segment_stats": segment_stats,
            "daily_monitor": self._build_daily_monitor_summary(conn),
            "items": page,
        }

    def _apply_filters(
        self,
        items: list[dict[str, Any]],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in items:
            if kwargs.get("date_from") and (item.get("kickoff_utc") or "")[:10] < kwargs["date_from"]:
                continue
            if kwargs.get("date_to") and (item.get("kickoff_utc") or "")[:10] > kwargs["date_to"]:
                continue
            if kwargs.get("competition") and item.get("competition") != kwargs["competition"]:
                continue
            if kwargs.get("team"):
                t = kwargs["team"].lower()
                if t not in (item.get("home_team") or "").lower() and t not in (item.get("away_team") or "").lower():
                    continue
            if kwargs.get("promotion_action") and item.get("promotion_action") != kwargs["promotion_action"]:
                continue
            st = kwargs.get("status", "all")
            if st == "finished" and not item.get("finished"):
                continue
            if st == "upcoming" and item.get("finished"):
                continue
            if kwargs.get("top1_score") and item.get("top_1_score") != kwargs["top1_score"]:
                continue
            if kwargs.get("top1_outcome") and item.get("shadow_outcome") != kwargs["top1_outcome"]:
                continue
            lh = float(item.get("lambda_home") or 0)
            la = float(item.get("lambda_away") or 0)
            if kwargs.get("lambda_home_min") is not None and lh < kwargs["lambda_home_min"]:
                continue
            if kwargs.get("lambda_home_max") is not None and lh > kwargs["lambda_home_max"]:
                continue
            if kwargs.get("lambda_away_min") is not None and la < kwargs["lambda_away_min"]:
                continue
            if kwargs.get("lambda_away_max") is not None and la > kwargs["lambda_away_max"]:
                continue
            if kwargs.get("top3_contains_actual") is True and item.get("top3_hit") is not True:
                continue
            if kwargs.get("top3_contains_actual") is False and item.get("top3_hit") is not False:
                continue
            if kwargs.get("top5_contains_actual") is True and item.get("top5_hit") is not True:
                continue
            if kwargs.get("top5_contains_actual") is False and item.get("top5_hit") is not False:
                continue
            if kwargs.get("bookmaker_agreement_min") is not None:
                if (item.get("bookmaker_agreement") or 0) < kwargs["bookmaker_agreement_min"]:
                    continue
            if kwargs.get("crosswalk_confidence_min"):
                cw = str(item.get("crosswalk_confidence") or "").upper()
                if kwargs["crosswalk_confidence_min"].upper() not in cw:
                    continue
            seg = {
                "segment_badge": item.get("segment_badge"),
                "promotion_eligibility": item.get("promotion_eligibility"),
            }
            if not segment_recommendation_filter_match(item, seg, kwargs.get("segment_recommendation")):
                continue
            out.append(item)
        return out

    def _build_daily_monitor_summary(self, conn: sqlite3.Connection) -> dict[str, Any]:
        from worldcup_predictor.owner.daily_oddalerts_ecse_pipeline import build_owner_daily_summary

        return build_owner_daily_summary(conn)

    def _build_summary(self, all_items: list[dict[str, Any]], filtered: list[dict[str, Any]]) -> dict[str, Any]:
        badge_counts = Counter(i.get("segment_badge") for i in all_items)
        badge_v2_counts = Counter(i.get("segment_badge_v2") for i in all_items)
        promo = defaultdict(lambda: {"n": 0, "top1": 0, "top3": 0})
        for i in all_items:
            if not i.get("finished"):
                continue
            p = i.get("promotion_action") or "unknown"
            promo[p]["n"] += 1
            promo[p]["top1"] += int(i.get("top1_hit") or False)
            promo[p]["top3"] += int(i.get("top3_hit") or False)

        promo_rates = {}
        for k, v in promo.items():
            if v["n"]:
                promo_rates[k] = {
                    "count": v["n"],
                    "top1_hit_rate": round(v["top1"] / v["n"], 4),
                    "top3_hit_rate": round(v["top3"] / v["n"], 4),
                }

        return {
            "total_shadow_records": len(all_items),
            "filtered_count": len(filtered),
            "finished_count": sum(1 for i in all_items if i.get("finished")),
            "upcoming_count": sum(1 for i in all_items if not i.get("finished")),
            "strong_signal_count": badge_counts.get("STRONG_SHADOW_SIGNAL", 0),
            "medium_signal_count": badge_counts.get("MEDIUM_SHADOW_SIGNAL", 0),
            "weak_signal_count": badge_counts.get("WEAK_SHADOW_SIGNAL", 0),
            "strong_signal_count_v2": badge_v2_counts.get("STRONG_SHADOW_SIGNAL", 0),
            "medium_signal_count_v2": badge_v2_counts.get("MEDIUM_SHADOW_SIGNAL", 0),
            "weak_signal_count_v2": badge_v2_counts.get("WEAK_SHADOW_SIGNAL", 0),
            "watch_only_count": badge_counts.get("WATCH_ONLY", 0),
            "do_not_use_count": badge_counts.get("DO_NOT_USE", 0),
            "inserted_vs_enriched": promo_rates,
        }

    def _evaluation_stats(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        finished = [i for i in items if i.get("finished")]
        n = len(finished)
        if not n:
            return {"evaluated_count": 0, "waiting_count": len(items), "status": "WAITING_FOR_RESULTS"}
        return {
            "status": "EVALUATED",
            "evaluated_count": n,
            "waiting_count": len(items) - n,
            "top1_hit_rate": round(sum(1 for i in finished if i.get("top1_hit")) / n, 4),
            "top3_hit_rate": round(sum(1 for i in finished if i.get("top3_hit")) / n, 4),
            "top5_hit_rate": round(sum(1 for i in finished if i.get("top5_hit")) / n, 4),
        }

    def _segment_stats(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        by_badge: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "top1_hits": 0, "finished": 0})
        for i in items:
            b = i.get("segment_badge") or "UNKNOWN"
            by_badge[b]["count"] += 1
            if i.get("finished"):
                by_badge[b]["finished"] += 1
                by_badge[b]["top1_hits"] += int(i.get("top1_hit") or False)
        out = {}
        for badge, stats in by_badge.items():
            fin = stats["finished"]
            out[badge] = {
                "count": stats["count"],
                "finished_count": fin,
                "top1_hit_rate": round(stats["top1_hits"] / fin, 4) if fin else None,
            }
        return out

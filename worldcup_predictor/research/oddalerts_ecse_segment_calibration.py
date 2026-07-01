"""PHASE ECSE-ODDALERTS-4 — feature extraction for segment calibration."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.oddalerts_ecse_segments import implied_1x2_pick, score_to_outcome
from worldcup_predictor.research.oddalerts_ecse_shadow import DEFAULT_RUN_ID, PROCESS_DATE

PHASE = "ECSE-ODDALERTS-4"
MIN_SAMPLE_CAUTION = 20


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _date_tag(process_date: str | None = None) -> str:
    return (process_date or PROCESS_DATE).replace("-", "")


def artifact_paths(process_date: str | None = None) -> dict[str, Path]:
    tag = _date_tag(process_date)
    return {
        "feature_matrix": Path(f"artifacts/ecse_oddalerts_segment_feature_matrix_{tag}.json"),
        "calibration": Path(f"artifacts/ecse_oddalerts_segment_calibration_{tag}.json"),
        "rescored_v2": Path(f"artifacts/ecse_oddalerts_owner_lab_rescored_v2_{tag}.json"),
        "v1_vs_v2": Path(f"artifacts/ecse_oddalerts_segment_v1_vs_v2_comparison_{tag}.json"),
        "validation": Path(f"artifacts/ecse_oddalerts_segment_calibration_validation_{tag}.json"),
    }


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


def _market_spread(probs: dict[str, Any]) -> float | None:
    h, d, a = probs.get("match_result_home"), probs.get("match_result_draw"), probs.get("match_result_away")
    if h is None or d is None or a is None:
        return None
    vals = sorted([float(h), float(d), float(a)], reverse=True)
    return round(vals[0] - vals[1], 4)


def _top1_concentration(top10: list[dict[str, Any]]) -> float | None:
    if not top10:
        return None
    try:
        return round(float(top10[0].get("probability") or 0), 6)
    except (TypeError, ValueError):
        return None


def _lambda_bucket(total: float) -> str:
    if total < 2.0:
        return "lambda_total_low"
    if total < 2.8:
        return "lambda_total_mid"
    return "lambda_total_high"


def _lambda_diff_bucket(diff: float) -> str:
    ad = abs(diff)
    if ad < 0.6:
        return "lambda_diff_tight"
    if ad < 1.4:
        return "lambda_diff_moderate"
    return "lambda_diff_wide"


def _draw_prob_bucket(draw: float | None) -> str:
    if draw is None:
        return "draw_unknown"
    if draw < 20:
        return "draw_low"
    if draw < 28:
        return "draw_mid"
    return "draw_high"


def _spread_bucket(spread: float | None) -> str:
    if spread is None:
        return "spread_unknown"
    if spread < 15:
        return "spread_tight"
    if spread < 35:
        return "spread_mid"
    return "spread_wide"


def _crosswalk_bucket(cw: str | None) -> str:
    u = str(cw or "").upper()
    if "HIGH" in u:
        return "crosswalk_high"
    if "LOW" in u:
        return "crosswalk_low"
    return "crosswalk_other"


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return round((centre - margin) / denom, 4), round((centre + margin) / denom, 4)


def extract_features_from_row(
    row: dict[str, Any],
    *,
    fx: dict[str, Any] | None = None,
    wde_dir: str | None = None,
) -> dict[str, Any]:
    fx = fx or {}
    hg, ag = fx.get("home_goals"), fx.get("away_goals")
    status = str(fx.get("status") or "").upper()
    finished = hg is not None and ag is not None and status in ("FT", "AET", "PEN", "FINISHED")
    final_score = f"{int(hg)}-{int(ag)}" if finished else None

    top3 = _top_scorelines(row.get("top_3_scores_json"), limit=3)
    top5 = _top_scorelines(row.get("top_5_scores_json"), limit=5)
    top10_raw = _parse_json(row.get("top_10_scores_json")) or []
    top10 = top10_raw if isinstance(top10_raw, list) else []

    lh = float(row.get("lambda_home") or 0)
    la = float(row.get("lambda_away") or 0)
    lt = round(lh + la, 4)
    ld = round(lh - la, 4)
    top1 = row.get("top_1_score")
    outcome = score_to_outcome(top1)
    probs = _parse_json(row.get("input_market_probabilities_json")) or {}
    book = implied_1x2_pick(probs)
    book_agrees = book == outcome if book and outcome else None
    wde_agrees = wde_dir == outcome if wde_dir and outcome else None
    draw_p = float(probs["match_result_draw"]) if probs.get("match_result_draw") is not None else None
    spread = _market_spread(probs)

    return {
        "fixture_id": int(row["fixture_id"]),
        "competition": row.get("competition"),
        "promotion_action": row.get("promotion_action"),
        "top_1_score": top1,
        "top_1_outcome": outcome,
        "top_3_scores": top3,
        "top_5_scores": top5,
        "top_10_scores": top10,
        "lambda_home": lh,
        "lambda_away": la,
        "lambda_total": lt,
        "lambda_diff": ld,
        "lambda_total_bucket": _lambda_bucket(lt),
        "lambda_diff_bucket": _lambda_diff_bucket(ld),
        "bookmaker_implied_direction": book,
        "bookmaker_agreement": book_agrees,
        "wde_direction": wde_dir,
        "wde_agreement": wde_agrees,
        "crosswalk_confidence": row.get("crosswalk_confidence"),
        "crosswalk_bucket": _crosswalk_bucket(row.get("crosswalk_confidence")),
        "market_probability_spread": spread,
        "spread_bucket": _spread_bucket(spread),
        "draw_probability": draw_p,
        "draw_probability_bucket": _draw_prob_bucket(draw_p),
        "btts_yes_probability": probs.get("btts_yes"),
        "ou_over_2_5_probability": probs.get("goals_over_2_5"),
        "top1_concentration": _top1_concentration(top10),
        "top1_is_1_1": top1 == "1-1",
        "top1_is_home_win": outcome == "home",
        "top1_is_draw": outcome == "draw",
        "top1_is_away_win": outcome == "away",
        "final_score": final_score,
        "finished": finished,
        "top1_hit": final_score == top1 if finished else None,
        "top3_hit": final_score in top3 if finished else None,
        "top5_hit": final_score in top5 if finished else None,
        "top10_hit": final_score in [x.get("scoreline") for x in top10 if isinstance(x, dict)] if finished else None,
    }


def _batch_results(conn: sqlite3.Connection, fixture_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not fixture_ids:
        return {}
    ph = ",".join("?" * len(fixture_ids))
    rows = conn.execute(
        f"""
        SELECT f.fixture_id, f.status, r.home_goals, r.away_goals
        FROM fixtures f
        LEFT JOIN fixture_results r ON r.fixture_id = f.fixture_id
        WHERE f.fixture_id IN ({ph})
        """,
        fixture_ids,
    ).fetchall()
    return {int(dict(r)["fixture_id"]): dict(r) for r in rows}


def _batch_wde(conn: sqlite3.Connection, fixture_ids: list[int]) -> dict[int, str | None]:
    if not fixture_ids:
        return {}
    ph = ",".join("?" * len(fixture_ids))
    rows = conn.execute(
        f"SELECT fixture_id, payload_json FROM worldcup_stored_predictions WHERE fixture_id IN ({ph})",
        fixture_ids,
    ).fetchall()
    out: dict[int, str | None] = {}
    for row in rows:
        try:
            out[int(row["fixture_id"])] = _wde_direction(json.loads(row["payload_json"]))
        except (KeyError, json.JSONDecodeError, TypeError):
            out[int(row["fixture_id"])] = None
    return out


def build_feature_matrix(
    conn: sqlite3.Connection,
    *,
    shadow_run_id: str = DEFAULT_RUN_ID,
) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT * FROM ecse_oddalerts_shadow_predictions WHERE shadow_run_id = ? ORDER BY fixture_id",
        (shadow_run_id,),
    ).fetchall()
    raw = [dict(r) for r in rows]
    fixture_ids = [int(r["fixture_id"]) for r in raw]
    results = _batch_results(conn, fixture_ids)
    wde_map = _batch_wde(conn, fixture_ids)

    features = [
        extract_features_from_row(
            row,
            fx=results.get(int(row["fixture_id"])),
            wde_dir=wde_map.get(int(row["fixture_id"])),
        )
        for row in raw
    ]
    evaluated = [f for f in features if f.get("finished")]
    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "shadow_run_id": shadow_run_id,
        "record_count": len(features),
        "evaluated_count": len(evaluated),
        "features": features,
    }


def bucket_keys_for_feature(f: dict[str, Any]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    if f.get("competition"):
        keys.append(("competition", str(f["competition"])))
    if f.get("promotion_action"):
        keys.append(("promotion_action", str(f["promotion_action"])))
    if f.get("top_1_score"):
        keys.append(("top1_score", str(f["top_1_score"])))
    if f.get("top_1_outcome"):
        keys.append(("top1_outcome", str(f["top_1_outcome"])))
    if f.get("bookmaker_agreement") is not None:
        keys.append(("bookmaker_agreement", str(bool(f["bookmaker_agreement"]))))
    if f.get("wde_agreement") is not None:
        keys.append(("wde_agreement", str(bool(f["wde_agreement"]))))
    elif f.get("wde_direction") is None:
        keys.append(("wde_agreement", "unavailable"))
    if f.get("lambda_total_bucket"):
        keys.append(("lambda_total_bucket", str(f["lambda_total_bucket"])))
    if f.get("lambda_diff_bucket"):
        keys.append(("lambda_diff_bucket", str(f["lambda_diff_bucket"])))
    if f.get("draw_probability_bucket"):
        keys.append(("draw_probability_bucket", str(f["draw_probability_bucket"])))
    keys.append(("top1_is_1_1", str(bool(f.get("top1_is_1_1")))))
    if f.get("spread_bucket"):
        keys.append(("spread_bucket", str(f["spread_bucket"])))
    if f.get("crosswalk_bucket"):
        keys.append(("crosswalk_bucket", str(f["crosswalk_bucket"])))
    return keys


def _rate_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"sample_size": 0}
    t1 = sum(1 for r in rows if r.get("top1_hit"))
    t3 = sum(1 for r in rows if r.get("top3_hit"))
    t5 = sum(1 for r in rows if r.get("top5_hit"))
    t10 = sum(1 for r in rows if r.get("top10_hit"))
    lo1, hi1 = wilson_ci(t1, n)
    lo3, hi3 = wilson_ci(t3, n)
    return {
        "sample_size": n,
        "top1_hit_rate": round(t1 / n, 4),
        "top3_hit_rate": round(t3 / n, 4),
        "top5_hit_rate": round(t5 / n, 4),
        "top10_hit_rate": round(t10 / n, 4),
        "top1_wilson_ci": [lo1, hi1],
        "top3_wilson_ci": [lo3, hi3],
        "low_sample_warning": n < MIN_SAMPLE_CAUTION,
    }


def build_calibration_analysis(feature_matrix: dict[str, Any]) -> dict[str, Any]:
    features = feature_matrix.get("features") or []
    evaluated = [f for f in features if f.get("finished")]
    baseline = _rate_stats(evaluated)

    buckets: dict[str, dict[str, Any]] = {}
    dimensions = (
        "competition",
        "promotion_action",
        "top1_score",
        "top1_outcome",
        "bookmaker_agreement",
        "wde_agreement",
        "lambda_total_bucket",
        "lambda_diff_bucket",
        "draw_probability_bucket",
        "top1_is_1_1",
        "spread_bucket",
        "crosswalk_bucket",
    )

    for dim in dimensions:
        groups: dict[str, list[dict[str, Any]]] = {}
        for f in evaluated:
            val = f.get(dim)
            if dim == "bookmaker_agreement" and val is None:
                continue
            if dim == "wde_agreement":
                if f.get("wde_direction") is None:
                    key = "unavailable"
                elif val is None:
                    continue
                else:
                    key = str(bool(val))
            else:
                key = str(val) if val is not None else "unknown"
            groups.setdefault(key, []).append(f)
        for key, rows in groups.items():
            stats = _rate_stats(rows)
            bucket_id = f"{dim}:{key}"
            buckets[bucket_id] = {
                "dimension": dim,
                "value": key,
                **stats,
                "caution_only": stats.get("sample_size", 0) < MIN_SAMPLE_CAUTION,
            }

    # Rank buckets by top3 lift vs baseline
    base_t3 = baseline.get("top3_hit_rate") or 0.2919
    ranked = []
    for bid, b in buckets.items():
        if b.get("sample_size", 0) >= MIN_SAMPLE_CAUTION:
            ranked.append(
                {
                    "bucket": bid,
                    "top3_lift": round((b.get("top3_hit_rate") or 0) - base_t3, 4),
                    "top5_lift": round((b.get("top5_hit_rate") or 0) - (baseline.get("top5_hit_rate") or 0), 4),
                    **b,
                }
            )
    ranked.sort(key=lambda x: -(x.get("top3_hit_rate") or 0))

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "evaluated_count": len(evaluated),
        "baseline": baseline,
        "buckets": buckets,
        "best_predictive_segments": ranked[:15],
        "weak_noisy_segments": sorted(ranked, key=lambda x: x.get("top3_hit_rate") or 0)[:10],
        "minimum_sample_caution": MIN_SAMPLE_CAUTION,
    }

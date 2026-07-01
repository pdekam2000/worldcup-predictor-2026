"""PHASE ECSE-ODDALERTS-5 — limited shadow monitor for new OddAlerts fixtures."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.data_import.oddalerts_csv_promotion_dryrun import SOURCE_DETAIL, SOURCE_PROVIDER
from worldcup_predictor.research.oddalerts_ecse_dryrun import (
    check_market_consistency,
    generate_ecse_dryrun_prediction,
    load_oddalerts_snapshot,
    _markets_complete,
)
from worldcup_predictor.research.oddalerts_ecse_monitor_ddl import ECSE_ODDALERTS_MONITOR_DDL, PHASE
from worldcup_predictor.research.oddalerts_ecse_segment_calibration import extract_features_from_row
from worldcup_predictor.research.oddalerts_ecse_segments import (
    SEGMENT_MODEL_V2,
    load_v2_calibration_context,
    score_shadow_segment_v2,
)
from worldcup_predictor.research.oddalerts_ecse_shadow import DEFAULT_RUN_ID

HIGH_CROSSWALK_MARKERS = ("HIGH", "MATCHED_HIGH_CONFIDENCE")
DISAGREEMENT_SPREAD_THRESHOLD = 40.0
ELIGIBLE_V2 = frozenset({"eligible_limited_write_later", "eligible_shadow_watch"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")


def date_range_tag(date_from: str, date_to: str) -> str:
    return f"{date_from.replace('-', '')}_{date_to.replace('-', '')}"


def monitor_run_id(date_from: str, date_to: str) -> str:
    return f"ecse_oa_monitor_{date_range_tag(date_from, date_to)}"


def artifact_paths(date_from: str, date_to: str) -> dict[str, Path]:
    tag = date_range_tag(date_from, date_to)
    return {
        "candidates": Path(f"artifacts/ecse_oddalerts_monitor_candidates_{tag}.json"),
        "run_out": Path(f"artifacts/ecse_oddalerts_limited_shadow_monitor_run_{tag}.json"),
        "evaluation": Path(f"artifacts/ecse_oddalerts_limited_shadow_monitor_evaluation_{tag}.json"),
        "validation": Path(f"artifacts/ecse_oddalerts_limited_shadow_monitor_validation_{tag}.json"),
        "report_md": Path(f"reports/owner/ecse_oddalerts_limited_shadow_monitor_{tag}.md"),
    }


def ensure_monitor_table(conn: sqlite3.Connection) -> None:
    for ddl in ECSE_ODDALERTS_MONITOR_DDL:
        conn.execute(ddl)
    conn.commit()


def _historical_fixture_ids(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute(
        "SELECT fixture_id FROM ecse_oddalerts_shadow_predictions WHERE shadow_run_id = ?",
        (DEFAULT_RUN_ID,),
    ).fetchall()
    return {int(r[0] if not isinstance(r, sqlite3.Row) else r["fixture_id"]) for r in rows}


def _monitored_pairs(conn: sqlite3.Connection, *, segment_model_version: str = SEGMENT_MODEL_V2) -> set[tuple[int, int]]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ecse_oddalerts_shadow_monitor'"
    ).fetchone()
    if not exists:
        return set()
    rows = conn.execute(
        """
        SELECT fixture_id, odds_snapshot_id FROM ecse_oddalerts_shadow_monitor
        WHERE segment_model_version = ?
        """,
        (segment_model_version,),
    ).fetchall()
    return {
        (int(r["fixture_id"]), int(r["odds_snapshot_id"]))
        for r in rows
    }


def _crosswalk_ok(meta: dict[str, Any]) -> bool:
    cw = str(meta.get("crosswalk_confidence") or "").upper()
    return any(m in cw for m in HIGH_CROSSWALK_MARKERS)


def _high_disagreement_block(payload: dict[str, Any], probs: dict[str, Any]) -> bool:
    meta = payload.get("metadata") or {}
    warnings = meta.get("normalization_warnings") or []
    if any("disagreement" in str(w).lower() for w in warnings):
        return True
    h, d, a = probs.get("match_result_home"), probs.get("match_result_draw"), probs.get("match_result_away")
    if h is not None and d is not None and a is not None:
        vals = sorted([float(h), float(d), float(a)], reverse=True)
        spread = vals[0] - vals[1]
        if spread > DISAGREEMENT_SPREAD_THRESHOLD:
            return True
    return bool(meta.get("disagreement_flag"))


def _valid_probabilities(probs: dict[str, Any]) -> bool:
    consistency = check_market_consistency({k: float(v) for k, v in probs.items() if v is not None})
    return not consistency.get("warnings")


def discover_monitor_candidates(
    conn: sqlite3.Connection,
    *,
    date_from: str,
    date_to: str,
    segment_model_version: str = SEGMENT_MODEL_V2,
    include_recent_finished_days: int = 3,
) -> dict[str, Any]:
    """Discover upcoming/recent fixtures with OddAlerts policy snapshots (targeted per-fixture reads)."""
    historical = _historical_fixture_ids(conn)
    monitored = _monitored_pairs(conn, segment_model_version=segment_model_version)

    # Kickoff window: date_from 00:00 through date_to+1 day; include recently finished for evaluation
    kickoff_end = date_to
    rows = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, competition_key, status
        FROM fixtures
        WHERE substr(kickoff_utc, 1, 10) >= ? AND substr(kickoff_utc, 1, 10) <= ?
        ORDER BY kickoff_utc ASC
        """,
        (date_from, kickoff_end),
    ).fetchall()

    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for fx in rows:
        fid = int(fx["fixture_id"])
        if fid in historical:
            skipped.append({"fixture_id": fid, "reason": "historical_shadow_batch"})
            continue

        snap = load_oddalerts_snapshot(conn, fid)
        if not snap:
            skipped.append({"fixture_id": fid, "reason": "no_oddalerts_snapshot"})
            continue

        payload = snap["payload"]
        if payload.get("source_provider") != SOURCE_PROVIDER or payload.get("source_detail") != SOURCE_DETAIL:
            skipped.append({"fixture_id": fid, "reason": "wrong_source"})
            continue

        complete, missing = _markets_complete(payload)
        if not complete:
            skipped.append({"fixture_id": fid, "reason": "incomplete_markets", "missing": missing})
            continue

        meta = payload.get("metadata") or {}
        probs = payload.get("normalized_probabilities") or {}
        if not _crosswalk_ok(meta):
            skipped.append({"fixture_id": fid, "reason": "low_crosswalk_confidence"})
            continue
        if _high_disagreement_block(payload, probs):
            skipped.append({"fixture_id": fid, "reason": "high_disagreement_block"})
            continue
        if not _valid_probabilities(probs):
            skipped.append({"fixture_id": fid, "reason": "invalid_probabilities"})
            continue

        oid = int(snap["odds_snapshot_id"])
        if (fid, oid) in monitored:
            skipped.append({"fixture_id": fid, "reason": "already_monitored", "odds_snapshot_id": oid})
            continue

        status = str(fx["status"] or "NS").upper()
        candidates.append(
            {
                "fixture_id": fid,
                "home_team": fx["home_team"],
                "away_team": fx["away_team"],
                "competition": fx["competition_key"],
                "kickoff_utc": fx["kickoff_utc"],
                "status": status,
                "odds_snapshot_id": oid,
                "snapshot_at": snap["snapshot_at"],
                "source_provider": SOURCE_PROVIDER,
                "source_detail": SOURCE_DETAIL,
                "crosswalk_confidence": meta.get("crosswalk_confidence"),
            }
        )

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "date_from": date_from,
        "date_to": date_to,
        "monitor_run_id": monitor_run_id(date_from, date_to),
        "historical_excluded_count": len(historical),
        "candidate_count": len(candidates),
        "skipped_count": len(skipped),
        "candidates": candidates,
        "skipped": skipped[:50],
    }


def _compute_record_hash(row: dict[str, Any]) -> str:
    payload = {
        "fixture_id": row["fixture_id"],
        "odds_snapshot_id": row["odds_snapshot_id"],
        "segment_model_version": row["segment_model_version"],
        "top_1_score": row["top_1_score"],
        "segment_score_v2": row["segment_score_v2"],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def generate_monitor_prediction(
    conn: sqlite3.Connection,
    candidate: dict[str, Any],
    *,
    calibration: dict[str, Any] | None = None,
    utility_percentiles: tuple[float, float] | None = None,
    wde_direction: str | None = None,
) -> dict[str, Any]:
    entry = {
        "fixture_id": candidate["fixture_id"],
        "home_team": candidate.get("home_team"),
        "away_team": candidate.get("away_team"),
        "competition": candidate.get("competition"),
        "kickoff_utc": candidate.get("kickoff_utc"),
        "promotion_action": "monitor_new",
    }
    pred = generate_ecse_dryrun_prediction(conn, entry)
    if pred.get("status") != "generated":
        return {"status": "failed", "fixture_id": candidate["fixture_id"], "reason": pred.get("reason")}

    snap = load_oddalerts_snapshot(conn, int(candidate["fixture_id"]))
    shadow_row = {
        "fixture_id": candidate["fixture_id"],
        "top_1_score": pred["top_1_score"],
        "lambda_home": pred["lambda_home"],
        "lambda_away": pred["lambda_away"],
        "promotion_action": "monitor_new",
        "competition": candidate.get("competition"),
        "input_market_probabilities_json": json.dumps(pred.get("input_market_probabilities") or {}),
        "top_3_scores_json": json.dumps(pred.get("top_3_scores") or []),
        "top_5_scores_json": json.dumps(pred.get("top_5_scores") or []),
        "top_10_scores_json": json.dumps(pred.get("top_10_exact_scores") or []),
        "crosswalk_confidence": (snap or {}).get("payload", {}).get("metadata", {}).get("crosswalk_confidence"),
    }
    fx_row = conn.execute(
        "SELECT status FROM fixtures WHERE fixture_id = ?", (int(candidate["fixture_id"]),)
    ).fetchone()
    feat = extract_features_from_row(shadow_row, fx=fx_row or {}, wde_dir=wde_direction)
    v2 = score_shadow_segment_v2(
        shadow_row,
        feat,
        calibration=calibration,
        wde_direction=wde_direction,
        utility_percentiles=utility_percentiles,
    )

    meta = (snap or {}).get("payload", {}).get("metadata") or {}
    source_trace = {
        "source_bookmakers": meta.get("source_bookmakers") or [],
        "source_row_hashes": meta.get("source_row_hashes") or [],
        "source_files": meta.get("source_files") or [],
        "crosswalk_confidence": meta.get("crosswalk_confidence"),
        "odds_snapshot_id": candidate.get("odds_snapshot_id"),
    }

    return {
        "status": "generated",
        "fixture_id": candidate["fixture_id"],
        "prediction": pred,
        "segment_v2": v2,
        "source_trace": source_trace,
    }


def write_monitor_records(
    conn: sqlite3.Connection,
    records: list[dict[str, Any]],
    *,
    monitor_run_id_val: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    ensure_monitor_table(conn)
    written = 0
    skipped = 0
    would_write = 0

    for rec in records:
        if rec.get("status") != "generated":
            continue
        pred = rec["prediction"]
        v2 = rec["segment_v2"]
        cand = rec.get("candidate") or {}
        row = {
            "fixture_id": int(cand["fixture_id"]),
            "odds_snapshot_id": int(cand["odds_snapshot_id"]),
            "home_team": cand.get("home_team"),
            "away_team": cand.get("away_team"),
            "competition": cand.get("competition"),
            "kickoff_utc": cand.get("kickoff_utc"),
            "source_provider": SOURCE_PROVIDER,
            "source_detail": SOURCE_DETAIL,
            "lambda_home": float(pred["lambda_home"]),
            "lambda_away": float(pred["lambda_away"]),
            "top_1_score": pred["top_1_score"],
            "top_3_scores_json": json.dumps(pred.get("top_3_scores") or []),
            "top_5_scores_json": json.dumps(pred.get("top_5_scores") or []),
            "top_10_scores_json": json.dumps(pred.get("top_10_exact_scores") or []),
            "segment_model_version": SEGMENT_MODEL_V2,
            "segment_score_v2": float(v2["segment_score_v2"]),
            "segment_badge_v2": v2["segment_badge_v2"],
            "expected_top3_rate": v2.get("expected_top3_rate"),
            "expected_top5_rate": v2.get("expected_top5_rate"),
            "top5_value_signal": 1 if v2.get("top5_value_signal") else 0,
            "promotion_eligibility_v2": v2["promotion_eligibility_v2"],
            "reasons_json": json.dumps(v2.get("reasons_v2") or []),
            "cautions_json": json.dumps(v2.get("cautions_v2") or []),
            "input_market_probabilities_json": json.dumps(pred.get("input_market_probabilities") or {}),
            "source_trace_json": json.dumps(rec.get("source_trace") or {}),
            "monitor_run_id": monitor_run_id_val,
            "created_at": _iso_now(),
        }
        row["record_hash"] = _compute_record_hash(row)

        if dry_run:
            would_write += 1
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO ecse_oddalerts_shadow_monitor (
                fixture_id, odds_snapshot_id, home_team, away_team, competition, kickoff_utc,
                source_provider, source_detail, lambda_home, lambda_away, top_1_score,
                top_3_scores_json, top_5_scores_json, top_10_scores_json,
                segment_model_version, segment_score_v2, segment_badge_v2,
                expected_top3_rate, expected_top5_rate, top5_value_signal, promotion_eligibility_v2,
                reasons_json, cautions_json, input_market_probabilities_json, source_trace_json,
                monitor_run_id, record_hash, created_at
            ) VALUES (
                :fixture_id, :odds_snapshot_id, :home_team, :away_team, :competition, :kickoff_utc,
                :source_provider, :source_detail, :lambda_home, :lambda_away, :top_1_score,
                :top_3_scores_json, :top_5_scores_json, :top_10_scores_json,
                :segment_model_version, :segment_score_v2, :segment_badge_v2,
                :expected_top3_rate, :expected_top5_rate, :top5_value_signal, :promotion_eligibility_v2,
                :reasons_json, :cautions_json, :input_market_probabilities_json, :source_trace_json,
                :monitor_run_id, :record_hash, :created_at
            )
            """,
            row,
        )
        if conn.total_changes:
            written += 1
        else:
            skipped += 1

    if not dry_run:
        conn.commit()

    total = conn.execute(
        "SELECT COUNT(*) c FROM ecse_oddalerts_shadow_monitor WHERE monitor_run_id = ?",
        (monitor_run_id_val,),
    ).fetchone()
    count = int(total[0] if not isinstance(total, sqlite3.Row) else total["c"])

    return {
        "written_count": written,
        "skipped_count": skipped,
        "would_write_count": would_write,
        "monitor_run_total": count,
    }


def evaluate_monitor_records(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    monitor_run_id_val: str | None = None,
) -> dict[str, Any]:
    ensure_monitor_table(conn)
    if monitor_run_id_val:
        rows = conn.execute(
            "SELECT * FROM ecse_oddalerts_shadow_monitor WHERE monitor_run_id = ? ORDER BY kickoff_utc",
            (monitor_run_id_val,),
        ).fetchall()
    elif date_from and date_to:
        rows = conn.execute(
            """
            SELECT * FROM ecse_oddalerts_shadow_monitor
            WHERE substr(kickoff_utc, 1, 10) >= ? AND substr(kickoff_utc, 1, 10) <= ?
            ORDER BY kickoff_utc
            """,
            (date_from, date_to),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ecse_oddalerts_shadow_monitor ORDER BY kickoff_utc DESC LIMIT 500"
        ).fetchall()

    evaluated_n = 0
    waiting_n = 0
    by_badge: dict[str, dict[str, Any]] = {}
    by_comp: dict[str, dict[str, Any]] = {}
    by_elig: dict[str, dict[str, Any]] = {}
    top5_signal: dict[str, int] = {"true": 0, "false": 0}

    for row in rows:
        r = dict(row)
        fid = int(r["fixture_id"])
        fx = conn.execute(
            """
            SELECT f.status, fr.home_goals, fr.away_goals
            FROM fixtures f
            LEFT JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
            WHERE f.fixture_id = ?
            """,
            (fid,),
        ).fetchone()

        hg = ag = None
        finished = False
        if fx:
            hg, ag = fx["home_goals"], fx["away_goals"]
            st = str(fx["status"] or "").upper()
            finished = hg is not None and ag is not None and st in ("FT", "AET", "PEN", "FINISHED")

        top3 = json.loads(r.get("top_3_scores_json") or "[]")
        top5 = json.loads(r.get("top_5_scores_json") or "[]")
        top10_raw = json.loads(r.get("top_10_scores_json") or "[]")
        top10 = [x.get("scoreline") for x in top10_raw if isinstance(x, dict)]

        if finished:
            actual = f"{int(hg)}-{int(ag)}"
            t1 = r["top_1_score"] == actual
            t3 = actual in top3
            t5 = actual in top5
            t10 = actual in top10
            conn.execute(
                """
                UPDATE ecse_oddalerts_shadow_monitor SET
                    evaluated_at = ?, final_score = ?,
                    top1_hit = ?, top3_hit = ?, top5_hit = ?, top10_hit = ?
                WHERE id = ?
                """,
                (_iso_now(), actual, int(t1), int(t3), int(t5), int(t10), r["id"]),
            )
            evaluated_n += 1
            badge = r.get("segment_badge_v2") or "UNKNOWN"
            comp = r.get("competition") or "unknown"
            elig = r.get("promotion_eligibility_v2") or "unknown"
            for bucket, key in ((by_badge, badge), (by_comp, comp), (by_elig, elig)):
                bucket.setdefault(key, {"n": 0, "t1": 0, "t3": 0, "t5": 0})
                bucket[key]["n"] += 1
                bucket[key]["t1"] += int(t1)
                bucket[key]["t3"] += int(t3)
                bucket[key]["t5"] += int(t5)
            sig = "true" if r.get("top5_value_signal") else "false"
            top5_signal[sig] = top5_signal.get(sig, 0) + 1
        else:
            waiting_n += 1

    conn.commit()

    def _rates(d: dict[str, dict]) -> dict[str, Any]:
        out = {}
        for k, v in d.items():
            n = v["n"]
            if n:
                out[k] = {
                    "count": n,
                    "top1_hit_rate": round(v["t1"] / n, 4),
                    "top3_hit_rate": round(v["t3"] / n, 4),
                    "top5_hit_rate": round(v["t5"] / n, 4),
                }
        return out

    if monitor_run_id_val:
        finished_rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM ecse_oddalerts_shadow_monitor WHERE monitor_run_id = ? AND top1_hit IS NOT NULL",
                (monitor_run_id_val,),
            ).fetchall()
        ]
    else:
        finished_rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM ecse_oddalerts_shadow_monitor WHERE top1_hit IS NOT NULL LIMIT 500"
            ).fetchall()
        ]

    n = len(finished_rows)
    overall = {}
    if n:
        overall = {
            "top1_hit_rate": round(sum(r["top1_hit"] for r in finished_rows) / n, 4),
            "top3_hit_rate": round(sum(r["top3_hit"] for r in finished_rows) / n, 4),
            "top5_hit_rate": round(sum(r["top5_hit"] for r in finished_rows) / n, 4),
            "top10_hit_rate": round(sum(r["top10_hit"] for r in finished_rows) / n, 4),
        }

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "monitor_count": len(rows),
        "evaluated_count": evaluated_n,
        "waiting_count": waiting_n,
        "overall": overall,
        "by_badge": _rates(by_badge),
        "by_competition": _rates(by_comp),
        "by_promotion_eligibility": _rates(by_elig),
        "by_top5_value_signal": top5_signal,
    }


def list_monitor_for_owner(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str = "all",
    limit: int = 200,
) -> dict[str, Any]:
    ensure_monitor_table(conn)
    q = "SELECT * FROM ecse_oddalerts_shadow_monitor WHERE 1=1"
    params: list[Any] = []
    if date_from:
        q += " AND substr(kickoff_utc, 1, 10) >= ?"
        params.append(date_from)
    if date_to:
        q += " AND substr(kickoff_utc, 1, 10) <= ?"
        params.append(date_to)
    q += " ORDER BY kickoff_utc DESC LIMIT ?"
    params.append(limit)

    items = []
    for row in conn.execute(q, params).fetchall():
        r = dict(row)
        top10 = json.loads(r.get("top_10_scores_json") or "[]")
        items.append(
            {
                "fixture_id": r["fixture_id"],
                "home_team": r["home_team"],
                "away_team": r["away_team"],
                "competition": r["competition"],
                "kickoff_utc": r["kickoff_utc"],
                "final_score": r.get("final_score"),
                "finished": r.get("final_score") is not None,
                "top_1_score": r["top_1_score"],
                "top_3_scores": json.loads(r.get("top_3_scores_json") or "[]"),
                "top_5_scores": json.loads(r.get("top_5_scores_json") or "[]"),
                "top_10_scores": top10,
                "top1_hit": bool(r["top1_hit"]) if r.get("top1_hit") is not None else None,
                "top3_hit": bool(r["top3_hit"]) if r.get("top3_hit") is not None else None,
                "top5_hit": bool(r["top5_hit"]) if r.get("top5_hit") is not None else None,
                "lambda_home": r["lambda_home"],
                "lambda_away": r["lambda_away"],
                "segment_model_version": r["segment_model_version"],
                "segment_score_v2": r["segment_score_v2"],
                "segment_badge_v2": r["segment_badge_v2"],
                "expected_top3_rate": r.get("expected_top3_rate"),
                "expected_top5_rate": r.get("expected_top5_rate"),
                "top5_value_signal": bool(r.get("top5_value_signal")),
                "promotion_eligibility_v2": r.get("promotion_eligibility_v2"),
                "segment_reasons_v2": json.loads(r.get("reasons_json") or "[]"),
                "segment_cautions_v2": json.loads(r.get("cautions_v2") or "[]"),
                "source_trace": json.loads(r.get("source_trace_json") or "{}"),
                "monitor_run_id": r.get("monitor_run_id"),
            }
        )

    if status == "finished":
        items = [i for i in items if i.get("finished")]
    elif status == "upcoming":
        items = [i for i in items if not i.get("finished")]

    return {
        "phase": PHASE,
        "view": "live_shadow_monitor",
        "segment_model_version": SEGMENT_MODEL_V2,
        "total": len(items),
        "items": items,
    }

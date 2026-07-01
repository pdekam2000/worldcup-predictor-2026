"""ECSE OddAlerts shadow write, evaluation, and baseline comparison (owner/internal)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.data_import.oddalerts_csv_promotion_dryrun import SOURCE_DETAIL, SOURCE_PROVIDER
from worldcup_predictor.research.oddalerts_ecse_shadow_ddl import ECSE_ODDALERTS_SHADOW_DDL, PHASE

PROCESS_DATE = "2026-06-30"
DEFAULT_RUN_ID = "ecse_oddalerts_20260630"
REPORT_PATH = Path("ECSE_ODDALERTS_SHADOW_WRITE_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")


def _date_tag(process_date: str | None = None) -> str:
    return (process_date or PROCESS_DATE).replace("-", "")


def artifact_paths(process_date: str | None = None) -> dict[str, Path]:
    tag = _date_tag(process_date)
    return {
        "predictions_jsonl": Path(f"artifacts/ecse_oddalerts_dryrun_predictions_{tag}.jsonl"),
        "write_out": Path(f"artifacts/ecse_oddalerts_shadow_write_{tag}.json"),
        "evaluation": Path(f"artifacts/ecse_oddalerts_shadow_evaluation_{tag}.json"),
        "comparison": Path(f"artifacts/ecse_oddalerts_shadow_baseline_comparison_{tag}.json"),
        "validation_out": Path(f"artifacts/ecse_oddalerts_shadow_validation_{tag}.json"),
    }


def ensure_shadow_table(conn: sqlite3.Connection) -> None:
    for ddl in ECSE_ODDALERTS_SHADOW_DDL:
        conn.execute(ddl)
    conn.commit()


def load_dryrun_records(
    input_path: Path,
    *,
    limit: int | None = None,
    fixture_id: int | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with input_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("status") != "generated":
                continue
            if fixture_id is not None and int(rec.get("fixture_id") or 0) != fixture_id:
                continue
            records.append(rec)
            if limit is not None and len(records) >= limit:
                break
    return records


def validate_shadow_record(record: dict[str, Any]) -> tuple[bool, str]:
    required = (
        "fixture_id",
        "odds_snapshot_id",
        "top_10_exact_scores",
        "lambda_home",
        "lambda_away",
        "source_provider",
        "source_detail",
    )
    for key in required:
        if record.get(key) is None:
            return False, f"missing_{key}"
    if record.get("source_provider") != SOURCE_PROVIDER:
        return False, "invalid_source_provider"
    if record.get("source_detail") != SOURCE_DETAIL:
        return False, "invalid_source_detail"
    top10 = record.get("top_10_exact_scores") or []
    if not top10:
        return False, "empty_top_10"
    lh, la = float(record["lambda_home"]), float(record["lambda_away"])
    if lh <= 0 or la <= 0 or lh > 6 or la > 6:
        return False, "invalid_lambda"
    return True, "ok"


def compute_record_hash(record: dict[str, Any], shadow_run_id: str) -> str:
    payload = {
        "fixture_id": int(record["fixture_id"]),
        "odds_snapshot_id": int(record["odds_snapshot_id"]),
        "shadow_run_id": shadow_run_id,
        "top_1_score": record.get("top_1_score"),
        "lambda_home": round(float(record["lambda_home"]), 6),
        "lambda_away": round(float(record["lambda_away"]), 6),
        "top_10": [e.get("scoreline") for e in (record.get("top_10_exact_scores") or [])[:10]],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_snapshot_traceability(conn: sqlite3.Connection, odds_snapshot_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT payload_json FROM odds_snapshots WHERE id = ? LIMIT 1",
        (int(odds_snapshot_id),),
    ).fetchone()
    if not row:
        return {}
    try:
        payload = json.loads(row[0] if isinstance(row[0], str) else row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        return {}
    meta = payload.get("metadata") or {}
    return {
        "source_bookmakers": meta.get("source_bookmakers") or [],
        "source_row_hashes": meta.get("source_row_hashes") or [],
        "source_files": meta.get("source_files") or [],
        "crosswalk_confidence": meta.get("crosswalk_confidence"),
    }


def record_to_shadow_row(
    record: dict[str, Any],
    *,
    shadow_run_id: str,
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trace = trace or {}
    generated_at = record.get("generated_at") or _iso_now()
    record_hash = compute_record_hash(record, shadow_run_id)
    return {
        "fixture_id": int(record["fixture_id"]),
        "home_team": record.get("home_team"),
        "away_team": record.get("away_team"),
        "competition": record.get("competition"),
        "kickoff_utc": record.get("kickoff_utc"),
        "odds_snapshot_id": int(record["odds_snapshot_id"]),
        "source_provider": record.get("source_provider"),
        "source_detail": record.get("source_detail"),
        "policy_version": record.get("policy_version"),
        "promotion_action": record.get("promotion_action") or record.get("generated_from_snapshot"),
        "lambda_home": float(record["lambda_home"]),
        "lambda_away": float(record["lambda_away"]),
        "top_1_score": record.get("top_1_score"),
        "top_3_scores_json": json.dumps(record.get("top_3_scores") or [], ensure_ascii=False),
        "top_5_scores_json": json.dumps(record.get("top_5_scores") or [], ensure_ascii=False),
        "top_10_scores_json": json.dumps(record.get("top_10_exact_scores") or [], ensure_ascii=False),
        "input_market_probabilities_json": json.dumps(
            record.get("input_market_probabilities") or {}, ensure_ascii=False
        ),
        "warning_flags_json": json.dumps(record.get("warning_flags") or [], ensure_ascii=False),
        "normalization_notes_json": json.dumps(record.get("normalization_notes") or [], ensure_ascii=False),
        "source_bookmakers_json": json.dumps(trace.get("source_bookmakers") or [], ensure_ascii=False),
        "source_row_hashes_json": json.dumps(trace.get("source_row_hashes") or [], ensure_ascii=False),
        "source_files_json": json.dumps(trace.get("source_files") or [], ensure_ascii=False),
        "crosswalk_confidence": trace.get("crosswalk_confidence") or record.get("crosswalk_confidence"),
        "confidence_score": record.get("confidence_score"),
        "confidence_tier": record.get("confidence_tier"),
        "data_quality_score": record.get("data_quality_score"),
        "generated_at": generated_at,
        "shadow_run_id": shadow_run_id,
        "record_hash": record_hash,
        "created_at": _iso_now(),
    }


def write_shadow_predictions(
    conn: sqlite3.Connection,
    records: list[dict[str, Any]],
    *,
    shadow_run_id: str,
    dry_run: bool = True,
    enrich_traceability: bool = True,
) -> dict[str, Any]:
    ensure_shadow_table(conn)

    invalid: list[dict[str, Any]] = []
    valid: list[dict[str, Any]] = []
    for rec in records:
        ok, reason = validate_shadow_record(rec)
        if ok:
            valid.append(rec)
        else:
            invalid.append({"fixture_id": rec.get("fixture_id"), "reason": reason})

    existing_hashes: set[str] = set()
    if not dry_run and valid:
        hashes = [compute_record_hash(r, shadow_run_id) for r in valid]
        placeholders = ",".join("?" * len(hashes))
        rows = conn.execute(
            f"SELECT record_hash FROM ecse_oddalerts_shadow_predictions WHERE record_hash IN ({placeholders})",
            hashes,
        ).fetchall()
        existing_hashes = {r[0] if not isinstance(r, sqlite3.Row) else r["record_hash"] for r in rows}

    written = 0
    skipped = 0
    would_write = 0
    written_fixture_ids: list[int] = []

    for rec in valid:
        rec_hash = compute_record_hash(rec, shadow_run_id)
        if rec_hash in existing_hashes:
            skipped += 1
            continue

        trace: dict[str, Any] = {}
        if enrich_traceability:
            trace = fetch_snapshot_traceability(conn, int(rec["odds_snapshot_id"]))

        row = record_to_shadow_row(rec, shadow_run_id=shadow_run_id, trace=trace)

        if dry_run:
            would_write += 1
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO ecse_oddalerts_shadow_predictions (
                fixture_id, home_team, away_team, competition, kickoff_utc,
                odds_snapshot_id, source_provider, source_detail, policy_version, promotion_action,
                lambda_home, lambda_away, top_1_score,
                top_3_scores_json, top_5_scores_json, top_10_scores_json,
                input_market_probabilities_json, warning_flags_json, normalization_notes_json,
                source_bookmakers_json, source_row_hashes_json, source_files_json,
                crosswalk_confidence, confidence_score, confidence_tier, data_quality_score,
                generated_at, shadow_run_id, record_hash, created_at
            ) VALUES (
                :fixture_id, :home_team, :away_team, :competition, :kickoff_utc,
                :odds_snapshot_id, :source_provider, :source_detail, :policy_version, :promotion_action,
                :lambda_home, :lambda_away, :top_1_score,
                :top_3_scores_json, :top_5_scores_json, :top_10_scores_json,
                :input_market_probabilities_json, :warning_flags_json, :normalization_notes_json,
                :source_bookmakers_json, :source_row_hashes_json, :source_files_json,
                :crosswalk_confidence, :confidence_score, :confidence_tier, :data_quality_score,
                :generated_at, :shadow_run_id, :record_hash, :created_at
            )
            """,
            row,
        )
        if conn.total_changes:
            written += 1
            written_fixture_ids.append(int(rec["fixture_id"]))
        else:
            skipped += 1

    if not dry_run:
        conn.commit()

    shadow_count = conn.execute(
        "SELECT COUNT(*) c FROM ecse_oddalerts_shadow_predictions WHERE shadow_run_id = ?",
        (shadow_run_id,),
    ).fetchone()
    count_val = shadow_count[0] if not isinstance(shadow_count, sqlite3.Row) else shadow_count["c"]

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "shadow_run_id": shadow_run_id,
        "dry_run": dry_run,
        "input_count": len(records),
        "valid_count": len(valid),
        "invalid_count": len(invalid),
        "written_count": written if not dry_run else 0,
        "would_write_count": would_write if dry_run else 0,
        "skipped_count": skipped,
        "shadow_run_total": int(count_val),
        "invalid_records": invalid[:20],
        "written_fixture_ids_sample": written_fixture_ids[:20],
    }


def _lambda_bucket(lh: float, la: float) -> str:
    total = lh + la
    if total < 2.0:
        return "low_total_goals"
    if total < 2.8:
        return "medium_total_goals"
    return "high_total_goals"


def _parse_json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except json.JSONDecodeError:
        return []


def _top_scorelines_from_json(raw: str | None, *, limit: int) -> list[str]:
    items = _parse_json_list(raw)
    if not items:
        return []
    if isinstance(items[0], dict):
        return [str(x.get("scoreline", "")) for x in items[:limit] if x.get("scoreline")]
    return [str(x) for x in items[:limit]]


def evaluate_shadow_predictions(
    conn: sqlite3.Connection,
    *,
    shadow_run_id: str,
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT s.*, r.home_goals, r.away_goals, f.status
        FROM ecse_oddalerts_shadow_predictions s
        LEFT JOIN fixtures f ON f.fixture_id = s.fixture_id
        LEFT JOIN fixture_results r ON r.fixture_id = s.fixture_id
        WHERE s.shadow_run_id = ?
        ORDER BY s.fixture_id
        """,
        (shadow_run_id,),
    ).fetchall()

    evaluated: list[dict[str, Any]] = []
    waiting = 0
    by_competition: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "top1": 0, "top3": 0, "top5": 0, "top10": 0})
    by_lambda_bucket: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "top1": 0, "top3": 0, "top5": 0})
    by_top1: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "top1": 0})
    by_promotion: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "top1": 0, "top3": 0, "top5": 0})

    for row in rows:
        r = dict(row)
        hg, ag = r.get("home_goals"), r.get("away_goals")
        status = str(r.get("status") or "").upper()
        if hg is None or ag is None or status not in ("FT", "AET", "PEN", "FINISHED"):
            waiting += 1
            continue

        actual = f"{int(hg)}-{int(ag)}"
        top3 = _top_scorelines_from_json(r.get("top_3_scores_json"), limit=3)
        top5 = _top_scorelines_from_json(r.get("top_5_scores_json"), limit=5)
        top10 = _top_scorelines_from_json(r.get("top_10_scores_json"), limit=10)
        top1 = r.get("top_1_score")
        hit1 = top1 == actual
        hit3 = actual in top3
        hit5 = actual in top5
        hit10 = actual in top10

        comp = r.get("competition") or "unknown"
        bucket = _lambda_bucket(float(r["lambda_home"]), float(r["lambda_away"]))
        promo = r.get("promotion_action") or "unknown"

        for group in (
            by_competition[comp],
            by_lambda_bucket[bucket],
            by_top1[top1 or "?"],
            by_promotion[promo],
        ):
            group["n"] += 1
        by_competition[comp]["top1"] += int(hit1)
        by_competition[comp]["top3"] += int(hit3)
        by_competition[comp]["top5"] += int(hit5)
        by_competition[comp]["top10"] += int(hit10)
        by_lambda_bucket[bucket]["top1"] += int(hit1)
        by_lambda_bucket[bucket]["top3"] += int(hit3)
        by_lambda_bucket[bucket]["top5"] += int(hit5)
        by_top1[top1 or "?"]["top1"] += int(hit1)
        by_promotion[promo]["top1"] += int(hit1)
        by_promotion[promo]["top3"] += int(hit3)
        by_promotion[promo]["top5"] += int(hit5)

        evaluated.append(
            {
                "fixture_id": r["fixture_id"],
                "actual_score": actual,
                "top_1_score": top1,
                "top_1_hit": hit1,
                "top_3_hit": hit3,
                "top_5_hit": hit5,
                "top_10_hit": hit10,
                "promotion_action": promo,
                "competition": comp,
                "lambda_bucket": bucket,
            }
        )

    n = len(evaluated)
    top1_dist = Counter(e["top_1_score"] for e in evaluated if e.get("top_1_hit"))

    def _rates(group: dict[str, dict[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, stats in group.items():
            cnt = stats["n"]
            if cnt == 0:
                continue
            out[key] = {
                "count": cnt,
                "top1_hit_rate": round(stats.get("top1", 0) / cnt, 4),
                "top3_hit_rate": round(stats.get("top3", 0) / cnt, 4) if "top3" in stats else None,
                "top5_hit_rate": round(stats.get("top5", 0) / cnt, 4) if "top5" in stats else None,
                "top10_hit_rate": round(stats.get("top10", 0) / cnt, 4) if "top10" in stats else None,
            }
        return out

    if n == 0:
        return {
            "phase": PHASE,
            "shadow_run_id": shadow_run_id,
            "status": "WAITING_FOR_RESULTS",
            "shadow_count": len(rows),
            "evaluated_count": 0,
            "waiting_count": waiting,
        }

    return {
        "phase": PHASE,
        "shadow_run_id": shadow_run_id,
        "status": "EVALUATED",
        "shadow_count": len(rows),
        "evaluated_count": n,
        "waiting_count": waiting,
        "top1_hit_rate": round(sum(1 for e in evaluated if e["top_1_hit"]) / n, 4),
        "top3_hit_rate": round(sum(1 for e in evaluated if e["top_3_hit"]) / n, 4),
        "top5_hit_rate": round(sum(1 for e in evaluated if e["top_5_hit"]) / n, 4),
        "top10_hit_rate": round(sum(1 for e in evaluated if e["top_10_hit"]) / n, 4),
        "top1_hit_score_distribution": dict(top1_dist),
        "by_competition": _rates(by_competition),
        "by_lambda_bucket": _rates(by_lambda_bucket),
        "by_top_1_score": _rates(by_top1),
        "by_promotion_action": _rates(by_promotion),
        "samples": evaluated[:30],
    }


def _implied_1x2_pick(probs: dict[str, Any]) -> str | None:
    home = probs.get("match_result_home")
    draw = probs.get("match_result_draw")
    away = probs.get("match_result_away")
    if home is None or draw is None or away is None:
        return None
    vals = {"home": float(home), "draw": float(draw), "away": float(away)}
    pick = max(vals, key=vals.get)
    return pick


def _wde_result_pick(payload: dict[str, Any]) -> str | None:
    for key in ("result_market", "match_result", "1x2", "markets"):
        block = payload.get(key)
        if isinstance(block, dict):
            pick = block.get("pick") or block.get("prediction") or block.get("top_pick")
            if pick:
                return str(pick).lower()
    preds = payload.get("predictions") or payload.get("market_predictions") or {}
    if isinstance(preds, dict):
        mr = preds.get("match_result") or preds.get("1x2") or {}
        if isinstance(mr, dict):
            return str(mr.get("pick") or mr.get("prediction") or "").lower() or None
    return None


def _score_to_outcome(score: str) -> str | None:
    parts = score.split("-")
    if len(parts) != 2:
        return None
    try:
        h, a = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if h > a:
        return "home"
    if h < a:
        return "away"
    return "draw"


def compare_shadow_vs_baselines(
    conn: sqlite3.Connection,
    *,
    shadow_run_id: str,
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT fixture_id, top_1_score, input_market_probabilities_json,
               promotion_action, competition, lambda_home, lambda_away
        FROM ecse_oddalerts_shadow_predictions
        WHERE shadow_run_id = ?
        ORDER BY fixture_id
        """,
        (shadow_run_id,),
    ).fetchall()

    ecse_available = 0
    wde_available = 0
    bookmaker_available = 0
    ecse_agree = 0
    wde_agree = 0
    bookmaker_agree = 0
    compared = 0
    samples: list[dict[str, Any]] = []

    for row in rows:
        r = dict(row)
        fid = int(r["fixture_id"])
        shadow_top1 = r.get("top_1_score")
        shadow_outcome = _score_to_outcome(shadow_top1 or "")

        ecse_row = conn.execute(
            "SELECT top_1_score FROM ecse_prediction_snapshots WHERE fixture_id = ? LIMIT 1",
            (fid,),
        ).fetchone()
        wde_row = conn.execute(
            "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id = ? LIMIT 1",
            (fid,),
        ).fetchone()

        probs: dict[str, Any] = {}
        try:
            probs = json.loads(r.get("input_market_probabilities_json") or "{}")
        except json.JSONDecodeError:
            probs = {}

        book_pick = _implied_1x2_pick(probs)
        ecse_top1 = None
        wde_pick = None

        if ecse_row:
            ecse_available += 1
            ecse_top1 = ecse_row[0] if not isinstance(ecse_row, sqlite3.Row) else ecse_row["top_1_score"]
        if wde_row:
            wde_available += 1
            raw = wde_row[0] if not isinstance(wde_row, sqlite3.Row) else wde_row["payload_json"]
            try:
                wde_pick = _wde_result_pick(json.loads(raw))
            except json.JSONDecodeError:
                wde_pick = None
        if book_pick:
            bookmaker_available += 1

        if shadow_outcome:
            compared += 1
            ecse_match = _score_to_outcome(ecse_top1 or "") == shadow_outcome if ecse_top1 else None
            wde_match = wde_pick == shadow_outcome if wde_pick else None
            book_match = book_pick == shadow_outcome if book_pick else None
            if ecse_match:
                ecse_agree += 1
            if wde_match:
                wde_agree += 1
            if book_match:
                bookmaker_agree += 1

            if len(samples) < 20:
                samples.append(
                    {
                        "fixture_id": fid,
                        "shadow_top_1": shadow_top1,
                        "shadow_outcome": shadow_outcome,
                        "ecse_top_1": ecse_top1,
                        "wde_pick": wde_pick,
                        "bookmaker_1x2_pick": book_pick,
                    }
                )

    def _rate(num: int, den: int) -> float | None:
        return round(num / den, 4) if den else None

    return {
        "phase": PHASE,
        "shadow_run_id": shadow_run_id,
        "shadow_count": len(rows),
        "compared_count": compared,
        "baselines": {
            "ecse_production": {
                "available_count": ecse_available,
                "missing_count": len(rows) - ecse_available,
                "outcome_agreement_rate": _rate(ecse_agree, ecse_available),
            },
            "wde": {
                "available_count": wde_available,
                "missing_count": len(rows) - wde_available,
                "outcome_agreement_rate": _rate(wde_agree, wde_available),
            },
            "bookmaker_implied_1x2": {
                "available_count": bookmaker_available,
                "missing_count": len(rows) - bookmaker_available,
                "outcome_agreement_rate": _rate(bookmaker_agree, bookmaker_available),
            },
        },
        "samples": samples,
        "note": "Outcome agreement compares 1X2 direction implied by shadow top-1 score vs baseline picks.",
    }


def shadow_final_recommendation(
    *,
    write_result: dict[str, Any],
    evaluation: dict[str, Any],
    comparison: dict[str, Any],
    validation_passed: bool,
) -> str:
    if not validation_passed:
        return "DO_NOT_PROMOTE_ECSE"

    shadow_total = int(write_result.get("shadow_run_total") or 0)
    if shadow_total == 0:
        return "DO_NOT_PROMOTE_ECSE"

    if write_result.get("dry_run"):
        return "ECSE_ODDALERTS_SHADOW_WRITTEN" if write_result.get("would_write_count") else "DO_NOT_PROMOTE_ECSE"

    eval_status = evaluation.get("status")
    top1 = evaluation.get("top1_hit_rate") or 0

    if shadow_total >= 197 and eval_status == "EVALUATED":
        if top1 >= 0.15 and evaluation.get("top3_hit_rate", 0) >= 0.28:
            return "READY_FOR_LIMITED_ECSE_PRODUCTION_WRITE"
        if top1 < 0.08:
            return "NEED_SEGMENT_FILTERS"
        return "ECSE_ODDALERTS_SHADOW_EVALUATED"

    if shadow_total >= int(write_result.get("valid_count") or 0):
        return "READY_FOR_OWNER_LAB_DISPLAY"

    return "ECSE_ODDALERTS_SHADOW_WRITTEN"


def build_shadow_report_markdown(
    *,
    write_result: dict[str, Any],
    evaluation: dict[str, Any],
    comparison: dict[str, Any],
    validation: dict[str, Any],
    production_guard: dict[str, Any],
    recommendation: str,
) -> str:
    checks = validation.get("checks") or []
    val_lines = [f"- [{'pass' if c.get('passed') else 'FAIL'}] {c.get('check')}" for c in checks]
    baselines = comparison.get("baselines") or {}

    best_segments: list[str] = []
    worst_segments: list[str] = []
    for label, block in (evaluation.get("by_lambda_bucket") or {}).items():
        rate = block.get("top1_hit_rate")
        if rate is not None:
            (best_segments if rate >= 0.12 else worst_segments).append(f"{label}: top1={rate}")

    sample_preds = (evaluation.get("samples") or [])[:5]
    sample_lines = [
        f"| {s.get('fixture_id')} | {s.get('actual_score')} | {s.get('top_1_score')} | "
        f"{'Y' if s.get('top_1_hit') else 'N'} | {s.get('promotion_action')} |"
        for s in sample_preds
    ]

    return f"""# ECSE OddAlerts Shadow Write Report

**Phase:** {PHASE}  
**Generated:** {_utc_now()}  
**Mode:** Owner/internal shadow write — no production ECSE, no public publish

---

## Summary

**Final recommendation:** `{recommendation}`

| Metric | Value |
|--------|-------|
| Input records | {write_result.get('input_count', 0)} |
| Valid records | {write_result.get('valid_count', 0)} |
| Written | {write_result.get('written_count', 0)} |
| Would write (dry-run) | {write_result.get('would_write_count', 0)} |
| Skipped (idempotent) | {write_result.get('skipped_count', 0)} |
| Shadow run total | {write_result.get('shadow_run_total', 0)} |
| Shadow run ID | `{write_result.get('shadow_run_id', '')}` |

---

## Production tables unchanged

| Table | Before | After |
|-------|--------|-------|
| ecse_prediction_snapshots | {production_guard.get('ecse_before')} | {production_guard.get('ecse_after')} |
| odds_snapshots | {production_guard.get('odds_before')} | {production_guard.get('odds_after')} |
| worldcup_stored_predictions | {production_guard.get('wde_before')} | {production_guard.get('wde_after')} |

---

## Idempotency

- Dry-run mode: {write_result.get('dry_run')}
- Skipped on re-run: {write_result.get('skipped_count', 0)}

---

## Evaluation metrics

Status: **{evaluation.get('status', 'N/A')}**  
Evaluated: {evaluation.get('evaluated_count', 0)} | Waiting: {evaluation.get('waiting_count', 0)}

| Metric | Rate |
|--------|------|
| Top-1 | {evaluation.get('top1_hit_rate', 'N/A')} |
| Top-3 | {evaluation.get('top3_hit_rate', 'N/A')} |
| Top-5 | {evaluation.get('top5_hit_rate', 'N/A')} |
| Top-10 | {evaluation.get('top10_hit_rate', 'N/A')} |

### By promotion action

```json
{json.dumps(evaluation.get('by_promotion_action', {}), indent=2)}
```

---

## Baseline comparison

```json
{json.dumps(baselines, indent=2)}
```

---

## Best / worst lambda segments

**Best:** {', '.join(best_segments[:5]) or '—'}  
**Worst:** {', '.join(worst_segments[:5]) or '—'}

---

## Sample evaluated predictions

| Fixture | Actual | Top-1 | Hit | Source |
|---------|--------|-------|-----|--------|
{chr(10).join(sample_lines) if sample_lines else '| — | — | — | — | — |'}

---

## Validation

{chr(10).join(val_lines)}

Passed: **{validation.get('passed', 0)}** / **{len(checks)}**
"""

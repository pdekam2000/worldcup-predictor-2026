"""Forward validation pipeline for prematch ESDI / Fragility risk metadata."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.forward_evaluation.constants import HIT, MISS
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.research.ecse_esdi_fragility.metrics import (
    SELECTOR_VERSION,
    build_prematch_risk_record,
    ranks_to_rows,
)
from worldcup_predictor.research.ecse_esdi_fragility.thresholds import (
    THRESHOLD_VERSION,
    assign_buckets,
    calibrate_thresholds,
    write_threshold_artifact,
)
from worldcup_predictor.research.ecse_live.store import get_snapshot

COHORT_A_END = 100
COHORT_B_END = 500
ART = Path("artifacts") / "ecse_esdi_forward"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def ensure_risk_metadata_schema(eval_conn: sqlite3.Connection) -> None:
    eval_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ecse_prematch_risk_metadata (
            prediction_id TEXT PRIMARY KEY,
            fixture_id INTEGER NOT NULL,
            content_hash TEXT,
            selector_version TEXT NOT NULL,
            threshold_version TEXT NOT NULL,
            esdi_score REAL,
            fragility_score REAL,
            esdi_bucket TEXT,
            fragility_bucket TEXT,
            metadata_json TEXT NOT NULL,
            frozen_at TEXT NOT NULL,
            kickoff TEXT,
            UNIQUE(fixture_id, content_hash, threshold_version, selector_version)
        )
        """
    )
    eval_conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ecse_risk_fixture ON ecse_prematch_risk_metadata(fixture_id)"
    )
    eval_conn.commit()


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _append_jsonl(path: Path, rows: list[dict[str, Any]], key_fields: tuple[str, ...]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: set[tuple[str, ...]] = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing.add(tuple(str(rec.get(k) or "") for k in key_fields))
    added = 0
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            key = tuple(str(row.get(k) or "") for k in key_fields)
            if key in existing:
                continue
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            existing.add(key)
            added += 1
    return added


def _load_top10(prod_conn: sqlite3.Connection | None, fixture_id: int, ranks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if prod_conn is not None:
        snap = get_snapshot(prod_conn, fixture_id)
        if snap and isinstance(snap.get("top_10_scorelines"), list):
            return snap["top_10_scorelines"]
    return ranks_to_rows(ranks, limit=10)


def freeze_forward_risk_metadata(
    eval_conn: sqlite3.Connection,
    prod_conn: sqlite3.Connection | None,
    thresholds: dict[str, Any],
) -> list[dict[str, Any]]:
    ensure_risk_metadata_schema(eval_conn)
    frozen_rows = [
        dict(r)
        for r in eval_conn.execute(
            "SELECT * FROM frozen_predictions ORDER BY kickoff, frozen_at"
        ).fetchall()
    ]
    out: list[dict[str, Any]] = []
    for frozen in frozen_rows:
        pid = str(frozen["prediction_id"])
        fid = int(frozen["fixture_id"])
        existing = eval_conn.execute(
            """
            SELECT prediction_id FROM ecse_prematch_risk_metadata
            WHERE prediction_id=? AND threshold_version=? AND selector_version=?
            """,
            (pid, THRESHOLD_VERSION, SELECTOR_VERSION),
        ).fetchone()
        if existing:
            continue
        ranks = [
            dict(r)
            for r in eval_conn.execute(
                "SELECT rank, score, probability FROM exact_score_rankings WHERE prediction_id=? ORDER BY rank",
                (pid,),
            ).fetchall()
        ]
        if len(ranks) < 5:
            continue
        top10 = _load_top10(prod_conn, fid, ranks)
        record = build_prematch_risk_record(
            prediction_id=pid,
            fixture_id=fid,
            ranks=ranks,
            frozen=frozen,
            top10_scorelines=top10,
        )
        buckets = assign_buckets(record, thresholds)
        record.update(buckets)
        record["threshold_version"] = THRESHOLD_VERSION
        record["recorded_at"] = _utc_now()
        eval_conn.execute(
            """
            INSERT OR IGNORE INTO ecse_prematch_risk_metadata (
                prediction_id, fixture_id, content_hash, selector_version, threshold_version,
                esdi_score, fragility_score, esdi_bucket, fragility_bucket,
                metadata_json, frozen_at, kickoff
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid,
                fid,
                record.get("source_freeze_hash"),
                SELECTOR_VERSION,
                THRESHOLD_VERSION,
                record["esdi_score"],
                record["fragility_score"],
                buckets["esdi_bucket"],
                buckets["fragility_bucket"],
                json.dumps(record, ensure_ascii=False, default=str),
                frozen.get("frozen_at") or _utc_now(),
                frozen.get("kickoff"),
            ),
        )
        out.append(record)
    eval_conn.commit()
    return out


def _assign_cohort(index_1based: int) -> str:
    if index_1based <= COHORT_A_END:
        return "A"
    if index_1based <= COHORT_B_END:
        return "B"
    return "C"


def build_daily_evaluations(eval_conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = eval_conn.execute(
        """
        SELECT
            f.prediction_id, f.fixture_id, f.match_name, f.kickoff, f.frozen_at,
            f.wde_decision, f.btts_prediction, f.ou25_prediction,
            m.ecse_top1_hit, m.ecse_top3_hit, m.ecse_top5_hit,
            m.wde_hit, m.btts_hit, m.ou25_hit, m.actual_score_rank,
            a.actual_score, a.actual_home_goals, a.actual_away_goals,
            a.actual_1x2, a.actual_btts, a.actual_ou25,
            r.esdi_score, r.fragility_score, r.esdi_bucket, r.fragility_bucket, r.metadata_json
        FROM frozen_predictions f
        JOIN market_evaluations m ON m.prediction_id = f.prediction_id
        JOIN actual_results a ON a.fixture_id = f.fixture_id
        LEFT JOIN ecse_prematch_risk_metadata r ON r.prediction_id = f.prediction_id
        ORDER BY f.kickoff, f.frozen_at
        """
    ).fetchall()
    evaluations: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        item = dict(row)
        meta = {}
        if item.get("metadata_json"):
            try:
                meta = json.loads(item["metadata_json"])
            except json.JSONDecodeError:
                meta = {}
        total_goals = None
        if item.get("actual_home_goals") is not None and item.get("actual_away_goals") is not None:
            total_goals = int(item["actual_home_goals"]) + int(item["actual_away_goals"])
        outside_top5 = item.get("ecse_top5_hit") == MISS
        high_score_miss = False
        if total_goals is not None and total_goals >= 4 and outside_top5:
            high_score_miss = True
        evaluations.append(
            {
                "prediction_id": item["prediction_id"],
                "fixture_id": item["fixture_id"],
                "match_name": item["match_name"],
                "kickoff": item["kickoff"],
                "cohort": _assign_cohort(idx),
                "cohort_index": idx,
                "esdi_score": item.get("esdi_score"),
                "fragility_score": item.get("fragility_score"),
                "esdi_bucket": item.get("esdi_bucket"),
                "fragility_bucket": item.get("fragility_bucket"),
                "risk_labels": meta.get("risk_labels") or [],
                "top1_hit": item.get("ecse_top1_hit") == HIT,
                "top3_hit": item.get("ecse_top3_hit") == HIT,
                "top5_hit": item.get("ecse_top5_hit") == HIT,
                "outside_top5": outside_top5,
                "actual_score_rank": item.get("actual_score_rank"),
                "actual_score": item.get("actual_score"),
                "actual_total_goals": total_goals,
                "high_score_miss": high_score_miss,
                "wde_hit": item.get("wde_hit") == HIT,
                "btts_hit": item.get("btts_hit") == HIT,
                "ou_hit": item.get("ou25_hit") == HIT,
                "evaluated_at": _utc_now(),
            }
        )
    return evaluations


def _bucket_metrics(rows: list[dict[str, Any]], bucket_field: str, bucket_value: str) -> dict[str, Any]:
    subset = [r for r in rows if r.get(bucket_field) == bucket_value]
    n = len(subset)
    if n == 0:
        return {"bucket": bucket_value, "fixture_count": 0}
    return {
        "bucket": bucket_value,
        "fixture_count": n,
        "top1_accuracy_pct": round(100.0 * sum(1 for r in subset if r["top1_hit"]) / n, 4),
        "top3_accuracy_pct": round(100.0 * sum(1 for r in subset if r["top3_hit"]) / n, 4),
        "top5_accuracy_pct": round(100.0 * sum(1 for r in subset if r["top5_hit"]) / n, 4),
        "outside_top5_rate_pct": round(100.0 * sum(1 for r in subset if r["outside_top5"]) / n, 4),
        "wde_accuracy_pct": round(100.0 * sum(1 for r in subset if r["wde_hit"]) / n, 4),
        "btts_accuracy_pct": round(100.0 * sum(1 for r in subset if r["btts_hit"]) / n, 4),
        "ou_accuracy_pct": round(100.0 * sum(1 for r in subset if r["ou_hit"]) / n, 4),
        "mean_actual_total_goals": round(
            sum(float(r["actual_total_goals"] or 0) for r in subset) / n, 4
        ),
        "high_score_miss_rate_pct": round(
            100.0 * sum(1 for r in subset if r["high_score_miss"]) / n, 4
        ),
    }


def bucket_performance_rows(evaluations: list[dict[str, Any]], *, split: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket_field in ("esdi_bucket", "fragility_bucket"):
        values = sorted({str(r.get(bucket_field)) for r in evaluations if r.get(bucket_field)})
        for value in values:
            stats = _bucket_metrics(evaluations, bucket_field, value)
            rows.append({"split": split, "bucket_type": bucket_field, **stats})
    for label in (
        "ALL_CLEAN_SHEET_TOP5",
        "SINGLE_DIRECTION_TOP5",
        "HIGH_SCORE_TAIL_EXPOSED",
        "DRAW_NOT_REPRESENTED",
        "BTTS_YES_NOT_REPRESENTED",
    ):
        subset = [r for r in evaluations if label in (r.get("risk_labels") or [])]
        n = len(subset)
        if n == 0:
            continue
        rows.append(
            {
                "split": split,
                "bucket_type": "risk_label",
                "bucket": label,
                "fixture_count": n,
                "top5_accuracy_pct": round(100.0 * sum(1 for r in subset if r["top5_hit"]) / n, 4),
                "outside_top5_rate_pct": round(100.0 * sum(1 for r in subset if r["outside_top5"]) / n, 4),
                "high_score_miss_rate_pct": round(100.0 * sum(1 for r in subset if r["high_score_miss"]) / n, 4),
            }
        )
    return rows


def abstention_rules() -> list[tuple[str, str]]:
    return [
        ("exclude_extreme_fragility", "EXTREME_FRAGILITY"),
        ("exclude_low_div_high_frag", "LOW_DIVERSITY+HIGH_FRAGILITY"),
        ("exclude_all_clean_sheet_domain_risk", "ALL_CLEAN_SHEET+DOMAIN_RISK"),
        ("exclude_high_score_tail_qualifier", "HIGH_SCORE_TAIL+DOMAIN_RISK"),
        ("require_top5_mass_max_fragility", "TOP5_MASS>=0.45 AND fragility<=75"),
        ("require_wde_ecse_agreement", "WDE_ECSE_AGREE"),
    ]


def _rule_keep(row_meta: dict[str, Any], eval_row: dict[str, Any], rule_id: str) -> bool:
    if rule_id == "exclude_extreme_fragility":
        return eval_row.get("fragility_bucket") != "EXTREME_FRAGILITY"
    if rule_id == "exclude_low_div_high_frag":
        if eval_row.get("esdi_bucket") == "LOW_DIVERSITY" and eval_row.get("fragility_bucket") in {
            "HIGH_FRAGILITY",
            "EXTREME_FRAGILITY",
        }:
            return False
        return True
    if rule_id == "exclude_all_clean_sheet_domain_risk":
        labels = set(row_meta.get("risk_labels") or [])
        if "ALL_CLEAN_SHEET_TOP5" in labels and "DOMAIN_RISK_ELEVATED" in labels:
            return False
        return True
    if rule_id == "exclude_high_score_tail_qualifier":
        labels = set(row_meta.get("risk_labels") or [])
        if "HIGH_SCORE_TAIL_EXPOSED" in labels and "DOMAIN_RISK_ELEVATED" in labels:
            return False
        return True
    if rule_id == "require_top5_mass_max_fragility":
        top5_mass = float(row_meta.get("top5_mass") or 0.0)
        if top5_mass > 1:
            top5_mass /= 100.0
        return top5_mass >= 0.45 and float(eval_row.get("fragility_score") or 100.0) <= 75.0
    if rule_id == "require_wde_ecse_agreement":
        return bool(row_meta.get("wde_ecse_agree"))
    return True


def abstention_shadow_rows(
    evaluations: list[dict[str, Any]], metadata_by_pid: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    total = len(evaluations)
    baseline_hits = sum(1 for r in evaluations if r["top5_hit"])
    rows: list[dict[str, Any]] = []
    for rule_id, label in abstention_rules():
        kept: list[dict[str, Any]] = []
        for ev in evaluations:
            meta = metadata_by_pid.get(str(ev["prediction_id"]), {})
            if _rule_keep(meta, ev, rule_id):
                kept.append(ev)
        n_kept = len(kept)
        hits_kept = sum(1 for r in kept if r["top5_hit"])
        misses_excluded = sum(1 for r in evaluations if not r["top5_hit"] and r not in kept)
        hits_wrongly_excluded = sum(1 for r in evaluations if r["top5_hit"] and r not in kept)
        rows.append(
            {
                "rule_id": rule_id,
                "rule_label": label,
                "fixtures_total": total,
                "fixtures_retained": n_kept,
                "coverage_pct": round(100.0 * n_kept / max(total, 1), 4),
                "abstention_rate_pct": round(100.0 * (total - n_kept) / max(total, 1), 4),
                "top5_accuracy_pct": round(100.0 * hits_kept / max(n_kept, 1), 4),
                "baseline_top5_accuracy_pct": round(100.0 * baseline_hits / max(total, 1), 4),
                "top5_hits_retained": hits_kept,
                "misses_excluded": misses_excluded,
                "hits_wrongly_excluded": hits_wrongly_excluded,
            }
        )
    return rows


def historical_proxy_evaluations(prod_conn: sqlite3.Connection, thresholds: dict[str, Any]) -> list[dict[str, Any]]:
    from worldcup_predictor.research.ecse_esdi_fragility.metrics import esdi_metrics, ranks_to_rows
    from worldcup_predictor.research.ecse_esdi_fragility.thresholds import (
        _historical_fixture_rows,
        _load_distributions,
    )

    rows = _historical_fixture_rows(prod_conn)
    n = len(rows)
    test_start = int(n * 0.85)
    test_rows = rows[test_start:]
    dist_map = _load_distributions(prod_conn, [int(r["registry_fixture_id"]) for r in test_rows])
    evals: list[dict[str, Any]] = []
    for meta in test_rows:
        fid = int(meta["registry_fixture_id"])
        dist = dist_map.get(fid) or []
        if len(dist) < 5:
            continue
        top5 = ranks_to_rows(dist, limit=5)
        m = esdi_metrics(top5)
        record = {"esdi_score": m["esdi_score"], "fragility_score": m["fragility_score"]}
        buckets = assign_buckets(record, thresholds)
        actual = f"{int(meta['home_goals'])}-{int(meta['away_goals'])}"
        scores = [r["scoreline"] for r in top5]
        evals.append(
            {
                "esdi_bucket": buckets["esdi_bucket"],
                "fragility_bucket": buckets["fragility_bucket"],
                "top5_hit": actual in scores,
                "top1_hit": bool(scores and actual == scores[0]),
                "top3_hit": actual in scores[:3],
                "outside_top5": actual not in scores,
                "wde_hit": False,
                "btts_hit": False,
                "ou_hit": False,
                "actual_total_goals": int(meta["home_goals"]) + int(meta["away_goals"]),
                "high_score_miss": (int(meta["home_goals"]) + int(meta["away_goals"]) >= 4) and actual not in scores,
                "risk_labels": ["ALL_CLEAN_SHEET_TOP5"] if m["clean_sheet_concentration"] >= 0.95 else [],
            }
        )
    return evals


def determine_final_status(
    evaluations: list[dict[str, Any]],
    abstention_rows: list[dict[str, Any]],
    bucket_rows: list[dict[str, Any]],
) -> str:
    n = len(evaluations)
    if n < COHORT_A_END:
        # still check proxy/hints but primary forward cohort incomplete
        forward_signal = False
        low = [r for r in bucket_rows if r.get("split") == "forward_evaluated" and r.get("bucket") == "LOW_FRAGILITY"]
        high = [r for r in bucket_rows if r.get("split") == "forward_evaluated" and r.get("bucket") == "EXTREME_FRAGILITY"]
        if low and high:
            if float(high[0].get("outside_top5_rate_pct") or 0) - float(low[0].get("outside_top5_rate_pct") or 0) >= 10.0 and n >= 30:
                forward_signal = True
        best_abst = max(abstention_rows, key=lambda r: float(r.get("top5_accuracy_pct") or 0), default=None)
        if best_abst and float(best_abst["top5_accuracy_pct"]) - float(best_abst["baseline_top5_accuracy_pct"]) >= 2.0 and float(best_abst["coverage_pct"]) >= 50.0:
            return "ECSE_ESDI_FRAGILITY_USEFUL_FOR_ABSTENTION_ONLY"
        if forward_signal:
            return "ECSE_ESDI_FRAGILITY_FORWARD_SIGNAL_PROVEN"
        return "ECSE_ESDI_FRAGILITY_MORE_FORWARD_DATA_REQUIRED"

    low = [r for r in bucket_rows if r.get("split") == "forward_evaluated" and r.get("bucket") == "LOW_FRAGILITY"]
    high = [r for r in bucket_rows if r.get("split") == "forward_evaluated" and r.get("bucket") == "EXTREME_FRAGILITY"]
    if low and high:
        spread = float(high[0].get("outside_top5_rate_pct") or 0) - float(low[0].get("outside_top5_rate_pct") or 0)
        if spread >= 8.0:
            return "ECSE_ESDI_FRAGILITY_FORWARD_SIGNAL_PROVEN"
    best_abst = max(abstention_rows, key=lambda r: float(r.get("top5_accuracy_pct") or 0), default=None)
    if best_abst and float(best_abst["top5_accuracy_pct"]) - float(best_abst["baseline_top5_accuracy_pct"]) >= 2.0 and float(best_abst["coverage_pct"]) >= 50.0:
        return "ECSE_ESDI_FRAGILITY_USEFUL_FOR_ABSTENTION_ONLY"
    return "ECSE_ESDI_FRAGILITY_NO_PREDICTIVE_VALUE"


def run_forward_validation(root: Path) -> dict[str, Any]:
    art = root / ART
    art.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    prod_conn = connect(get_db_path(settings.sqlite_path))
    eval_conn = connect_eval_db(root)

    thresholds = calibrate_thresholds(prod_conn)
    write_threshold_artifact(art / "threshold_version.json", thresholds)

    frozen_records = freeze_forward_risk_metadata(eval_conn, prod_conn, thresholds)
    _append_jsonl(
        art / "frozen_risk_metadata.jsonl",
        frozen_records,
        ("prediction_id", "threshold_version", "selector_version"),
    )

    evaluations = build_daily_evaluations(eval_conn)
    _append_jsonl(art / "daily_evaluations.jsonl", evaluations, ("prediction_id", "evaluated_at"))

    metadata_by_pid: dict[str, dict[str, Any]] = {}
    for row in eval_conn.execute("SELECT prediction_id, metadata_json FROM ecse_prematch_risk_metadata").fetchall():
        try:
            metadata_by_pid[str(row["prediction_id"])] = json.loads(row["metadata_json"])
        except json.JSONDecodeError:
            metadata_by_pid[str(row["prediction_id"])] = {}

    forward_buckets = bucket_performance_rows(evaluations, split="forward_evaluated")
    proxy_buckets = bucket_performance_rows(
        historical_proxy_evaluations(prod_conn, thresholds),
        split="historical_untouched_test_proxy",
    )
    bucket_rows = forward_buckets + proxy_buckets
    _write_csv(art / "bucket_performance.csv", bucket_rows)

    clean_sheet_rows = [r for r in bucket_rows if r.get("bucket") == "ALL_CLEAN_SHEET_TOP5"]
    tail_rows = [r for r in bucket_rows if r.get("bucket") == "HIGH_SCORE_TAIL_EXPOSED"]
    _write_csv(art / "all_clean_sheet_analysis.csv", clean_sheet_rows)
    _write_csv(art / "high_score_tail_analysis.csv", tail_rows)

    abstention_rows = abstention_shadow_rows(evaluations, metadata_by_pid)
    _write_csv(art / "abstention_shadow_results.csv", abstention_rows)

    cohort_status = {
        "cohort_a_target": COHORT_A_END,
        "cohort_b_target": COHORT_B_END - COHORT_A_END,
        "cohort_c_open_ended": True,
        "forward_evaluated_count": len(evaluations),
        "cohort_a_completed": len(evaluations),
        "cohort_a_complete": len(evaluations) >= COHORT_A_END,
        "cohort_b_started": len(evaluations) > COHORT_A_END,
        "selector_locked": SELECTOR_VERSION,
        "threshold_version": THRESHOLD_VERSION,
        "frozen_metadata_count": eval_conn.execute("SELECT COUNT(1) FROM ecse_prematch_risk_metadata").fetchone()[0],
        "generated_at": _utc_now(),
    }
    _write_json(art / "cohort_status.json", cohort_status)

    final_status = determine_final_status(evaluations, abstention_rows, bucket_rows)
    report_en = _report_en(final_status, thresholds, evaluations, bucket_rows, abstention_rows, cohort_status)
    report_fa = _report_fa(final_status, evaluations, cohort_status)
    reports_owner = root / "reports" / "owner"
    reports_daily = reports_owner / "daily"
    reports_owner.mkdir(parents=True, exist_ok=True)
    reports_daily.mkdir(parents=True, exist_ok=True)
    (reports_owner / "ECSE_ESDI_FRAGILITY_FORWARD_VALIDATION.md").write_text(report_en, encoding="utf-8")
    (reports_owner / "ECSE_ESDI_FRAGILITY_FORWARD_VALIDATION_FA.md").write_text(report_fa, encoding="utf-8")
    (reports_daily / f"{_today()}_ECSE_RISK_VALIDATION_FA.md").write_text(report_fa, encoding="utf-8")

    prod_conn.close()
    eval_conn.close()
    return {
        "final_status": final_status,
        "forward_evaluated_count": len(evaluations),
        "frozen_metadata_new": len(frozen_records),
        "threshold_version": THRESHOLD_VERSION,
        "selector_locked": SELECTOR_VERSION,
        "cohort_status": cohort_status,
    }


def _report_en(
    final_status: str,
    thresholds: dict[str, Any],
    evaluations: list[dict[str, Any]],
    bucket_rows: list[dict[str, Any]],
    abstention_rows: list[dict[str, Any]],
    cohort_status: dict[str, Any],
) -> str:
    lines = [
        "# ECSE ESDI / Fragility Forward Validation",
        "",
        f"**Final status:** `{final_status}`  ",
        f"**Selector locked:** `S4` (canonical Top5 unchanged)  ",
        f"**Threshold version:** `{THRESHOLD_VERSION}`  ",
        "",
        "## Cohort status",
        "",
        f"- Forward evaluated fixtures: **{cohort_status['forward_evaluated_count']}**",
        f"- Cohort A target: {cohort_status['cohort_a_target']} (complete: {cohort_status['cohort_a_complete']})",
        f"- Frozen prematch risk metadata rows: {cohort_status['frozen_metadata_count']}",
        "",
        "## Research questions (forward evaluated)",
        "",
    ]
    if evaluations:
        high_frag = [e for e in evaluations if e.get("fragility_bucket") == "EXTREME_FRAGILITY"]
        low_frag = [e for e in evaluations if e.get("fragility_bucket") == "LOW_FRAGILITY"]
        lines.append(
            f"- High-Fragility outside-Top5 rate: {_rate(high_frag, 'outside_top5')}% (n={len(high_frag)})"
        )
        lines.append(
            f"- Low-Fragility outside-Top5 rate: {_rate(low_frag, 'outside_top5')}% (n={len(low_frag)})"
        )
        low_esdi = [e for e in evaluations if e.get("esdi_bucket") == "LOW_DIVERSITY"]
        lines.append(f"- Low-ESDI Top5 hit rate: {_rate(low_esdi, 'top5_hit', invert=True)}% (n={len(low_esdi)})")
        all_cs = [e for e in evaluations if "ALL_CLEAN_SHEET_TOP5" in (e.get("risk_labels") or [])]
        lines.append(f"- All-clean-sheet Top5 miss rate: {_rate(all_cs, 'outside_top5')}% (n={len(all_cs)})")
        tail = [e for e in evaluations if "HIGH_SCORE_TAIL_EXPOSED" in (e.get("risk_labels") or [])]
        lines.append(f"- High-score-tail exposed high-score miss rate: {_rate(tail, 'high_score_miss')}% (n={len(tail)})")
    else:
        lines.append("- No forward evaluated fixtures yet.")
    lines.extend(["", "## Abstention shadow (no production change)", ""])
    for row in abstention_rows:
        lines.append(
            f"- `{row['rule_id']}`: coverage {row['coverage_pct']}%, Top5 {row['top5_accuracy_pct']}% "
            f"(baseline {row['baseline_top5_accuracy_pct']}%), wrongly excluded hits {row['hits_wrongly_excluded']}"
        )
    lines.extend(["", "## Historical untouched-test proxy (not forward proof)", ""])
    for row in bucket_rows:
        if row.get("split") != "historical_untouched_test_proxy":
            continue
        if row.get("bucket_type") != "fragility_bucket":
            continue
        lines.append(
            f"- {row['bucket']}: n={row['fixture_count']}, Top5={row.get('top5_accuracy_pct')}%, "
            f"outside={row.get('outside_top5_rate_pct')}%"
        )
    lines.extend(
        [
            "",
            "## Thresholds (train+calibration locked)",
            "",
            f"- ESDI low/medium cut: {thresholds['esdi']['low_max']} / {thresholds['esdi']['medium_max']}",
            f"- Fragility quartiles: {thresholds['fragility']['low_max']} / {thresholds['fragility']['medium_max']} / {thresholds['fragility']['high_max']}",
            "",
            "*Canonical S4 unchanged. No S5. Shadow-only abstention simulation.*",
        ]
    )
    return "\n".join(lines)


def _report_fa(final_status: str, evaluations: list[dict[str, Any]], cohort_status: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# اعتبارسنجی رو به جلو ESDI / Fragility",
            "",
            f"**وضعیت نهایی:** `{final_status}`",
            f"**Selector قفل‌شده:** `S4` — بدون تغییر canonical Top5",
            f"**نسخه آستانه:** `{THRESHOLD_VERSION}`",
            "",
            f"- تعداد fixtureهای ارزیابی‌شده forward: **{cohort_status['forward_evaluated_count']}**",
            f"- هدف کوهورت A: {cohort_status['cohort_a_target']} (کامل: {'بله' if cohort_status['cohort_a_complete'] else 'خیر'})",
            f"- ردیف‌های metadata ریسک prematch: {cohort_status['frozen_metadata_count']}",
            "",
            "این فاز فقط شاخص‌های ریسک prematch را فریز و ارزیابی می‌کند؛ selector تولیدی تغییر نکرد.",
            "شبیه‌سازی NO_BET فقط shadow است.",
        ]
    )


def _rate(rows: list[dict[str, Any]], field: str, *, invert: bool = False) -> str:
    if not rows:
        return "n/a"
    if invert and field == "top5_hit":
        val = sum(1 for r in rows if r.get(field)) / len(rows)
    else:
        val = sum(1 for r in rows if r.get(field)) / len(rows)
    return f"{100.0 * val:.2f}"

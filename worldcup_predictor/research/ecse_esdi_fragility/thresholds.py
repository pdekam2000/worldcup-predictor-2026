"""Train/calibration-locked ESDI and Fragility bucket thresholds."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_esdi_fragility.metrics import esdi_metrics, ranks_to_rows

THRESHOLD_VERSION = "ecse-esdi-fragility-thresholds-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (len(ordered) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _historical_fixture_rows(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT d.registry_fixture_id, d.kickoff_utc, d.league, d.season,
               r.home_goals, r.away_goals
        FROM ecse_training_dataset d
        JOIN historical_fixture_results r ON r.registry_fixture_id = d.registry_fixture_id
        ORDER BY d.kickoff_utc, d.registry_fixture_id
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _load_distributions(con: sqlite3.Connection, fixture_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    chunk = 800
    for start in range(0, len(fixture_ids), chunk):
        part = fixture_ids[start : start + chunk]
        qmarks = ",".join("?" for _ in part)
        rows = con.execute(
            f"""
            SELECT registry_fixture_id, scoreline, rank, probability
            FROM ecse_score_distributions
            WHERE registry_fixture_id IN ({qmarks}) AND rank <= 10
            ORDER BY registry_fixture_id, rank
            """,
            part,
        ).fetchall()
        for r in rows:
            fid = int(r[0])
            out.setdefault(fid, []).append(
                {"scoreline": r[1], "rank": int(r[2]), "probability": float(r[3]), "score": r[1]}
            )
    return out


def _split_train_calib(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    n = len(rows)
    train_end = int(n * 0.7)
    calib_end = train_end + int(n * 0.15)
    return rows[:train_end], rows[train_end:calib_end]


def _collect_calibration_samples(
    rows: list[dict[str, Any]], dist_map: dict[int, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for meta in rows:
        fid = int(meta["registry_fixture_id"])
        dist = dist_map.get(fid) or []
        if len(dist) < 5:
            continue
        top5 = ranks_to_rows(dist, limit=5)
        m = esdi_metrics(top5)
        samples.append(
            {
                "registry_fixture_id": fid,
                "esdi_score": m["esdi_score"],
                "fragility_score": m["fragility_score"],
                "clean_sheet_concentration": m["clean_sheet_concentration"],
            }
        )
    return samples


def calibrate_thresholds(prod_conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _historical_fixture_rows(prod_conn)
    train_rows, calib_rows = _split_train_calib(rows)
    calib_ids = [int(r["registry_fixture_id"]) for r in train_rows + calib_rows]
    dist_map = _load_distributions(prod_conn, calib_ids)
    samples = _collect_calibration_samples(train_rows + calib_rows, dist_map)
    esdi_vals = [float(s["esdi_score"]) for s in samples]
    frag_vals = [float(s["fragility_score"]) for s in samples]
    cs_vals = [float(s["clean_sheet_concentration"]) for s in samples]
    thresholds = {
        "threshold_version": THRESHOLD_VERSION,
        "generated_at_utc": _utc_now(),
        "calibration_sample_count": len(samples),
        "train_count": len(train_rows),
        "calibration_count": len(calib_rows),
        "selector_locked": "S4",
        "esdi": {
            "low_max": round(_percentile(esdi_vals, 1 / 3), 3),
            "medium_max": round(_percentile(esdi_vals, 2 / 3), 3),
            "buckets": ["LOW_DIVERSITY", "MEDIUM_DIVERSITY", "HIGH_DIVERSITY"],
        },
        "fragility": {
            "low_max": round(_percentile(frag_vals, 0.25), 3),
            "medium_max": round(_percentile(frag_vals, 0.50), 3),
            "high_max": round(_percentile(frag_vals, 0.75), 3),
            "buckets": ["LOW_FRAGILITY", "MEDIUM_FRAGILITY", "HIGH_FRAGILITY", "EXTREME_FRAGILITY"],
        },
        "warnings": {
            "high_score_tail_min": 0.25,
            "all_clean_sheet_min": 0.95,
            "single_direction_min": 0.98,
            "draw_underrank_min": 0.5,
        },
        "clean_sheet_concentration_p75": round(_percentile(cs_vals, 0.75), 6),
    }
    return thresholds


def assign_buckets(record: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, str]:
    esdi = float(record.get("esdi_score") or 0.0)
    frag = float(record.get("fragility_score") or 0.0)
    e = thresholds["esdi"]
    f = thresholds["fragility"]
    if esdi <= float(e["low_max"]):
        esdi_bucket = "LOW_DIVERSITY"
    elif esdi <= float(e["medium_max"]):
        esdi_bucket = "MEDIUM_DIVERSITY"
    else:
        esdi_bucket = "HIGH_DIVERSITY"
    if frag <= float(f["low_max"]):
        frag_bucket = "LOW_FRAGILITY"
    elif frag <= float(f["medium_max"]):
        frag_bucket = "MEDIUM_FRAGILITY"
    elif frag <= float(f["high_max"]):
        frag_bucket = "HIGH_FRAGILITY"
    else:
        frag_bucket = "EXTREME_FRAGILITY"
    return {"esdi_bucket": esdi_bucket, "fragility_bucket": frag_bucket}


def write_threshold_artifact(path: Path, thresholds: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(thresholds, indent=2, ensure_ascii=False), encoding="utf-8")

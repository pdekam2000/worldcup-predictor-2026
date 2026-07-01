"""PHASE ECSE-X2-M5 — Shortlist enhancer research runner."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m2.prob_features import load_baseline_top_scores, load_fixture_records
from worldcup_predictor.research.ecse_x2_m3.scorer import build_lift_model
from worldcup_predictor.research.ecse_x2_m4.segment import classify_match_state
from worldcup_predictor.research.ecse_x2_m5.constants import (
    EQUATION_NAME,
    METHOD_VERSION,
    METHODS,
    NUM_TEMPORAL_FOLDS,
    PHASE,
    SHADOW_ARTIFACT,
    TRAIN_FRACTION,
    TOP_N_STORE,
)
from worldcup_predictor.research.ecse_x2_m5.metrics import (
    MethodMetrics,
    delta_vs_champion,
    hit_positions,
    segment_labels,
)
from worldcup_predictor.research.ecse_x2_m5.methods import score_all_methods
from worldcup_predictor.research.ecse_x2_m5.rejection import assess_method, recommend


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _temporal_folds(records: list[dict[str, Any]], k: int) -> list[tuple[list[dict], list[dict]]]:
    ordered = sorted(records, key=lambda r: (r.get("kickoff_unix") or 0, r["registry_fixture_id"]))
    n = len(ordered)
    size = max(1, n // k)
    folds: list[tuple[list[dict], list[dict]]] = []
    for i in range(k):
        start = i * size
        end = (i + 1) * size if i < k - 1 else n
        test = ordered[start:end]
        train = ordered[:start]
        if train and test:
            folds.append((train, test))
    return folds


def _filter_segment(rows: list[dict[str, Any]], segment: str) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        labels = segment_labels(r["probs"], home_prob=r["probs"].get("ft_home"))
        if segment in labels:
            out.append(r)
    return out


def _evaluate_methods(
    test_rows: list[dict[str, Any]],
    dist_map: dict[int, list[dict[str, Any]]],
    lift_model: dict[str, Any] | None,
) -> tuple[dict[str, MethodMetrics], dict[str, int]]:
    per_method: dict[str, MethodMetrics] = {m: MethodMetrics() for m in METHODS}
    leak_counts: dict[str, int] = defaultdict(int)

    for rec in test_rows:
        fid = int(rec["registry_fixture_id"])
        if fid not in dist_map:
            continue
        actual = rec["actual"]
        scored = score_all_methods(
            dist_rows=dist_map[fid],
            probs=rec["probs"],
            lift_model=lift_model,
            coverage=rec.get("feature_coverage_count"),
        )
        baseline_top = scored["outputs"]["champion"]
        for method in METHODS:
            method_top = scored["outputs"][method]
            per_method[method].add(actual=actual, method_top=method_top, baseline_top=baseline_top)
            if method != "champion" and method_top != baseline_top and not scored["algebra_ready"]:
                leak_counts[method] += 1

    return per_method, dict(leak_counts)


def _load_existing_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            keys.add(f"{row.get('fixture_id')}|{row.get('method_version')}")
        except json.JSONDecodeError:
            continue
    return keys


def run_shortlist_enhancer(
    conn: sqlite3.Connection,
    *,
    artifact_path: str | Path = SHADOW_ARTIFACT,
    write_shadow: bool = True,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "phase": PHASE,
        "method_version": METHOD_VERSION,
        "equation_name": EQUATION_NAME,
    }
    result["baseline_rows_before"] = baseline_table_row_count(conn)

    records = load_fixture_records(conn)
    dist_map = load_baseline_top_scores(conn, top_n=TOP_N_STORE)
    eligible = [
        r
        for r in records
        if int(r["registry_fixture_id"]) in dist_map
        and r["probs"].get("ft_home") is not None
    ]
    result["eligible_n"] = len(eligible)

    ordered = sorted(eligible, key=lambda r: (r.get("kickoff_unix") or 0, r["registry_fixture_id"]))
    cut = int(len(ordered) * TRAIN_FRACTION)
    train_main = ordered[:cut]
    test_main = ordered[cut:]
    result["test_n"] = len(test_main)
    lift_model = build_lift_model(train_main)

    folds = _temporal_folds(eligible, NUM_TEMPORAL_FOLDS)
    method_results: dict[str, Any] = {}

    overall_metrics, overall_leaks = _evaluate_methods(test_main, dist_map, lift_model)
    champion_overall = overall_metrics["champion"]

    for method in METHODS:
        fold_deltas: list[dict[str, Any]] = []
        fold_results: list[dict[str, Any]] = []
        for i, (train, test) in enumerate(folds, start=1):
            fold_model = build_lift_model(train)
            fm, _ = _evaluate_methods(test, dist_map, fold_model)
            fd = delta_vs_champion(fm["champion"], fm[method])
            fold_results.append({"fold": i, "test_n": fm[method].n, "delta": fd})
            if fd:
                fold_deltas.append({"fold": i, **fd})

        balanced_rows = [r for r in test_main if classify_match_state(r["probs"]) == "balanced"]
        bm, bl = _evaluate_methods(balanced_rows, dist_map, lift_model)
        balanced_delta = delta_vs_champion(bm["champion"], bm[method])
        balanced_delta["n"] = bm[method].n

        delta = delta_vs_champion(champion_overall, overall_metrics[method])
        ms = overall_metrics[method].summary()
        ms["delta"] = delta

        assessment = assess_method(
            method,
            delta=delta,
            fold_deltas=fold_deltas,
            balanced_delta=balanced_delta,
            volatility=float(ms.get("rank_volatility") or 0),
            leak_count=overall_leaks.get(method, 0),
            metrics_n=overall_metrics[method].n,
        )

        method_results[method] = {
            "overall": ms,
            "fold_results": fold_results,
            "balanced_control": balanced_delta,
            "assessment": assessment,
        }

    segment_results: dict[str, Any] = {}
    for segment in (
        "all_eligible",
        "home_ge_55",
        "home_ge_60",
        "home_favorite",
        "strong_home_favorite",
        "balanced_control",
    ):
        seg_rows = _filter_segment(test_main, segment)
        sm, _ = _evaluate_methods(seg_rows, dist_map, lift_model)
        champ = sm["champion"]
        segment_results[segment] = {
            "n": champ.n,
            "methods": {
                m: {"summary": sm[m].summary(), "delta": delta_vs_champion(champ, sm[m])}
                for m in METHODS
                if m != "champion"
            },
            "champion": champ.summary(),
        }

    coverage_rate = result["eligible_n"] / max(len(records), 1)
    result["segment_coverage_rate"] = round(
        sum(1 for r in eligible if r["probs"].get("ft_home")) / max(len(records), 1), 4
    )
    result["method_results"] = method_results
    result["segment_results"] = segment_results
    result["recommendation"] = recommend(
        method_results,
        eligible_n=result["eligible_n"],
        coverage_rate=coverage_rate,
    )

    artifact = Path(artifact_path)
    existing = _load_existing_keys(artifact) if write_shadow else set()
    shadow_lines: list[str] = []

    for rec in test_main:
        fid = int(rec["registry_fixture_id"])
        if fid not in dist_map:
            continue
        key = f"{fid}|{METHOD_VERSION}"
        scored = score_all_methods(
            dist_rows=dist_map[fid],
            probs=rec["probs"],
            lift_model=lift_model,
            coverage=rec.get("feature_coverage_count"),
        )
        actual = rec["actual"]
        labels = segment_labels(rec["probs"], home_prob=scored.get("home_prob"))
        hits = {m: hit_positions(scored["outputs"][m], actual) for m in METHODS}
        rejection_flags = {
            m: (method_results[m].get("assessment") or {}).get("reasons", [])
            for m in METHODS
            if m != "champion"
        }

        if write_shadow:
            if key in existing:
                result["shadow_rows_skipped"] = result.get("shadow_rows_skipped", 0) + 1
            else:
                row = {
                    "fixture_id": fid,
                    "kickoff_time": rec.get("kickoff_utc"),
                    "league": rec.get("league"),
                    "tournament": rec.get("league"),
                    "home_prob": scored.get("home_prob"),
                    "equation_name": EQUATION_NAME,
                    "equation_value": scored.get("equation_value"),
                    "baseline_top_10": scored["outputs"]["champion"],
                    "m3_full_reorder_top_10": scored["outputs"]["m3_full_reorder"],
                    "m4_weight_005_top_10": scored["outputs"]["m4_weight_005"],
                    "shortlist_enhancer_top_10": scored["outputs"]["shortlist_enhancer"],
                    "tie_breaker_top_10": scored["outputs"]["tie_breaker"],
                    "actual_score": actual,
                    "hit_positions": hits,
                    "segment_labels": labels,
                    "rejection_flags": rejection_flags,
                    "evaluation_status": "evaluated",
                    "method_version": METHOD_VERSION,
                    "created_at": _utc_now(),
                }
                shadow_lines.append(json.dumps(row, ensure_ascii=False))
                result["shadow_rows_written"] = result.get("shadow_rows_written", 0) + 1

    if write_shadow and shadow_lines:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        with artifact.open("a", encoding="utf-8") as handle:
            for line in shadow_lines:
                handle.write(line + "\n")

    return result

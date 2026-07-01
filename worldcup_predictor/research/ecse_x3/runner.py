"""PHASE ECSE-X3-A — Composite shadow research runner."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m2.prob_features import load_baseline_top_scores, load_fixture_records
from worldcup_predictor.research.ecse_x2_m4.segment import classify_match_state
from worldcup_predictor.research.ecse_x3.constants import (
    METHOD_VERSION,
    METHODS,
    NUM_TEMPORAL_FOLDS,
    PHASE,
    SHADOW_ARTIFACT,
    SUMMARY_ARTIFACT,
    TOP_N_STORE,
    TRAIN_FRACTION,
)
from worldcup_predictor.research.ecse_x3.mapping import score_all_methods
from worldcup_predictor.research.ecse_x3.metrics import MethodMetrics, delta_vs_champion, segment_labels
from worldcup_predictor.research.ecse_x3.rejection import assess_method, recommend
from worldcup_predictor.research.ecse_x3.signals import compute_composite_signals, signals_finite


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
        labels = segment_labels(
            r["probs"],
            home_prob=r["probs"].get("ft_home"),
            league=r.get("league"),
            coverage_count=r.get("feature_coverage_count"),
        )
        if segment in labels:
            out.append(r)
    return out


def _evaluate_methods(
    test_rows: list[dict[str, Any]],
    dist_map: dict[int, list[dict[str, Any]]],
) -> tuple[dict[str, MethodMetrics], dict[str, int], int]:
    per_method: dict[str, MethodMetrics] = {m: MethodMetrics() for m in METHODS}
    nan_counts: dict[str, int] = defaultdict(int)
    missing_odds = 0

    for rec in test_rows:
        fid = int(rec["registry_fixture_id"])
        if fid not in dist_map:
            continue
        actual = rec["actual"]
        scored = score_all_methods(
            dist_rows=dist_map[fid],
            probs=rec["probs"],
            raw_row=rec,
        )
        sig = compute_composite_signals(rec["probs"], raw_row=rec)
        if not signals_finite(sig):
            nan_counts["signals"] += 1
        if rec["probs"].get("ft_home") is None:
            missing_odds += 1

        baseline_top = scored["outputs"]["champion"]
        for method in METHODS:
            method_top = scored["outputs"][method]
            per_method[method].add(
                actual=actual,
                method_top=method_top,
                baseline_top=baseline_top,
                full_dist=dist_map[fid],
                signals_ok=bool(scored.get("signals_ok")),
                zz2_meta=scored.get("zz2_meta"),
            )

    return per_method, dict(nan_counts), missing_odds


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


def _coverage_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    with_home = sum(1 for r in records if r["probs"].get("ft_home") is not None)
    full_signals = 0
    zz2_count = 0
    missing_counter: Counter[str] = Counter()
    for r in records:
        sig = compute_composite_signals(r["probs"], raw_row=r)
        for f in sig.missing_fields:
            missing_counter[f] += 1
        if sig.signal_families_available >= 4:
            full_signals += 1
        if sig.zz2_flag:
            zz2_count += 1
    return {
        "total_fixtures": total,
        "ft_home_coverage_pct": round(100.0 * with_home / max(total, 1), 4),
        "full_signal_families_pct": round(100.0 * full_signals / max(total, 1), 4),
        "zz2_flag_rate_pct": round(100.0 * zz2_count / max(total, 1), 4),
        "missing_odds_rate_pct": round(100.0 * (total - with_home) / max(total, 1), 4),
        "missing_field_counts": dict(missing_counter),
    }


def run_composite_shadow(
    conn: sqlite3.Connection,
    *,
    artifact_path: str | Path = SHADOW_ARTIFACT,
    write_shadow: bool = True,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "phase": PHASE,
        "method_version": METHOD_VERSION,
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
    result["coverage"] = _coverage_stats(eligible)

    ordered = sorted(eligible, key=lambda r: (r.get("kickoff_unix") or 0, r["registry_fixture_id"]))
    cut = int(len(ordered) * TRAIN_FRACTION)
    test_main = ordered[cut:]
    result["test_n"] = len(test_main)

    folds = _temporal_folds(eligible, NUM_TEMPORAL_FOLDS)
    method_results: dict[str, Any] = {}

    overall_metrics, nan_counts, _ = _evaluate_methods(test_main, dist_map)
    champion_overall = overall_metrics["champion"]

    for method in METHODS:
        fold_deltas: list[dict[str, Any]] = []
        fold_results: list[dict[str, Any]] = []
        for i, (_, test) in enumerate(folds, start=1):
            fm, _, _ = _evaluate_methods(test, dist_map)
            fd = delta_vs_champion(fm["champion"], fm[method])
            fold_results.append({"fold": i, "test_n": fm[method].n, "delta": fd})
            if fd:
                fold_deltas.append({"fold": i, **fd})

        balanced_rows = [r for r in test_main if classify_match_state(r["probs"]) == "balanced"]
        bm, _, _ = _evaluate_methods(balanced_rows, dist_map)
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
            metrics_n=overall_metrics[method].n,
            nan_inf=nan_counts.get("signals", 0) > 0 and method != "champion",
        )

        method_results[method] = {
            "overall": ms,
            "fold_results": fold_results,
            "balanced_control": balanced_delta,
            "assessment": assessment,
        }

    segment_keys = (
        "all_eligible",
        "home_favorite",
        "away_favorite",
        "balanced_match",
        "home_ge_55",
        "home_ge_60",
        "draw_high",
        "btts_high",
        "under_25_high",
        "over_25_high",
        "world_cup_group",
        "odds_liquidity_high",
        "odds_liquidity_low",
    )
    segment_results: dict[str, Any] = {}
    for segment in segment_keys:
        seg_rows = _filter_segment(test_main, segment)
        if not seg_rows:
            continue
        sm, _, _ = _evaluate_methods(seg_rows, dist_map)
        champ = sm["champion"]
        segment_results[segment] = {
            "n": champ.n,
            "champion": champ.summary(),
            "methods": {
                m: {"summary": sm[m].summary(), "delta": delta_vs_champion(champ, sm[m])}
                for m in METHODS
                if m != "champion"
            },
        }

    cov = result["coverage"]
    result["method_results"] = method_results
    result["segment_results"] = segment_results
    result["recommendation"] = recommend(
        method_results,
        eligible_n=result["eligible_n"],
        coverage_rate=float(cov.get("ft_home_coverage_pct", 0)) / 100.0,
        missing_odds_rate=float(cov.get("missing_odds_rate_pct", 0)) / 100.0,
    )

    artifact = Path(artifact_path)
    existing = _load_existing_keys(artifact) if write_shadow else set()
    shadow_lines: list[str] = []
    examples_improved: list[dict[str, Any]] = []
    examples_worsened: list[dict[str, Any]] = []

    best_method = (result["recommendation"] or {}).get("best_method") or "composite_full"

    for rec in test_main:
        fid = int(rec["registry_fixture_id"])
        if fid not in dist_map:
            continue
        key = f"{fid}|{METHOD_VERSION}"
        scored = score_all_methods(dist_rows=dist_map[fid], probs=rec["probs"], raw_row=rec)
        actual = rec["actual"]
        labels = segment_labels(
            rec["probs"],
            home_prob=scored.get("home_prob"),
            league=rec.get("league"),
            coverage_count=rec.get("feature_coverage_count"),
        )
        hits = {
            m: {
                "actual_rank": next(
                    (int(r["rank"]) for r in scored["outputs"][m] if r["scoreline"] == actual),
                    None,
                )
            }
            for m in METHODS
        }
        rejection_flags = {
            m: (method_results[m].get("assessment") or {}).get("reasons", [])
            for m in METHODS
            if m != "champion"
        }

        challenger_top10 = {m: scored["outputs"][m] for m in METHODS if m != "champion"}
        br = hits["champion"]["actual_rank"]
        cr = hits.get(best_method, {}).get("actual_rank")
        if br and cr and cr < br and len(examples_improved) < 5:
            examples_improved.append(
                {
                    "fixture_id": fid,
                    "actual": actual,
                    "baseline_rank": br,
                    f"{best_method}_rank": cr,
                    "baseline_top1": scored["outputs"]["champion"][0]["scoreline"],
                    f"{best_method}_top1": scored["outputs"].get(best_method, [{}])[0].get("scoreline"),
                }
            )
        if br and cr and cr > br and len(examples_worsened) < 5:
            examples_worsened.append(
                {
                    "fixture_id": fid,
                    "actual": actual,
                    "baseline_rank": br,
                    f"{best_method}_rank": cr,
                }
            )

        if write_shadow and key not in existing:
            row = {
                "fixture_id": fid,
                "kickoff_time": rec.get("kickoff_utc"),
                "league": rec.get("league"),
                "tournament": rec.get("league"),
                "normalized_odds": scored.get("signals"),
                "computed_signals": {
                    k: scored["signals"].get(k)
                    for k in ("H", "I", "zz2_flag", "J2", "G", "ou_slope")
                },
                "missing_fields": scored["signals"].get("missing_fields"),
                "baseline_top10": scored["outputs"]["champion"],
                "challenger_top10": challenger_top10,
                "rank_movements": scored.get("rank_movements"),
                "segment_labels": labels,
                "actual_score": actual,
                "hit_ranks": hits,
                "zz2_research": scored.get("zz2_meta"),
                "rejection_flags": rejection_flags,
                "evaluation_status": "evaluated",
                "method_version": METHOD_VERSION,
                "created_at": _utc_now(),
            }
            shadow_lines.append(json.dumps(row, ensure_ascii=False))
            result["shadow_rows_written"] = result.get("shadow_rows_written", 0) + 1
        elif write_shadow:
            result["shadow_rows_skipped"] = result.get("shadow_rows_skipped", 0) + 1

    result["examples_improved"] = examples_improved
    result["examples_worsened"] = examples_worsened

    if write_shadow and shadow_lines:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        with artifact.open("a", encoding="utf-8") as handle:
            for line in shadow_lines:
                handle.write(line + "\n")

    return result

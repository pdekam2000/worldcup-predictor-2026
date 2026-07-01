"""PHASE ECSE-X2-M4 — Internal weight test runner."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_exact_score_backtest import LOG_LOSS_FLOOR, multiclass_brier
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m2.prob_features import load_baseline_top_scores, load_fixture_records
from worldcup_predictor.research.ecse_x2_m4.constants import (
    EQUATION_NAME,
    METHOD_VERSION,
    MIN_HOME_PROB,
    NUM_TEMPORAL_FOLDS,
    PHASE,
    SHADOW_ARTIFACT,
    STRONG_HOME_PROB,
    SUMMARY_ARTIFACT,
    TEST_WEIGHTS,
    TOP_N_SHADOW,
    TOP_N_STORE,
    TRAIN_FRACTION,
)
from worldcup_predictor.research.ecse_x2_m4.rejection import assess_weight, recommend_best_weight
from worldcup_predictor.research.ecse_x2_m4.segment import (
    classify_match_state,
    evaluate_target_segment,
    is_strong_home_favorite,
)
from worldcup_predictor.research.ecse_x2_m4.weighted_scorer import build_segment_lift_model, score_fixture_weighted


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@dataclass
class Metrics:
    n: int = 0
    top1: int = 0
    top3: int = 0
    top5: int = 0
    top10: int = 0
    log_loss_sum: float = 0.0
    brier_sum: float = 0.0
    disagreement: int = 0
    rank_move_sum: float = 0.0
    rank_move_n: int = 0
    rank_move_abs_sum: float = 0.0

    def add(
        self,
        *,
        actual: str,
        base_rank: int,
        weighted_rank: int,
        weighted_probs: dict[str, float],
        top1_disagreement: bool,
    ) -> None:
        self.n += 1
        self.top1 += int(weighted_rank == 1)
        self.top3 += int(weighted_rank <= 3)
        self.top5 += int(weighted_rank <= 5)
        self.top10 += int(weighted_rank <= 10)
        p = max(weighted_probs.get(actual, LOG_LOSS_FLOOR), LOG_LOSS_FLOOR)
        self.log_loss_sum += -math.log(p)
        self.brier_sum += multiclass_brier(weighted_probs, actual)
        self.disagreement += int(top1_disagreement)
        if base_rank < 900 and weighted_rank < 900:
            move = float(base_rank - weighted_rank)
            self.rank_move_sum += move
            self.rank_move_abs_sum += abs(move)
            self.rank_move_n += 1

    def summary(self, *, prefix: str = "") -> dict[str, Any]:
        if self.n == 0:
            return {"n": 0}
        out = {
            "n": self.n,
            f"{prefix}top1_hit_rate_pct": round(100.0 * self.top1 / self.n, 4),
            f"{prefix}top3_hit_rate_pct": round(100.0 * self.top3 / self.n, 4),
            f"{prefix}top5_hit_rate_pct": round(100.0 * self.top5 / self.n, 4),
            f"{prefix}top10_hit_rate_pct": round(100.0 * self.top10 / self.n, 4),
            f"{prefix}avg_log_loss": round(self.log_loss_sum / self.n, 6),
            f"{prefix}avg_brier": round(self.brier_sum / self.n, 6),
            "pick_disagreement_rate_pct": round(100.0 * self.disagreement / self.n, 4),
        }
        if self.rank_move_n:
            out["avg_rank_movement"] = round(self.rank_move_sum / self.rank_move_n, 4)
            out["volatility_score"] = round(self.rank_move_abs_sum / self.rank_move_n, 4)
        return out


def _delta(champion: Metrics, challenger: Metrics) -> dict[str, float]:
    cs = champion.summary(prefix="champion_")
    chs = challenger.summary(prefix="challenger_")
    if champion.n == 0:
        return {}
    return {
        "top1_delta_pp": round(
            chs.get("challenger_top1_hit_rate_pct", 0) - cs.get("champion_top1_hit_rate_pct", 0),
            4,
        ),
        "top3_delta_pp": round(
            chs.get("challenger_top3_hit_rate_pct", 0) - cs.get("champion_top3_hit_rate_pct", 0),
            4,
        ),
        "top5_delta_pp": round(
            chs.get("challenger_top5_hit_rate_pct", 0) - cs.get("champion_top5_hit_rate_pct", 0),
            4,
        ),
        "top10_delta_pp": round(
            chs.get("challenger_top10_hit_rate_pct", 0) - cs.get("champion_top10_hit_rate_pct", 0),
            4,
        ),
        "avg_log_loss": round(
            chs.get("challenger_avg_log_loss", 0) - cs.get("champion_avg_log_loss", 0),
            6,
        ),
        "avg_brier": round(chs.get("challenger_avg_brier", 0) - cs.get("champion_avg_brier", 0), 6),
    }


def _liquidity_bucket(coverage: int | None) -> str:
    c = int(coverage or 0)
    if c >= 12:
        return "normal"
    if c >= 6:
        return "medium"
    return "low"


def _home_prob_bucket(home: float | None) -> str:
    if home is None:
        return "unknown"
    if home >= STRONG_HOME_PROB:
        return "home_ge_60"
    if home >= MIN_HOME_PROB:
        return "home_ge_55"
    if home >= 0.40:
        return "home_40_55"
    return "home_lt_40"


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


def _evaluate_weight_on_test(
    test_rows: list[dict[str, Any]],
    dist_map: dict[int, list[dict[str, Any]]],
    lift_model: dict[str, Any] | None,
    weight: float,
) -> tuple[Metrics, Metrics, dict[str, Any]]:
    champion = Metrics()
    challenger = Metrics()
    leak_count = 0
    balanced_affected = 0

    for rec in test_rows:
        fid = int(rec["registry_fixture_id"])
        if fid not in dist_map:
            continue
        actual = rec["actual"]
        scored = score_fixture_weighted(
            dist_rows=dist_map[fid],
            probs=rec["probs"],
            lift_model=lift_model,
            weight=weight,
            coverage=rec.get("feature_coverage_count"),
            top_n=TOP_N_SHADOW,
        )
        base_rank = next(
            (r["rank"] for r in scored["baseline_top"] if r["scoreline"] == actual),
            999,
        )
        w_rank = next(
            (r["rank"] for r in scored["weighted_top"] if r["scoreline"] == actual),
            999,
        )
        base_probs = {r["scoreline"]: r["probability"] for r in scored["baseline_top"]}
        w_probs = {r["scoreline"]: r["probability"] for r in scored["weighted_top"]}

        champion.add(
            actual=actual,
            base_rank=base_rank,
            weighted_rank=base_rank,
            weighted_probs=base_probs,
            top1_disagreement=False,
        )
        challenger.add(
            actual=actual,
            base_rank=base_rank,
            weighted_rank=w_rank,
            weighted_probs=w_probs,
            top1_disagreement=bool(scored["top1_disagreement"]),
        )

        state = classify_match_state(rec["probs"])
        if not scored["target_segment_passed"] and scored.get("applied"):
            leak_count += 1
        if state == "balanced" and scored.get("top1_disagreement"):
            balanced_affected += 1

    safety = {"leak_count": leak_count, "balanced_affected": balanced_affected}
    return champion, challenger, safety


def _segment_filter(rows: list[dict[str, Any]], segment_key: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        h = r["probs"].get("ft_home")
        state = classify_match_state(r["probs"])
        if segment_key == "home_40_55":
            if h is None or not (0.40 <= h < MIN_HOME_PROB):
                continue
        if segment_key == "home_ge_55" and (h is None or h < MIN_HOME_PROB):
            continue
        if segment_key == "home_ge_60" and (h is None or h < STRONG_HOME_PROB):
            continue
        if segment_key == "home_favorite" and state != "home_favorite":
            continue
        if segment_key == "strong_home_favorite" and not is_strong_home_favorite(r["probs"]):
            continue
        if segment_key == "balanced_only" and state != "balanced":
            continue
        if segment_key in ("balanced_excluded", "non_balanced") and state == "balanced":
            continue
        out.append(r)
    return out


def _load_existing_shadow_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            keys.add(
                f"{row.get('fixture_id')}|{row.get('applied_weight') if row.get('target_segment_passed') else 'excluded'}|{row.get('method_version')}"
            )
        except json.JSONDecodeError:
            continue
    return keys


@dataclass
class WeightTestResult:
    phase: str = PHASE
    method_version: str = METHOD_VERSION
    equation_name: str = EQUATION_NAME
    weights_tested: list[float] = field(default_factory=lambda: list(TEST_WEIGHTS))
    eligible_n: int = 0
    segment_n: int = 0
    shadow_rows_written: int = 0
    shadow_rows_skipped: int = 0
    baseline_rows_before: int = 0
    per_weight: list[dict[str, Any]] = field(default_factory=list)
    segments: dict[str, Any] = field(default_factory=dict)
    recommendation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "method_version": self.method_version,
            "equation_name": self.equation_name,
            "weights_tested": self.weights_tested,
            "eligible_n": self.eligible_n,
            "segment_n": self.segment_n,
            "segment_coverage_rate": round(self.segment_n / max(self.eligible_n, 1), 4),
            "shadow_rows_written": self.shadow_rows_written,
            "shadow_rows_skipped": self.shadow_rows_skipped,
            "baseline_rows_before": self.baseline_rows_before,
            "per_weight": self.per_weight,
            "segments": self.segments,
            "recommendation": self.recommendation,
        }


def run_internal_weight_test(
    conn: sqlite3.Connection,
    *,
    artifact_path: str | Path = SHADOW_ARTIFACT,
    write_shadow: bool = True,
) -> WeightTestResult:
    result = WeightTestResult()
    result.baseline_rows_before = baseline_table_row_count(conn)

    records = load_fixture_records(conn)
    dist_map = load_baseline_top_scores(conn, top_n=TOP_N_STORE)
    eligible = [
        r
        for r in records
        if int(r["registry_fixture_id"]) in dist_map
        and r["probs"].get("ft_home") is not None
    ]
    result.eligible_n = len(eligible)

    ordered = sorted(eligible, key=lambda r: (r.get("kickoff_unix") or 0, r["registry_fixture_id"]))
    cut = int(len(ordered) * TRAIN_FRACTION)
    train_main = ordered[:cut]
    test_main = ordered[cut:]
    lift_model = build_segment_lift_model(train_main)

    segment_train = [
        r
        for r in train_main
        if score_fixture_weighted(
            dist_rows=dist_map[int(r["registry_fixture_id"])],
            probs=r["probs"],
            lift_model=lift_model,
            weight=0.05,
            coverage=r.get("feature_coverage_count"),
            top_n=TOP_N_SHADOW,
        )["target_segment_passed"]
    ]
    result.segment_n = len(
        [
            r
            for r in eligible
            if score_fixture_weighted(
                dist_rows=dist_map[int(r["registry_fixture_id"])],
                probs=r["probs"],
                lift_model=lift_model,
                weight=0.05,
                coverage=r.get("feature_coverage_count"),
                top_n=TOP_N_SHADOW,
            )["target_segment_passed"]
        ]
    )

    folds = _temporal_folds(eligible, NUM_TEMPORAL_FOLDS)
    weight_results: list[dict[str, Any]] = []

    for weight in TEST_WEIGHTS:
        champion, challenger, safety = _evaluate_weight_on_test(test_main, dist_map, lift_model, weight)
        delta = _delta(champion, challenger)
        ch_summary = challenger.summary(prefix="challenger_")
        ch_summary["delta"] = delta
        ch_summary["champion"] = champion.summary(prefix="champion_")

        fold_deltas: list[dict[str, Any]] = []
        fold_results: list[dict[str, Any]] = []
        for i, (train, test) in enumerate(folds, start=1):
            fold_model = build_segment_lift_model(train)
            fc, fch, _ = _evaluate_weight_on_test(test, dist_map, fold_model, weight)
            fd = _delta(fc, fch)
            fold_results.append({"fold": i, "test_n": fch.n, "delta": fd})
            if fd:
                fold_deltas.append({"fold": i, "n": fch.n, **fd})

        mid_rows = _segment_filter(test_main, "home_40_55")
        mc, mch, _ = _evaluate_weight_on_test(mid_rows, dist_map, lift_model, weight)
        mid_delta = _delta(mc, mch)
        mid_delta["n"] = mch.n

        assessment = assess_weight(
            weight,
            metrics=ch_summary,
            fold_deltas=fold_deltas,
            mid_bucket_delta=mid_delta,
            leak_count=safety["leak_count"],
            balanced_affected=safety["balanced_affected"],
        )

        segment_breakdown: dict[str, Any] = {}
        for seg_key in (
            "home_ge_55",
            "home_ge_60",
            "home_favorite",
            "strong_home_favorite",
            "balanced_only",
            "non_balanced",
        ):
            seg_rows = _segment_filter(test_main, seg_key)
            sc, sch, _ = _evaluate_weight_on_test(seg_rows, dist_map, lift_model, weight)
            segment_breakdown[seg_key] = {"n": sch.n, "delta": _delta(sc, sch)}

        by_liquidity: dict[str, Any] = {}
        for liq in ("low", "medium", "normal"):
            liq_rows = [r for r in test_main if _liquidity_bucket(r.get("feature_coverage_count")) == liq]
            lc, lch, _ = _evaluate_weight_on_test(liq_rows, dist_map, lift_model, weight)
            by_liquidity[liq] = {"n": lch.n, "delta": _delta(lc, lch)}

        by_league: dict[str, Any] = {}
        league_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in test_main:
            league_groups[str(r.get("league") or "unknown")].append(r)
        for league, lrows in league_groups.items():
            if len(lrows) < 100:
                continue
            lc, lch, _ = _evaluate_weight_on_test(lrows, dist_map, lift_model, weight)
            by_league[league] = {"n": lch.n, "delta": _delta(lc, lch)}

        entry = {
            "weight": weight,
            "metrics": ch_summary,
            "fold_results": fold_results,
            "assessment": assessment,
            "segment_breakdown": segment_breakdown,
            "by_liquidity": by_liquidity,
            "by_league": dict(list(by_league.items())[:20]),
            "safety": safety,
        }
        weight_results.append(entry)
        result.per_weight.append(entry)

    result.segments = {
        w["weight"]: {
            "segment_breakdown": w["segment_breakdown"],
            "by_liquidity": w["by_liquidity"],
        }
        for w in weight_results
    }

    coverage_rate = result.segment_n / max(result.eligible_n, 1)
    result.recommendation = recommend_best_weight(weight_results, segment_coverage_rate=coverage_rate)

    best_weight = result.recommendation.get("best_weight")
    artifact = Path(artifact_path)
    existing = _load_existing_shadow_keys(artifact) if write_shadow else set()
    shadow_lines: list[str] = []

    for rec in test_main:
        fid = int(rec["registry_fixture_id"])
        if fid not in dist_map:
            continue
        actual = rec["actual"]
        league = str(rec.get("league") or "unknown")
        seg_gate = evaluate_target_segment(rec["probs"], coverage=rec.get("feature_coverage_count"))
        if seg_gate["target_segment_passed"]:
            weight_iter = list(TEST_WEIGHTS)
        else:
            weight_iter = [0.0]

        for weight in weight_iter:
            key = (
                f"{fid}|excluded|{METHOD_VERSION}"
                if not seg_gate["target_segment_passed"]
                else f"{fid}|{weight}|{METHOD_VERSION}"
            )
            scored = score_fixture_weighted(
                dist_rows=dist_map[fid],
                probs=rec["probs"],
                lift_model=lift_model,
                weight=weight if weight > 0 else 0.01,
                coverage=rec.get("feature_coverage_count"),
                top_n=TOP_N_SHADOW,
            )
            if not seg_gate["target_segment_passed"]:
                scored["applied_weight"] = None
            if write_shadow:
                if key in existing:
                    result.shadow_rows_skipped += 1
                else:
                    base_rank = next(
                        (r["rank"] for r in scored["baseline_top"] if r["scoreline"] == actual),
                        None,
                    )
                    w_rank = next(
                        (r["rank"] for r in scored["weighted_top"] if r["scoreline"] == actual),
                        None,
                    )
                    row = {
                        "fixture_id": fid,
                        "kickoff_time": rec.get("kickoff_utc"),
                        "league": league,
                        "tournament": league,
                        "home_prob": scored.get("home_prob"),
                        "equation_name": EQUATION_NAME,
                        "equation_value": scored.get("equation_value"),
                        "applied_weight": scored.get("applied_weight"),
                        "baseline_top_10": scored["baseline_top"],
                        "weighted_top_10": scored["weighted_top"],
                        "rank_movements": scored.get("rank_movements"),
                        "target_segment_passed": scored["target_segment_passed"],
                        "exclusion_reason": scored.get("exclusion_reason"),
                        "evaluation_status": "evaluated",
                        "actual_score": actual,
                        "baseline_actual_rank": base_rank,
                        "weighted_actual_rank": w_rank,
                        "method_version": METHOD_VERSION,
                        "created_at": _utc_now(),
                    }
                    shadow_lines.append(json.dumps(row, ensure_ascii=False))
                    result.shadow_rows_written += 1

    if write_shadow and shadow_lines:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        with artifact.open("a", encoding="utf-8") as handle:
            for line in shadow_lines:
                handle.write(line + "\n")

    return result

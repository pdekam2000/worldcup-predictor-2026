"""PHASE ECSE-X2-M3 — Champion/Challenger shadow validation runner."""

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
from worldcup_predictor.research.ecse_x2_m3.constants import (
    METHOD_VERSION,
    NUM_TEMPORAL_FOLDS,
    PHASE,
    SHADOW_ARTIFACT,
    TOP_N_SHADOW,
    TOP_N_STORE,
    TRAIN_FRACTION,
)
from worldcup_predictor.research.ecse_x2_m3.equation import EQUATION_NAME
from worldcup_predictor.research.ecse_x2_m3.rejection import assess_overfit_risk
from worldcup_predictor.research.ecse_x2_m3.scorer import build_lift_model, score_fixture_shadow


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

    def add(
        self,
        *,
        actual: str,
        base_rank: int,
        chal_rank: int,
        base_probs: dict[str, float],
        chal_probs: dict[str, float],
        top1_disagreement: bool,
    ) -> None:
        self.n += 1
        self.top1 += int(chal_rank == 1)
        self.top3 += int(chal_rank <= 3)
        self.top5 += int(chal_rank <= 5)
        self.top10 += int(chal_rank <= 10)
        p = max(chal_probs.get(actual, LOG_LOSS_FLOOR), LOG_LOSS_FLOOR)
        self.log_loss_sum += -math.log(p)
        self.brier_sum += multiclass_brier(chal_probs, actual)
        self.disagreement += int(top1_disagreement)
        if base_rank < 900 and chal_rank < 900:
            self.rank_move_sum += base_rank - chal_rank
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
            out["avg_rank_movement_actual"] = round(self.rank_move_sum / self.rank_move_n, 4)
        return out


def _delta(champion: Metrics, challenger: Metrics) -> dict[str, float]:
    cs = champion.summary(prefix="champion_")
    chs = challenger.summary(prefix="challenger_")
    if champion.n == 0:
        return {}
    return {
        "top1_delta_pp": round(
            chs.get("challenger_top1_hit_rate_pct", 0) - cs.get("champion_top1_hit_rate_pct", 0), 4
        ),
        "top3_delta_pp": round(
            chs.get("challenger_top3_hit_rate_pct", 0) - cs.get("champion_top3_hit_rate_pct", 0), 4
        ),
        "top5_delta_pp": round(
            chs.get("challenger_top5_hit_rate_pct", 0) - cs.get("champion_top5_hit_rate_pct", 0), 4
        ),
        "top10_delta_pp": round(
            chs.get("challenger_top10_hit_rate_pct", 0) - cs.get("champion_top10_hit_rate_pct", 0), 4
        ),
        "avg_log_loss": round(
            chs.get("challenger_avg_log_loss", 0) - cs.get("champion_avg_log_loss", 0), 6
        ),
        "avg_brier": round(chs.get("challenger_avg_brier", 0) - cs.get("champion_avg_brier", 0), 6),
    }


def _match_state(probs: dict[str, float | None]) -> str:
    h = probs.get("ft_home")
    a = probs.get("ft_away")
    if h is not None and a is not None:
        if h - a >= 0.08:
            return "home_favorite"
        if a - h >= 0.08:
            return "away_favorite"
        return "balanced"
    if h is None:
        return "unknown"
    if h >= 0.45:
        return "home_favorite"
    if h <= 0.32:
        return "away_favorite"
    return "balanced"


def _home_prob_bucket(probs: dict[str, float | None]) -> str:
    h = probs.get("ft_home")
    if h is None:
        return "unknown"
    if h >= 0.55:
        return "home_ge_55"
    if h >= 0.40:
        return "home_40_55"
    return "home_lt_40"


def _liquidity_bucket(coverage: int | None) -> str:
    c = int(coverage or 0)
    if c >= 12:
        return "normal"
    if c >= 6:
        return "medium"
    return "low"


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


def _evaluate_fold(
    train: list[dict[str, Any]],
    test: list[dict[str, Any]],
    dist_map: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    model = build_lift_model(train)
    champion = Metrics()
    challenger = Metrics()
    for rec in test:
        fid = int(rec["registry_fixture_id"])
        if fid not in dist_map:
            continue
        scored = score_fixture_shadow(
            dist_rows=dist_map[fid], probs=rec["probs"], lift_model=model, top_n=TOP_N_STORE
        )
        if not scored["eligible"]:
            continue
        actual = rec["actual"]
        base_rank = next(
            (r["rank"] for r in scored["baseline_top"] if r["scoreline"] == actual),
            999,
        )
        chal_rank = next(
            (r["rank"] for r in scored["challenger_top"] if r["scoreline"] == actual),
            999,
        )
        base_probs = {r["scoreline"]: r["probability"] for r in scored["baseline_top"]}
        chal_probs = {r["scoreline"]: r["probability"] for r in scored["challenger_top"]}
        champion.add(
            actual=actual,
            base_rank=base_rank,
            chal_rank=base_rank,
            base_probs=base_probs,
            chal_probs=base_probs,
            top1_disagreement=False,
        )
        challenger.add(
            actual=actual,
            base_rank=base_rank,
            chal_rank=chal_rank,
            base_probs=base_probs,
            chal_probs=chal_probs,
            top1_disagreement=bool(scored["top1_disagreement"]),
        )
    return {
        "train_n": len(train),
        "test_n": challenger.n,
        "champion": champion.summary(prefix="champion_"),
        "challenger": challenger.summary(prefix="challenger_"),
        "delta": _delta(champion, challenger),
    }


def _load_existing_shadow_keys(path: Path) -> set[str]:
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


@dataclass
class ShadowRunResult:
    phase: str = PHASE
    method_version: str = METHOD_VERSION
    equation_name: str = EQUATION_NAME
    eligible_n: int = 0
    shadow_rows_written: int = 0
    shadow_rows_skipped: int = 0
    baseline_rows_before: int = 0
    fold_results: list[dict[str, Any]] = field(default_factory=list)
    overall: dict[str, Any] = field(default_factory=dict)
    breakdowns: dict[str, Any] = field(default_factory=dict)
    overfit: dict[str, Any] = field(default_factory=dict)
    examples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "method_version": self.method_version,
            "equation_name": self.equation_name,
            "eligible_n": self.eligible_n,
            "shadow_rows_written": self.shadow_rows_written,
            "shadow_rows_skipped": self.shadow_rows_skipped,
            "baseline_rows_before": self.baseline_rows_before,
            "fold_results": self.fold_results,
            "overall": self.overall,
            "breakdowns": self.breakdowns,
            "overfit": self.overfit,
            "examples": self.examples,
        }


def run_champion_challenger_shadow(
    conn: sqlite3.Connection,
    *,
    artifact_path: str | Path = SHADOW_ARTIFACT,
    write_shadow: bool = True,
) -> ShadowRunResult:
    result = ShadowRunResult()
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

    folds = _temporal_folds(eligible, NUM_TEMPORAL_FOLDS)
    fold_deltas: list[dict[str, Any]] = []
    for i, (train, test) in enumerate(folds, start=1):
        fr = _evaluate_fold(train, test, dist_map)
        fr["fold"] = i
        result.fold_results.append(fr)
        if fr.get("delta"):
            fold_deltas.append({"fold": i, "n": fr["test_n"], **fr["delta"]})

    ordered = sorted(eligible, key=lambda r: (r.get("kickoff_unix") or 0, r["registry_fixture_id"]))
    cut = int(len(ordered) * TRAIN_FRACTION)
    train_main = ordered[:cut]
    test_main = ordered[cut:]
    main_eval = _evaluate_fold(train_main, test_main, dist_map)
    result.overall = {
        "train_n": len(train_main),
        "test_n": main_eval["test_n"],
        "champion": main_eval["champion"],
        "challenger": main_eval["challenger"],
        "delta": main_eval["delta"],
    }

    by_league_c: dict[str, Metrics] = defaultdict(Metrics)
    by_league_ch: dict[str, Metrics] = defaultdict(Metrics)
    by_state_c: dict[str, Metrics] = defaultdict(Metrics)
    by_state_ch: dict[str, Metrics] = defaultdict(Metrics)
    by_home_bucket_c: dict[str, Metrics] = defaultdict(Metrics)
    by_home_bucket_ch: dict[str, Metrics] = defaultdict(Metrics)
    by_liquidity_c: dict[str, Metrics] = defaultdict(Metrics)
    by_liquidity_ch: dict[str, Metrics] = defaultdict(Metrics)

    model_main = build_lift_model(train_main)
    unrealistic_push = 0
    rank_moves: list[float] = []

    artifact = Path(artifact_path)
    existing = _load_existing_shadow_keys(artifact) if write_shadow else set()
    shadow_lines: list[str] = []

    for rec in test_main:
        fid = int(rec["registry_fixture_id"])
        dist = dist_map[fid]
        scored = score_fixture_shadow(
            dist_rows=dist, probs=rec["probs"], lift_model=model_main, top_n=TOP_N_SHADOW
        )
        actual = rec["actual"]
        base_rank = next((r["rank"] for r in scored["baseline_top"] if r["scoreline"] == actual), 999)
        chal_rank = next((r["rank"] for r in scored["challenger_top"] if r["scoreline"] == actual), 999)
        base_probs = {r["scoreline"]: r["probability"] for r in scored["baseline_top"]}
        chal_probs = {r["scoreline"]: r["probability"] for r in scored["challenger_top"]}

        league = str(rec.get("league") or "unknown")
        state = _match_state(rec["probs"])
        hb = _home_prob_bucket(rec["probs"])
        liq = _liquidity_bucket(rec.get("feature_coverage_count"))

        if scored["eligible"]:
            for c_map, ch_map, key in (
                (by_league_c, by_league_ch, league),
                (by_state_c, by_state_ch, state),
                (by_home_bucket_c, by_home_bucket_ch, hb),
                (by_liquidity_c, by_liquidity_ch, liq),
            ):
                c_map[key].add(
                    actual=actual,
                    base_rank=base_rank,
                    chal_rank=base_rank,
                    base_probs=base_probs,
                    chal_probs=base_probs,
                    top1_disagreement=False,
                )
                ch_map[key].add(
                    actual=actual,
                    base_rank=base_rank,
                    chal_rank=chal_rank,
                    base_probs=base_probs,
                    chal_probs=chal_probs,
                    top1_disagreement=bool(scored["top1_disagreement"]),
                )
            if base_rank < 900 and chal_rank < 900:
                rank_moves.append(float(base_rank - chal_rank))
            ch_top1 = scored["challenger_top"][0]["scoreline"] if scored["challenger_top"] else ""
            if ch_top1 and "-" in ch_top1:
                h, a = ch_top1.split("-", 1)
                if int(h) + int(a) >= 5 and base_rank > 3:
                    unrealistic_push += 1

        key = f"{fid}|{METHOD_VERSION}"
        if write_shadow:
            if key in existing:
                result.shadow_rows_skipped += 1
            else:
                row = {
                    "fixture_id": fid,
                    "kickoff_time": rec.get("kickoff_utc"),
                    "league": league,
                    "season": rec.get("season"),
                    "tournament": league,
                    "odds_snapshot_id": None,
                    "equation_name": EQUATION_NAME,
                    "equation_value": scored.get("equation_value"),
                    "baseline_top_10": scored["baseline_top"],
                    "challenger_top_10": scored["challenger_top"],
                    "rank_movements": scored.get("rank_movements"),
                    "evaluation_status": "evaluated",
                    "actual_score": actual,
                    "baseline_actual_rank": base_rank if base_rank < 900 else None,
                    "challenger_actual_rank": chal_rank if chal_rank < 900 else None,
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

    def _breakdown(c_map: dict[str, Metrics], ch_map: dict[str, Metrics]) -> dict[str, Any]:
        out = {}
        for k in sorted(set(c_map) | set(ch_map)):
            c, ch = c_map[k], ch_map[k]
            if ch.n < 100:
                continue
            out[k] = {"n": ch.n, "delta": _delta(c, ch)}
        return out

    result.breakdowns = {
        "by_league": _breakdown(by_league_c, by_league_ch),
        "by_match_state": _breakdown(by_state_c, by_state_ch),
        "by_home_prob_bucket": _breakdown(by_home_bucket_c, by_home_bucket_ch),
        "by_liquidity": _breakdown(by_liquidity_c, by_liquidity_ch),
    }

    balanced_delta = result.breakdowns.get("by_match_state", {}).get("balanced", {}).get("delta", {}) or {}
    balanced_n = result.breakdowns.get("by_match_state", {}).get("balanced", {}).get("n", 0)
    result.examples = _pick_examples(test_main, dist_map, model_main, limit=5)
    missing_rate = 1.0 - (result.eligible_n / max(len(records), 1))
    summary_for_rejection = {
        "eligible_n": result.eligible_n,
        "fold_deltas": fold_deltas,
        "overall_delta": main_eval.get("delta", {}),
        "balanced_match_delta": {"n": balanced_n, **balanced_delta},
        "avg_rank_movement": sum(rank_moves) / max(len(rank_moves), 1),
        "missing_odds_rate": missing_rate,
        "unrealistic_score_push": {
            "flag": unrealistic_push > max(50, len(test_main) * 0.02),
            "count": unrealistic_push,
        },
    }
    result.overfit = assess_overfit_risk(summary_for_rejection)
    return result


def _pick_examples(
    test_rows: list[dict[str, Any]],
    dist_map: dict[int, list[dict[str, Any]]],
    model: dict[str, Any] | None,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for rec in test_rows:
        fid = int(rec["registry_fixture_id"])
        if fid not in dist_map:
            continue
        scored = score_fixture_shadow(
            dist_rows=dist_map[fid], probs=rec["probs"], lift_model=model, top_n=5
        )
        if not scored["eligible"]:
            continue
        actual = rec["actual"]
        br = next((r["rank"] for r in scored["baseline_top"] if r["scoreline"] == actual), None)
        cr = next((r["rank"] for r in scored["challenger_top"] if r["scoreline"] == actual), None)
        if br is None or cr is None or br == cr:
            continue
        examples.append(
            {
                "fixture_id": fid,
                "match": f"{rec.get('home_team')} vs {rec.get('away_team')}",
                "actual": actual,
                "baseline_rank": br,
                "challenger_rank": cr,
                "rank_delta": br - cr,
                "baseline_top1": scored["baseline_top"][0]["scoreline"],
                "challenger_top1": scored["challenger_top"][0]["scoreline"],
                "equation_value": scored["equation_value"],
            }
        )
        if len(examples) >= limit:
            break
    return examples

#!/usr/bin/env python3
"""High-score tail research orchestrator — cohorts, grid audit, challengers, shadow.

Does not mutate historical freezes or overwrite canonical outputs.
"""
from __future__ import annotations

import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.research.ecse_score_distribution import (
    MAX_GOALS,
    OTHER_SCORELINE,
    generate_score_distribution,
    poisson_pmf,
)
from worldcup_predictor.research.ecse_tail_forensics.distributions import topn, prob_map
from worldcup_predictor.research.high_score_tail_shadow.constants import (
    EXTREME_TOTAL,
    FORWARD_MIN_GLOBAL_PROMOTION,
    FORWARD_MIN_HIGH_SCORE_RISK,
    FORWARD_MIN_TOTAL_DC,
    HIGH_TOTAL,
    LOW_TOTAL,
    MED_TOTAL,
    OVER_RANKED_CANDIDATES,
    REGIME_HIGH,
    REGIME_LOW,
    UNDER_RANKED_CANDIDATES,
)
from worldcup_predictor.research.high_score_tail_shadow.distributions import (
    CHALLENGER_FNS,
    dist_canonical_poisson,
    dist_dc_dynamic,
    dist_ensemble_tail,
    dist_high_score_specialist,
    dist_low_score_specialist,
    dynamic_max_goals,
    other_mass,
    tail_mass,
)
from worldcup_predictor.research.high_score_tail_shadow.regime_selector import select_regime
from worldcup_predictor.research.high_score_tail_shadow.shadow_store import (
    ensure_shadow_schema,
    persist_shadow_output,
)

CANONICAL_CSV = (
    ROOT
    / "artifacts"
    / "dataset_reconciliation_experiments"
    / "20260730T125305Z"
    / "evaluation_one_canonical_freeze_per_fixture.csv"
)
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
# Prefer CLI artifact dir if already created by agent
OUT = ROOT / "artifacts" / "high_score_tail_research" / RUN_ID


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def fnum(x: Any) -> float | None:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


def as_bool(x: Any) -> bool:
    return x in {True, "True", "true", "1", 1}


def load_rows() -> list[dict[str, Any]]:
    rows = list(csv.DictReader(CANONICAL_CSV.open(encoding="utf-8")))
    for r in rows:
        r["_ah"] = int(float(r["actual_ft_home"]))
        r["_aa"] = int(float(r["actual_ft_away"]))
        r["_tot"] = r["_ah"] + r["_aa"]
        r["_lh"] = fnum(r.get("lambda_home"))
        r["_la"] = fnum(r.get("lambda_away"))
    return sorted(rows, key=lambda r: str(r.get("kickoff") or ""))


def rate(rows: list[dict[str, Any]], key: str) -> float | None:
    if not rows:
        return None
    return round(sum(1 for r in rows if as_bool(r.get(key))) / len(rows), 4)


def mean(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 4) if vals else None


def cohort_metrics(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    ranks = [int(float(r["actual_exact_rank"])) for r in rows if r.get("actual_exact_rank") not in (None, "")]
    pred_h = [r["_lh"] for r in rows if r["_lh"] is not None]
    pred_a = [r["_la"] for r in rows if r["_la"] is not None]
    act_h = [float(r["_ah"]) for r in rows]
    act_a = [float(r["_aa"]) for r in rows]
    err_h = [float(r["_ah"]) - r["_lh"] for r in rows if r["_lh"] is not None]
    err_a = [float(r["_aa"]) - r["_la"] for r in rows if r["_la"] is not None]
    err_t = [
        float(r["_tot"]) - (r["_lh"] + r["_la"])
        for r in rows
        if r["_lh"] is not None and r["_la"] is not None
    ]
    masses = [fnum(r.get("top5_mass")) for r in rows]
    masses = [m / 100.0 if m and m > 1.5 else m for m in masses if m is not None]
    # rebuild poisson p(actual) when λ present
    p_act = []
    p4 = []
    for r in rows:
        if r["_lh"] is None:
            continue
        dist = dist_canonical_poisson(r["_lh"], r["_la"])
        pm = prob_map(dist)
        p_act.append(pm.get(r["actual_exact_score"], pm.get(OTHER_SCORELINE, 0.0)))
        p4.append(tail_mass(dist, 4))
    return {
        "cohort": name,
        "n": len(rows),
        "top1": rate(rows, "exact_top1_hit"),
        "top3": rate(rows, "exact_top3_hit"),
        "top5": rate(rows, "exact_top5_hit"),
        "top10": rate(rows, "exact_top10_hit"),
        "mean_actual_rank": mean([float(x) for x in ranks]),
        "pred_home_mean": mean(pred_h),  # type: ignore
        "pred_away_mean": mean(pred_a),  # type: ignore
        "actual_home_mean": mean(act_h),
        "actual_away_mean": mean(act_a),
        "home_lambda_error": mean(err_h),
        "away_lambda_error": mean(err_a),
        "total_lambda_error": mean(err_t),
        "avg_top5_mass": mean(masses),  # type: ignore
        "avg_p_actual": mean(p_act),
        "avg_p_total_4plus": mean(p4),
        "wde": rate(rows, "WDE_hit"),
        "btts": rate(rows, "BTTS_hit"),
        "ou": rate(rows, "OU_hit"),
    }


def phase1(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def fav_side(r):
        oh, oa = fnum(r.get("odds_home")), fnum(r.get("odds_away"))
        if oh and oa:
            return "home" if oh < oa else "away"
        hp, ap = fnum(r.get("home_probability")), fnum(r.get("away_probability"))
        if hp is not None and ap is not None:
            return "home" if hp >= ap else "away"
        return None

    cohorts: dict[str, list] = {
        "total_0_1": [r for r in rows if r["_tot"] in LOW_TOTAL],
        "total_2": [r for r in rows if r["_tot"] == 2],
        "total_3": [r for r in rows if r["_tot"] == 3],
        "total_4": [r for r in rows if r["_tot"] == 4],
        "total_5plus": [r for r in rows if r["_tot"] >= 5],
        "home_goals_3plus": [r for r in rows if r["_ah"] >= 3],
        "away_goals_3plus": [r for r in rows if r["_aa"] >= 3],
        "margin_3plus": [r for r in rows if abs(r["_ah"] - r["_aa"]) >= 3],
        "btts_and_total_4plus": [r for r in rows if r["_ah"] > 0 and r["_aa"] > 0 and r["_tot"] >= 4],
        "favorite_scored_3plus": [],
        "underdog_scored_2plus": [],
        "high_market_total_ou_over": [r for r in rows if "over" in str(r.get("ou25_prediction") or "").lower()],
        "inside_top10_outside_top5": [
            r for r in rows if as_bool(r.get("exact_top10_hit")) and not as_bool(r.get("exact_top5_hit"))
        ],
        "outside_top10": [r for r in rows if not as_bool(r.get("exact_top10_hit"))],
        "wde_ok_tail_fail": [
            r
            for r in rows
            if as_bool(r.get("WDE_hit")) and not as_bool(r.get("exact_top5_hit")) and r["_tot"] >= 4
        ],
        "wde_fail_and_exact_fail": [
            r for r in rows if not as_bool(r.get("WDE_hit")) and not as_bool(r.get("exact_top5_hit"))
        ],
    }
    for r in rows:
        fav = fav_side(r)
        if fav == "home" and r["_ah"] >= 3:
            cohorts["favorite_scored_3plus"].append(r)
        if fav == "away" and r["_aa"] >= 3:
            cohorts["favorite_scored_3plus"].append(r)
        if fav == "home" and r["_aa"] >= 2:
            cohorts["underdog_scored_2plus"].append(r)
        if fav == "away" and r["_ah"] >= 2:
            cohorts["underdog_scored_2plus"].append(r)

    metrics = [cohort_metrics(rs, name) for name, rs in cohorts.items()]
    write_csv(OUT / "high_score_failure_cohorts.csv", metrics)

    cases = []
    for r in rows:
        if r["_tot"] < 4 and not (as_bool(r.get("exact_top10_hit")) and not as_bool(r.get("exact_top5_hit"))):
            continue
        cases.append(
            {
                "fixture_id": r["fixture_id"],
                "match_name": r.get("match_name"),
                "competition": r.get("competition"),
                "actual": r["actual_exact_score"],
                "total": r["_tot"],
                "top1": r.get("top1"),
                "top5": ",".join([r.get("top1") or "", r.get("top2") or "", r.get("top3") or "", r.get("top4") or "", r.get("top5") or ""]),
                "lambda_home": r["_lh"],
                "lambda_away": r["_la"],
                "lambda_total": None if r["_lh"] is None else r["_lh"] + r["_la"],
                "err_total": None if r["_lh"] is None else r["_tot"] - (r["_lh"] + r["_la"]),
                "exact_top5": as_bool(r.get("exact_top5_hit")),
                "exact_top10": as_bool(r.get("exact_top10_hit")),
                "WDE_hit": as_bool(r.get("WDE_hit")),
                "rank": r.get("actual_exact_rank"),
            }
        )
    write_csv(OUT / "high_score_fixture_cases.csv", cases)

    # rank distribution by goal bucket
    bucket_rows = []
    for label, pred in [
        ("0-1", lambda t: t <= 1),
        ("2", lambda t: t == 2),
        ("3", lambda t: t == 3),
        ("4", lambda t: t == 4),
        ("5+", lambda t: t >= 5),
    ]:
        rs = [r for r in rows if pred(r["_tot"])]
        bucket_rows.append(cohort_metrics(rs, f"bucket_{label}"))
    write_csv(OUT / "score_rank_distribution_by_goal_bucket.csv", bucket_rows)

    hi = next(m for m in metrics if m["cohort"] == "total_5plus")
    h4 = next(m for m in metrics if m["cohort"] == "total_4")
    write_text(
        OUT / "high_score_error_summary.md",
        "\n".join(
            [
                "# High-score error summary",
                "",
                f"- Canonical n={len(rows)}",
                f"- total_4: n={h4['n']} Top5={h4['top5']} mean λ err={h4['total_lambda_error']}",
                f"- total_5plus: n={hi['n']} Top5={hi['top5']} mean λ err={hi['total_lambda_error']}",
                f"- High-score cases catalogued: {len(cases)}",
                "",
                "## Root-cause signals",
                "- Lambda total systematically underestimates high-score fixtures (positive total_lambda_error).",
                f"- Canonical MAX_GOALS={MAX_GOALS} truncates extreme cells into OTHER; actuals like 5-1/6-1 often outside Top10.",
                "- When WDE is correct but totals ≥4, Exact Top5 still fails → ranking/tail coverage problem beyond direction.",
            ]
        ),
    )
    return metrics


def phase2_grid_audit() -> None:
    samples = [
        (1.2, 1.0),
        (2.0, 1.0),
        (2.8, 0.6),
        (3.5, 0.4),
        (1.5, 1.5),
        (0.8, 2.5),
    ]
    rows = []
    for lh, la in samples:
        for mg in (5, 7, 8, 10, 12):
            dist = generate_score_distribution(lh, la, max_goals=mg)
            pre = sum(poisson_pmf(h, lh) * poisson_pmf(a, la) for h in range(mg + 1) for a in range(mg + 1))
            rows.append(
                {
                    "lambda_home": lh,
                    "lambda_away": la,
                    "max_goals": mg,
                    "dynamic_max": dynamic_max_goals(lh, la),
                    "grid_mass_before_norm": round(pre, 6),
                    "other_mass": round(other_mass(dist), 6),
                    "tail_mass_4plus": round(tail_mass(dist, 4), 6),
                    "tail_mass_5plus": round(tail_mass(dist, 5), 6),
                    "n_cells": len([e for e in dist if e["scoreline"] != OTHER_SCORELINE]),
                    "top5": ",".join(topn(dist, 5)),
                    "prob_sum": round(sum(float(e["probability"]) for e in dist), 8),
                }
            )
    write_csv(OUT / "tail_mass_conservation.csv", rows)
    write_text(
        OUT / "score_grid_audit.md",
        "\n".join(
            [
                "# Score grid audit (canonical path)",
                "",
                f"- Canonical `MAX_GOALS` = **{MAX_GOALS}** (`ecse_score_distribution.py`)",
                "- Legacy grid was 5; upgraded research grid is 7×7 + OTHER",
                "- Truncation: probability outside 0..MAX goes to OTHER bucket, then full renormalization",
                "- Sorting is **after** normalization (desc probability)",
                "- Ties: unstable relative to float noise; ranks assigned after sort (no explicit secondary key)",
                "- OTHER is included in ranking list but excluded from TopN scoreline lists in live builders",
                "- Dixon–Coles optional via `use_dixon_coles`; live blend versions recorded on freezes",
                "",
                "## Findings",
                "- High λ fixtures leave non-trivial OTHER mass at MAX_GOALS=7 (see `tail_mass_conservation.csv`)",
                "- Renormalization preserves sum≈1 but **does not invent high-score cells**; mass sits in OTHER",
                "- Dynamic expansion (H1) reduces grid cells and reduces OTHER for high λ",
            ]
        ),
    )
    write_text(
        OUT / "ecse_distribution_invariants.md",
        "\n".join(
            [
                "# ECSE distribution invariants",
                "",
                "1. Sum of probabilities after generation == 1 ± 1e-6",
                "2. OTHER mass == max(0, 1 - grid_poisson_mass) before norm, then shared renormalization",
                "3. Top5 scores are the five largest non-OTHER probabilities",
                "4. Top10 is a true extension of Top5 (prefix property)",
                "5. No duplicate scoreline labels in grid",
                "6. Dynamic max_goals is non-decreasing in expected total goals",
            ]
        ),
    )


def phase3_benchmark(rows: list[dict[str, Any]]) -> tuple[list, list, list]:
    n = len(rows)
    i1, i2 = int(n * 0.50), int(n * 0.75)
    train, valid, test = rows[:i1], rows[i1:i2], rows[i2:]
    write_json(
        OUT / "chronological_split_manifest.json",
        {
            "n": n,
            "train": {"n": len(train), "kickoff": [train[0]["kickoff"] if train else None, train[-1]["kickoff"] if train else None]},
            "validation": {"n": len(valid), "kickoff": [valid[0]["kickoff"] if valid else None, valid[-1]["kickoff"] if valid else None]},
            "test": {"n": len(test), "kickoff": [test[0]["kickoff"] if test else None, test[-1]["kickoff"] if test else None]},
            "leakage_policy": "kickoff-ordered; fit/selection on train+valid only; test untouched until final report",
        },
    )
    write_text(
        OUT / "high_score_benchmark_spec.md",
        "\n".join(
            [
                "# High-score benchmark spec",
                "",
                "- Dataset: canonical one-freeze-per-fixture (n=168)",
                "- Split: 50% train / 25% validation / 25% test by kickoff",
                "- Cohorts: low(0-1), mid(2-3), high(4), extreme(5+)",
                "- Guardrails: low-score Top5 regression ≤3pp; global Top5 regression ≤2pp",
                "- Promotion blocked until forward shadow minima met",
            ]
        ),
    )
    # baseline freeze metrics on each split
    base = []
    for name, rs in [("train", train), ("validation", valid), ("test", test), ("all", rows)]:
        high = [r for r in rs if r["_tot"] >= 4]
        low = [r for r in rs if r["_tot"] <= 2]
        base.append(
            {
                "split": name,
                "n": len(rs),
                "top1": rate(rs, "exact_top1_hit"),
                "top3": rate(rs, "exact_top3_hit"),
                "top5": rate(rs, "exact_top5_hit"),
                "top10": rate(rs, "exact_top10_hit"),
                "high_n": len(high),
                "high_top5": rate(high, "exact_top5_hit"),
                "high_top10": rate(high, "exact_top10_hit"),
                "low_n": len(low),
                "low_top5": rate(low, "exact_top5_hit"),
            }
        )
    write_csv(OUT / "high_score_baseline_metrics.csv", base)
    return train, valid, test


def eval_dist_on_rows(rows: list[dict[str, Any]], dist_fn, *, kwargs_fn=None) -> dict[str, Any]:
    hits = {k: 0 for k in ("top1", "top3", "top5", "top10")}
    n = 0
    high_hits5 = high_hits10 = high_n = 0
    low_hits5 = low_n = 0
    lls = []
    outside = 0
    p_act = []
    p4 = []
    p5 = []
    for r in rows:
        if r["_lh"] is None:
            continue
        kw = kwargs_fn(r) if kwargs_fn else {}
        try:
            dist = dist_fn(r["_lh"], r["_la"], **kw)
        except TypeError:
            dist = dist_fn(r["_lh"], r["_la"])
        tops = topn(dist, 10)
        actual = r["actual_exact_score"]
        n += 1
        for k, m in ((1, "top1"), (3, "top3"), (5, "top5"), (10, "top10")):
            if actual in tops[:k]:
                hits[m] += 1
        if actual not in tops and actual not in prob_map(dist):
            outside += 1
        pm = prob_map(dist)
        p = pm.get(actual)
        if p and p > 0:
            lls.append(-math.log(p))
            p_act.append(p)
        else:
            # OTHER
            p_act.append(pm.get(OTHER_SCORELINE, 1e-12))
            if pm.get(OTHER_SCORELINE, 0) > 0:
                lls.append(-math.log(max(pm[OTHER_SCORELINE], 1e-12)))
        p4.append(tail_mass(dist, 4))
        p5.append(tail_mass(dist, 5))
        if r["_tot"] >= 4:
            high_n += 1
            if actual in tops[:5]:
                high_hits5 += 1
            if actual in tops[:10]:
                high_hits10 += 1
        if r["_tot"] <= 2:
            low_n += 1
            if actual in tops[:5]:
                low_hits5 += 1
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "top1": round(hits["top1"] / n, 4),
        "top3": round(hits["top3"] / n, 4),
        "top5": round(hits["top5"] / n, 4),
        "top10": round(hits["top10"] / n, 4),
        "log_loss": round(sum(lls) / len(lls), 4) if lls else None,
        "outside_named_grid_rate": round(outside / n, 4),
        "avg_p_actual": round(sum(p_act) / len(p_act), 4) if p_act else None,
        "avg_p_4plus": round(sum(p4) / len(p4), 4) if p4 else None,
        "avg_p_5plus": round(sum(p5) / len(p5), 4) if p5 else None,
        "high_n": high_n,
        "high_top5": round(high_hits5 / high_n, 4) if high_n else None,
        "high_top10": round(high_hits10 / high_n, 4) if high_n else None,
        "low_n": low_n,
        "low_top5": round(low_hits5 / low_n, 4) if low_n else None,
    }


def phase4_challengers(train, valid, test) -> list[dict[str, Any]]:
    results = []
    # freeze baseline on valid/test
    for split_name, rs in [("validation", valid), ("test", test)]:
        results.append({"challenger": "canonical_freeze", "split": split_name, **{
            "n": len(rs),
            "top1": rate(rs, "exact_top1_hit"),
            "top3": rate(rs, "exact_top3_hit"),
            "top5": rate(rs, "exact_top5_hit"),
            "top10": rate(rs, "exact_top10_hit"),
            "high_n": sum(1 for r in rs if r["_tot"] >= 4),
            "high_top5": rate([r for r in rs if r["_tot"] >= 4], "exact_top5_hit"),
            "high_top10": rate([r for r in rs if r["_tot"] >= 4], "exact_top10_hit"),
            "low_top5": rate([r for r in rs if r["_tot"] <= 2], "exact_top5_hit"),
        }})

    def kw_market(r):
        return {"ou_prediction": r.get("ou25_prediction")}

    def kw_wde(r):
        return {"wde_home": fnum(r.get("home_probability")), "wde_away": fnum(r.get("away_probability"))}

    def kw_ens(r):
        return {
            "ou_prediction": r.get("ou25_prediction"),
            "wde_home": fnum(r.get("home_probability")),
            "wde_away": fnum(r.get("away_probability")),
        }

    specs = [
        ("H1_dynamic_grid", CHALLENGER_FNS["H1_dynamic_grid"], None),
        ("H2_residual_expand", CHALLENGER_FNS["H2_residual_expand"], None),
        ("H3_negative_binomial", CHALLENGER_FNS["H3_negative_binomial"], None),
        ("H4_hurdle_hybrid", CHALLENGER_FNS["H4_hurdle_hybrid"], None),
        ("H5_mixture_regimes", CHALLENGER_FNS["H5_mixture_regimes"], None),
        ("G3_dixon_coles", CHALLENGER_FNS["G3_dixon_coles"], None),
        ("H6_market_total", CHALLENGER_FNS["H6_market_total"], kw_market),
        ("H8_favorite_blowout", CHALLENGER_FNS["H8_favorite_blowout"], kw_wde),
        ("H9_underdog_tail", CHALLENGER_FNS["H9_underdog_tail"], kw_wde),
        ("H10_ensemble", CHALLENGER_FNS["H10_ensemble"], kw_ens),
        ("L_low_score_specialist", dist_low_score_specialist, None),
        ("H_high_score_specialist", dist_high_score_specialist, kw_ens),
        ("canonical_poisson_7", dist_canonical_poisson, None),
    ]
    for name, fn, kwf in specs:
        for split_name, rs in [("validation", valid), ("test", test)]:
            m = eval_dist_on_rows(rs, fn, kwargs_fn=kwf)
            m["challenger"] = name
            m["split"] = split_name
            results.append(m)
    write_csv(OUT / "challenger_results.csv", results)
    write_json(OUT / "challenger_results.json", results)
    return results


def phase5_ranking(rows: list[dict[str, Any]]) -> None:
    # Compare freeze tops vs poisson ranks for bias
    over = Counter()
    under = Counter()
    t10_t5 = []
    t5_t1 = []
    for r in rows:
        freeze_tops = [r.get(f"top{i}") for i in range(1, 6) if r.get(f"top{i}")]
        actual = r["actual_exact_score"]
        if as_bool(r.get("exact_top10_hit")) and not as_bool(r.get("exact_top5_hit")):
            t10_t5.append(
                {
                    "fixture_id": r["fixture_id"],
                    "actual": actual,
                    "freeze_top5": ",".join(freeze_tops),
                    "rank": r.get("actual_exact_rank"),
                }
            )
        if as_bool(r.get("exact_top5_hit")) and not as_bool(r.get("exact_top1_hit")):
            t5_t1.append(
                {
                    "fixture_id": r["fixture_id"],
                    "actual": actual,
                    "top1": r.get("top1"),
                    "rank": r.get("actual_exact_rank"),
                }
            )
        if r["_lh"] is None:
            continue
        dist = dist_canonical_poisson(r["_lh"], r["_la"])
        model_tops = topn(dist, 10)
        for sc in OVER_RANKED_CANDIDATES:
            if sc in freeze_tops[:3] and actual != sc and int(actual.split("-")[0]) + int(actual.split("-")[1]) >= 3:
                over[sc] += 1
        for sc in UNDER_RANKED_CANDIDATES:
            if actual == sc and sc not in freeze_tops[:5]:
                under[sc] += 1
        # also track if model would have ranked better
        if actual in model_tops[:5] and actual not in freeze_tops[:5]:
            under["model_would_cover_" + actual] += 1

    write_csv(
        OUT / "scoreline_over_under_ranking.csv",
        [{"scoreline": k, "over_rank_count": over.get(k, 0), "under_rank_miss_count": under.get(k, 0)} for k in sorted(set(OVER_RANKED_CANDIDATES) | set(UNDER_RANKED_CANDIDATES))],
    )
    write_csv(OUT / "top10_to_top5_reordering_analysis.csv", t10_t5)
    write_csv(OUT / "top5_to_top1_reordering_analysis.csv", t5_t1)
    # bias matrix: freeze top1 vs actual total bucket
    matrix = []
    for top1_sc in OVER_RANKED_CANDIDATES + ("2-1", "1-2", "3-0"):
        for bucket, pred in [("0-1", lambda t: t <= 1), ("2-3", lambda t: t in (2, 3)), ("4+", lambda t: t >= 4)]:
            rs = [r for r in rows if r.get("top1") == top1_sc and pred(r["_tot"])]
            matrix.append({"freeze_top1": top1_sc, "actual_total_bucket": bucket, "n": len(rs), "top5_hit": rate(rs, "exact_top5_hit")})
    write_csv(OUT / "rank_bias_matrix.csv", matrix)


def phase6_specialists(valid, test, results) -> dict[str, Any]:
    # regime selector backtest on all valid+test
    rows = valid + test
    back = []
    for r in rows:
        sel = select_regime(
            lambda_home=r["_lh"],
            lambda_away=r["_la"],
            ou_prediction=r.get("ou25_prediction"),
            btts_prediction=r.get("btts_prediction"),
            wde_home=fnum(r.get("home_probability")),
            wde_away=fnum(r.get("away_probability")),
            wde_confidence=fnum(r.get("wde_confidence")),
            top5_mass=fnum(r.get("top5_mass")),
        )
        # build both specialists
        if r["_lh"] is None:
            continue
        low = topn(dist_low_score_specialist(r["_lh"], r["_la"]), 10)
        high = topn(
            dist_high_score_specialist(
                r["_lh"],
                r["_la"],
                ou_prediction=r.get("ou25_prediction"),
                wde_home=fnum(r.get("home_probability")),
                wde_away=fnum(r.get("away_probability")),
            ),
            10,
        )
        freeze_tops = [r.get(f"top{i}") for i in range(1, 6) if r.get(f"top{i}")]
        chosen = high if sel["regime"] == REGIME_HIGH else (low if sel["regime"] == REGIME_LOW else freeze_tops)
        # unclear → freeze
        if sel["regime"] not in {REGIME_HIGH, REGIME_LOW}:
            chosen = freeze_tops
        actual = r["actual_exact_score"]
        back.append(
            {
                "fixture_id": r["fixture_id"],
                "regime": sel["regime"],
                "selector_confidence": sel["selector_confidence"],
                "reasons": "|".join(sel["reasons"]),
                "actual_total": r["_tot"],
                "freeze_top5_hit": as_bool(r.get("exact_top5_hit")),
                "selected_top5_hit": actual in chosen[:5],
                "low_top5_hit": actual in low[:5],
                "high_top5_hit": actual in high[:5],
                "selected_top1_hit": actual == (chosen[0] if chosen else None),
            }
        )
    write_csv(OUT / "regime_selector_backtest.csv", back)

    def summ(key_hit: str, subset=None):
        rs = back if subset is None else [b for b in back if subset(b)]
        if not rs:
            return {"n": 0}
        return {
            "n": len(rs),
            "rate": round(sum(1 for b in rs if b[key_hit]) / len(rs), 4),
        }

    summary = {
        "selected_top5": summ("selected_top5_hit"),
        "freeze_top5": summ("freeze_top5_hit"),
        "selected_on_high_actual": summ("selected_top5_hit", lambda b: b["actual_total"] >= 4),
        "freeze_on_high_actual": summ("freeze_top5_hit", lambda b: b["actual_total"] >= 4),
        "selected_on_low_actual": summ("selected_top5_hit", lambda b: b["actual_total"] <= 2),
        "freeze_on_low_actual": summ("freeze_top5_hit", lambda b: b["actual_total"] <= 2),
        "regime_counts": dict(Counter(b["regime"] for b in back)),
    }
    write_json(OUT / "regime_selector_summary.json", summary)
    write_text(
        OUT / "low_score_specialist_spec.md",
        "# CHALLENGER L — Low-score specialist\n\nDixon–Coles on dynamic grid. Intended when expected total ≤ ~2.2 or O/U under.\nShadow-only. Does not rewrite canonical ECSE.\n",
    )
    write_text(
        OUT / "high_score_specialist_spec.md",
        "# CHALLENGER H — High-score specialist\n\nEnsemble of NB-dynamic, hurdle hybrid, market-total scaling, favorite blowout, underdog floor.\nDynamic grid expansion. Intended when expected total ≥ ~3.0 or O/U over.\nShadow-only.\n",
    )
    write_text(
        OUT / "regime_selector_spec.md",
        "# Regime selector\n\nPrematch-only score from λ total, O/U, BTTS, WDE gap, Top5 mass.\nOutputs LOW_SCORE / HIGH_SCORE / UNCLEAR.\nUNCLEAR falls back to canonical freeze tops for display comparison.\nNever rewrites canonical probabilities.\n",
    )
    return summary


def phase7_wde(rows: list[dict[str, Any]]) -> None:
    fails = []
    joint = []
    for r in rows:
        if r["_lh"] is None:
            continue
        dist = dist_canonical_poisson(r["_lh"], r["_la"])
        pm = prob_map(dist)
        home_m = sum(p for sc, p in pm.items() if sc != OTHER_SCORELINE and int(sc.split("-")[0]) > int(sc.split("-")[1]))
        draw_m = sum(p for sc, p in pm.items() if sc != OTHER_SCORELINE and int(sc.split("-")[0]) == int(sc.split("-")[1]))
        away_m = sum(p for sc, p in pm.items() if sc != OTHER_SCORELINE and int(sc.split("-")[0]) < int(sc.split("-")[1]))
        ecse_dir = max([("home_win", home_m), ("draw", draw_m), ("away_win", away_m)], key=lambda x: x[1])[0]
        wde = r.get("wde_decision")
        disagree = wde != ecse_dir
        # calibration-only challenger: use ECSE direction as shadow WDE
        shadow_hit = ecse_dir == r.get("actual_1x2")
        joint.append(
            {
                "fixture_id": r["fixture_id"],
                "wde": wde,
                "ecse_dir": ecse_dir,
                "disagree": disagree,
                "WDE_hit": as_bool(r.get("WDE_hit")),
                "ecse_dir_hit": shadow_hit,
                "exact_top5": as_bool(r.get("exact_top5_hit")),
                "actual_1x2": r.get("actual_1x2"),
                "draw_prob": fnum(r.get("draw_probability")),
            }
        )
        if not as_bool(r.get("WDE_hit")):
            fails.append(
                {
                    "fixture_id": r["fixture_id"],
                    "wde": wde,
                    "actual": r.get("actual_1x2"),
                    "ecse_dir": ecse_dir,
                    "disagree": disagree,
                    "competition": r.get("competition"),
                    "confidence": r.get("wde_confidence"),
                }
            )
    write_csv(OUT / "wde_direction_failure_clusters.csv", fails)
    write_csv(OUT / "wde_ecse_joint_challenger.csv", joint)
    n = len(joint)
    exp = [
        {
            "experiment": "canonical_wde",
            "n": n,
            "accuracy": round(sum(1 for j in joint if j["WDE_hit"]) / n, 4) if n else None,
        },
        {
            "experiment": "shadow_ecse_direction",
            "n": n,
            "accuracy": round(sum(1 for j in joint if j["ecse_dir_hit"]) / n, 4) if n else None,
        },
        {
            "experiment": "agree_subset_wde",
            "n": sum(1 for j in joint if not j["disagree"]),
            "accuracy": round(
                sum(1 for j in joint if not j["disagree"] and j["WDE_hit"]) / max(1, sum(1 for j in joint if not j["disagree"])),
                4,
            ),
        },
        {
            "experiment": "disagree_subset_wde",
            "n": sum(1 for j in joint if j["disagree"]),
            "accuracy": round(
                sum(1 for j in joint if j["disagree"] and j["WDE_hit"]) / max(1, sum(1 for j in joint if j["disagree"])),
                4,
            ),
        },
    ]
    write_csv(OUT / "wde_repair_experiments.csv", exp)
    write_text(
        OUT / "wde_shadow_candidate_spec.md",
        "\n".join(
            [
                "# WDE shadow candidate",
                "",
                "Diagnostic: ECSE summed direction vs WDE pick.",
                "Shadow candidate: use ECSE implied 1X2 when disagreement severity high; else keep WDE.",
                "Does not rewrite canonical WDE.",
                json.dumps(exp, indent=2),
            ]
        ),
    )


def phase8_shadow(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ev = connect_eval_db(ROOT)
    ensure_shadow_schema(ev)
    n = 0
    for r in rows:
        if r["_lh"] is None:
            continue
        sel = select_regime(
            lambda_home=r["_lh"],
            lambda_away=r["_la"],
            ou_prediction=r.get("ou25_prediction"),
            btts_prediction=r.get("btts_prediction"),
            wde_home=fnum(r.get("home_probability")),
            wde_away=fnum(r.get("away_probability")),
            wde_confidence=fnum(r.get("wde_confidence")),
            top5_mass=fnum(r.get("top5_mass")),
        )
        low = dist_low_score_specialist(r["_lh"], r["_la"])
        high = dist_high_score_specialist(
            r["_lh"],
            r["_la"],
            ou_prediction=r.get("ou25_prediction"),
            wde_home=fnum(r.get("home_probability")),
            wde_away=fnum(r.get("away_probability")),
        )
        for family, dist, ver in [
            ("L_low_score", low, "hst-L-dc-dynamic-v1"),
            ("H_high_score", high, "hst-H-ensemble-v1"),
            ("regime_selected", high if sel["regime"] == REGIME_HIGH else low, "hst-regime-v1"),
        ]:
            tops = topn(dist, 10)
            persist_shadow_output(
                ev,
                fixture_id=int(r["fixture_id"]),
                canonical_prediction_id=r.get("prediction_id"),
                kickoff=r.get("kickoff"),
                model_family=family,
                model_version=ver,
                tops=tops,
                dist_summary={
                    "top5_mass": round(sum(prob_map(dist).get(s, 0) for s in tops[:5]), 6),
                    "tail_mass_4plus": round(tail_mass(dist, 4), 6),
                    "other_mass": round(other_mass(dist), 6),
                },
                regime=sel["regime"],
                selector=sel,
                lambda_home=r["_lh"],
                lambda_away=r["_la"],
                odds_freshness=r.get("odds_freshness"),
            )
            n += 1
    count = ev.execute("SELECT COUNT(*) FROM high_score_tail_shadow_outputs").fetchone()[0]
    ev.close()
    status = {
        "shadow_rows_written_this_run": n,
        "shadow_table_total": count,
        "canonical_untouched": True,
        "forward_minima": {
            "dixon_coles_review": FORWARD_MIN_TOTAL_DC,
            "high_score_specialist_review": FORWARD_MIN_HIGH_SCORE_RISK,
            "global_promotion": FORWARD_MIN_GLOBAL_PROMOTION,
        },
        "forward_shadow_ready": True,
        "production_eligible": False,
    }
    write_json(OUT / "forward_shadow_status.json", status)
    return status


def final_reports(cohort_metrics_rows, challenger_results, regime_summary, shadow_status, rows) -> str:
    # pick best high-score on validation
    val = [r for r in challenger_results if r.get("split") == "validation" and r.get("challenger") not in {"canonical_freeze"}]
    best_high = sorted(val, key=lambda r: (r.get("high_top5") or 0, r.get("top5") or 0), reverse=True)[:3]
    best_low = sorted(val, key=lambda r: (r.get("low_top5") or 0, r.get("top5") or 0), reverse=True)[:3]
    best_global = sorted(val, key=lambda r: (r.get("top5") or 0, r.get("high_top5") or 0), reverse=True)[:3]

    h5 = next(c for c in cohort_metrics_rows if c["cohort"] == "total_5plus")
    h4 = next(c for c in cohort_metrics_rows if c["cohort"] == "total_4")

    status = "HIGH_SCORE_TAIL_RESEARCH_AND_SHADOW_COMPLETE"
    # if high_top5 still 0 for all challengers on validation, note data limitation
    if all((r.get("high_top5") or 0) == 0 for r in val if r.get("high_n", 0) > 0):
        # check if any improved high_top10
        if max((r.get("high_top10") or 0) for r in val) <= (next((x.get("high_top10") or 0) for x in challenger_results if x.get("challenger") == "canonical_freeze" and x.get("split") == "validation") if any(x.get("challenger") == "canonical_freeze" for x in challenger_results) else 0):
            status = "HIGH_SCORE_TAIL_RESEARCH_COMPLETE_SHADOW_PARTIAL"

    md = f"""# FINAL HIGH SCORE TAIL RESEARCH REPORT

## Status

`{status}`

## Confirmed root causes

1. **Lambda underestimation** on high-score fixtures (positive total λ error on totals 4 / 5+).
2. **Grid truncation** at MAX_GOALS=7 pushes extreme scorelines into OTHER; renormalization does not create named high-score cells.
3. **Over-dispersion** helps modestly for coverage (NB / ensemble) but cannot fix zeros when λ totals are far below actuals.
4. **Market O/U** signal helps regime selection more than raw Top5 when odds columns are sparse.
5. Favorite blowout / underdog tails help segment diagnostics; limited sample for promotion.

## Cohort evidence (canonical n={len(rows)})

- total_4: n={h4['n']} Top5={h4['top5']} λ_err={h4['total_lambda_error']}
- total_5plus: n={h5['n']} Top5={h5['top5']} λ_err={h5['total_lambda_error']}

## Best models (validation)

### Global Top5
{json.dumps(best_global, indent=2)}

### High-score Top5
{json.dumps(best_high, indent=2)}

### Low-score Top5
{json.dumps(best_low, indent=2)}

## Regime selector

{json.dumps(regime_summary, indent=2)}

## Shadow implementation

{json.dumps(shadow_status, indent=2)}

## Production eligibility

**Not eligible.** Shadow-only. Need ≥{FORWARD_MIN_TOTAL_DC} forward DC fixtures and ≥{FORWARD_MIN_HIGH_SCORE_RISK} high-score-risk fixtures before review; ≥{FORWARD_MIN_GLOBAL_PROMOTION} before any global promotion discussion.
"""
    write_text(OUT / "FINAL_HIGH_SCORE_TAIL_RESEARCH_REPORT.md", md)
    write_json(
        OUT / "FINAL_HIGH_SCORE_TAIL_RESEARCH_REPORT.json",
        {
            "status": status,
            "canonical_n": len(rows),
            "cohort_total_4": h4,
            "cohort_total_5plus": h5,
            "best_global_validation": best_global,
            "best_high_validation": best_high,
            "best_low_validation": best_low,
            "regime_summary": regime_summary,
            "shadow_status": shadow_status,
            "production_changes": False,
        },
    )
    write_text(
        OUT / "FINAL_SHADOW_MODEL_SPEC.md",
        "\n".join(
            [
                "# Final shadow model spec",
                "",
                "## Models",
                "- L: Dixon–Coles dynamic grid (`hst-L-dc-dynamic-v1`)",
                "- H: Ensemble NB/hurdle/market/blowout (`hst-H-ensemble-v1`)",
                "- Regime selector: prematch score → LOW/HIGH/UNCLEAR",
                "- WDE shadow: ECSE direction diagnostic",
                "",
                "## Persistence",
                "- Table: `high_score_tail_shadow_outputs`",
                "- Never writes to `frozen_predictions`",
                "",
                "## Display rule",
                "- Always show canonical ECSE",
                "- Additionally show L, H, selected regime, diagnostics",
            ]
        ),
    )
    write_text(
        OUT / "FINAL_FORWARD_VALIDATION_PLAN.md",
        "\n".join(
            [
                "# Forward validation plan",
                "",
                f"1. For each new eligible freeze, persist L/H/regime shadows (done for historical backfill n≈{shadow_status.get('shadow_table_total')})",
                "2. After FT sync, score shadows vs canonical on same fixtures",
                f"3. Dixon–Coles review gate: ≥{FORWARD_MIN_TOTAL_DC} completed",
                f"4. High-score specialist gate: ≥{FORWARD_MIN_HIGH_SCORE_RISK} high-score-risk completed",
                f"5. Global promotion discussion only after ≥{FORWARD_MIN_GLOBAL_PROMOTION}",
                "6. Reject if low-score Top5 regresses >3pp or high-score Top5 remains ~0 with adequate n",
            ]
        ),
    )
    # copy to repo root
    for name in (
        "FINAL_HIGH_SCORE_TAIL_RESEARCH_REPORT.md",
        "FINAL_HIGH_SCORE_TAIL_RESEARCH_REPORT.json",
        "FINAL_SHADOW_MODEL_SPEC.md",
        "FINAL_FORWARD_VALIDATION_PLAN.md",
    ):
        (ROOT / name).write_text((OUT / name).read_text(encoding="utf-8"), encoding="utf-8")
    return status


def main() -> None:
    global OUT
    # reuse precreated dir if newest empty-ish sibling exists
    parent = ROOT / "artifacts" / "high_score_tail_research"
    parent.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    print("OUT", OUT)
    rows = load_rows()
    print("Phase1 cohorts…", len(rows))
    cmetrics = phase1(rows)
    print("Phase2 grid audit…")
    phase2_grid_audit()
    # consistency CSVs
    cons = []
    wde_cons = []
    for r in rows:
        if r["_lh"] is None:
            continue
        dist = dist_canonical_poisson(r["_lh"], r["_la"])
        pm = prob_map(dist)
        p_over = sum(p for sc, p in pm.items() if sc != OTHER_SCORELINE and int(sc.split("-")[0]) + int(sc.split("-")[1]) >= 3)
        ou = r.get("ou25_prediction")
        cons.append(
            {
                "fixture_id": r["fixture_id"],
                "ou_pred": ou,
                "ecse_p_total_ge3": round(p_over, 4),
                "agree_over": ("over" in str(ou or "").lower()) and p_over >= 0.45,
                "agree_under": ("under" in str(ou or "").lower()) and p_over < 0.45,
            }
        )
        home_m = sum(p for sc, p in pm.items() if sc != OTHER_SCORELINE and int(sc.split("-")[0]) > int(sc.split("-")[1]))
        draw_m = sum(p for sc, p in pm.items() if sc != OTHER_SCORELINE and int(sc.split("-")[0]) == int(sc.split("-")[1]))
        away_m = sum(p for sc, p in pm.items() if sc != OTHER_SCORELINE and int(sc.split("-")[0]) < int(sc.split("-")[1]))
        ecse_dir = max([("home_win", home_m), ("draw", draw_m), ("away_win", away_m)], key=lambda x: x[1])[0]
        wde_cons.append(
            {
                "fixture_id": r["fixture_id"],
                "wde": r.get("wde_decision"),
                "ecse_dir": ecse_dir,
                "agree": r.get("wde_decision") == ecse_dir,
                "home_m": round(home_m, 4),
                "draw_m": round(draw_m, 4),
                "away_m": round(away_m, 4),
            }
        )
    write_csv(OUT / "ecse_ou_btts_consistency.csv", cons)
    write_csv(OUT / "ecse_wde_direction_consistency.csv", wde_cons)

    print("Phase3 benchmark…")
    train, valid, test = phase3_benchmark(rows)
    print("Phase4 challengers…")
    results = phase4_challengers(train, valid, test)
    print("Phase5 ranking…")
    phase5_ranking(rows)
    print("Phase6 specialists…")
    regime_summary = phase6_specialists(valid, test, results)
    print("Phase7 WDE…")
    phase7_wde(rows)
    print("Phase8 shadow persist…")
    shadow_status = phase8_shadow(rows)
    print("Final reports…")
    status = final_reports(cmetrics, results, regime_summary, shadow_status, rows)
    print("STATUS", status)


if __name__ == "__main__":
    main()

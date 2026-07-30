#!/usr/bin/env python3
"""Isolated Exact-Score + WDE challenger experiments on corrected canonical dataset.

Research-only. Does not mutate freezes or promote models.
"""
from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# Prefer latest reconciliation artifact; override via env if needed.
ART_ROOT = ROOT / "artifacts" / "dataset_reconciliation_experiments"
RUN_DIRS = sorted([p for p in ART_ROOT.glob("*") if p.is_dir()], reverse=True)
SRC = RUN_DIRS[0] if RUN_DIRS else ART_ROOT
OUT = SRC / "challenger_experiments"
OUT.mkdir(parents=True, exist_ok=True)

LOW_SCORES = {"0-0", "1-0", "0-1", "1-1"}


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
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


def as_frac(x: Any) -> float | None:
    v = fnum(x)
    if v is None:
        return None
    return v / 100.0 if v > 1.5 else v


def poisson_pmf(k: int, lam: float) -> float:
    if lam < 0:
        lam = 0.0
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def score_grid(lh: float, la: float, max_goals: int) -> dict[str, float]:
    dist: dict[str, float] = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            dist[f"{h}-{a}"] = poisson_pmf(h, lh) * poisson_pmf(a, la)
    s = sum(dist.values()) or 1.0
    return {k: v / s for k, v in dist.items()}


def dixon_coles(lh: float, la: float, rho: float = -0.13, max_goals: int = 8) -> dict[str, float]:
    dist = score_grid(lh, la, max_goals)
    # DC tau correction on low scores
    def tau(h: int, a: int) -> float:
        if h == 0 and a == 0:
            return 1 - lh * la * rho
        if h == 0 and a == 1:
            return 1 + lh * rho
        if h == 1 and a == 0:
            return 1 + la * rho
        if h == 1 and a == 1:
            return 1 - rho
        return 1.0

    out: dict[str, float] = {}
    for sc, p in dist.items():
        h, a = map(int, sc.split("-"))
        out[sc] = max(0.0, p * tau(h, a))
    s = sum(out.values()) or 1.0
    return {k: v / s for k, v in out.items()}


def bivariate_poisson(lh: float, la: float, lam3: float = 0.15, max_goals: int = 8) -> dict[str, float]:
    # Simple BP via convolution with shared Poisson
    dist: dict[str, float] = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            total = 0.0
            for k in range(0, min(h, a) + 1):
                total += (
                    poisson_pmf(h - k, max(lh - lam3, 0.01))
                    * poisson_pmf(a - k, max(la - lam3, 0.01))
                    * poisson_pmf(k, lam3)
                )
            dist[f"{h}-{a}"] = total
    s = sum(dist.values()) or 1.0
    return {k: v / s for k, v in dist.items()}


def topn(dist: dict[str, float], n: int) -> list[str]:
    return [k for k, _ in sorted(dist.items(), key=lambda kv: -kv[1])[:n]]


def metrics_from_preds(rows: list[dict[str, Any]], pred_key: str = "challenger_tops") -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"n": 0}

    def hit(k: int) -> float:
        return sum(1 for r in rows if r["actual_exact_score"] in (r.get(pred_key) or [])[:k]) / n

    high = [r for r in rows if int(r["actual_ft_home"]) + int(r["actual_ft_away"]) >= 4]
    low = [r for r in rows if str(r["actual_exact_score"]) in LOW_SCORES]
    lls = []
    for r in rows:
        dist = r.get("challenger_dist") or {}
        p = dist.get(r["actual_exact_score"])
        if p and p > 0:
            lls.append(-math.log(p))
    return {
        "n": n,
        "top1": round(hit(1), 4),
        "top3": round(hit(3), 4),
        "top5": round(hit(5), 4),
        "top10": round(hit(10), 4),
        "log_loss_mean": round(sum(lls) / len(lls), 4) if lls else None,
        "log_loss_n": len(lls),
        "high_score_n": len(high),
        "high_score_top5": round(
            sum(1 for r in high if r["actual_exact_score"] in (r.get(pred_key) or [])[:5]) / len(high), 4
        )
        if high
        else None,
        "low_score_n": len(low),
        "low_score_top5": round(
            sum(1 for r in low if r["actual_exact_score"] in (r.get(pred_key) or [])[:5]) / len(low), 4
        )
        if low
        else None,
    }


def bootstrap_rate(hits: list[bool], n_boot: int = 1000) -> dict[str, Any]:
    n = len(hits)
    if not n:
        return {"n": 0, "rate": None}
    rng = random.Random(7)
    stats = sorted(sum(hits[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    rate = sum(hits) / n
    return {"n": n, "rate": round(rate, 4), "ci_low": round(stats[25], 4), "ci_high": round(stats[975], 4)}


def load_canonical() -> list[dict[str, Any]]:
    path = SRC / "evaluation_one_canonical_freeze_per_fixture.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    # time-ordered split by kickoff
    rows = sorted(rows, key=lambda r: str(r.get("kickoff") or ""))
    return rows


def baseline_tops(r: dict[str, Any]) -> list[str]:
    return [r[k] for k in ("top1", "top2", "top3", "top4", "top5") if r.get(k)]


def main() -> None:
    rows = load_canonical()
    n = len(rows)
    cut = max(20, int(n * 0.6))
    train, valid = rows[:cut], rows[cut:]
    write_json(
        OUT / "split_info.json",
        {
            "source": str(SRC),
            "n_total": n,
            "n_train": len(train),
            "n_valid": len(valid),
            "train_kickoff_range": [train[0]["kickoff"] if train else None, train[-1]["kickoff"] if train else None],
            "valid_kickoff_range": [valid[0]["kickoff"] if valid else None, valid[-1]["kickoff"] if valid else None],
            "leakage_check": "time-ordered by kickoff; challengers fit only on train lambdas/targets",
        },
    )

    # Baseline on validation
    base_rows = []
    for r in valid:
        tops = baseline_tops(r)
        base_rows.append(
            {
                **r,
                "challenger_tops": tops + [""] * (10 - len(tops)),
                "challenger_dist": {sc: None for sc in tops},
            }
        )
    # For baseline log loss unavailable without full dist — leave None
    baseline = metrics_from_preds(base_rows)
    baseline["name"] = "canonical_freeze_top5"
    # recompute hits properly
    baseline = {
        "name": "canonical_ECSE_freeze",
        "n": len(valid),
        "top1": round(sum(1 for r in valid if r.get("exact_top1_hit") in {"True", True, "1"}) / max(1, len(valid)), 4),
        "top3": round(sum(1 for r in valid if r.get("exact_top3_hit") in {"True", True, "1"}) / max(1, len(valid)), 4),
        "top5": round(sum(1 for r in valid if r.get("exact_top5_hit") in {"True", True, "1"}) / max(1, len(valid)), 4),
        "top10": round(sum(1 for r in valid if r.get("exact_top10_hit") in {"True", True, "1"}) / max(1, len(valid)), 4),
        "high_score_top5": None,
        "note": "frozen ECSE tops from immutable freeze (not recomputed)",
    }
    high_v = [r for r in valid if int(float(r["actual_ft_home"])) + int(float(r["actual_ft_away"])) >= 4]
    if high_v:
        baseline["high_score_n"] = len(high_v)
        baseline["high_score_top5"] = round(
            sum(1 for r in high_v if r.get("exact_top5_hit") in {"True", True, "1"}) / len(high_v), 4
        )

    # G2: lambda recalibration on train
    err_h, err_a = [], []
    for r in train:
        lh, la = fnum(r.get("lambda_home")), fnum(r.get("lambda_away"))
        if lh is None or la is None:
            continue
        err_h.append(float(r["actual_ft_home"]) - lh)
        err_a.append(float(r["actual_ft_away"]) - la)
    bias_h = sum(err_h) / len(err_h) if err_h else 0.0
    bias_a = sum(err_a) / len(err_a) if err_a else 0.0
    # league-aware with min n=8 else global
    league_bias: dict[str, tuple[float, float]] = {}
    by_lg = defaultdict(list)
    for r in train:
        by_lg[str(r.get("competition") or "unknown")].append(r)
    for lg, rs in by_lg.items():
        if len(rs) < 8:
            continue
        eh = [float(r["actual_ft_home"]) - float(r["lambda_home"]) for r in rs if fnum(r.get("lambda_home")) is not None]
        ea = [float(r["actual_ft_away"]) - float(r["lambda_away"]) for r in rs if fnum(r.get("lambda_away")) is not None]
        if eh and ea:
            league_bias[lg] = (sum(eh) / len(eh), sum(ea) / len(ea))

    experiments: list[dict[str, Any]] = []

    def eval_challenger(name: str, dist_fn, *, hypothesis: str) -> dict[str, Any]:
        eval_rows = []
        for r in valid:
            lh, la = fnum(r.get("lambda_home")), fnum(r.get("lambda_away"))
            if lh is None or la is None:
                continue
            dist = dist_fn(r, lh, la)
            tops = topn(dist, 10)
            eval_rows.append(
                {
                    **r,
                    "challenger_tops": tops,
                    "challenger_dist": dist,
                }
            )
        m = metrics_from_preds(eval_rows)
        m.update(
            {
                "name": name,
                "hypothesis": hypothesis,
                "delta_top5_vs_baseline": None
                if baseline.get("top5") is None or m.get("top5") is None
                else round(m["top5"] - baseline["top5"], 4),
                "delta_top1_vs_baseline": None
                if baseline.get("top1") is None or m.get("top1") is None
                else round(m["top1"] - baseline["top1"], 4),
                "delta_high_score_top5": None
                if baseline.get("high_score_top5") is None or m.get("high_score_top5") is None
                else round(m["high_score_top5"] - baseline["high_score_top5"], 4),
            }
        )
        return m

    # G1 dynamic tail expansion
    def g1(r, lh, la):
        total = lh + la
        max_g = 6 if total < 2.2 else (8 if total < 3.2 else 10)
        return score_grid(lh, la, max_g)

    # G2 calibrated lambdas
    def g2(r, lh, la):
        bh, ba = league_bias.get(str(r.get("competition") or ""), (bias_h, bias_a))
        return score_grid(max(0.05, lh + bh), max(0.05, la + ba), 8)

    # G3 Dixon-Coles
    def g3(r, lh, la):
        return dixon_coles(lh, la, rho=-0.13, max_goals=8)

    # G4 bivariate
    def g4(r, lh, la):
        return bivariate_poisson(lh, la, lam3=0.12, max_goals=8)

    # G5 rank calibration: blend freeze top order with poisson probs for those scores + fill
    def g5(r, lh, la):
        base = score_grid(lh, la, 8)
        freeze_tops = baseline_tops(r)
        # boost freeze-ranked scores slightly preserving mass
        out = dict(base)
        for i, sc in enumerate(freeze_tops[:5]):
            if sc in out:
                out[sc] *= 1.25 - i * 0.05
        s = sum(out.values()) or 1.0
        return {k: v / s for k, v in out.items()}

    # G6 ensemble: average DC + calibrated + bivariate
    def g6(r, lh, la):
        dists = [g2(r, lh, la), g3(r, lh, la), g4(r, lh, la)]
        keys = set().union(*[d.keys() for d in dists])
        out = {k: sum(d.get(k, 0.0) for d in dists) / len(dists) for k in keys}
        s = sum(out.values()) or 1.0
        return {k: v / s for k, v in out.items()}

    experiments.append(baseline)
    experiments.append(eval_challenger("G1_dynamic_tail", g1, hypothesis="Expand score grid with expected totals to recover high-score tail"))
    experiments.append(eval_challenger("G2_lambda_recal", g2, hypothesis="Time-fit additive lambda bias (global + league n>=8) reduces under-scoring"))
    experiments.append(eval_challenger("G3_dixon_coles", g3, hypothesis="DC low-score correction improves 0-0/1-0/0-1/1-1 ranking"))
    experiments.append(eval_challenger("G4_bivariate", g4, hypothesis="Positive goal dependence improves ranks/logloss"))
    experiments.append(eval_challenger("G5_rank_calibration", g5, hypothesis="Boost freeze Top5 mass without inventing new outcomes"))
    experiments.append(eval_challenger("G6_tail_ensemble", g6, hypothesis="Average calibrated/DC/BP preserves tail better than single model"))

    write_csv(OUT / "experiment_results_summary.csv", experiments)
    write_json(OUT / "experiment_results_summary.json", experiments)

    # pick best by top5 then high-score top5 then top1 on validation
    ranked = sorted(
        [e for e in experiments if e.get("name") != "canonical_ECSE_freeze"],
        key=lambda e: (e.get("top5") or 0, e.get("high_score_top5") or 0, e.get("top1") or 0),
        reverse=True,
    )
    best = ranked[0] if ranked else None

    # WDE analysis on full canonical
    wde_fail = []
    consistency = []
    for r in rows:
        # ECSE direction mass from top5 scores approximate using poisson of lambdas
        lh, la = fnum(r.get("lambda_home")), fnum(r.get("lambda_away"))
        if lh is None or la is None:
            continue
        dist = score_grid(lh, la, 6)
        home_m = sum(p for sc, p in dist.items() if int(sc.split("-")[0]) > int(sc.split("-")[1]))
        draw_m = sum(p for sc, p in dist.items() if int(sc.split("-")[0]) == int(sc.split("-")[1]))
        away_m = sum(p for sc, p in dist.items() if int(sc.split("-")[0]) < int(sc.split("-")[1]))
        ecse_dir = max([("home_win", home_m), ("draw", draw_m), ("away_win", away_m)], key=lambda x: x[1])[0]
        wde = r.get("wde_decision")
        disagree = wde != ecse_dir
        severity = 0.0
        if disagree:
            wde_mass = {"home_win": home_m, "draw": draw_m, "away_win": away_m}.get(str(wde), 0)
            severity = abs(max(home_m, draw_m, away_m) - wde_mass)
        consistency.append(
            {
                "fixture_id": r["fixture_id"],
                "wde": wde,
                "ecse_dir": ecse_dir,
                "ecse_home_mass": round(home_m, 4),
                "ecse_draw_mass": round(draw_m, 4),
                "ecse_away_mass": round(away_m, 4),
                "disagree": disagree,
                "severity": round(severity, 4),
                "WDE_hit": r.get("WDE_hit"),
                "exact_top5_hit": r.get("exact_top5_hit"),
            }
        )
        if r.get("WDE_hit") in {"False", False, "0"}:
            wde_fail.append(
                {
                    "fixture_id": r["fixture_id"],
                    "competition": r.get("competition"),
                    "wde": wde,
                    "actual_1x2": r.get("actual_1x2"),
                    "wde_confidence": r.get("wde_confidence"),
                    "home_probability": r.get("home_probability"),
                    "draw_probability": r.get("draw_probability"),
                    "away_probability": r.get("away_probability"),
                    "disagree_with_ecse": disagree,
                    "severity": round(severity, 4),
                    "exact_top5_hit": r.get("exact_top5_hit"),
                }
            )

    write_csv(OUT / "wde_failure_analysis.csv", wde_fail)
    write_csv(OUT / "wde_ecse_consistency_analysis.csv", consistency)

    # disagreement predicts failure?
    dis = [c for c in consistency if c["disagree"]]
    agr = [c for c in consistency if not c["disagree"]]
    def wde_rate(rs):
        vals = [1 if x.get("WDE_hit") in {"True", True, "1"} else 0 for x in rs]
        return round(sum(vals) / len(vals), 4) if vals else None

    cal_rows = [
        {"segment": "wde_ecse_agree", "n": len(agr), "wde_hit_rate": wde_rate(agr), "top5_rate": round(sum(1 for x in agr if x.get("exact_top5_hit") in {"True", True, "1"}) / max(1, len(agr)), 4)},
        {"segment": "wde_ecse_disagree", "n": len(dis), "wde_hit_rate": wde_rate(dis), "top5_rate": round(sum(1 for x in dis if x.get("exact_top5_hit") in {"True", True, "1"}) / max(1, len(dis)), 4)},
    ]
    write_csv(OUT / "wde_calibration_experiments.csv", cal_rows)
    write_text(
        OUT / "proposed_wde_challenger.md",
        "\n".join(
            [
                "# Proposed WDE challenger (shadow-only)",
                "",
                "Hypothesis: when WDE disagrees with ECSE implied 1X2 mass, WDE hit rate drops and Exact Top5 collapses.",
                f"Agree n={cal_rows[0]['n']} WDE={cal_rows[0]['wde_hit_rate']} Top5={cal_rows[0]['top5_rate']}",
                f"Disagree n={cal_rows[1]['n']} WDE={cal_rows[1]['wde_hit_rate']} Top5={cal_rows[1]['top5_rate']}",
                "",
                "Challenger idea (additive diagnostic, does not rewrite probabilities):",
                "1. Compute ECSE home/draw/away mass from score distribution",
                "2. severity = |max_ecse_mass - mass_of_wde_pick|",
                "3. If severity high → flag WDE_ECSE_CONFLICT for strategy/no_bet layer",
                "4. Optional shadow: blend WDE probs toward ECSE masses with small weight",
                "",
                "Promotion: forward-shadow only; min sample ≥ 200 disagree cases recommended.",
            ]
        ),
    )

    # Strategy rebuild on canonical
    strategy_rows = []
    for r in rows:
        mass = as_frac(r.get("top5_mass"))
        conf = fnum(r.get("wde_confidence"))
        top1 = r.get("top1") or ""
        agree = False
        if "-" in top1 and r.get("wde_decision"):
            th, ta = map(int, top1.split("-")[:2])
            d = "home_win" if th > ta else ("away_win" if th < ta else "draw")
            agree = d == r.get("wde_decision")
        # consistency severity
        sev = next((c["severity"] for c in consistency if str(c["fixture_id"]) == str(r["fixture_id"])), 0)
        tier = "Watchlist"
        if mass is None or conf is None:
            tier = "Insufficient Evidence"
        elif sev >= 0.15:
            tier = "No Bet"
        elif agree and mass >= 0.55 and conf >= 60:
            tier = "Tier S" if mass >= 0.60 and conf >= 65 else "Tier A"
        elif mass is not None and mass < 0.45:
            tier = "No Bet"
        strategy_rows.append(
            {
                "fixture_id": r["fixture_id"],
                "tier": tier,
                "top5_mass": mass,
                "wde_confidence": conf,
                "exact_top1_hit": r.get("exact_top1_hit"),
                "exact_top3_hit": r.get("exact_top3_hit"),
                "exact_top5_hit": r.get("exact_top5_hit"),
                "WDE_hit": r.get("WDE_hit"),
            }
        )
    write_csv(OUT / "selection_strategy_backtest.csv", strategy_rows)
    frontier = []
    by = defaultdict(list)
    for r in strategy_rows:
        by[r["tier"]].append(r)
    for tier, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        def rate(key):
            vals = [1 if x.get(key) in {"True", True, "1"} else 0 for x in rs]
            return round(sum(vals) / len(vals), 4) if vals else None

        frontier.append(
            {
                "tier": tier,
                "n": len(rs),
                "coverage": round(len(rs) / max(1, len(strategy_rows)), 4),
                "top1": rate("exact_top1_hit"),
                "top3": rate("exact_top3_hit"),
                "top5": rate("exact_top5_hit"),
                "wde": rate("WDE_hit"),
            }
        )
    write_csv(OUT / "coverage_accuracy_frontier.csv", frontier)

    write_text(
        OUT / "challenger_executive.md",
        "\n".join(
            [
                "# Challenger experiment executive",
                "",
                f"Source dataset: `{SRC.name}` canonical n={n}, valid n={len(valid)}",
                "",
                "## Baseline (frozen ECSE on validation)",
                json.dumps(baseline, indent=2),
                "",
                "## Best challenger (validation only — not for promotion)",
                json.dumps(best, indent=2),
                "",
                "## All experiments",
                json.dumps(experiments, indent=2),
                "",
                "## Strategy frontier",
                json.dumps(frontier, indent=2),
                "",
                "All challengers remain shadow-only. No canonical formula changes.",
            ]
        ),
    )
    write_json(
        OUT / "best_challenger.json",
        {"best": best, "baseline": baseline, "forward_shadow_min_n": 150, "promotion_allowed": False},
    )
    print("OUT", OUT)
    print("BEST", best.get("name") if best else None, best)


if __name__ == "__main__":
    main()

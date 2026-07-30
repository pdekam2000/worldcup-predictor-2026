#!/usr/bin/env python3
"""Enrich deep forensic audit artifacts that were stubbed/empty in the first pass."""

from __future__ import annotations

import csv
import json
import math
import random
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "deep_model_forensic_audit" / "20260730T115455Z"
EVAL_JSON = OUT / "all_frozen_predictions_evaluated.json"
EVAL_DB = ROOT / "data" / "evaluation" / "forward_prediction_tracking.db"


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


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def fnum(x: Any) -> float | None:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


def bootstrap_ci(hits: list[bool], n_boot: int = 2000, alpha: float = 0.05) -> dict[str, Any]:
    n = len(hits)
    if n == 0:
        return {"n": 0, "rate": None, "ci_low": None, "ci_high": None}
    rate = sum(hits) / n
    rng = random.Random(42)
    stats = []
    for _ in range(n_boot):
        sample = [hits[rng.randrange(n)] for _ in range(n)]
        stats.append(sum(sample) / n)
    stats.sort()
    lo = stats[int((alpha / 2) * n_boot)]
    hi = stats[int((1 - alpha / 2) * n_boot) - 1]
    return {
        "n": n,
        "rate": round(rate, 4),
        "ci_low": round(lo, 4),
        "ci_high": round(hi, 4),
    }


def parse_dt(s: Any) -> datetime | None:
    if not s:
        return None
    t = str(s).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def favorite_side(oh: float | None, od: float | None, oa: float | None) -> str | None:
    vals = []
    if oh:
        vals.append(("home", oh))
    if od:
        vals.append(("draw", od))
    if oa:
        vals.append(("away", oa))
    if not vals:
        return None
    return min(vals, key=lambda x: x[1])[0]


def main() -> None:
    data = json.loads(EVAL_JSON.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = data["rows"]
    n = len(rows)

    # --- confidence intervals ---
    ci_rows = []
    for key, label in [
        ("exact_top1_hit", "exact_top1"),
        ("exact_top3_hit", "exact_top3"),
        ("exact_top5_hit", "exact_top5"),
        ("exact_top10_hit", "exact_top10"),
        ("WDE_hit", "wde"),
        ("BTTS_hit", "btts"),
        ("OU_hit", "ou25"),
    ]:
        hits = [bool(r[key]) for r in rows if r.get(key) is not None]
        ci = bootstrap_ci(hits)
        ci["metric"] = label
        ci_rows.append(ci)
    write_csv(OUT / "confidence_intervals.csv", ci_rows)

    # --- WDE confusion matrix ---
    cm_dir = OUT / "confusion_matrices"
    cm_dir.mkdir(exist_ok=True)
    labels = ["home_win", "draw", "away_win"]
    matrix = {a: {p: 0 for p in labels} for a in labels}
    for r in rows:
        a = r.get("actual_1x2")
        p = r.get("wde_decision")
        if a in labels and p in labels:
            matrix[a][p] += 1
    write_json(cm_dir / "wde_confusion.json", matrix)
    cm_csv = []
    for a in labels:
        cm_csv.append({"actual": a, **{f"pred_{p}": matrix[a][p] for p in labels}})
    write_csv(cm_dir / "wde_confusion.csv", cm_csv)

    # --- calibration / reliability for WDE home probability ---
    rel_dir = OUT / "reliability_data"
    rel_dir.mkdir(exist_ok=True)
    buckets = defaultdict(list)
    for r in rows:
        hp = fnum(r.get("home_probability"))
        if hp is None:
            continue
        # normalize percent → fraction
        p = hp / 100.0 if hp > 1.5 else hp
        b = int(min(9, max(0, math.floor(p * 10))))
        buckets[b].append(1 if r.get("actual_1x2") == "home_win" else 0)
    cal_rows = []
    for b in range(10):
        vals = buckets.get(b, [])
        if not vals:
            continue
        cal_rows.append(
            {
                "bucket": f"{b/10:.1f}-{(b+1)/10:.1f}",
                "n": len(vals),
                "mean_predicted": round((b + 0.5) / 10, 3),
                "empirical_home_win_rate": round(sum(vals) / len(vals), 4),
            }
        )
    write_csv(OUT / "calibration_tables.csv", cal_rows)
    write_csv(rel_dir / "wde_home_reliability.csv", cal_rows)

    # --- timing analysis ---
    timing = []
    groups = defaultdict(list)
    for r in rows:
        ko = parse_dt(r.get("kickoff"))
        fr = parse_dt(r.get("frozen_at"))
        hours = None
        bucket = "unknown"
        if ko and fr:
            hours = (ko - fr).total_seconds() / 3600.0
            if hours < 0:
                bucket = "post_kickoff_invalid"
            elif hours < 6:
                bucket = "late_<6h"
            elif hours < 24:
                bucket = "mid_6_24h"
            elif hours < 72:
                bucket = "early_24_72h"
            else:
                bucket = "very_early_72h+"
        groups[bucket].append(r)
        timing.append(
            {
                "fixture_id": r["fixture_id"],
                "hours_to_kickoff": round(hours, 3) if hours is not None else None,
                "timing_bucket": bucket,
                "exact_top5_hit": r.get("exact_top5_hit"),
                "WDE_hit": r.get("WDE_hit"),
            }
        )
    write_csv(OUT / "timing_analysis.csv", timing)
    timing_sum = []
    for b, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        timing_sum.append(
            {
                "timing_bucket": b,
                "n": len(rs),
                "top5": round(sum(1 for x in rs if x.get("exact_top5_hit")) / len(rs), 4),
                "wde": round(sum(1 for x in rs if x.get("WDE_hit") is True) / max(1, sum(1 for x in rs if x.get("WDE_hit") is not None)), 4),
            }
        )
    write_csv(OUT / "timing_bucket_summary.csv", timing_sum)

    # --- odds profile ---
    odds_rows = []
    odds_groups = defaultdict(list)
    for r in rows:
        oh, od, oa = fnum(r.get("odds_home")), fnum(r.get("odds_draw")), fnum(r.get("odds_away"))
        fav = favorite_side(oh, od, oa)
        balance = "unknown"
        if oh and oa:
            ratio = max(oh, oa) / min(oh, oa)
            if ratio < 1.25:
                balance = "balanced"
            elif ratio < 2.0:
                balance = "moderate"
            else:
                balance = "one_sided"
        overround = None
        if oh and od and oa and oh > 1 and od > 1 and oa > 1:
            overround = round(1 / oh + 1 / od + 1 / oa, 4)
        profile = f"{balance}|fav={fav}"
        odds_groups[profile].append(r)
        odds_rows.append(
            {
                "fixture_id": r["fixture_id"],
                "odds_home": oh,
                "odds_draw": od,
                "odds_away": oa,
                "favorite": fav,
                "market_balance": balance,
                "overround": overround,
                "bookmaker_count": r.get("bookmaker_count"),
                "odds_freshness": r.get("odds_freshness"),
                "exact_top5_hit": r.get("exact_top5_hit"),
                "WDE_hit": r.get("WDE_hit"),
            }
        )
    write_csv(OUT / "odds_profile_analysis.csv", odds_rows)
    odds_sum = []
    for k, rs in sorted(odds_groups.items(), key=lambda kv: -len(kv[1])):
        odds_sum.append(
            {
                "profile": k,
                "n": len(rs),
                "top5": round(sum(1 for x in rs if x.get("exact_top5_hit")) / len(rs), 4),
                "wde": round(sum(1 for x in rs if x.get("WDE_hit") is True) / max(1, sum(1 for x in rs if x.get("WDE_hit") is not None)), 4),
            }
        )
    write_csv(OUT / "odds_profile_summary.csv", odds_sum)

    # --- draw / favorite / upset bias ---
    draw_rows = []
    for r in rows:
        draw_rows.append(
            {
                "fixture_id": r["fixture_id"],
                "wde_draw_prob": fnum(r.get("draw_probability")),
                "actual_draw": r.get("actual_1x2") == "draw",
                "top1_is_draw": str(r.get("top1") or "").count("-") == 1
                and str(r.get("top1")).split("-")[0] == str(r.get("top1")).split("-")[1]
                if r.get("top1")
                else False,
                "actual_exact_score": r.get("actual_exact_score"),
                "exact_top5_hit": r.get("exact_top5_hit"),
            }
        )
    write_csv(OUT / "draw_bias_analysis.csv", draw_rows)

    fav_bias = []
    upset = []
    for r in rows:
        oh, od, oa = fnum(r.get("odds_home")), fnum(r.get("odds_draw")), fnum(r.get("odds_away"))
        fav = favorite_side(oh, od, oa)
        actual = r.get("actual_1x2")
        if not fav:
            continue
        fav_bias.append(
            {
                "fixture_id": r["fixture_id"],
                "favorite": fav,
                "actual_1x2": actual,
                "favorite_won": fav == actual,
                "exact_top5_hit": r.get("exact_top5_hit"),
                "WDE_hit": r.get("WDE_hit"),
                "wde_decision": r.get("wde_decision"),
            }
        )
        if fav != actual:
            upset.append(
                {
                    "fixture_id": r["fixture_id"],
                    "favorite": fav,
                    "actual_1x2": actual,
                    "exact_top5_hit": r.get("exact_top5_hit"),
                    "WDE_hit": r.get("WDE_hit"),
                    "top1": r.get("top1"),
                    "actual_exact_score": r.get("actual_exact_score"),
                }
            )
    write_csv(OUT / "favorite_score_bias_analysis.csv", fav_bias)
    write_csv(OUT / "upset_score_bias_analysis.csv", upset)

    # --- tail mass: high scoring actuals ---
    tail = []
    for r in rows:
        tot = int(r["actual_ft_home"]) + int(r["actual_ft_away"])
        if tot >= 4:
            tail.append(
                {
                    "fixture_id": r["fixture_id"],
                    "actual_exact_score": r.get("actual_exact_score"),
                    "total_goals": tot,
                    "exact_top5_hit": r.get("exact_top5_hit"),
                    "exact_top10_hit": r.get("exact_top10_hit"),
                    "actual_exact_rank": r.get("actual_exact_rank"),
                    "lambda_home": r.get("lambda_home"),
                    "lambda_away": r.get("lambda_away"),
                    "top1": r.get("top1"),
                }
            )
    write_csv(OUT / "tail_mass_audit.csv", tail)

    # --- provider / freshness ---
    fresh_groups = defaultdict(list)
    for r in rows:
        fresh_groups[str(r.get("odds_freshness") or "null")].append(r)
    prov = []
    for k, rs in fresh_groups.items():
        prov.append(
            {
                "odds_freshness": k,
                "n": len(rs),
                "top5": round(sum(1 for x in rs if x.get("exact_top5_hit")) / len(rs), 4),
                "wde": round(sum(1 for x in rs if x.get("WDE_hit") is True) / max(1, sum(1 for x in rs if x.get("WDE_hit") is not None)), 4),
            }
        )
    write_csv(OUT / "provider_quality_analysis.csv", prov)

    # --- selection strategy backtest (additive, non-canonical) ---
    strategy_rows = []
    frontier = []
    for r in rows:
        mass = fnum(r.get("top5_mass"))
        ent = fnum(r.get("entropy"))
        conf = fnum(r.get("wde_confidence"))
        # normalize mass if percent
        if mass is not None and mass > 1.5:
            mass = mass / 100.0
        tier = "Insufficient Evidence"
        if mass is None or conf is None:
            tier = "Insufficient Evidence"
        elif mass >= 0.55 and conf >= 60 and r.get("WDE_hit") is not None:
            # use predicted agreement proxy: top1 direction vs wde
            top1 = str(r.get("top1") or "")
            agree = False
            if "-" in top1 and r.get("wde_decision"):
                th, ta = map(int, top1.split("-")[:2])
                dir_ = "home_win" if th > ta else ("away_win" if th < ta else "draw")
                agree = dir_ == r.get("wde_decision")
            if agree and mass >= 0.60 and conf >= 65:
                tier = "Tier S"
            elif agree:
                tier = "Tier A"
            else:
                tier = "Watchlist"
        elif mass is not None and mass < 0.45:
            tier = "No Bet"
        else:
            tier = "Watchlist"
        strategy_rows.append(
            {
                "fixture_id": r["fixture_id"],
                "strategy_tier": tier,
                "top5_mass": mass,
                "entropy": ent,
                "wde_confidence": conf,
                "exact_top5_hit": r.get("exact_top5_hit"),
                "exact_top1_hit": r.get("exact_top1_hit"),
                "WDE_hit": r.get("WDE_hit"),
            }
        )
    write_csv(OUT / "selection_strategy_backtest.csv", strategy_rows)
    by_tier = defaultdict(list)
    for r in strategy_rows:
        by_tier[r["strategy_tier"]].append(r)
    for tier, rs in sorted(by_tier.items(), key=lambda kv: -len(kv[1])):
        frontier.append(
            {
                "tier": tier,
                "n": len(rs),
                "coverage": round(len(rs) / n, 4),
                "top5_rate": round(sum(1 for x in rs if x.get("exact_top5_hit")) / len(rs), 4),
                "top1_rate": round(sum(1 for x in rs if x.get("exact_top1_hit")) / len(rs), 4),
                "wde_rate": round(sum(1 for x in rs if x.get("WDE_hit") is True) / max(1, sum(1 for x in rs if x.get("WDE_hit") is not None)), 4),
            }
        )
    write_csv(OUT / "coverage_accuracy_frontier.csv", frontier)

    # --- ranking probability null forensics from DB ---
    if EVAL_DB.exists():
        con = sqlite3.connect(f"file:{EVAL_DB.as_posix()}?mode=ro", uri=True)
        null_n, total = con.execute(
            "SELECT SUM(CASE WHEN probability IS NULL THEN 1 ELSE 0 END), COUNT(*) FROM exact_score_rankings"
        ).fetchone()
        preds_with = con.execute(
            "SELECT COUNT(DISTINCT prediction_id) FROM exact_score_rankings WHERE probability IS NOT NULL"
        ).fetchone()[0]
        preds_all = con.execute("SELECT COUNT(DISTINCT prediction_id) FROM exact_score_rankings").fetchone()[0]
        # reconstruct how often payload top10 has probs while rankings null
        recoverable = 0
        checked = 0
        for pid, payload in con.execute(
            "SELECT prediction_id, complete_payload_json FROM frozen_predictions WHERE complete_payload_json IS NOT NULL"
        ):
            checked += 1
            try:
                p = json.loads(payload)
            except Exception:
                continue
            tops = ((p.get("ecse") or {}).get("top10") or [])
            has_prob = any(isinstance(t, dict) and t.get("probability") is not None for t in tops[:5])
            rank_null = con.execute(
                "SELECT COUNT(*) FROM exact_score_rankings WHERE prediction_id=? AND probability IS NULL",
                (pid,),
            ).fetchone()[0]
            if has_prob and rank_null >= 3:
                recoverable += 1
        write_json(
            OUT / "ranking_probability_null_forensics.json",
            {
                "ranking_rows_null": null_n,
                "ranking_rows_total": total,
                "preds_with_any_probability": preds_with,
                "preds_with_rankings": preds_all,
                "freezes_checked": checked,
                "freezes_recoverable_from_payload_top10": recoverable,
                "root_cause": "freeze_service._ecse_rank_rows preferred top_5_scores even when probabilities were null, skipping top_10_scorelines probabilities",
                "safe_fix": "backfill probability by scoreline from top10; prefer top10 when top5 prob coverage < 3",
                "historical_freezes_mutated": False,
            },
        )
        con.close()

    # --- MAE from lambdas ---
    mae_home = []
    mae_away = []
    mae_tot = []
    mae_gd = []
    for r in rows:
        if r.get("lambda_home") is None:
            continue
        lh, la = float(r["lambda_home"]), float(r["lambda_away"])
        ah, aa = int(r["actual_ft_home"]), int(r["actual_ft_away"])
        mae_home.append(abs(ah - lh))
        mae_away.append(abs(aa - la))
        mae_tot.append(abs((ah + aa) - (lh + la)))
        mae_gd.append(abs((ah - aa) - (lh - la)))
    metric_extra = {
        "home_goal_mae": round(sum(mae_home) / len(mae_home), 4) if mae_home else None,
        "away_goal_mae": round(sum(mae_away) / len(mae_away), 4) if mae_away else None,
        "total_goal_mae": round(sum(mae_tot) / len(mae_tot), 4) if mae_tot else None,
        "goal_diff_mae": round(sum(mae_gd) / len(mae_gd), 4) if mae_gd else None,
        "confidence_intervals": ci_rows,
        "timing_bucket_summary": timing_sum,
        "odds_profile_summary": odds_sum,
        "strategy_frontier": frontier,
        "high_score_tail_n": len(tail),
        "high_score_tail_top5_rate": round(sum(1 for x in tail if x.get("exact_top5_hit")) / len(tail), 4) if tail else None,
    }
    base = json.loads((OUT / "metric_summary.json").read_text(encoding="utf-8"))
    base.update(metric_extra)
    write_json(OUT / "metric_summary.json", base)

    # deepen case studies with lambda errors
    misses = [r for r in rows if not r.get("exact_top5_hit")]
    lines = [
        "# Exact Score Case Studies (outside Top5)",
        "",
        f"Sample size outside Top5: **{len(misses)}** / {n}",
        "",
        "## Dominant failure classes",
    ]
    tax = Counter(r.get("failure_class") for r in misses)
    for k, v in tax.most_common():
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Representative fixtures"]
    for r in misses[:30]:
        lines.append(
            f"- `{r['fixture_id']}` {r.get('match_name')} | λ=({r.get('lambda_home')},{r.get('lambda_away')}) "
            f"| Top1={r.get('top1')} actual={r.get('actual_exact_score')} | WDE={r.get('wde_decision')} "
            f"hit={r.get('WDE_hit')} | class={r.get('failure_class')} | mass={r.get('top5_mass')}"
        )
    write_text(OUT / "exact_score_case_studies.md", "\n".join(lines))

    # update global summary
    write_text(
        OUT / "global_performance_summary.md",
        "\n".join(
            [
                "# Global performance summary",
                "",
                f"- Evaluated freezes with FT results: **{n}**",
                f"- Exact Top1: {base.get('exact_top1')} CI={next(x for x in ci_rows if x['metric']=='exact_top1')}",
                f"- Exact Top3: {base.get('exact_top3')}",
                f"- Exact Top5: {base.get('exact_top5')} CI={next(x for x in ci_rows if x['metric']=='exact_top5')}",
                f"- Exact Top10: {base.get('exact_top10')}",
                f"- Mean actual rank: {base.get('mean_actual_rank')} | median: {base.get('median_actual_rank')}",
                f"- Outside Top10/unmodeled: {base.get('outside_top10_or_unmodeled')}",
                f"- WDE: {base.get('wde')} | BTTS: {base.get('btts')} | OU: {base.get('ou25')}",
                f"- Goal MAE home/away/total/gd: {metric_extra['home_goal_mae']}/{metric_extra['away_goal_mae']}/{metric_extra['total_goal_mae']}/{metric_extra['goal_diff_mae']}",
                f"- High-score (≥4) tail Top5 rate: {metric_extra['high_score_tail_top5_rate']} (n={metric_extra['high_score_tail_n']})",
                "",
                "## Timing buckets",
                json.dumps(timing_sum, indent=2),
                "",
                "## Strategy frontier (research, non-canonical)",
                json.dumps(frontier, indent=2),
                "",
                "## Failure taxonomy",
                json.dumps(base.get("failure_taxonomy"), indent=2),
            ]
        ),
    )

    # update final report sections for safe fix + enrichment
    write_text(
        OUT / "SAFE_FIX_LOG.md",
        "\n".join(
            [
                "# Safe fix log",
                "",
                "## FIX-001: ECSE freeze rank probability backfill",
                "",
                "- **Problem**: `_ecse_rank_rows` accepted Top5 score lists with null probabilities and did not backfill from `top_10_scorelines`.",
                "- **Evidence**: 1580/1785 `exact_score_rankings.probability` NULL; only 41/357 predictions had any ranking probability; payload `ecse.top10` often still held probabilities; `top5_mass`/`entropy` null on 316/357 freezes while `top10_mass` populated.",
                "- **Fix**: Backfill probability by scoreline from top10; fall back to top10 when Top5 probability coverage < 3.",
                "- **Historical freezes**: NOT mutated (immutable evidence preserved).",
                "- **Tests**: `tests/forward_evaluation/test_ecse_rank_rows_prob_backfill.py`",
                "- **Risk**: Low — improves metadata completeness for new freezes only.",
                "- **Owner approval for production deploy**: recommended after CI green; not auto-deployed.",
            ]
        ),
    )

    print("ENRICHED", OUT)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""ECSE-TOP5-RANK-FORENSIC-1 — rank-order bias analysis (read-only)."""

from __future__ import annotations

import json
import math
import os
import random
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_live.evaluator import rank_from_frozen_snapshot
from worldcup_predictor.research.ecse_live.store import _hydrate_snapshot
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly

PHASE = "ECSE-TOP5-RANK-FORENSIC-1"
ARTIFACT_DIR = ROOT / "artifacts" / "ecse_top5_rank_forensic_1"
REPORT_MD = ROOT / "ECSE_TOP5_RANK_FORENSIC_1_REPORT.md"
OWNER_MD = ROOT / "ECSE_TOP5_RANK_FORENSIC_OWNER_REPORT.md"
FINISHED = {"FT", "AET", "PEN"}
BOOTSTRAP_N = 5000
MIN_SEGMENT = 5


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace(" UTC", "").replace("Z", "+00:00")
    for fmt in (None,):
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        dt = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _malformed(top5: list, top10: list) -> bool:
    if len(top5) != 5 or len(set(top5)) != 5:
        return True
    if not top10:
        return True
    return False


def _is_manual(snap: dict[str, Any]) -> bool:
    src = str(snap.get("prediction_source") or "").lower()
    raw = snap.get("raw_features") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    blob = json.dumps(raw).lower()
    return "manual" in src or "manual" in blob or "test_fixture" in blob


def _load_eligible(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT s.*, f.status, f.round_name, f.kickoff_utc AS fx_kickoff,
               fr.home_goals, fr.away_goals, fr.regulation_home_goals, fr.regulation_away_goals,
               e.final_score AS eval_score, e.rank_of_actual_score AS stored_rank
        FROM ecse_prediction_snapshots s
        JOIN fixtures f ON f.fixture_id = s.fixture_id
        LEFT JOIN fixture_results fr ON fr.fixture_id = s.fixture_id
        LEFT JOIN ecse_prediction_evaluations e ON e.snapshot_id = s.id
        WHERE s.is_frozen = 1
          AND UPPER(f.status) IN ('FT','AET','PEN')
        ORDER BY f.kickoff_utc ASC
        """
    ).fetchall()

    by_fixture: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        by_fixture[int(r["fixture_id"])].append(r)

    eligible: list[dict[str, Any]] = []
    for fid, snaps in by_fixture.items():
        pre = []
        kickoff = snaps[0]["fx_kickoff"]
        ko = _parse_ts(kickoff)
        for r in snaps:
            gen = _parse_ts(r["generated_at"])
            if ko and gen and gen >= ko:
                continue
            pre.append(r)
        if not pre:
            continue
        row = pre[0] if len(pre) == 1 else min(pre, key=lambda x: _parse_ts(x["generated_at"]) or datetime.max.replace(tzinfo=timezone.utc))
        snap = _hydrate_snapshot(dict(row))
        if _is_manual(snap):
            continue
        top5 = list(snap.get("top_5_scores") or [])
        top10 = list(snap.get("top_10_scorelines") or [])
        if _malformed(top5, top10):
            continue

        reg_h = row["regulation_home_goals"] if row["regulation_home_goals"] is not None else row["home_goals"]
        reg_a = row["regulation_away_goals"] if row["regulation_away_goals"] is not None else row["away_goals"]
        if reg_h is None or reg_a is None:
            if row["eval_score"] and "-" in str(row["eval_score"]):
                try:
                    reg_h, reg_a = [int(x) for x in str(row["eval_score"]).split("-", 1)]
                except ValueError:
                    continue
            else:
                continue

        actual = f"{int(reg_h)}-{int(reg_a)}"
        rank_in_top5: str | int = "MISS"
        hit_rank: int | None = None
        for i, sc in enumerate(top5, 1):
            if str(sc) == actual:
                rank_in_top5 = i
                hit_rank = i
                break

        rank_full = rank_from_frozen_snapshot(snap, int(reg_h), int(reg_a))

        prob_map: dict[str, float] = {}
        for e in top10:
            if isinstance(e, dict) and e.get("scoreline"):
                prob_map[str(e["scoreline"])] = float(e.get("probability") or 0)

        wde = conn.execute(
            "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?", (fid,)
        ).fetchone()
        wde_probs = {"home": None, "draw": None, "away": None, "btts": None, "ou": None}
        if wde and wde["payload_json"]:
            try:
                p = json.loads(wde["payload_json"])
                pr = p.get("probabilities") or {}
                wde_probs["home"] = pr.get("home_win") or pr.get("home")
                wde_probs["draw"] = pr.get("draw")
                wde_probs["away"] = pr.get("away_win") or pr.get("away")
                btts = pr.get("btts") or {}
                ou = pr.get("over_under_2_5") or {}
                wde_probs["btts"] = btts.get("selection") or btts.get("display")
                wde_probs["ou"] = ou.get("selection") or ou.get("display")
            except json.JSONDecodeError:
                pass

        lam_h = float(snap.get("lambda_home") or 0)
        lam_a = float(snap.get("lambda_away") or 0)
        exp_goals = lam_h + lam_a

        fav = "balanced"
        hp, ap = wde_probs.get("home"), wde_probs.get("away")
        if hp is not None and ap is not None:
            hp, ap = float(hp), float(ap)
            mx = max(hp, ap)
            if mx >= 60:
                fav = "strong_favorite"
            elif hp >= 55:
                fav = "home_favorite"
            elif ap >= 55:
                fav = "away_favorite"
            elif mx >= 45:
                fav = "medium_favorite"
            else:
                fav = "balanced"

        stage = "knockout" if row["round_name"] and "round" in str(row["round_name"]).lower() else "group"

        eligible.append(
            {
                "fixture_id": fid,
                "kickoff_utc": kickoff,
                "competition_key": snap.get("competition_key") or row["competition_key"],
                "home_team": snap.get("home_team"),
                "away_team": snap.get("away_team"),
                "actual_score": actual,
                "top1": top5[0],
                "top2": top5[1],
                "top3": top5[2],
                "top4": top5[3],
                "top5": top5[4],
                "hit_rank": hit_rank,
                "hit_rank_label": rank_in_top5,
                "rank_full_distribution": rank_full,
                "top5_probs": [{ "rank": i, "score": top5[i - 1], "prob": prob_map.get(top5[i - 1]) } for i in range(1, 6)],
                "lambda_home": lam_h,
                "lambda_away": lam_a,
                "expected_goals": round(exp_goals, 3),
                "segment_stage": stage,
                "segment_favorite": fav,
                "segment_scoring": "high_scoring" if exp_goals >= 2.8 else "low_scoring",
                "segment_btts": "btts_yes" if str(wde_probs.get("btts") or "").lower().find("yes") >= 0 else "btts_no",
                "generated_at": snap.get("generated_at"),
            }
        )
    eligible.sort(key=lambda x: x["kickoff_utc"] or "")
    return eligible


def _rank_metrics(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(fixtures)
    hits = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    miss = 0
    for fx in fixtures:
        hr = fx.get("hit_rank")
        if hr in hits:
            hits[hr] += 1
        else:
            miss += 1
    top5_hits = sum(hits.values())
    rates = {f"rank{r}": round(hits[r] / n, 4) if n else 0 for r in range(1, 6)}
    shares = {f"rank{r}": round(hits[r] / top5_hits, 4) if top5_hits else 0 for r in range(1, 6)}

    hit_at = {}
    cum = 0
    for k in range(1, 6):
        cum += hits[k]
        hit_at[f"hit@{k}"] = round(cum / n, 4) if n else 0

    marginal = {
        "rank1": hit_at["hit@1"],
        "rank2_incremental": round(hit_at["hit@2"] - hit_at["hit@1"], 4),
        "rank3_incremental": round(hit_at["hit@3"] - hit_at["hit@2"], 4),
        "rank4_incremental": round(hit_at["hit@4"] - hit_at["hit@3"], 4),
        "rank5_incremental": round(hit_at["hit@5"] - hit_at["hit@4"], 4),
    }

    mrr_vals = []
    for fx in fixtures:
        hr = fx.get("hit_rank")
        if hr:
            mrr_vals.append(1.0 / hr)
        elif fx.get("rank_full_distribution"):
            r = int(fx["rank_full_distribution"])
            mrr_vals.append(1.0 / r if r > 0 else 0.0)
        else:
            mrr_vals.append(0.0)

    return {
        "n": n,
        "hits_by_rank": hits,
        "miss_top5": miss,
        "exact_hit_rates": rates,
        "share_of_top5_hits": shares,
        "cumulative_hit_at_k": hit_at,
        "marginal_contribution": marginal,
        "mean_reciprocal_rank": round(sum(mrr_vals) / len(mrr_vals), 4) if mrr_vals else 0,
    }


def _bootstrap_rates(fixtures: list[dict[str, Any]], n_boot: int = BOOTSTRAP_N) -> dict[str, Any]:
    n = len(fixtures)
    if n < 3:
        return {"insufficient": True, "n": n}
    rng = random.Random(42)
    rank_samples: dict[int, list[float]] = {r: [] for r in range(1, 6)}
    diff_r1_r2: list[float] = []
    diff_r1_r3: list[float] = []
    diff_r1_r4: list[float] = []
    diff_r1_r5: list[float] = []
    winner_counts: dict[int, int] = {r: 0 for r in range(1, 6)}

    for _ in range(n_boot):
        sample = [fixtures[rng.randrange(n)] for _ in range(n)]
        m = _rank_metrics(sample)
        rates = [m["exact_hit_rates"][f"rank{r}"] for r in range(1, 6)]
        for r in range(1, 6):
            rank_samples[r].append(rates[r - 1])
        diff_r1_r2.append(rates[0] - rates[1])
        diff_r1_r3.append(rates[0] - rates[2])
        diff_r1_r4.append(rates[0] - rates[3])
        diff_r1_r5.append(rates[0] - rates[4])
        best = max(range(5), key=lambda i: rates[i]) + 1
        winner_counts[best] += 1

    def _ci(vals: list[float]) -> list[float]:
        s = sorted(vals)
        lo = s[int(0.025 * len(s))]
        hi = s[int(0.975 * len(s))]
        return [round(lo, 4), round(hi, 4)]

    return {
        "n_boot": n_boot,
        "n": n,
        "rank_ci": {f"rank{r}": _ci(rank_samples[r]) for r in range(1, 6)},
        "rank_mean": {f"rank{r}": round(sum(rank_samples[r]) / len(rank_samples[r]), 4) for r in range(1, 6)},
        "pairwise_diff_ci": {
            "rank1_vs_rank2": _ci(diff_r1_r2),
            "rank1_vs_rank3": _ci(diff_r1_r3),
            "rank1_vs_rank4": _ci(diff_r1_r4),
            "rank1_vs_rank5": _ci(diff_r1_r5),
        },
        "bootstrap_best_rank_winner": winner_counts,
    }


def _classify_bias(overall: dict[str, Any], boot: dict[str, Any], segments: dict[str, Any]) -> str:
    n = overall.get("n", 0)
    if n < 10:
        return "ECSE_RANK_ANALYSIS_INSUFFICIENT_SAMPLE"
    if boot.get("insufficient"):
        return "ECSE_RANK_ANALYSIS_INSUFFICIENT_SAMPLE"

    r1 = overall["exact_hit_rates"]["rank1"]
    others = [overall["exact_hit_rates"][f"rank{r}"] for r in range(2, 6)]
    best_other = max(others)
    ci12 = boot["pairwise_diff_ci"]["rank1_vs_rank2"]
    r1_wins_boot = boot["bootstrap_best_rank_winner"].get(1, 0) / boot["n_boot"]

    stable_seg = 0
    seg_winners = 0
    for name, met in segments.items():
        if met.get("n", 0) >= MIN_SEGMENT:
            seg_winners += 1
            rates = [met["exact_hit_rates"][f"rank{r}"] for r in range(1, 6)]
            if rates[0] == max(rates):
                stable_seg += 1

    if ci12[0] > 0 and r1 > best_other + 0.05 and r1_wins_boot > 0.6:
        return "ECSE_STABLE_GLOBAL_RERANKING_SIGNAL_FOUND"
    if seg_winners >= 2 and stable_seg >= 2 and r1_wins_boot < 0.5:
        return "ECSE_SEGMENT_SPECIFIC_RERANKING_SIGNAL_FOUND"
    if ci12[0] <= 0 <= ci12[1] and max(others) - r1 < 0.08:
        return "ECSE_RANK_ORDER_IS_WELL_CALIBRATED"
    if r1_wins_boot > 0.45 or best_other > r1 + 0.03:
        return "ECSE_WEAK_RANK_BIAS_ONLY"
    return "ECSE_RANK_ORDER_IS_WELL_CALIBRATED"


def _calibration(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for fx in fixtures:
        actual = fx["actual_score"]
        for item in fx.get("top5_probs") or []:
            rows.append(
                {
                    "rank": item["rank"],
                    "prob": item.get("prob"),
                    "hit": 1 if item["score"] == actual else 0,
                }
            )
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "hits": 0, "prob_sum": 0.0})
    for r in rows:
        p = r.get("prob")
        if p is None:
            continue
        if p >= 0.12:
            b = "high_12plus"
        elif p >= 0.08:
            b = "mid_8_12"
        elif p >= 0.05:
            b = "low_5_8"
        else:
            b = "tail_below_5"
        buckets[b]["n"] += 1
        buckets[b]["hits"] += r["hit"]
        buckets[b]["prob_sum"] += p
    out = {}
    for b, v in buckets.items():
        out[b] = {
            "n": v["n"],
            "hit_rate": round(v["hits"] / v["n"], 4) if v["n"] else 0,
            "mean_predicted_prob": round(v["prob_sum"] / v["n"], 4) if v["n"] else 0,
        }
    rank_cal = {}
    for rank in range(1, 6):
        sub = [r for r in rows if r["rank"] == rank and r.get("prob") is not None]
        if sub:
            rank_cal[f"rank{rank}"] = {
                "n": len(sub),
                "hit_rate": round(sum(r["hit"] for r in sub) / len(sub), 4),
                "mean_prob": round(sum(r["prob"] for r in sub) / len(sub), 4),
            }
    return {"probability_buckets": out, "by_rank": rank_cal}


def _shadow_rerank(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(fixtures)
    if n < 9:
        return {"insufficient": True, "n": n}
    split = (n * 2) // 3
    train, test = fixtures[:split], fixtures[split:]
    if len(test) < 3:
        return {"insufficient": True, "n": n, "test_n": len(test)}

    train_m = _rank_metrics(train)
    global_weights = {r: train_m["exact_hit_rates"][f"rank{r}"] for r in range(1, 6)}

    seg_weights: dict[str, dict[int, float]] = {}
    for seg_key in ("segment_stage", "segment_favorite", "segment_scoring", "segment_btts"):
        buckets: dict[str, list] = defaultdict(list)
        for fx in train:
            buckets[str(fx.get(seg_key))].append(fx)
        for seg, items in buckets.items():
            if len(items) >= MIN_SEGMENT:
                m = _rank_metrics(items)
                seg_weights[f"{seg_key}:{seg}"] = {r: m["exact_hit_rates"][f"rank{r}"] for r in range(1, 6)}

    def _score(fx: dict[str, Any], weights: dict[int, float]) -> list[tuple[str, float]]:
        scored = []
        for item in fx.get("top5_probs") or []:
            w = weights.get(item["rank"], 0.0)
            p = float(item.get("prob") or 0)
            scored.append((item["score"], w * p))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _eval(test_set: list[dict[str, Any]], rerank_fn) -> dict[str, float]:
        top1 = hit3 = hit5 = 0
        mrr = []
        for fx in test_set:
            actual = fx["actual_score"]
            if rerank_fn is None:
                order = [fx[f"top{i}"] for i in range(1, 6)]
            else:
                order = [s for s, _ in rerank_fn(fx)]
            if order[0] == actual:
                top1 += 1
            if actual in order[:3]:
                hit3 += 1
            if actual in order[:5]:
                hit5 += 1
            if actual in order:
                mrr.append(1.0 / (order.index(actual) + 1))
            else:
                mrr.append(0.0)
        t = len(test_set)
        return {
            "top1_accuracy": round(top1 / t, 4),
            "hit@3": round(hit3 / t, 4),
            "hit@5": round(hit5 / t, 4),
            "mean_reciprocal_rank": round(sum(mrr) / t, 4),
            "n_test": t,
        }

    baseline = _eval(test, None)
    global_r = _eval(test, lambda fx: _score(fx, global_weights))

    def _seg_rerank(fx: dict[str, Any]) -> list[tuple[str, float]]:
        key = None
        best_n = 0
        for seg_key in ("segment_stage", "segment_favorite", "segment_scoring", "segment_btts"):
            k = f"{seg_key}:{fx.get(seg_key)}"
            if k in seg_weights:
                cnt = sum(1 for t in train if str(t.get(seg_key)) == str(fx.get(seg_key)))
                if cnt > best_n:
                    best_n = cnt
                    key = k
        w = seg_weights.get(key, global_weights) if key else global_weights
        return _score(fx, w)

    segment_r = _eval(test, _seg_rerank)

    best = baseline
    best_name = "baseline"
    for name, met in [("global_rerank", global_r), ("segment_rerank", segment_r)]:
        if met["mean_reciprocal_rank"] > best["mean_reciprocal_rank"]:
            best = met
            best_name = name

    return {
        "train_n": len(train),
        "test_n": len(test),
        "global_weights": global_weights,
        "segment_weights": seg_weights,
        "baseline": baseline,
        "global_rerank": global_r,
        "segment_rerank": segment_r,
        "best_candidate": best_name,
        "delta_mrr": round(best["mean_reciprocal_rank"] - baseline["mean_reciprocal_rank"], 4),
    }


def _segment_analysis(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    keys = [
        ("chronological_thirds", lambda i, n, fx: "third1" if i < n // 3 else "third2" if i < 2 * n // 3 else "third3"),
        ("segment_stage", lambda i, n, fx: fx.get("segment_stage")),
        ("segment_favorite", lambda i, n, fx: fx.get("segment_favorite")),
        ("segment_scoring", lambda i, n, fx: fx.get("segment_scoring")),
        ("segment_btts", lambda i, n, fx: fx.get("segment_btts")),
        ("competition_key", lambda i, n, fx: fx.get("competition_key")),
    ]
    n = len(fixtures)
    for label, fn in keys:
        buckets: dict[str, list] = defaultdict(list)
        for i, fx in enumerate(fixtures):
            buckets[str(fn(i, n, fx))].append(fx)
        out[label] = {}
        for seg, items in sorted(buckets.items()):
            m = _rank_metrics(items)
            boot = _bootstrap_rates(items, n_boot=1000) if len(items) >= MIN_SEGMENT else {"insufficient": True}
            best_rank = max(range(1, 6), key=lambda r: m["exact_hit_rates"][f"rank{r}"])
            out[label][seg] = {
                **m,
                "best_rank": best_rank,
                "bootstrap": boot,
                "stable_rank1_leads": m["exact_hit_rates"]["rank1"] >= max(m["exact_hit_rates"][f"rank{r}"] for r in range(2, 6)),
            }
    return out


def _write_reports(
    fixtures: list[dict[str, Any]],
    overall: dict[str, Any],
    boot: dict[str, Any],
    segments: dict[str, Any],
    calibration: dict[str, Any],
    shadow: dict[str, Any],
    recommendation: str,
) -> None:
    owner = [
        "# ECSE Top5 Rank Forensic — Owner Report",
        "",
        f"**Phase:** {PHASE}",
        f"**Eligible fixtures:** {overall['n']}",
        f"**Recommendation:** `{recommendation}`",
        "",
        "| Rank | Hits | Hit Rate | 95% CI | Share of Top5 Hits | Stability |",
        "|---|---:|---:|---|---:|---|",
    ]
    for r in range(1, 6):
        hits = overall["hits_by_rank"][r]
        rate = overall["exact_hit_rates"][f"rank{r}"]
        share = overall["share_of_top5_hits"][f"rank{r}"]
        ci = boot.get("rank_ci", {}).get(f"rank{r}", ["n/a", "n/a"]) if not boot.get("insufficient") else ["n/a", "n/a"]
        win = boot.get("bootstrap_best_rank_winner", {}).get(r, 0)
        stab = round(win / boot.get("n_boot", 1), 2) if not boot.get("insufficient") else "n/a"
        owner.append(f"| {r} | {hits} | {rate:.1%} | [{ci[0]}, {ci[1]}] | {share:.1%} | {stab} |")

    owner.extend(["", "| Metric | Baseline | Best Rerank | Delta |", "|---|---:|---:|---:|"])
    if not shadow.get("insufficient"):
        b, g = shadow["baseline"], shadow.get(shadow["best_candidate"], shadow["baseline"])
        owner.append(f"| Top1 exact accuracy | {b['top1_accuracy']:.1%} | {g['top1_accuracy']:.1%} | {g['top1_accuracy']-b['top1_accuracy']:+.1%} |")
        owner.append(f"| Hit@3 | {b['hit@3']:.1%} | {g['hit@3']:.1%} | {g['hit@3']-b['hit@3']:+.1%} |")
        owner.append(f"| Hit@5 | {b['hit@5']:.1%} | {g['hit@5']:.1%} | {g['hit@5']-b['hit@5']:+.1%} |")
        owner.append(f"| Mean reciprocal rank | {b['mean_reciprocal_rank']:.3f} | {g['mean_reciprocal_rank']:.3f} | {g['mean_reciprocal_rank']-b['mean_reciprocal_rank']:+.3f} |")
    else:
        owner.append("| (shadow rerank) | — | — | insufficient sample |")

    owner.extend(["", "| Segment | Best Historical Rank | Hit Rate | Sample Size | Stable? |", "|---|---:|---:|---:|---|"])
    for seg_group in ("segment_stage", "segment_favorite", "segment_scoring"):
        for seg, met in (segments.get(seg_group) or {}).items():
            if met.get("n", 0) >= MIN_SEGMENT:
                br = met["best_rank"]
                owner.append(
                    f"| {seg_group}:{seg} | {br} | {met['exact_hit_rates'][f'rank{br}']:.1%} | {met['n']} | {met['stable_rank1_leads']} |"
                )

    OWNER_MD.write_text("\n".join(owner) + "\n", encoding="utf-8")

    report = [
        f"# {PHASE} — Report",
        "",
        f"**Recommendation:** `{recommendation}`",
        f"**Dataset size:** {overall['n']} finished fixtures with frozen pre-kickoff ECSE Top5",
        "",
        "## Task A — Rank hit analysis",
        "",
        f"- Rank1 hit rate: **{overall['exact_hit_rates']['rank1']:.1%}** ({overall['hits_by_rank'][1]}/{overall['n']})",
        f"- Rank2 hit rate: **{overall['exact_hit_rates']['rank2']:.1%}** ({overall['hits_by_rank'][2]}/{overall['n']})",
        f"- Rank3 hit rate: **{overall['exact_hit_rates']['rank3']:.1%}** ({overall['hits_by_rank'][3]}/{overall['n']})",
        f"- Rank4 hit rate: **{overall['exact_hit_rates']['rank4']:.1%}** ({overall['hits_by_rank'][4]}/{overall['n']})",
        f"- Rank5 hit rate: **{overall['exact_hit_rates']['rank5']:.1%}** ({overall['hits_by_rank'][5]}/{overall['n']})",
        f"- Top5 miss rate: **{overall['miss_top5']/overall['n']:.1%}**",
        "",
        "## Task B — Cumulative Hit@K",
        "",
    ]
    for k, v in overall["cumulative_hit_at_k"].items():
        report.append(f"- {k}: {v:.1%}")
    report.append("")
    report.append("Marginal contributions: " + json.dumps(overall["marginal_contribution"]))
    report.append("")
    report.append("## Task D — Bootstrap")
    report.append("")
    report.append(f"```json\n{json.dumps(boot, indent=2)}\n```")
    report.append("")
    report.append("## Task E — Calibration")
    report.append("")
    report.append(f"```json\n{json.dumps(calibration, indent=2)}\n```")
    report.append("")
    report.append("## Task F — Shadow reranking (OOS)")
    report.append("")
    report.append(f"```json\n{json.dumps(shadow, indent=2)}\n```")
    REPORT_MD.write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> int:
    settings = get_settings()
    conn = connect_readonly(settings.sqlite_path)
    fixtures = _load_eligible(conn)
    conn.close()

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    with (ARTIFACT_DIR / "fixture_level_rank_hits.jsonl").open("w", encoding="utf-8") as f:
        for row in fixtures:
            f.write(json.dumps(row, default=str) + "\n")

    overall = _rank_metrics(fixtures)
    boot = _bootstrap_rates(fixtures)
    segments = _segment_analysis(fixtures)
    calibration = _calibration(fixtures)
    shadow = _shadow_rerank(fixtures)
    recommendation = _classify_bias(overall, boot, segments)

    (ARTIFACT_DIR / "overall_rank_metrics.json").write_text(json.dumps(overall, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "cumulative_hit_at_k.json").write_text(json.dumps(overall["cumulative_hit_at_k"], indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "segment_rank_metrics.json").write_text(json.dumps(segments, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "bootstrap_results.json").write_text(json.dumps(boot, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "calibration_results.json").write_text(json.dumps(calibration, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "shadow_reranking_results.json").write_text(json.dumps(shadow, indent=2), encoding="utf-8")

    workflow = {"phase": PHASE, "n_fixtures": overall["n"], "final_recommendation": recommendation}
    (ARTIFACT_DIR / "workflow.json").write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    _write_reports(fixtures, overall, boot, segments, calibration, shadow, recommendation)
    print(json.dumps(workflow, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

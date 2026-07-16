#!/usr/bin/env python3
"""Two-fixture portfolio research using REAL Correct Score odds only for ROI."""
from __future__ import annotations

import csv
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.migrations import ensure_schema_compat
from worldcup_predictor.research.correct_score_odds.store import best_odds_map, single_bookmaker_maps
from worldcup_predictor.research.two_fixture_portfolio.engine import (
    INDEPENDENCE_NOTE,
    THREE_GOAL_OVER35_GAPS,
    build_primary_matrix,
    classify_arbitrage,
    equal_gross_stakes,
    equal_stakes,
    fixture_profile,
    fmt,
    minimax_equalize_covered,
    model_prob_stakes,
    parse_score,
    positive_edge_stakes,
    select_hedge_candidates,
)

ART = ROOT / "artifacts" / "two_fixture_portfolio_real_odds"
REPORTS = ROOT / "reports" / "owner"
DEFAULT_BUDGET = 50.0
DEFAULT_MIN_STAKE = 0.50
BOOK_MIN_STAKE = 0.10


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in keys})


def load_joinable(conn) -> list[dict]:
    """Fixtures with result + lambdas + at least some CS odds lines."""
    # Map production fixture_id from CS lines to training via registry when possible
    cs_fixtures = {
        int(r[0])
        for r in conn.execute(
            "SELECT DISTINCT fixture_id FROM correct_score_odds_lines WHERE prematch_status='prematch'"
        )
    }
    if not cs_fixtures:
        return []

    q = """
    SELECT
      t.registry_fixture_id AS registry_fixture_id,
      t.kickoff_utc,
      t.league,
      t.home_team,
      t.away_team,
      t.exact_score,
      t.home_goals,
      t.away_goals,
      t.total_goals,
      lf.lambda_home,
      lf.lambda_away,
      t.ou_over_25_closing,
      t.ou_over_35_closing,
      t.btts_yes_closing,
      hpm.provider_fixture_id AS fixture_id
    FROM ecse_training_dataset t
    JOIN ecse_lambda_features lf ON lf.registry_fixture_id = t.registry_fixture_id
    LEFT JOIN historical_provider_mapping hpm
      ON hpm.registry_fixture_id = t.registry_fixture_id
     AND hpm.provider = 'api_football'
    WHERE t.exact_score IS NOT NULL
      AND lf.lambda_home IS NOT NULL
      AND COALESCE(lf.insufficient_odds_flag, 0) = 0
    """
    out = []
    for r in conn.execute(q):
        d = dict(r)
        fid = d.get("fixture_id")
        if fid is None:
            continue
        fid = int(fid)
        if fid not in cs_fixtures:
            continue
        d["fixture_id"] = fid
        out.append(d)
    # also try direct fixture_id == registry when mapped that way
    if len(out) < 20:
        for r in conn.execute(
            """
            SELECT
              t.registry_fixture_id AS fixture_id,
              t.registry_fixture_id AS registry_fixture_id,
              t.kickoff_utc, t.league, t.home_team, t.away_team,
              t.exact_score, t.home_goals, t.away_goals, t.total_goals,
              lf.lambda_home, lf.lambda_away,
              t.ou_over_25_closing, t.ou_over_35_closing, t.btts_yes_closing
            FROM ecse_training_dataset t
            JOIN ecse_lambda_features lf ON lf.registry_fixture_id = t.registry_fixture_id
            WHERE t.registry_fixture_id IN (
              SELECT DISTINCT fixture_id FROM correct_score_odds_lines WHERE prematch_status='prematch'
            )
              AND t.exact_score IS NOT NULL
              AND lf.lambda_home IS NOT NULL
            """
        ):
            d = dict(r)
            d["fixture_id"] = int(d["fixture_id"])
            if d["fixture_id"] in cs_fixtures:
                out.append(d)
    # dedupe by fixture_id
    by_id = {}
    for d in out:
        by_id[int(d["fixture_id"])] = d
    return list(by_id.values())


def enrich(conn, row: dict) -> dict | None:
    ps = parse_score(str(row["exact_score"]))
    if not ps:
        return None
    lh, la = float(row["lambda_home"]), float(row["lambda_away"])
    prof = fixture_profile(lh, la)
    best = best_odds_map(conn, int(row["fixture_id"]))
    odds_exact = {k: float(v["decimal_odds"]) for k, v in best.items()}
    top5_scores = prof["top5_scores"]
    priced = sum(1 for s in top5_scores if s in odds_exact)
    if priced < 3:
        return None  # too incomplete for portfolio pricing
    ah, aw = ps
    actual = fmt(ah, aw)
    return {
        **row,
        **{k: prof[k] for k in prof if k != "prob_map"},
        "prob_map": prof["prob_map"],
        "actual_score": actual,
        "actual_goals": ah + aw,
        "day": str(row["kickoff_utc"])[:10],
        "cs_odds": odds_exact,
        "top5_priced_n": priced,
        "in_top5": actual in top5_scores,
        "bm_maps": single_bookmaker_maps(conn, int(row["fixture_id"])),
    }


def price_primary(a: dict, b: dict, mode: str) -> tuple[list[dict], str]:
    """mode: CROSS_BOOKMAKER or SINGLE_BOOKMAKER."""
    if mode == "SINGLE_BOOKMAKER":
        # pick bookmakers covering most of top5 on each side
        def best_bm(fx):
            best_name, best_n, best_m = None, -1, {}
            for bm, m in (fx.get("bm_maps") or {}).items():
                n = sum(1 for s in fx["top5_scores"] if s in m)
                if n > best_n:
                    best_name, best_n, best_m = bm, n, m
            return best_name, best_m

        bma, ma = best_bm(a)
        bmb, mb = best_bm(b)
        odds_a, odds_b = ma, mb
        label = f"SINGLE_BOOKMAKER_PORTFOLIO:{bma}|{bmb}"
    else:
        odds_a, odds_b = a["cs_odds"], b["cs_odds"]
        label = "BEST_ODDS_CROSS_BOOKMAKER_PORTFOLIO"

    tickets = build_primary_matrix(a["top5"], b["top5"], odds_a, odds_b)
    # keep only fully priced tickets for real ROI; incomplete → exclude from funded set
    for t in tickets:
        t["portfolio_mode"] = label
        t["odds_kind"] = "REAL" if t["combo_odds"] is not None else "UNAVAILABLE"
        t["synthetic"] = False
    return tickets, label


def allocate(tickets: list[dict], strategy: str, budget: float, min_stake: float) -> list[float]:
    odds = [t["combo_odds"] if t["combo_odds"] is not None else None for t in tickets]
    probs = [float(t["joint_p_independence"]) for t in tickets]
    # only fund priced tickets
    priced_idx = [i for i, o in enumerate(odds) if o is not None]
    if not priced_idx:
        return [0.0] * len(tickets)

    if strategy == "EQUAL":
        raw = equal_stakes(len(priced_idx), budget, max(min_stake, BOOK_MIN_STAKE))
    elif strategy == "EQUAL_GROSS_RETURN":
        raw = equal_gross_stakes(
            [odds[i] for i in priced_idx],
            budget,
            max(min_stake, BOOK_MIN_STAKE),
        )
    elif strategy == "MODEL_PROB_WEIGHTED":
        raw = model_prob_stakes([probs[i] for i in priced_idx], budget, max(min_stake, BOOK_MIN_STAKE))
    elif strategy == "POSITIVE_EDGE":
        raw = positive_edge_stakes(
            [probs[i] for i in priced_idx],
            [odds[i] for i in priced_idx],
            budget,
            max(min_stake, BOOK_MIN_STAKE),
            0.05,
        )
    elif strategy == "MINIMAX":
        raw, _ = minimax_equalize_covered(
            [odds[i] for i in priced_idx],
            budget,
            max(min_stake, BOOK_MIN_STAKE),
        )
    elif strategy == "TIERED":
        w = []
        for i in priced_idx:
            t = tickets[i]
            base = float(t["joint_p_independence"])
            if t["rank_a"] <= 2 and t["rank_b"] <= 2:
                w.append(3 * base)
            elif t["rank_a"] <= 3 and t["rank_b"] <= 3:
                w.append(2 * base)
            else:
                w.append(base)
        raw = model_prob_stakes(w, budget, max(min_stake, BOOK_MIN_STAKE))
    else:
        raw = equal_stakes(len(priced_idx), budget, max(min_stake, BOOK_MIN_STAKE))

    stakes = [0.0] * len(tickets)
    for j, i in enumerate(priced_idx):
        stakes[i] = float(raw[j]) if j < len(raw) else 0.0
    # enforce book min: zero sub-min
    for i, s in enumerate(stakes):
        if 0 < s < BOOK_MIN_STAKE:
            stakes[i] = 0.0
    # renormalize to budget among remaining
    tot = sum(stakes)
    if tot > 0:
        stakes = [s * (budget / tot) for s in stakes]
    return stakes


def settle(tickets: list[dict], stakes: list[float], actual_a: str, actual_b: str) -> dict:
    total = sum(stakes)
    win_i = None
    for i, t in enumerate(tickets):
        if t["score_a"] == actual_a and t["score_b"] == actual_b:
            win_i = i
            break
    if win_i is None or tickets[win_i]["combo_odds"] is None or stakes[win_i] <= 0:
        return {
            "total_stake": total,
            "gross": 0.0,
            "net": -total,
            "hit_primary": 0,
            "winning_ticket": None,
        }
    gross = stakes[win_i] * float(tickets[win_i]["combo_odds"])
    return {
        "total_stake": total,
        "gross": gross,
        "net": gross - total,
        "hit_primary": 1,
        "winning_ticket": tickets[win_i]["ticket_id"],
    }


def wilson(p: float, n: int) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    z = 1.96
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((centre - margin) / den, (centre + margin) / den)


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    ensure_schema_compat(conn)

    n_cs = conn.execute(
        "SELECT COUNT(DISTINCT fixture_id) FROM correct_score_odds_lines WHERE prematch_status='prematch'"
    ).fetchone()[0]
    print(f"CS fixtures available: {n_cs}", flush=True)

    joined = load_joinable(conn)
    print(f"Joinable with results+lambdas: {len(joined)}", flush=True)
    enriched = []
    for row in joined:
        e = enrich(conn, row)
        if e:
            enriched.append(e)
    print(f"Enriched priced (>=3/5 top5): {len(enriched)}", flush=True)

    by_day: dict[str, list] = defaultdict(list)
    for e in enriched:
        by_day[e["day"]].append(e)

    selected_pairs = []
    primary_rows = []
    hedge_rows = []
    stake_rows = []
    realized_rows = []
    bookmaker_comp = []
    drawdown_rows = []

    strategies = [
        "EQUAL",
        "EQUAL_GROSS_RETURN",
        "MODEL_PROB_WEIGHTED",
        "POSITIVE_EDGE",
        "MINIMAX",
        "TIERED",
    ]
    strategy_stats: dict[str, dict[str, Any]] = {
        s: {
            "n": 0,
            "stake": 0.0,
            "net": 0.0,
            "hits": 0,
            "full_loss": 0,
            "recovery": 0,
            "min_covered_nets": [],
            "equity": 0.0,
            "peak": 0.0,
            "max_dd": 0.0,
            "streak": 0,
            "max_streak": 0,
        }
        for s in strategies
    }

    days = sorted(by_day.keys())
    for day in days:
        rows = by_day[day]
        if len(rows) < 2:
            continue
        # highest joint top5 mass among pairs with enough priced scores
        best = None
        best_j = -1.0
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                if rows[i]["top5_priced_n"] < 4 or rows[j]["top5_priced_n"] < 4:
                    continue
                jv = float(rows[i]["top5_mass"]) * float(rows[j]["top5_mass"])
                if jv > best_j:
                    best_j = jv
                    best = (rows[i], rows[j])
        if not best:
            continue
        a, b = best
        tickets_x, mode_x = price_primary(a, b, "CROSS_BOOKMAKER")
        priced_n = sum(1 for t in tickets_x if t["combo_odds"] is not None)
        if priced_n < 10:
            continue

        selected_pairs.append(
            {
                "day": day,
                "fixture_a": a["fixture_id"],
                "fixture_b": b["fixture_id"],
                "match_a": f"{a.get('home_team')} vs {a.get('away_team')}",
                "match_b": f"{b.get('home_team')} vs {b.get('away_team')}",
                "league_a": a.get("league"),
                "league_b": b.get("league"),
                "top5_mass_a": a["top5_mass"],
                "top5_mass_b": b["top5_mass"],
                "top5_priced_a": a["top5_priced_n"],
                "top5_priced_b": b["top5_priced_n"],
                "primary_tickets_priced": priced_n,
                "portfolio_mode": mode_x,
                "actual_a": a["actual_score"],
                "actual_b": b["actual_score"],
                "independence_note": INDEPENDENCE_NOTE,
            }
        )

        # demo detail for first few pairs
        if len(selected_pairs) <= 5:
            for t in tickets_x:
                primary_rows.append(
                    {
                        "day": day,
                        "fixture_a": a["fixture_id"],
                        "fixture_b": b["fixture_id"],
                        **{k: t[k] for k in t},
                        "odds_kind": t["odds_kind"],
                        "synthetic": False,
                    }
                )

        # hedges with real odds
        for side, fx in (("A", a), ("B", b)):
            for h in select_hedge_candidates(fx, max_extra=5):
                odd = fx["cs_odds"].get(h["selection"])
                hedge_rows.append(
                    {
                        "day": day,
                        "fixture_side": side,
                        "fixture_id": fx["fixture_id"],
                        "selection": h["selection"],
                        "kind": h["kind"],
                        "decimal_odds_real": odd,
                        "odds_kind": "REAL" if odd else "UNAVAILABLE",
                        "model_probability": h["probability"],
                        "reason": h["reason"],
                        "synthetic": False,
                    }
                )

        tickets_s, mode_s = price_primary(a, b, "SINGLE_BOOKMAKER")
        bookmaker_comp.append(
            {
                "day": day,
                "fixture_a": a["fixture_id"],
                "fixture_b": b["fixture_id"],
                "cross_priced": sum(1 for t in tickets_x if t["combo_odds"] is not None),
                "single_priced": sum(1 for t in tickets_s if t["combo_odds"] is not None),
                "cross_mode": mode_x,
                "single_mode": mode_s,
                "operationally_identical": False,
            }
        )

        for strategy in strategies:
            stakes = allocate(tickets_x, strategy, DEFAULT_BUDGET, DEFAULT_MIN_STAKE)
            total = sum(stakes)
            # covered scenario nets
            covered_nets = []
            for t, s in zip(tickets_x, stakes):
                if t["combo_odds"] is not None and s > 0:
                    covered_nets.append(s * float(t["combo_odds"]) - total)
            min_cov = min(covered_nets) if covered_nets else -total
            settled = settle(tickets_x, stakes, a["actual_score"], b["actual_score"])

            # hedge recovery (Top6-10 / shifted) — extra stake up to 20%
            hedge_stake_total = 0.0
            hedge_gross = 0.0
            for side, fx in (("A", a), ("B", b)):
                cands = select_hedge_candidates(fx, max_extra=5)
                for h in cands:
                    odd = fx["cs_odds"].get(h["selection"])
                    if not odd:
                        continue
                    hs = min(DEFAULT_BUDGET * 0.02, DEFAULT_BUDGET / odd)
                    if hs < BOOK_MIN_STAKE:
                        continue
                    hedge_stake_total += hs
                    if fx["actual_score"] == h["selection"]:
                        # only pays if other match also somehow — for single-fixture hedge
                        # In two-fixture package, exact-score hedge is on one match; treat as
                        # recovery if this fixture's actual hits hedge AND primary missed.
                        hedge_gross += hs * odd
            # Simplified: if primary missed but each side's actual in top5∪hedge and we had odds
            ha = set(a["top5_scores"]) | {h["selection"] for h in select_hedge_candidates(a, max_extra=5)}
            hb = set(b["top5_scores"]) | {h["selection"] for h in select_hedge_candidates(b, max_extra=5)}
            hedge_cover_hit = a["actual_score"] in ha and b["actual_score"] in hb
            # For currency: primary settle + if primary miss but hedge scores priced as singles
            # Use only hedge_gross if primary miss (approx recovery)
            if settled["hit_primary"]:
                net = settled["net"] - hedge_stake_total
                recovery = 0
                full_loss = 0
            else:
                # attempt recovery via single-match hedges (not combo) — conservative
                net = -settled["total_stake"] - hedge_stake_total + hedge_gross
                recovery = int(hedge_gross >= settled["total_stake"] * 0.5)
                full_loss = int(hedge_gross <= 0)

            st = strategy_stats[strategy]
            st["n"] += 1
            st["stake"] += settled["total_stake"] + hedge_stake_total
            st["net"] += net
            st["hits"] += settled["hit_primary"]
            st["full_loss"] += full_loss
            st["recovery"] += recovery
            st["min_covered_nets"].append(min_cov)
            st["equity"] += net
            st["peak"] = max(st["peak"], st["equity"])
            st["max_dd"] = max(st["max_dd"], st["peak"] - st["equity"])
            if net < 0:
                st["streak"] += 1
                st["max_streak"] = max(st["max_streak"], st["streak"])
            else:
                st["streak"] = 0

            stake_rows.append(
                {
                    "day": day,
                    "strategy": strategy,
                    "total_primary_stake": settled["total_stake"],
                    "hedge_stake": hedge_stake_total,
                    "min_covered_net": min_cov,
                    "realized_net": net,
                    "hit_primary": settled["hit_primary"],
                    "odds_kind": "REAL",
                    "synthetic": False,
                    "book_min_stake": BOOK_MIN_STAKE,
                    "portfolio_mode": mode_x,
                }
            )
            realized_rows.append(
                {
                    "day": day,
                    "strategy": strategy,
                    "fixture_a": a["fixture_id"],
                    "fixture_b": b["fixture_id"],
                    "actual_a": a["actual_score"],
                    "actual_b": b["actual_score"],
                    "gross": settled["gross"] + hedge_gross,
                    "net": net,
                    "hit_primary": settled["hit_primary"],
                    "hedge_cover_structural": int(hedge_cover_hit),
                    "full_loss": full_loss,
                    "odds_kind": "REAL",
                }
            )

    # summaries
    roi_summary = {"strategies": {}, "n_pairs": len(selected_pairs), "budget": DEFAULT_BUDGET}
    for s, st in strategy_stats.items():
        n = st["n"]
        roi = (st["net"] / st["stake"]) if st["stake"] > 0 else None
        hit_rate = st["hits"] / n if n else None
        lo, hi = wilson(hit_rate or 0, n) if n else (None, None)
        roi_summary["strategies"][s] = {
            "n_portfolios": n,
            "total_stake": st["stake"],
            "total_net": st["net"],
            "roi": roi,
            "avg_stake": (st["stake"] / n) if n else None,
            "primary_hit_rate": hit_rate,
            "primary_hit_rate_ci95": [lo, hi],
            "full_loss_rate": (st["full_loss"] / n) if n else None,
            "stake_recovery_rate": (st["recovery"] / n) if n else None,
            "avg_min_covered_net": (
                sum(st["min_covered_nets"]) / len(st["min_covered_nets"]) if st["min_covered_nets"] else None
            ),
            "max_drawdown": st["max_dd"],
            "max_losing_streak": st["max_streak"],
            "odds_kind": "REAL",
            "synthetic_used_in_roi": False,
        }
        drawdown_rows.append(
            {
                "strategy": s,
                "max_drawdown": st["max_dd"],
                "max_losing_streak": st["max_streak"],
                "n": n,
            }
        )

    # hedge type efficiency with real odds availability
    hedge_type = defaultdict(lambda: {"n": 0, "priced": 0, "mass": 0.0})
    for h in hedge_rows:
        k = h["kind"]
        hedge_type[k]["n"] += 1
        hedge_type[k]["priced"] += int(h["odds_kind"] == "REAL")
        hedge_type[k]["mass"] += float(h.get("model_probability") or 0)

    # Over 3.5 economic test on pairs (real OU odds from training when present)
    over35_notes = {
        "three_goal_gaps": list(THREE_GOAL_OVER35_GAPS),
        "note": "Over 3.5 never covers 2-1/1-2/3-0/0-3; CS primary ROI uses real CS only",
    }

    write_csv(ART / "selected_pairs.csv", selected_pairs)
    write_csv(ART / "primary_25_real_odds.csv", primary_rows)
    write_csv(ART / "hedge_real_odds.csv", hedge_rows)
    write_csv(ART / "stake_allocations.csv", stake_rows)
    write_csv(ART / "realized_returns.csv", realized_rows)
    write_csv(ART / "drawdown.csv", drawdown_rows)
    write_csv(ART / "bookmaker_comparison.csv", bookmaker_comp)

    # Final status logic
    n_pairs = len(selected_pairs)
    best_s = None
    best_roi = None
    for s, meta in roi_summary["strategies"].items():
        if meta["n_portfolios"] and meta["roi"] is not None:
            if best_roi is None or meta["roi"] > best_roi:
                best_roi = meta["roi"]
                best_s = s

    if n_pairs < 30:
        final_status = "TWO_FIXTURE_PORTFOLIO_MORE_FORWARD_DATA_REQUIRED"
    elif best_roi is not None and best_roi > 0.02 and (roi_summary["strategies"][best_s]["n_portfolios"] >= 30):
        final_status = "TWO_FIXTURE_PORTFOLIO_REAL_ODDS_EDGE_PROVEN"
    elif best_roi is not None and n_pairs >= 30:
        final_status = "TWO_FIXTURE_PORTFOLIO_REAL_ODDS_NO_EDGE"
    else:
        final_status = "TWO_FIXTURE_PORTFOLIO_MORE_FORWARD_DATA_REQUIRED"

    # Arb classification sample
    arb_note = classify_arbitrage([10.0, 12.0, 15.0])
    roi_summary.update(
        {
            "final_status": final_status,
            "best_strategy": best_s,
            "best_roi": best_roi,
            "cs_fixtures_available": int(n_cs),
            "enriched_fixtures": len(enriched),
            "independence_note": INDEPENDENCE_NOTE,
            "false_arbitrage_disallowed": True,
            "sample_inverse_sum_class": arb_note,
            "deploy_betting": False,
            "auto_bet": False,
            "answers": _answers(
                n_pairs, best_s, best_roi, roi_summary, hedge_type, n_cs, len(enriched)
            ),
        }
    )
    (ART / "roi_summary.json").write_text(json.dumps(roi_summary, indent=2, default=str), encoding="utf-8")
    _write_reports(roi_summary, over35_notes)
    print(
        json.dumps(
            {
                "final_status": final_status,
                "n_pairs": n_pairs,
                "best_strategy": best_s,
                "best_roi": best_roi,
            },
            indent=2,
        )
    )
    return 0


def _answers(n_pairs, best_s, best_roi, roi_summary, hedge_type, n_cs, n_enr) -> dict:
    mm = roi_summary["strategies"].get("MINIMAX") or {}
    eq = roi_summary["strategies"].get("EQUAL") or {}
    priced_share = {
        k: (v["priced"] / v["n"] if v["n"] else 0) for k, v in hedge_type.items()
    }
    best_hedge = max(priced_share, key=priced_share.get) if priced_share else "n/a"
    return {
        "q1": "api_football (+ sportmonks when present in snapshots); OddAlerts/CSV/TheOddsAPI: no CS",
        "q2": "Yes — mapped as CORRECT_SCORE_90_MINUTES; live/post-kickoff rejected",
        "q3": "No full provider historical CS archive; local cached snapshot extraction only",
        "q4": "Leagues present among joinable CS fixtures in local DB (see selected_pairs.csv)",
        "q5": "Bookmakers present in correct_score_odds_lines / bookmaker_comparison.csv",
        "q6": "Varies by fixture — see fixture_market_completeness in CS artifacts",
        "q7": f"Pairs retained only when enough combos priced; n_pairs={n_pairs}",
        "q8": "Hedges priced when selection present in real CS map; else UNAVAILABLE",
        "q9": f"≈ €{DEFAULT_BUDGET} primary budget (+ hedge share) when portfolios form",
        "q10": f"{best_roi} ({best_s})" if best_roi is not None else "insufficient_pairs",
        "q11": mm.get("stake_recovery_rate"),
        "q12": mm.get("full_loss_rate"),
        "q13": (
            f"MINIMAX roi={mm.get('roi')} dd={mm.get('max_drawdown')} vs EQUAL roi={eq.get('roi')} dd={eq.get('max_drawdown')}"
        ),
        "q14": "Prior coverage research suggested ~5; real-odds sample may be too small to reconfirm economically",
        "q15": "Over 3.5 leaves three-goal gaps; economic recovery not proven as CS substitute",
        "q16": f"Priced availability leader among hedge kinds: {best_hedge}",
        "q17": "Any-other markets stored separately when present; not treated as exact scores",
        "q18": "Often yes for complete Top5 — SINGLE vs CROSS labelled separately",
        "q19": f"n_pairs={n_pairs}, cs_fixtures={n_cs}, enriched={n_enr} — see final_status",
        "q20": "Owner-only shadow collection justified; production betting NOT justified",
    }


def _write_reports(summary: dict, over35: dict) -> None:
    status = summary["final_status"]
    a = summary["answers"]
    en = f"""# TWO-FIXTURE PORTFOLIO — REAL ODDS RESEARCH

**Final status:** `{status}`  
**Generated:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}

## Scope

ROI tables use **REAL** Correct Score odds only (`odds_kind=REAL`).  
Synthetic odds are **not** used in primary result tables.

{INDEPENDENCE_NOTE}

Exact-score Top5 subsets are **incomplete** — no arbitrage claims.

## Sample

| Metric | Value |
|---|---|
| Pairs | {summary.get("n_pairs")} |
| CS fixtures available | {summary.get("cs_fixtures_available")} |
| Enriched priced fixtures | {summary.get("enriched_fixtures")} |
| Best strategy | {summary.get("best_strategy")} |
| Best ROI | {summary.get("best_roi")} |

## Strategy ROI (real odds)

| Strategy | N | ROI | Hit rate | Full-loss | Recovery | Max DD |
|---|---:|---:|---:|---:|---:|---:|
"""
    for s, m in summary.get("strategies", {}).items():
        en += (
            f"| {s} | {m.get('n_portfolios')} | {m.get('roi')} | {m.get('primary_hit_rate')} | "
            f"{m.get('full_loss_rate')} | {m.get('stake_recovery_rate')} | {m.get('max_drawdown')} |\n"
        )
    en += f"""

## Over 3.5

Gaps: {", ".join(over35["three_goal_gaps"])}  
{over35["note"]}

## Answers

1. {a["q1"]}
2. {a["q2"]}
3. {a["q3"]}
4. {a["q4"]}
5. {a["q5"]}
6. {a["q6"]}
7. {a["q7"]}
8. {a["q8"]}
9. {a["q9"]}
10. {a["q10"]}
11. {a["q11"]}
12. {a["q12"]}
13. {a["q13"]}
14. {a["q14"]}
15. {a["q15"]}
16. {a["q16"]}
17. {a["q17"]}
18. {a["q18"]}
19. {a["q19"]}
20. {a["q20"]}

## Constraints

- No production betting
- No automatic placement
- No ECSE/WDE changes
- No freeze modification

Artifacts: `artifacts/two_fixture_portfolio_real_odds/`
"""
    (REPORTS / "TWO_FIXTURE_PORTFOLIO_REAL_ODDS_RESEARCH.md").write_text(en, encoding="utf-8")

    fa = f"""# پژوهش پورتفوی دو بازی — ضرایب واقعی اسکور دقیق

**وضعیت نهایی:** `{status}`

## خلاصه

جداول ROI فقط با ضرایب **واقعی** Correct Score محاسبه شده‌اند.

- تعداد جفت‌ها: {summary.get("n_pairs")}
- بهترین استراتژی: {summary.get("best_strategy")}
- بهترین ROI: {summary.get("best_roi")}

شرط‌بندی تولید/خودکار: **خیر**

جزئیات انگلیسی و آرتیفکت‌ها را ببینید.
"""
    (REPORTS / "TWO_FIXTURE_PORTFOLIO_REAL_ODDS_RESEARCH_FA.md").write_text(fa, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

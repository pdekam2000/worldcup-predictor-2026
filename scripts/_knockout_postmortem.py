#!/usr/bin/env python3
"""Knockout + recent WC prediction post-mortem."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "football_intelligence.db"
PRED = ROOT / "artifacts" / "manual_owner_exact_score_predictions_20260703.json"


def load_predictions():
    if PRED.exists():
        return json.loads(PRED.read_text(encoding="utf-8"))["predictions"]
    return []


def main():
    preds = {p["fixture_id"]: p for p in load_predictions()}
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    fixture_ids = list(preds.keys()) + [1562586, 1567311]
    rows = conn.execute(
        f"""
        SELECT f.fixture_id, f.home_team, f.away_team, f.status,
               fr.home_goals, fr.away_goals, fr.final_score
        FROM fixtures f
        JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
        WHERE f.fixture_id IN ({','.join('?'*len(set(fixture_ids)))})
        """,
        list(set(fixture_ids)),
    ).fetchall()
    conn.close()

    print("=== POST-MORTEM: Predictions vs Final Results ===\n")

    stats = {
        "finished": 0,
        "ecse_top1": 0,
        "ecse_top3": 0,
        "ecse_top5": 0,
        "wde_1x2": 0,
        "wde_ou": 0,
        "wde_btts": 0,
        "total_goals_err": [],
    }

    for r in rows:
        fid = r["fixture_id"]
        p = preds.get(fid, {})
        if not p and fid not in (1562586, 1567311):
            continue
        h, a = int(r["home_goals"]), int(r["away_goals"])
        actual = f"{h}-{a}"
        top1 = p.get("exact_top1") or ""
        top3 = p.get("exact_top3") or []
        top5 = p.get("exact_top5") or []
        wde = p.get("wde") or {}

        a1 = "home_win" if h > a else ("away_win" if h < a else "draw")
        aou = "over_2_5" if h + a > 2 else "under_2_5"
        abtts = "yes" if h > 0 and a > 0 else "no"

        stats["finished"] += 1
        if top1 == actual:
            stats["ecse_top1"] += 1
        if actual in top3:
            stats["ecse_top3"] += 1
        if actual in top5:
            stats["ecse_top5"] += 1
        if wde.get("predicted_1x2") == a1:
            stats["wde_1x2"] += 1
        if wde.get("predicted_over_under_2_5") == aou:
            stats["wde_ou"] += 1
        if wde.get("btts_pick") == abtts:
            stats["wde_btts"] += 1

        pred_goals = 0
        if top1 and "-" in top1:
            try:
                ph, pa = map(int, top1.split("-"))
                pred_goals = ph + pa
            except ValueError:
                pass
        stats["total_goals_err"].append(abs((h + a) - pred_goals))

        flags = []
        if top1 == actual:
            flags.append("EXACT_OK")
        elif actual in top3:
            flags.append("TOP3_OK")
        elif actual in top5:
            flags.append("TOP5_OK")
        if wde.get("predicted_1x2") == a1:
            flags.append("1X2_OK")
        if wde.get("predicted_over_under_2_5") == aou:
            flags.append("OU_OK")
        if wde.get("btts_pick") == abtts:
            flags.append("BTTS_OK")

        print(f"{r['home_team']} vs {r['away_team']} [{r['status']}]")
        print(f"  Actual: {actual} | Predicted Top1: {top1} | Top3: {', '.join(top3[:3])}")
        print(f"  WDE: 1X2={wde.get('predicted_1x2')} O/U={wde.get('predicted_over_under_2_5')} BTTS={wde.get('btts_pick')}")
        print(f"  Result: {' | '.join(flags) if flags else 'MISS'}")
        print()

    n = stats["finished"] or 1
    avg_goal_err = sum(stats["total_goals_err"]) / len(stats["total_goals_err"]) if stats["total_goals_err"] else 0
    print("=== AGGREGATE (knockout batch with results) ===")
    print(f"  Matches: {stats['finished']}")
    print(f"  ECSE Exact Top-1: {stats['ecse_top1']}/{n} = {100*stats['ecse_top1']/n:.0f}%")
    print(f"  ECSE Top-3 hit:   {stats['ecse_top3']}/{n} = {100*stats['ecse_top3']/n:.0f}%")
    print(f"  ECSE Top-5 hit:   {stats['ecse_top5']}/{n} = {100*stats['ecse_top5']/n:.0f}%")
    print(f"  WDE 1X2:          {stats['wde_1x2']}/{n} = {100*stats['wde_1x2']/n:.0f}%")
    print(f"  WDE O/U 2.5:      {stats['wde_ou']}/{n} = {100*stats['wde_ou']/n:.0f}%")
    print(f"  WDE BTTS:         {stats['wde_btts']}/{n} = {100*stats['wde_btts']/n:.0f}%")
    print(f"  Avg total-goals error (vs Top1): {avg_goal_err:.2f}")


if __name__ == "__main__":
    main()

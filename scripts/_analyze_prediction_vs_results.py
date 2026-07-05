#!/usr/bin/env python3
"""Analyze stored predictions vs actual final results."""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "football_intelligence.db"


def parse_json_list(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def actual_1x2(h, a):
    if h > a:
        return "home_win"
    if h < a:
        return "away_win"
    return "draw"


def actual_ou(h, a):
    return "over_2_5" if h + a > 2 else "under_2_5"


def actual_btts(h, a):
    return "yes" if h > 0 and a > 0 else "no"


def norm_btts(val):
    if not val:
        return None
    v = str(val).lower().replace("btts_", "")
    return v if v in ("yes", "no") else val


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
          f.fixture_id, f.home_team, f.away_team, f.kickoff_utc, f.status,
          fr.final_score, fr.home_goals, fr.away_goals,
          sp.payload_json,
          ec.top_1_score, ec.top_3_scores_json, ec.top_10_scorelines_json,
          ec.lambda_home, ec.lambda_away
        FROM fixtures f
        JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
        LEFT JOIN worldcup_stored_predictions sp ON sp.fixture_id = f.fixture_id
        LEFT JOIN ecse_prediction_snapshots ec ON ec.fixture_id = f.fixture_id
        WHERE f.competition_key = 'world_cup_2026'
          AND fr.home_goals IS NOT NULL
        ORDER BY f.kickoff_utc DESC
        """
    ).fetchall()
    conn.close()

    stats = defaultdict(int)
    misses = []
    hits_top1 = []

    for r in rows:
        h, a = int(r["home_goals"]), int(r["away_goals"])
        actual = f"{h}-{a}"
        a1, aou, abtts = actual_1x2(h, a), actual_ou(h, a), actual_btts(h, a)

        wde_1x2 = wde_ou = wde_btts = None
        wde_top3 = []
        if r["payload_json"]:
            try:
                p = json.loads(r["payload_json"])
                wde_1x2 = (p.get("one_x_two") or {}).get("selection")
                wde_ou = (p.get("over_under") or {}).get("selection")
                btts = (p.get("extended_markets") or {}).get("btts") or (p.get("detailed_markets") or {}).get("btts") or {}
                wde_btts = norm_btts(btts.get("selection"))
                cands = p.get("scoreline_candidates") or []
                wde_top3 = [f"{c.get('home_goals')}-{c.get('away_goals')}" for c in cands[:3]]
            except json.JSONDecodeError:
                pass

        ecse_top1 = r["top_1_score"]
        ecse_top3 = [
            x if isinstance(x, str) else x.get("scoreline")
            for x in parse_json_list(r["top_3_scores_json"])[:3]
        ]
        ecse_top10 = [
            x if isinstance(x, str) else x.get("scoreline")
            for x in parse_json_list(r["top_10_scorelines_json"])[:10]
        ]

        stats["total"] += 1
        if wde_1x2:
            stats["wde_1x2_total"] += 1
            if wde_1x2 == a1:
                stats["wde_1x2_hit"] += 1
        if wde_ou:
            stats["wde_ou_total"] += 1
            if wde_ou == aou:
                stats["wde_ou_hit"] += 1
        if wde_btts:
            stats["wde_btts_total"] += 1
            if wde_btts == abtts:
                stats["wde_btts_hit"] += 1
        if ecse_top1:
            stats["ecse_top1_total"] += 1
            if ecse_top1 == actual:
                stats["ecse_top1_hit"] += 1
                hits_top1.append(f"{r['home_team']} vs {r['away_team']}: {actual}")
            if actual in ecse_top3:
                stats["ecse_top3_hit"] += 1
            if actual in ecse_top10:
                stats["ecse_top10_hit"] += 1
            if actual not in ecse_top10:
                misses.append(
                    {
                        "match": f"{r['home_team']} vs {r['away_team']}",
                        "actual": actual,
                        "ecse_top1": ecse_top1,
                        "ecse_top3": ecse_top3,
                        "wde_1x2": wde_1x2,
                        "actual_1x2": a1,
                        "total_goals": h + a,
                    }
                )

    print("=== WORLD CUP 2026 — Prediction vs Actual ===")
    print(f"Finished matches with results: {stats['total']}")
    for key, label in [
        ("wde_1x2", "WDE 1X2"),
        ("wde_ou", "WDE O/U 2.5"),
        ("wde_btts", "WDE BTTS"),
        ("ecse_top1", "ECSE Exact Top-1"),
        ("ecse_top3", "ECSE Exact Top-3"),
        ("ecse_top10", "ECSE Exact Top-10"),
    ]:
        t = stats.get(f"{key}_total", 0)
        h = stats.get(f"{key}_hit", 0)
        if t:
            print(f"  {label}: {h}/{t} = {100 * h / t:.1f}%")

    print("\n=== Top-1 HITS (exact score) ===")
    for x in hits_top1[:15]:
        print(f"  ✓ {x}")

    print("\n=== Recent MISSES (actual not in ECSE top-10) ===")
    for m in misses[:20]:
        print(
            f"  {m['match']}: actual {m['actual']} | predicted {m['ecse_top1']} | top3 {m['ecse_top3']} | goals {m['total_goals']}"
        )

    # Knockout eval artifact
    ko_path = ROOT / "artifacts" / "owner_knockout_prediction_evaluation_20260701.json"
    if ko_path.exists():
        ko = json.loads(ko_path.read_text(encoding="utf-8"))
        ev = ko.get("evaluated") or ko.get("results") or []
        if isinstance(ko.get("summary"), dict):
            s = ko["summary"]
            print("\n=== Owner Knockout Eval Summary ===")
            for k, v in s.items():
                print(f"  {k}: {v}")
        elif ev:
            print(f"\n=== Owner Knockout Eval rows: {len(ev)} ===")


if __name__ == "__main__":
    main()

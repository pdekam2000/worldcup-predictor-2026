#!/usr/bin/env python3
"""Phase A13A — Match Center prediction coverage + combo audit."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "validation"
BASE = os.environ.get("A13A_API_BASE", "https://footballpredictor.it.com")


def http_get(url: str, timeout: int = 60) -> tuple[int, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def classify_1x2(best_pick: str | None) -> str:
    if not best_pick:
        return "missing"
    s = str(best_pick).lower()
    if "draw" in s or s.strip() in {"x", "1x2: x"}:
        return "draw"
    if "home" in s or "1" == s.strip():
        return "home"
    if "away" in s or "2" == s.strip():
        return "away"
    if ":" in s:
        return "other_market"
    return "unknown"


def audit_combo_candidates(matches: list[dict]) -> dict[str, Any]:
    considered = len(matches)
    with_summary = sum(1 for m in matches if m.get("prediction_summary"))
    bettable = 0
    rejected: Counter[str] = Counter()
    for m in matches:
        s = m.get("prediction_summary") or {}
        if not s.get("best_pick"):
            rejected["missing_best_pick"] += 1
            continue
        if s.get("no_bet"):
            rejected["no_bet"] += 1
            continue
        ai = (m.get("ai_match_score") or {}).get("score") or 0
        conf = s.get("confidence") or 0
        if ai < 58 and conf < 55:
            rejected["low_ai_and_confidence"] += 1
            continue
        bettable += 1
    return {
        "fixtures_considered": considered,
        "predictions_available": with_summary,
        "candidates_accepted": bettable,
        "candidates_rejected": sum(rejected.values()),
        "rejection_reasons": dict(rejected),
    }


def main() -> int:
    report: dict[str, Any] = {"base": BASE, "parts": {}}

    code, comps_payload = http_get(f"{BASE}/api/competitions?include_counts=true")
    if code != 200 or not isinstance(comps_payload, dict):
        print(f"FAIL competitions http={code}")
        return 1

    league_rows = []
    for c in comps_payload.get("competitions") or []:
        league_rows.append(
            {
                "competition_id": c.get("key"),
                "provider_id": c.get("provider_league_id") or c.get("league_id"),
                "resolved_season": c.get("resolved_season") or c.get("season"),
                "upcoming_fixtures": c.get("upcoming_count", 0),
                "enabled": c.get("enabled", True),
                "zero_reason": c.get("zero_fixture_reason"),
            }
        )
    report["parts"]["league_coverage"] = league_rows

    all_matches: list[dict] = []
    page = 1
    while page <= 5:
        code, matches_payload = http_get(
            f"{BASE}/api/matches?competition=all&status=upcoming&page={page}&page_size=100&include_summary=true"
        )
        if code != 200 or not isinstance(matches_payload, dict):
            print(f"FAIL matches http={code} page={page}")
            return 1
        batch = matches_payload.get("matches") or []
        all_matches.extend(batch)
        total_pages = int(matches_payload.get("total_pages") or 1)
        if page >= total_pages or not batch:
            break
        page += 1
    matches = all_matches
    ui_by_comp: Counter[str] = Counter()
    pred_by_comp: Counter[str] = Counter()
    fix_by_comp: Counter[str] = Counter()
    draw_log: list[dict] = []
    dist = Counter()

    for m in matches:
        ck = m.get("competition_key") or "unknown"
        ui_by_comp[ck] += 1
        fix_by_comp[ck] += 1
        summary = m.get("prediction_summary") or {}
        if m.get("has_prediction"):
            pred_by_comp[ck] += 1
        bp = summary.get("best_pick")
        bucket = classify_1x2(bp)
        if bp and ("1x2" in str(bp).lower() or bucket in {"home", "draw", "away"}):
            dist[bucket] += 1
            if bucket == "draw":
                draw_log.append(
                    {
                        "fixture_id": m.get("fixture_id"),
                        "teams": f"{m.get('home_team')} vs {m.get('away_team')}",
                        "best_pick": bp,
                        "confidence": summary.get("confidence"),
                        "no_bet": summary.get("no_bet"),
                        "competition_key": ck,
                        "extraction": "api_prediction_summary",
                    }
                )

    coverage_rows = []
    for c in league_rows:
        cid = c["competition_id"]
        fixtures = fix_by_comp.get(cid, 0)
        preds = pred_by_comp.get(cid, 0)
        coverage_rows.append(
            {
                "competition_id": cid,
                "fixture_count": fixtures,
                "prediction_count": preds,
                "coverage_pct": round(100 * preds / fixtures, 1) if fixtures else 0.0,
                "ui_fixture_count": ui_by_comp.get(cid, 0),
            }
        )

    total_fix = len(matches)
    with_pred = sum(1 for m in matches if m.get("has_prediction"))
    with_best = sum(1 for m in matches if (m.get("prediction_summary") or {}).get("best_pick"))
    no_bet = sum(1 for m in matches if (m.get("prediction_summary") or {}).get("no_bet"))

    report["parts"]["prediction_coverage"] = {
        "total_fixtures": total_fix,
        "with_cached_prediction": with_pred,
        "with_best_pick": with_best,
        "no_bet_summaries": no_bet,
        "without_best_pick": with_pred - with_best,
        "per_competition": coverage_rows,
    }

    report["parts"]["draw_distribution"] = {
        "counts": dict(dist),
        "draw_samples": draw_log[:50],
        "draw_total": dist.get("draw", 0),
        "visible_1x2_total": sum(dist.get(k, 0) for k in ("home", "draw", "away", "unknown", "missing")),
    }

    code2, combo_pool = http_get(
        f"{BASE}/api/matches?competition=all&status=upcoming&page=1&page_size=100&has_prediction=true&include_summary=true"
    )
    combo_matches = combo_pool.get("matches", []) if isinstance(combo_pool, dict) else []
    report["parts"]["combo_audit"] = audit_combo_candidates(combo_matches)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "phase_a13a_audit_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Phase A13A audit written to {out_path}")
    print(f"  Leagues: {len(league_rows)} | Upcoming fixtures: {total_fix}")
    print(f"  Predictions: {with_pred} | Best picks: {with_best} | Draw labels: {dist.get('draw', 0)}")
    print(f"  Combo bettable legs: {report['parts']['combo_audit']['candidates_accepted']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
